// phantom-core/src/tolaria_bridge.rs
use crate::mcp_client::McpClient;
use anyhow::Result;
use serde_json::json;
use tracing::{info, warn};

pub struct TolariaBridge {
    client: McpClient,
}

impl TolariaBridge {
    pub fn new(tolaria_path: &str) -> Self {
        // According to the LLM Wiki pattern, Tolaria exposes an MCP server.
        // We connect via stdio to the Tolaria executable in MCP mode.
        Self {
            client: McpClient::new(tolaria_path, &["mcp"]),
        }
    }

    pub async fn fetch_enterprise_context(&self, query: &str) -> Result<String> {
        info!(
            "Fetching enterprise context from Tolaria for query: {}",
            query
        );

        let args = json!({
            "query": query,
            "limit": 5
        });

        // "search_notes" is a standard Tolaria MCP tool
        match self.client.call_tool("search_notes", args).await {
            Ok(response) => {
                if let Some(results) = response.get("results") {
                    Ok(results.to_string())
                } else {
                    Ok(response.to_string())
                }
            }
            Err(e) => {
                warn!("Tolaria MCP bridge failed: {}", e);
                Err(e)
            }
        }
    }

    pub async fn get_brand_guidelines(&self) -> Result<String> {
        self.fetch_enterprise_context("brand guidelines").await
    }

    pub async fn get_legal_boilerplate(&self) -> Result<String> {
        self.fetch_enterprise_context("legal boilerplate").await
    }
}
