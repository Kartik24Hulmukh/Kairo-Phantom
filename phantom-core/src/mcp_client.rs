use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::Command;
use tracing::info;

#[derive(Serialize, Deserialize, Debug)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub id: u64,
    pub method: String,
    pub params: serde_json::Value,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub id: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<serde_json::Value>,
}

pub struct McpClient {
    command: String,
    args: Vec<String>,
}

impl McpClient {
    pub fn new(command: &str, args: &[&str]) -> Self {
        Self {
            command: command.to_string(),
            args: args.iter().map(|s| s.to_string()).collect(),
        }
    }

    /// Executes a single tool call on the MCP server via stdio.
    pub async fn call_tool(
        &self,
        tool_name: &str,
        arguments: serde_json::Value,
    ) -> Result<serde_json::Value> {
        info!(
            "MCP Client calling tool: {} via {}",
            tool_name, self.command
        );

        let mut child = Command::new(&self.command)
            .args(&self.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .context("Failed to spawn MCP server")?;

        let mut stdin = child.stdin.take().context("Failed to open stdin")?;
        let stdout = child.stdout.take().context("Failed to open stdout")?;

        // Construct the call tool request (simulating MCP protocol)
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: 1,
            method: "tools/call".to_string(),
            params: serde_json::json!({
                "name": tool_name,
                "arguments": arguments
            }),
        };

        let req_bytes = serde_json::to_vec(&request)?;
        stdin.write_all(&req_bytes).await?;
        stdin.write_all(b"\n").await?;
        stdin.flush().await?;

        let mut reader = BufReader::new(stdout);
        let mut line = String::new();

        // Wait for response
        let _ = reader.read_line(&mut line).await?;

        // Ensure child cleans up
        let _ = child.kill().await;

        let response: JsonRpcResponse =
            serde_json::from_str(&line).context("Failed to parse MCP response")?;

        if let Some(err) = response.error {
            anyhow::bail!("MCP Tool Error: {err:?}");
        }

        if let Some(result) = response.result {
            Ok(result)
        } else {
            anyhow::bail!("MCP Tool returned no result");
        }
    }
}
