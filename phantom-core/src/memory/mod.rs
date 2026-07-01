pub mod document_graph;
pub mod feedback;
pub mod mem_gas;
pub mod mem_machine;
pub mod optimizer;
pub mod types;
pub use mem_machine::MemMachine;
pub use types::*;

use rusqlite::{params, Connection, Result};

use chrono::Utc;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

pub struct VaultV2 {
    conn: Connection,
    vault_dir: PathBuf,
}

impl VaultV2 {
    pub fn new(vault_dir: PathBuf) -> Result<Self> {
        fs::create_dir_all(&vault_dir).unwrap();
        let db_path = vault_dir.join("memory.db");
        let conn = Connection::open(db_path)?;

        // Schema
        conn.execute(
            "CREATE TABLE IF NOT EXISTS interactions (
                id TEXT PRIMARY KEY,
                timestamp INTEGER,
                app_name TEXT,
                agent_used TEXT,
                prompt_hash TEXT,
                outcome TEXT,
                accepted_chars INTEGER,
                generated_chars INTEGER,
                tone_detected TEXT,
                format_detected TEXT
            )",
            [],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_preferences (
                app_name TEXT PRIMARY KEY,
                preferred_tone TEXT,
                preferred_format TEXT,
                preferred_length TEXT,
                acceptance_rate REAL,
                last_updated INTEGER
            )",
            [],
        )?;

        Ok(Self { conn, vault_dir })
    }

    #[allow(clippy::too_many_arguments)]
    pub fn log_interaction(
        &self,
        id: &str,
        app_name: &str,
        agent_used: &str,
        prompt_hash: &str,
        outcome: &str,
        accepted_chars: i64,
        generated_chars: i64,
        tone_detected: &str,
        format_detected: &str,
    ) -> Result<()> {
        let timestamp = Utc::now().timestamp();
        self.conn.execute(
            "INSERT INTO interactions (id, timestamp, app_name, agent_used, prompt_hash, outcome, accepted_chars, generated_chars, tone_detected, format_detected)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
            params![id, timestamp, app_name, agent_used, prompt_hash, outcome, accepted_chars, generated_chars, tone_detected, format_detected],
        )?;

        self.update_preferences(app_name)?;
        Ok(())
    }

    fn update_preferences(&self, app_name: &str) -> Result<()> {
        // Calculate rolling 10-interaction acceptance rate
        let mut stmt = self.conn.prepare(
            "SELECT format_detected, outcome FROM interactions 
             WHERE app_name = ?1 
             ORDER BY timestamp DESC LIMIT 10",
        )?;

        let rows = stmt.query_map(params![app_name], |row| {
            let format: String = row.get(0)?;
            let outcome: String = row.get(1)?;
            Ok((format, outcome))
        })?;

        let mut format_counts = std::collections::HashMap::new();
        let mut total = 0;
        let mut accepted = 0;

        for (format, outcome) in rows.flatten() {
            total += 1;
            if outcome == "accepted" {
                accepted += 1;
                *format_counts.entry(format).or_insert(0) += 1;
            }
        }

        if total == 0 {
            return Ok(());
        }

        let acceptance_rate = accepted as f64 / total as f64;
        let mut preferred_format = "prose".to_string(); // Default

        // If a specific format has high acceptance, learn it
        for (format, count) in format_counts {
            if (count as f64 / total as f64) > 0.7 {
                preferred_format = format;
            }
        }

        let timestamp = Utc::now().timestamp();
        self.conn.execute(
            "INSERT INTO app_preferences (app_name, preferred_tone, preferred_format, preferred_length, acceptance_rate, last_updated)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)
             ON CONFLICT(app_name) DO UPDATE SET
                preferred_format = excluded.preferred_format,
                acceptance_rate = excluded.acceptance_rate,
                last_updated = excluded.last_updated",
            params![app_name, "formal", preferred_format, "medium", acceptance_rate, timestamp],
        )?;

        Ok(())
    }

    pub fn get_preferences(&self, app_name: &str) -> Result<String> {
        let mut stmt = self.conn.prepare(
            "SELECT preferred_tone, preferred_format, preferred_length, acceptance_rate 
             FROM app_preferences WHERE app_name = ?1",
        )?;

        let mut rows = stmt.query(params![app_name])?;
        if let Some(row) = rows.next()? {
            let tone: String = row.get(0)?;
            let format: String = row.get(1)?;
            let length: String = row.get(2)?;
            let acc: f64 = row.get(3)?;
            Ok(format!("USER PREFERENCES FOR {}: Tone={}, Format={}, Length={}. Historical acceptance: {:.0}%", 
                app_name, tone, format, length, acc * 100.0))
        } else {
            Ok(String::new())
        }
    }

    pub fn compile_memory(&self) -> Result<()> {
        let pref_dir = self.vault_dir.join("preferences");
        let daily_dir = self.vault_dir.join("daily");
        fs::create_dir_all(&pref_dir).unwrap();
        fs::create_dir_all(&daily_dir).unwrap();

        let date_str = Utc::now().format("%Y-%m-%d").to_string();
        let log_file = daily_dir.join(format!("{date_str}.md"));

        fs::write(&log_file, format!("# Memory compilation for {date_str}\n")).unwrap();

        // Git commit
        Command::new("git")
            .current_dir(&self.vault_dir)
            .args(["add", "."])
            .output()
            .ok();

        Command::new("git")
            .current_dir(&self.vault_dir)
            .args(["commit", "-m", &format!("Memory update {date_str}")])
            .output()
            .ok();

        Ok(())
    }
}
