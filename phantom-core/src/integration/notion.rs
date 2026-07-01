use super::IntegrationAdapter;
use anyhow::{anyhow, Result};
use async_trait::async_trait;

pub struct NotionAdapter {
    api_key: Option<String>,
}

impl Default for NotionAdapter {
    fn default() -> Self {
        Self::new()
    }
}

impl NotionAdapter {
    pub fn new() -> Self {
        Self { api_key: None }
    }

    fn get_api_key(&self) -> Result<String> {
        self.api_key
            .clone()
            .or_else(|| {
                // Mock: Get from env or config
                std::env::var("NOTION_API_KEY").ok()
            })
            .ok_or_else(|| anyhow!("Notion API key not configured"))
    }
}

#[async_trait]
impl IntegrationAdapter for NotionAdapter {
    fn id(&self) -> &'static str {
        "notion"
    }

    async fn is_available(&self) -> bool {
        self.get_api_key().is_ok()
    }

    async fn get_deep_context(&self) -> Result<String> {
        let _key = self.get_api_key()?;

        // Mock Notion API call to fetch workspace metadata
        Ok(
            "Notion Workspace: Kairo Team\nDatabases: [Projects, Tasks, Knowledge Base]"
                .to_string(),
        )
    }

    async fn execute_action(&self, action: &str, data: &str) -> Result<()> {
        let _key = self.get_api_key()?;

        match action {
            "append_block" => {
                // Mock Notion API call to append block
                println!("Notion: Appending block with data: {data}");
                Ok(())
            }
            _ => Err(anyhow!("Unsupported action: {action}")),
        }
    }
}
