//! KPX Export — P1-A4
//! Exports MemMachine to the .kpx format (portable Kairo Preference Exchange).
//! Human-readable JSON metadata + opaque binary embedding vectors.
//! Import: `kairo import <file.kpx>`

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::Path;

/// Header metadata stored in the .kpx file (human-readable)
#[derive(Debug, Serialize, Deserialize)]
pub struct KpxManifest {
    pub version: String,
    pub created_at: i64,
    pub kairo_version: String,
    pub episode_count: usize,
    pub description: String,
    pub machine_id_hash: String, // SHA256 of machine ID — NOT the actual ID
}

/// One episode in the .kpx export
#[derive(Debug, Serialize, Deserialize)]
pub struct KpxEpisode {
    pub id: String,
    pub timestamp: i64,
    pub content: String,
    pub app_context: String,
    pub context_key: String,
    pub is_ground_truth: bool,
    pub tags: String,
    pub storage_strength: f64,
    /// Opaque binary blob (base64-encoded embedding vector)
    pub embedding_b64: String,
}

/// Full .kpx file structure
#[derive(Debug, Serialize, Deserialize)]
pub struct KpxFile {
    pub manifest: KpxManifest,
    pub episodes: Vec<KpxEpisode>,
}

pub struct KpxExporter;

impl KpxExporter {
    /// Export all memories from the SQLite database to a .kpx file.
    pub fn export(db_path: &Path, output_path: &Path, description: &str) -> Result<usize> {
        use rusqlite::{params, Connection};

        let conn = Connection::open(db_path)?;

        // Fetch all episodes
        let mut stmt = conn.prepare(
            "SELECT id, timestamp, content, full_episode, app_context, context_key,
                    is_ground_truth, tags, storage_strength, embedding
             FROM semantic_memory ORDER BY timestamp DESC",
        )?;

        let mut episodes = Vec::new();
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, bool>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, f64>(8)?,
                row.get::<_, Option<Vec<u8>>>(9)?,
            ))
        })?;

        for row in rows.flatten() {
            let (id, ts, content, _full, app_ctx, ctx_key, ground_truth, tags, strength, emb) = row;
            let embedding_b64 = emb
                .map(|b| base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &b))
                .unwrap_or_default();

            episodes.push(KpxEpisode {
                id,
                timestamp: ts,
                content,
                app_context: app_ctx,
                context_key: ctx_key,
                is_ground_truth: ground_truth,
                tags,
                storage_strength: strength,
                embedding_b64,
            });
        }

        let count = episodes.len();
        let manifest = KpxManifest {
            version: "1.0".to_string(),
            created_at: chrono::Utc::now().timestamp(),
            kairo_version: env!("CARGO_PKG_VERSION").to_string(),
            episode_count: count,
            description: description.to_string(),
            machine_id_hash: Self::machine_id_hash(),
        };

        let kpx = KpxFile { manifest, episodes };
        let json = serde_json::to_string_pretty(&kpx)?;
        std::fs::write(output_path, json)?;

        tracing::info!(
            "📦 KPX: exported {} episodes to {}",
            count,
            output_path.display()
        );
        Ok(count)
    }

    /// Import a .kpx file into the SQLite database.
    pub fn import(kpx_path: &Path, db_path: &Path) -> Result<usize> {
        use rusqlite::{params, Connection};

        let content = std::fs::read_to_string(kpx_path)?;
        let kpx: KpxFile = serde_json::from_str(&content)?;

        let conn = Connection::open(db_path)?;
        let mut imported = 0;

        for ep in kpx.episodes {
            let emb_blob = if ep.embedding_b64.is_empty() {
                None
            } else {
                base64::Engine::decode(
                    &base64::engine::general_purpose::STANDARD,
                    &ep.embedding_b64,
                )
                .ok()
            };

            conn.execute(
                "INSERT OR IGNORE INTO semantic_memory
                 (id, timestamp, content, full_episode, app_context, context_key,
                  is_ground_truth, tags, storage_strength, embedding)
                 VALUES (?1,?2,?3,'',?4,?5,?6,?7,?8,?9)",
                params![
                    ep.id,
                    ep.timestamp,
                    ep.content,
                    ep.app_context,
                    ep.context_key,
                    ep.is_ground_truth as i32,
                    ep.tags,
                    ep.storage_strength,
                    emb_blob
                ],
            )?;
            imported += 1;
        }

        tracing::info!(
            "📥 KPX: imported {} episodes from {}",
            imported,
            kpx_path.display()
        );
        Ok(imported)
    }

    fn machine_id_hash() -> String {
        use sha2::{Digest, Sha256};
        let id = std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .unwrap_or_else(|_| "unknown".to_string());
        let mut hasher = Sha256::new();
        hasher.update(id.as_bytes());
        format!("{:x}", hasher.finalize())[..16].to_string()
    }
}
