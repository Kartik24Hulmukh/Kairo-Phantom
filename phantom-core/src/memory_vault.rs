// phantom-core/src/memory_vault.rs
use crate::memory::KairoMemory;
use chrono::Local;
use std::fs;
use std::path::PathBuf;
use tracing::{info, warn};

pub struct MemoryVault {
    base_path: PathBuf,
}

impl Default for MemoryVault {
    fn default() -> Self {
        Self::new()
    }
}

impl MemoryVault {
    pub fn new() -> Self {
        let path = dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".kairo-phantom")
            .join("memory");

        Self { base_path: path }
    }

    pub fn with_path(path: PathBuf) -> Self {
        Self { base_path: path }
    }

    pub fn ensure_directories(&self) -> std::io::Result<()> {
        fs::create_dir_all(self.base_path.join("daily"))?;
        fs::create_dir_all(self.base_path.join("knowledge/concepts"))?;
        fs::create_dir_all(self.base_path.join("knowledge/prefs"))?;
        Ok(())
    }

    pub fn save_vault(&self, memory: &KairoMemory) {
        if let Err(e) = self.ensure_directories() {
            warn!("Failed to create memory vault directories: {}", e);
            return;
        }

        self.save_daily_log(memory);
        self.save_knowledge_concepts(memory);
        self.save_knowledge_prefs(memory);
        self.save_index(memory);
        self.commit_to_git("Updated Kairo memory vault");
    }

    fn save_daily_log(&self, memory: &KairoMemory) {
        let date = Local::now().format("%Y-%m-%d").to_string();
        let daily_path = self.base_path.join("daily").join(format!("{date}.md"));

        let mut content = format!("# Daily Log: {date}\n\n");

        let today_timestamp = chrono::Local::now()
            .date_naive()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc()
            .timestamp() as u64;

        for interaction in &memory.interactions {
            // Only add interactions from today (heuristic approximation here)
            // Just outputting the most recent ones if they happened today.
            if interaction.timestamp >= today_timestamp {
                let status = if interaction.accepted {
                    "✅ Accepted"
                } else {
                    "❌ Rejected"
                };
                content.push_str(&format!("## [{}] App: {}\n", status, interaction.app));
                content.push_str(&format!("**Prompt:** {}\n\n", interaction.prompt));
                content.push_str(&format!(
                    "**Response:** {}\n\n---\n\n",
                    interaction.response
                ));
            }
        }

        if let Err(e) = fs::write(&daily_path, content) {
            warn!("Failed to write daily log {:?}: {}", daily_path, e);
        }
    }

    fn save_knowledge_concepts(&self, memory: &KairoMemory) {
        for node in &memory.graph.nodes {
            let safe_node = node.replace(|c: char| !c.is_alphanumeric(), "_");
            let node_path = self
                .base_path
                .join("knowledge/concepts")
                .join(format!("{safe_node}.md"));

            let mut content = format!("# Concept: {node}\n\n");
            content.push_str("## Relationships\n");

            for (from, to, rel) in &memory.graph.edges {
                if let Some(from_node) = memory.graph.nodes.get(*from) {
                    if let Some(to_node) = memory.graph.nodes.get(*to) {
                        if from_node == node {
                            content.push_str(&format!("- {rel} {to_node}\n"));
                        } else if to_node == node {
                            content.push_str(&format!("- {rel} (from {from_node})\n"));
                        }
                    }
                }
            }

            if let Err(e) = fs::write(&node_path, content) {
                warn!("Failed to write concept {:?}: {}", node_path, e);
            }
        }
    }

    fn save_knowledge_prefs(&self, memory: &KairoMemory) {
        let prefs_path = self
            .base_path
            .join("knowledge/prefs")
            .join("user_preferences.md");
        let mut content = String::from("# User Preferences\n\n");

        content.push_str("## Core Preferences\n");
        for pref in &memory.preferences {
            content.push_str(&format!(
                "- **{}**: {} (weight: {})\n",
                pref.key, pref.value, pref.weight
            ));
        }

        content.push_str("\n## App Bias\n");
        for (app, bias) in &memory.app_bias {
            content.push_str(&format!("- **{app}**: {bias}\n"));
        }

        content.push_str("\n## Word Preferences\n");
        for (k, v) in &memory.user_model.word_preferences {
            content.push_str(&format!("- **{k}**: {v}\n"));
        }

        content.push_str("\n## PowerPoint Preferences\n");
        for (k, v) in &memory.user_model.ppt_preferences {
            content.push_str(&format!("- **{k}**: {v}\n"));
        }

        if let Err(e) = fs::write(&prefs_path, content) {
            warn!("Failed to write preferences {:?}: {}", prefs_path, e);
        }
    }

    fn save_index(&self, memory: &KairoMemory) {
        let index_path = self.base_path.join("index.md");
        let mut content = String::from("# Kairo Memory Index\n\n");

        content.push_str(&format!(
            "- Interactions recorded: {}\n",
            memory.interactions.len()
        ));
        content.push_str(&format!(
            "- Concepts tracked: {}\n",
            memory.graph.nodes.len()
        ));
        content.push_str(&format!(
            "- Preferences mapped: {}\n",
            memory.preferences.len()
        ));
        content.push_str("\n## Quick Links\n");
        content.push_str("- [Daily Logs](daily/)\n");
        content.push_str("- [Concepts](knowledge/concepts/)\n");
        content.push_str("- [Preferences](knowledge/prefs/user_preferences.md)\n");

        if let Err(e) = fs::write(&index_path, content) {
            warn!("Failed to write index {:?}: {}", index_path, e);
        }
    }

    fn commit_to_git(&self, message: &str) {
        // Initialize git repo if it doesn't exist
        if !self.base_path.join(".git").exists() {
            let init_status = std::process::Command::new("git")
                .arg("init")
                .current_dir(&self.base_path)
                .output();
            if let Err(e) = init_status {
                warn!("Failed to initialize git repository in memory vault: {}", e);
                return;
            }
        }

        // Add all files
        let add_status = std::process::Command::new("git")
            .args(["add", "."])
            .current_dir(&self.base_path)
            .output();

        if let Err(e) = add_status {
            warn!("Failed to git add in memory vault: {}", e);
            return;
        }

        // Commit
        let _commit_status = std::process::Command::new("git")
            .args(["commit", "-m", message])
            .current_dir(&self.base_path)
            .output();

        info!("📚 Memory vault updated and git-versioned.");
    }
}
