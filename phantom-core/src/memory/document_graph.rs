use anyhow::{Context, Result};
use petgraph::graph::DiGraph;
use petgraph::visit::EdgeRef;
use rusqlite::{params, Connection};
use serde::Deserialize;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tracing::{error, info};

use crate::ai::AiBackend;
use crate::document_context::ExtractorRegistry;

pub struct DocumentGraph {
    db_path: PathBuf,
    backend: Arc<dyn AiBackend>,
}

#[derive(Deserialize, Debug, Clone)]
struct ExtractedEntity {
    name: String,
    entity_type: String,
    relation: String,
}

impl DocumentGraph {
    pub fn new(db_path: PathBuf, backend: Arc<dyn AiBackend>) -> Result<Self> {
        let conn = Connection::open(&db_path)?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                node_type TEXT NOT NULL,
                content TEXT NOT NULL
            )",
            [],
        )?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                relation TEXT NOT NULL,
                PRIMARY KEY (source, target, relation)
            )",
            [],
        )?;
        Ok(Self { db_path, backend })
    }

    /// Scan directory and index new files
    pub async fn index_directory(&self, dir_path: &Path) -> Result<()> {
        info!(
            "🕸️  [DocumentGraph] Scanning folder: {}",
            dir_path.display()
        );
        if !dir_path.exists() {
            std::fs::create_dir_all(dir_path).ok();
            return Ok(());
        }

        let extractor_registry = ExtractorRegistry::with_defaults();
        let conn = Connection::open(&self.db_path)?;

        let entries = std::fs::read_dir(dir_path)?;
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                let file_name = path
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string();
                let file_id = path.to_string_lossy().to_string();

                // Skip non-documents
                let ext = path
                    .extension()
                    .and_then(|e| e.to_str())
                    .unwrap_or("")
                    .to_lowercase();
                if !["txt", "md", "docx", "doc", "pdf", "xlsx", "xls"].contains(&ext.as_str()) {
                    continue;
                }

                // Extract current text of the file
                let current_text = match extractor_registry.extract(&path, "", None) {
                    Some(doc_ctx) => {
                        let text = doc_ctx.full_text;
                        if text.trim().is_empty() {
                            continue;
                        }
                        text
                    }
                    None => continue,
                };

                // Query the database to retrieve stored content for the document file_id (if it exists)
                let stored_content: Option<String> = {
                    let mut stmt = conn.prepare("SELECT content FROM nodes WHERE id = ?1")?;
                    let mut rows = stmt.query(params![file_id])?;
                    if let Some(row) = rows.next()? {
                        let content: String = row.get(0)?;
                        Some(content)
                    } else {
                        None
                    }
                };

                if let Some(stored) = &stored_content {
                    if stored == &current_text {
                        continue;
                    } else {
                        conn.execute("DELETE FROM nodes WHERE id = ?1", params![file_id])?;
                        conn.execute("DELETE FROM edges WHERE source = ?1", params![file_id])?;
                    }
                }

                info!("🕸️  [DocumentGraph] Indexing document: {}", file_name);

                // Insert document node
                conn.execute(
                    "INSERT OR IGNORE INTO nodes (id, name, node_type, content) VALUES (?1, ?2, 'document', ?3)",
                    params![file_id, file_name, current_text],
                )?;

                // Call LLM to extract entities
                match self.extract_entities_via_llm(&current_text).await {
                    Ok(entities) => {
                        info!(
                            "🕸️  [DocumentGraph] Extracted {} entities from {}",
                            entities.len(),
                            file_name
                        );
                        for ent in entities {
                            let ent_id = format!(
                                "entity:{}",
                                ent.name.to_lowercase().trim().replace(' ', "-")
                            );

                            // Insert entity node (ignore if conflict)
                            conn.execute(
                                "INSERT OR IGNORE INTO nodes (id, name, node_type, content) VALUES (?1, ?2, ?3, '')",
                                params![ent_id, ent.name.trim(), ent.entity_type.trim()],
                            )?;

                            // Insert edge from document to entity
                            conn.execute(
                                "INSERT OR IGNORE INTO edges (source, target, relation) VALUES (?1, ?2, ?3)",
                                params![file_id, ent_id, ent.relation.trim()],
                            )?;
                        }
                    }
                    Err(e) => {
                        error!(
                            "❌ [DocumentGraph] Entity extraction failed for {}: {:?}",
                            file_name, e
                        );
                    }
                }
            }
        }
        Ok(())
    }

    async fn extract_entities_via_llm(&self, text: &str) -> Result<Vec<ExtractedEntity>> {
        let system_prompt = r#"You are the Kairo Entity Extraction Engine.
Your task is to extract key entities (people, companies, dates, legal clauses, monetary values) from the provided document text and identify their relationship to the document.
Output ONLY a JSON array of objects, each with exactly these keys:
- "name" (string, the name of the entity)
- "entity_type" (must be one of: "person", "company", "date", "legal", "money")
- "relation" (how the entity relates to the document, e.g. "author", "party", "date_signed", "clause_type", "amount")

Do NOT include any markdown code blocks (e.g. ```json). Output ONLY valid JSON."#;

        // Take first 4000 characters of the document text to avoid token limits
        let text_snippet: String = text.chars().take(4000).collect();
        let user_prompt = format!("Document text:\n\"\"\"\n{text_snippet}\n\"\"\"");

        let response = self.backend.complete(system_prompt, &user_prompt).await?;
        let cleaned = response
            .trim()
            .trim_start_matches("```json")
            .trim_start_matches("```")
            .trim_end_matches("```")
            .trim();

        let entities: Vec<ExtractedEntity> = serde_json::from_str(cleaned)
            .context("Failed to parse extracted entities JSON from LLM response")?;
        Ok(entities)
    }

    /// Load the graph in memory using petgraph
    pub fn build_in_memory_graph(&self) -> Result<DiGraph<String, String>> {
        let conn = Connection::open(&self.db_path)?;
        let mut graph = DiGraph::new();
        let mut node_indices = std::collections::HashMap::new();

        // 1. Load nodes
        let mut stmt = conn.prepare("SELECT id FROM nodes")?;
        let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
        for id in rows.flatten() {
            let idx = graph.add_node(id.clone());
            node_indices.insert(id, idx);
        }

        // 2. Load edges
        let mut stmt = conn.prepare("SELECT source, target, relation FROM edges")?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?;
        for (src, tgt, rel) in rows.flatten() {
            if let (Some(&s_idx), Some(&t_idx)) = (node_indices.get(&src), node_indices.get(&tgt)) {
                graph.add_edge(s_idx, t_idx, rel);
            }
        }

        Ok(graph)
    }

    /// Query the graph memory for a specific entity
    pub fn query_entity(&self, name: &str) -> Result<String> {
        let conn = Connection::open(&self.db_path)?;
        let mut stmt = conn.prepare(
            "SELECT id, name, node_type FROM nodes WHERE LOWER(name) = ?1 OR LOWER(id) = ?1",
        )?;
        let mut rows = stmt.query(params![name.to_lowercase().trim()])?;

        let (entity_id, entity_name, entity_type) = match rows.next()? {
            Some(row) => (
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ),
            None => return Ok(format!("Entity '{name}' not found in document graph.")),
        };

        // Load graph in memory
        let graph = self.build_in_memory_graph()?;

        // Find target entity node in the DiGraph in memory
        let node_idx = match graph.node_indices().find(|&idx| graph[idx] == entity_id) {
            Some(idx) => idx,
            None => return Ok(format!("Entity '{name}' not found in document graph.")),
        };

        let mut connected = Vec::new();
        // Outgoing edges (entity_id is source, target is connected node)
        for edge in graph.edges_directed(node_idx, petgraph::Direction::Outgoing) {
            connected.push((graph[edge.target()].clone(), edge.weight().clone(), "out"));
        }
        // Incoming edges (connected node is source, entity_id is target)
        for edge in graph.edges_directed(node_idx, petgraph::Direction::Incoming) {
            connected.push((graph[edge.source()].clone(), edge.weight().clone(), "in"));
        }

        let mut out_str = format!("Entity: {entity_name} ({entity_type})\nRelationships:\n");
        let mut has_rels = false;

        // Look up metadata/content from SQLite database using those IDs only when needed
        for (conn_id, relation, dir) in connected {
            let mut stmt = conn.prepare("SELECT name, node_type FROM nodes WHERE id = ?1")?;
            let mut rows = stmt.query(params![conn_id])?;
            if let Some(row) = rows.next()? {
                let tgt_name: String = row.get(0)?;
                let tgt_type: String = row.get(1)?;
                has_rels = true;
                if dir == "out" {
                    out_str.push_str(&format!(
                        "  - [{entity_name}] -> [{relation}] -> [{tgt_name}] ({tgt_type})\n"
                    ));
                } else {
                    out_str.push_str(&format!(
                        "  - [{tgt_name}] -> [{relation}] -> [{entity_name}] ({entity_type})\n"
                    ));
                }
            }
        }

        if !has_rels {
            out_str.push_str("  No direct relationships found.\n");
        }
        Ok(out_str)
    }

    /// List all indexed entities
    pub fn list_entities(&self) -> Result<String> {
        let conn = Connection::open(&self.db_path)?;
        let mut stmt =
            conn.prepare("SELECT name, node_type FROM nodes WHERE node_type != 'document'")?;
        let rows = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?;

        let mut out = String::from("Document Graph Entities:\n");
        let mut count = 0;
        for entity in rows.flatten() {
            count += 1;
            let (name, node_type) = entity;
            out.push_str(&format!("  • {name} ({node_type})\n"));
        }
        if count == 0 {
            out.push_str("  No entities indexed yet. Add documents to the Kairo folder.\n");
        }
        Ok(out)
    }

    /// Enrich the prompt if it references known entities
    pub fn enrich_context(&self, prompt: &str) -> Result<Option<String>> {
        let conn = Connection::open(&self.db_path)?;
        let mut stmt =
            conn.prepare("SELECT id, name, node_type FROM nodes WHERE node_type != 'document'")?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?;

        let prompt_lower = prompt.to_lowercase();
        let mut matched_entities = Vec::new();

        for entity in rows.flatten() {
            let (id, name, node_type) = entity;
            if prompt_lower.contains(&name.to_lowercase()) {
                matched_entities.push((id, name, node_type));
            }
        }

        if matched_entities.is_empty() {
            return Ok(None);
        }

        info!(
            "🕸️  [DocumentGraph] Matched {} entity/entities in prompt: {:?}",
            matched_entities.len(),
            matched_entities
        );

        // Load graph in memory
        let graph = self.build_in_memory_graph()?;

        let mut context_block = String::from("\n🕸️  [DOCUMENT GRAPH CONTEXT]\n");
        for (id, name, node_type) in matched_entities {
            context_block.push_str(&format!("Entity: {name} ({node_type})\n"));

            // Find target entity node in the DiGraph in memory
            let node_idx = match graph.node_indices().find(|&idx| graph[idx] == id) {
                Some(idx) => idx,
                None => continue,
            };

            let mut connected_ids = Vec::new();
            // Incoming edges: source -> node_idx
            for edge in graph.edges_directed(node_idx, petgraph::Direction::Incoming) {
                connected_ids.push(graph[edge.source()].clone());
            }
            // Outgoing edges: node_idx -> target
            for edge in graph.edges_directed(node_idx, petgraph::Direction::Outgoing) {
                connected_ids.push(graph[edge.target()].clone());
            }

            // Look up metadata/content from SQLite database using those IDs only when needed
            for conn_id in connected_ids {
                let mut stmt =
                    conn.prepare("SELECT name, content, node_type FROM nodes WHERE id = ?1")?;
                let mut rows = stmt.query(params![conn_id])?;
                if let Some(row) = rows.next()? {
                    let doc_name: String = row.get(0)?;
                    let doc_content: String = row.get(1)?;
                    let node_type: String = row.get(2)?;
                    if node_type == "document" {
                        let snippet: String = doc_content.chars().take(500).collect();
                        context_block.push_str(&format!(
                            "  From Document '{doc_name}':\n\"\"\"\n{snippet}\n\"\"\"\n"
                        ));
                    }
                }
            }
        }
        context_block.push_str("[END GRAPH CONTEXT]\n");

        Ok(Some(context_block))
    }
}
