use super::IntegrationAdapter;
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use std::path::PathBuf;
use tokio::fs;

pub struct ObsidianAdapter {
    vault_path: Option<PathBuf>,
}

impl Default for ObsidianAdapter {
    fn default() -> Self {
        Self::new()
    }
}

impl ObsidianAdapter {
    pub fn new() -> Self {
        // In a real scenario, we would read this from Kairo config or auto-detect
        Self { vault_path: None }
    }

    async fn detect_vault(&mut self) -> Result<PathBuf> {
        if let Some(path) = &self.vault_path {
            return Ok(path.clone());
        }

        // Mock detection: check common locations or config
        let home = dirs::home_dir().ok_or_else(|| anyhow!("Could not find home directory"))?;
        let possible_vault = home.join("Documents/Obsidian Vault");

        if fs::metadata(&possible_vault).await.is_ok() {
            self.vault_path = Some(possible_vault.clone());
            Ok(possible_vault)
        } else {
            Err(anyhow!("Obsidian vault not found"))
        }
    }
}

#[async_trait]
impl IntegrationAdapter for ObsidianAdapter {
    fn id(&self) -> &'static str {
        "obsidian"
    }

    async fn is_available(&self) -> bool {
        // Check if Obsidian process is running or if vault is accessible
        // For now, check if vault exists
        let mut self_clone = Self {
            vault_path: self.vault_path.clone(),
        };
        self_clone.detect_vault().await.is_ok()
    }

    async fn get_deep_context(&self) -> Result<String> {
        let mut self_clone = Self {
            vault_path: self.vault_path.clone(),
        };
        let vault = self_clone.detect_vault().await?;

        // Example: List recent notes or tags to provide context
        let mut context = format!("Obsidian Vault: {}\n", vault.display());
        context.push_str("Recent Files: [mock_list_of_files.md]\n");

        Ok(context)
    }

    async fn execute_action(&self, action: &str, data: &str) -> Result<()> {
        let mut self_clone = Self {
            vault_path: self.vault_path.clone(),
        };
        let vault = self_clone.detect_vault().await?;

        match action {
            "create_note" => {
                let file_path = vault.join(format!("{data}.md"));
                fs::write(file_path, "# New Note\nCreated by Kairo Phantom").await?;
                Ok(())
            }
            _ => Err(anyhow!("Unsupported action: {action}")),
        }
    }
}
