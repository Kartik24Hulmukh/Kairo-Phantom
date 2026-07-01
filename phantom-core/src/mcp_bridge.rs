/// MCP Bridge — Phase 2: Subprocess MCP client for Office-PPTX-Bridge, Figma-Bridge, etc.
/// Kairo spawns Python MCP servers as stdio subprocesses and communicates via JSON-RPC.
/// This is the "route to best available MCP server" layer described in the phase2 plan.
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tracing::{debug, info};

// ─── JSON-RPC types ────────────────────────────────────────────────────────────

#[derive(Serialize, Debug)]
struct JsonRpcRequest<'a> {
    jsonrpc: &'static str,
    id: u64,
    method: &'a str,
    params: Value,
}

#[derive(Deserialize, Debug)]
struct JsonRpcResponse {
    #[allow(dead_code)]
    jsonrpc: String,
    id: Option<u64>,
    result: Option<Value>,
    error: Option<Value>,
}

// ─── MCP Bridge Client ────────────────────────────────────────────────────────

/// A handle to a running MCP server subprocess (stdio transport).
pub struct McpBridgeClient {
    /// The spawned subprocess
    child: Mutex<Child>,
    /// The subprocess stdin writer
    stdin: Mutex<std::process::ChildStdin>,
    /// The subprocess stdout reader (line-by-line JSON-RPC)
    stdout: Mutex<BufReader<std::process::ChildStdout>>,
    /// The server identifier (e.g. "office-pptx-bridge", "figma-bridge")
    pub server_id: String,
    /// Request counter
    next_id: Mutex<u64>,
}

impl McpBridgeClient {
    /// Spawn a Python-based MCP server script as a subprocess.
    ///
    /// # Arguments
    /// * `server_id` — Human-readable name (for logging)
    /// * `script_path` — Full path to the Python script
    /// * `extra_args` — Additional CLI arguments
    pub fn spawn_python(server_id: &str, script_path: &str, extra_args: &[&str]) -> Result<Self> {
        info!("🔌 Spawning MCP bridge: {} ({})", server_id, script_path);

        let mut cmd = Command::new("python");
        cmd.arg(script_path);
        for a in extra_args {
            cmd.arg(a);
        }
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());

        let mut child = cmd
            .spawn()
            .with_context(|| format!("Failed to spawn {server_id} — is Python installed?"))?;

        let stdin = child
            .stdin
            .take()
            .context("Could not capture subprocess stdin")?;
        let stdout = child
            .stdout
            .take()
            .context("Could not capture subprocess stdout")?;

        info!(
            "✅ MCP bridge '{}' started (PID: {})",
            server_id,
            child.id()
        );

        Ok(Self {
            child: Mutex::new(child),
            stdin: Mutex::new(stdin),
            stdout: Mutex::new(BufReader::new(stdout)),
            server_id: server_id.to_string(),
            next_id: Mutex::new(1),
        })
    }

    /// Send a JSON-RPC request and wait for the matching response.
    pub fn call(&self, method: &str, params: Value) -> Result<Value> {
        let id = {
            let mut n = self.next_id.lock().unwrap();
            let id = *n;
            *n += 1;
            id
        };

        let req = JsonRpcRequest {
            jsonrpc: "2.0",
            id,
            method,
            params,
        };

        let req_line = serde_json::to_string(&req).unwrap();
        debug!(
            "→ MCP[{}]: {}",
            self.server_id,
            &req_line[..req_line.len().min(200)]
        );

        {
            let mut stdin = self.stdin.lock().unwrap();
            stdin.write_all(req_line.as_bytes())?;
            stdin.write_all(b"\n")?;
            stdin.flush()?;
        }

        // Read lines until we find the matching response id
        let mut stdout = self.stdout.lock().unwrap();
        loop {
            let mut line = String::new();
            let n = stdout.read_line(&mut line)?;
            if n == 0 {
                anyhow::bail!("MCP server '{}' closed stdout unexpectedly", self.server_id);
            }
            let line = line.trim();
            if line.is_empty() {
                continue;
            }

            debug!(
                "← MCP[{}]: {}",
                self.server_id,
                &line[..line.len().min(300)]
            );

            let resp: JsonRpcResponse = serde_json::from_str(line)
                .with_context(|| format!("Failed to parse MCP response: {line}"))?;

            if resp.id == Some(id) {
                if let Some(err) = resp.error {
                    anyhow::bail!("MCP error from '{}': {}", self.server_id, err);
                }
                return resp.result.context("MCP response had no result");
            }
        }
    }

    /// Initialize the MCP session (required by MCP protocol)
    pub fn initialize(&self) -> Result<()> {
        let result = self.call(
            "initialize",
            json!({
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kairo-phantom", "version": env!("CARGO_PKG_VERSION")}
            }),
        )?;
        info!(
            "🤝 MCP '{}' initialized: {}",
            self.server_id,
            result.get("serverInfo").unwrap_or(&json!({}))
        );
        Ok(())
    }

    /// Kill the subprocess on drop
    pub fn shutdown(&self) {
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
        }
    }
}

impl Drop for McpBridgeClient {
    fn drop(&mut self) {
        self.shutdown();
    }
}

// ─── PPTX Bridge High-Level API ───────────────────────────────────────────────

/// High-level API for the Office PowerPoint MCP bridge.
pub struct PptxBridge {
    client: McpBridgeClient,
}

impl PptxBridge {
    /// Spawn the office-pptx-bridge Python server.
    pub fn new(script_path: &str) -> Result<Self> {
        let client = McpBridgeClient::spawn_python("office-pptx-bridge", script_path, &[])?;
        client.initialize()?;
        Ok(Self { client })
    }

    /// Create a new presentation with given slides.
    /// Each slide is a (title, content, image_base64?) tuple.
    pub fn create_presentation(&self, output_path: &str, slides: &[SlideSpec]) -> Result<()> {
        let slides_json: Vec<Value> = slides
            .iter()
            .map(|s| {
                let mut obj = json!({
                    "title": s.title,
                    "content": s.content
                });
                if let Some(ref img) = s.image_base64 {
                    obj["image_base64"] = Value::String(img.clone());
                    obj["image_mime"] =
                        Value::String(s.image_mime.clone().unwrap_or_else(|| "image/png".into()));
                }
                obj
            })
            .collect();

        self.client.call(
            "tools/call",
            json!({
                "name": "create_presentation",
                "arguments": {
                    "output_path": output_path,
                    "slides": slides_json
                }
            }),
        )?;

        info!("📊 PPTX created: {}", output_path);
        Ok(())
    }

    /// Add an image to a specific slide.
    pub fn add_image_to_slide(
        &self,
        pptx_path: &str,
        slide_index: u32,
        image_base64: &str,
    ) -> Result<()> {
        self.client.call(
            "tools/call",
            json!({
                "name": "add_image_to_slide",
                "arguments": {
                    "pptx_path": pptx_path,
                    "slide_index": slide_index,
                    "image_base64": image_base64
                }
            }),
        )?;
        info!("🖼️  Image added to slide {} in {}", slide_index, pptx_path);
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct SlideSpec {
    pub title: String,
    pub content: String,
    pub image_base64: Option<String>,
    pub image_mime: Option<String>,
}

// ─── Figma Bridge High-Level API ──────────────────────────────────────────────

/// High-level API for the Figma MCP bridge (figma-mcp-go compatible).
pub struct FigmaBridge {
    client: McpBridgeClient,
}

impl FigmaBridge {
    /// Spawn the figma-bridge server (Node.js/Python wrapper).
    pub fn new(script_path: &str) -> Result<Self> {
        let client = McpBridgeClient::spawn_python("figma-bridge", script_path, &[])?;
        client.initialize()?;
        Ok(Self { client })
    }

    /// Import an image (base64) into the current Figma frame.
    pub fn import_image(&self, name: &str, image_base64: &str) -> Result<Value> {
        let result = self.client.call(
            "tools/call",
            json!({
                "name": "import_image",
                "arguments": {
                    "name": name,
                    "image_base64": image_base64
                }
            }),
        )?;
        info!("🎨 Image imported to Figma frame: {}", name);
        Ok(result)
    }

    /// Create a text node in Figma.
    pub fn create_text(&self, text: &str, x: f32, y: f32) -> Result<Value> {
        let result = self.client.call(
            "tools/call",
            json!({
                "name": "create_text",
                "arguments": {
                    "text": text,
                    "x": x,
                    "y": y
                }
            }),
        )?;
        Ok(result)
    }
}

// ─── MCP Bridge Registry ──────────────────────────────────────────────────────

/// Discovers and lazily initializes MCP bridge servers based on config.
pub struct McpBridgeRegistry {
    pub pptx_script: Option<String>,
    pub figma_script: Option<String>,
}

impl McpBridgeRegistry {
    pub fn from_env() -> Self {
        // Look for bridge scripts relative to the binary
        let base = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_default();

        let pptx_script = {
            let candidate = base.join("../mcp-servers/office-pptx-bridge/server.py");
            if candidate.exists() {
                Some(candidate.to_string_lossy().to_string())
            } else {
                // Also check relative to cwd
                let cwd_candidate =
                    std::path::Path::new("mcp-servers/office-pptx-bridge/server.py");
                if cwd_candidate.exists() {
                    Some(cwd_candidate.to_string_lossy().to_string())
                } else {
                    None
                }
            }
        };

        let figma_script = {
            let candidate = base.join("../mcp-servers/figma-bridge/server.py");
            if candidate.exists() {
                Some(candidate.to_string_lossy().to_string())
            } else {
                let cwd_candidate = std::path::Path::new("mcp-servers/figma-bridge/server.py");
                if cwd_candidate.exists() {
                    Some(cwd_candidate.to_string_lossy().to_string())
                } else {
                    None
                }
            }
        };

        if pptx_script.is_some() {
            info!("🔌 PPTX bridge discovered");
        }
        if figma_script.is_some() {
            info!("🎨 Figma bridge discovered");
        }

        Self {
            pptx_script,
            figma_script,
        }
    }

    pub fn has_pptx_bridge(&self) -> bool {
        self.pptx_script.is_some()
    }
    pub fn has_figma_bridge(&self) -> bool {
        self.figma_script.is_some()
    }
}
