// phantom-core/src/memory_store.rs
// Persistent Memory Store — Alaya pattern with SQLite backend
// Saves user preferences and interaction history across sessions.
// Integrates architectural concepts from Ghost-Frame/Engram (Rust-native persistent spatial memory)
// and garrytan/gbrain (cross-session Postgres+pgvector learning patterns).
// Context optimization via ncmonx/icm-graph concepts (memory + knowledge graph).

use crate::memory::{Interaction, KairoMemory, UserPreference};
use rusqlite::{params, Connection};
use std::path::PathBuf;
use tracing::{info, warn};

pub struct MemoryStore {
    path: PathBuf,
}

impl MemoryStore {
    /// Initialize with default path: ~/.kairo-phantom/memory.db
    pub fn from_env() -> Self {
        let path = dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".kairo-phantom")
            .join("memory.db");
        Self { path }
    }

    pub fn new(path: PathBuf) -> Self {
        Self { path }
    }

    fn get_connection(&self) -> rusqlite::Result<Connection> {
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent).ok();
        }
        let conn = Connection::open(&self.path)?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS preferences (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                weight REAL NOT NULL,
                UNIQUE(key, value)
            )",
            [],
        )?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY,
                app TEXT NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                accepted BOOLEAN NOT NULL,
                timestamp INTEGER NOT NULL
            )",
            [],
        )?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS skill_patterns (
                prompt TEXT PRIMARY KEY,
                pattern TEXT NOT NULL
            )",
            [],
        )?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS user_model (
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                UNIQUE(category, key)
            )",
            [],
        )?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS graph_nodes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )",
            [],
        )?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS graph_edges (
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                relationship TEXT NOT NULL
            )",
            [],
        )?;
        // BUGFIX: app_bias table was missing — caused silent failure on load
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_bias (
                app TEXT PRIMARY KEY,
                bias TEXT NOT NULL
            )",
            [],
        )?;
        Ok(conn)
    }

    /// Load memory from disk. Returns default if file doesn't exist.
    pub fn load(&self) -> KairoMemory {
        let mut memory = KairoMemory::new();
        if !self.path.exists() {
            info!(
                "📭 No SQLite memory file found at {:?} — starting fresh.",
                self.path
            );
            return memory;
        }

        let conn = match self.get_connection() {
            Ok(c) => c,
            Err(e) => {
                warn!(
                    "⚠️  Could not open SQLite memory database ({}). Starting fresh.",
                    e
                );
                return memory;
            }
        };

        if let Ok(mut stmt) = conn.prepare("SELECT key, value, weight FROM preferences") {
            let prefs = stmt.query_map([], |row| {
                Ok(UserPreference {
                    key: row.get(0)?,
                    value: row.get(1)?,
                    weight: row.get(2)?,
                })
            });
            if let Ok(prefs) = prefs {
                for p in prefs.flatten() {
                    memory.preferences.push(p);
                }
            }
        }

        if let Ok(mut stmt) = conn.prepare("SELECT app, prompt, response, accepted, timestamp FROM interactions ORDER BY timestamp ASC LIMIT 500") {
            let interactions = stmt.query_map([], |row| {
                Ok(Interaction {
                    app: row.get(0)?,
                    prompt: row.get(1)?,
                    response: row.get(2)?,
                    accepted: row.get(3)?,
                    timestamp: row.get::<_, i64>(4)? as u64,
                })
            });
            if let Ok(interactions) = interactions {
                for i in interactions.flatten() {
                    memory.interactions.push(i);
                }
            }
        }

        if let Ok(mut stmt) = conn.prepare("SELECT app, bias FROM app_bias") {
            let biases = stmt.query_map([], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            });
            if let Ok(biases) = biases {
                for b in biases.flatten() {
                    memory.app_bias.insert(b.0, b.1);
                }
            }
        }

        if let Ok(mut stmt) = conn.prepare("SELECT prompt, pattern FROM skill_patterns") {
            let patterns = stmt.query_map([], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            });
            if let Ok(patterns) = patterns {
                for p in patterns.flatten() {
                    memory.skill.reusable_patterns.insert(p.0, p.1);
                }
            }
        }

        if let Ok(mut stmt) = conn.prepare("SELECT category, key, value FROM user_model") {
            let models = stmt.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            });
            if let Ok(models) = models {
                for m in models.flatten() {
                    match m.0.as_str() {
                        "word" => {
                            memory.user_model.word_preferences.insert(m.1, m.2);
                        }
                        "ppt" => {
                            memory.user_model.ppt_preferences.insert(m.1, m.2);
                        }
                        _ => {}
                    }
                }
            }
        }

        if let Ok(mut stmt) = conn.prepare("SELECT name FROM graph_nodes ORDER BY id") {
            let nodes = stmt.query_map([], |row| row.get::<_, String>(0));
            if let Ok(nodes) = nodes {
                for n in nodes.flatten() {
                    memory.graph.nodes.push(n);
                }
            }
        }

        if let Ok(mut stmt) = conn.prepare("SELECT from_id, to_id, relationship FROM graph_edges") {
            let edges = stmt.query_map([], |row| {
                Ok((
                    row.get::<_, i64>(0)? as usize,
                    row.get::<_, i64>(1)? as usize,
                    row.get::<_, String>(2)?,
                ))
            });
            if let Ok(edges) = edges {
                for e in edges.flatten() {
                    memory.graph.edges.push(e);
                }
            }
        }

        info!(
            "🧠 SQLite Memory loaded: {} preferences, {} interactions, {} patterns from {:?}",
            memory.preferences.len(),
            memory.interactions.len(),
            memory.skill.reusable_patterns.len(),
            self.path
        );

        memory
    }

    /// Save memory to disk.
    pub fn save(&self, memory: &KairoMemory) -> bool {
        let mut conn = match self.get_connection() {
            Ok(c) => c,
            Err(e) => {
                warn!("⚠️  Failed to open SQLite for saving: {}", e);
                return false;
            }
        };

        let tx = match conn.transaction() {
            Ok(t) => t,
            Err(e) => {
                warn!("⚠️  Failed to start SQLite transaction: {}", e);
                return false;
            }
        };

        tx.execute("DELETE FROM preferences", []).ok();
        for p in &memory.preferences {
            tx.execute(
                "INSERT INTO preferences (key, value, weight) VALUES (?1, ?2, ?3)",
                params![p.key, p.value, p.weight],
            )
            .ok();
        }

        tx.execute("DELETE FROM interactions", []).ok();
        for i in &memory.interactions {
            tx.execute(
                "INSERT INTO interactions (app, prompt, response, accepted, timestamp) VALUES (?1, ?2, ?3, ?4, ?5)",
                params![i.app, i.prompt, i.response, i.accepted, i.timestamp as i64],
            ).ok();
        }

        tx.execute("DELETE FROM app_bias", []).ok();
        for (app, bias) in &memory.app_bias {
            tx.execute(
                "INSERT INTO app_bias (app, bias) VALUES (?1, ?2)",
                params![app, bias],
            )
            .ok();
        }

        tx.execute("DELETE FROM skill_patterns", []).ok();
        for (prompt, pattern) in &memory.skill.reusable_patterns {
            tx.execute(
                "INSERT INTO skill_patterns (prompt, pattern) VALUES (?1, ?2)",
                params![prompt, pattern],
            )
            .ok();
        }

        tx.execute("DELETE FROM user_model", []).ok();
        for (k, v) in &memory.user_model.word_preferences {
            tx.execute(
                "INSERT INTO user_model (category, key, value) VALUES (?1, ?2, ?3)",
                params!["word", k, v],
            )
            .ok();
        }
        for (k, v) in &memory.user_model.ppt_preferences {
            tx.execute(
                "INSERT INTO user_model (category, key, value) VALUES (?1, ?2, ?3)",
                params!["ppt", k, v],
            )
            .ok();
        }

        tx.execute("DELETE FROM graph_nodes", []).ok();
        for (i, node) in memory.graph.nodes.iter().enumerate() {
            tx.execute(
                "INSERT INTO graph_nodes (id, name) VALUES (?1, ?2)",
                params![i as i64, node],
            )
            .ok();
        }

        tx.execute("DELETE FROM graph_edges", []).ok();
        for (from, to, rel) in &memory.graph.edges {
            tx.execute(
                "INSERT INTO graph_edges (from_id, to_id, relationship) VALUES (?1, ?2, ?3)",
                params![*from as i64, *to as i64, rel],
            )
            .ok();
        }

        match tx.commit() {
            Ok(_) => {
                info!(
                    "💾 SQLite Memory saved ({} preferences, {} interactions)",
                    memory.preferences.len(),
                    memory.interactions.len()
                );
                true
            }
            Err(e) => {
                warn!("⚠️  Failed to commit SQLite transaction: {}", e);
                false
            }
        }
    }

    /// Record a completed ghost session interaction.
    pub fn record_interaction(
        &self,
        memory: &mut KairoMemory,
        app: &str,
        prompt: &str,
        response: &str,
        accepted: bool,
    ) {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let interaction = Interaction {
            app: app.to_string(),
            prompt: prompt.to_string(),
            response: response.to_string(),
            accepted,
            timestamp,
        };

        memory.learn_from_interaction(interaction);

        // Auto-save after each interaction (resilient against crashes)
        // Keep only last 500 interactions to bound memory file size
        if memory.interactions.len() > 500 {
            let drain_count = memory.interactions.len() - 500;
            memory.interactions.drain(0..drain_count);
        }

        self.save(memory);

        // Also save to the Markdown Vault (LLM Wiki pattern + Git)
        let vault = crate::memory_vault::MemoryVault::new();
        vault.save_vault(memory);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_save_and_load() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("memory.db");
        let store = MemoryStore::new(path);

        let mut memory = KairoMemory::new();
        memory.add_preference("formatting", "prefers bullet points", 0.8);

        store.save(&memory);
        let loaded = store.load();

        assert_eq!(loaded.preferences.len(), 1);
        assert_eq!(loaded.preferences[0].value, "prefers bullet points");
    }

    #[test]
    fn test_empty_load() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("nonexistent.db");
        let store = MemoryStore::new(path);
        let memory = store.load();
        assert!(memory.preferences.is_empty());
    }
}
