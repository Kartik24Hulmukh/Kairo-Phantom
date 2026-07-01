//! # VLM Bridge — Rust ↔ Python VLM Communication
//!
//! Provides the Rust-side interface to Kairo's Python VLM grounding engine.
//!
//! The VLM (Qwen2.5-VL-7B-GGUF) runs in the Python sidecar via Ollama.
//! Rust requests grounding or verification by sending JSON over the
//! existing named-pipe IPC to the sidecar.
//!
//! ## Protocol
//! Request:
//! ```json
//! {"type": "vlm_ground", "screenshot": "/path/to/screen.png", "description": "Submit button"}
//! ```
//! Response:
//! ```json
//! {"found": true, "x": 840, "y": 450, "confidence": 0.97, "latency_ms": 1200}
//! ```
//!
//! ## Usage
//! ```rust,ignore
//! use crate::cua::vlm_bridge::{VlmBridge, VlmGroundRequest, VlmVerifyRequest};
//!
//! let bridge = VlmBridge::new();
//! if bridge.is_available() {
//!     let result = bridge.ground_element("/tmp/screen.png", "Submit button").await?;
//! }
//! ```

use serde::{Deserialize, Serialize};
use std::path::Path;
use std::time::Duration;

/// VLM grounding request payload
#[derive(Debug, Clone, Serialize)]
pub struct VlmGroundRequest {
    /// Path to screenshot PNG
    pub screenshot: String,
    /// Natural language description of target element
    pub description: String,
}

/// VLM grounding response from Python sidecar
#[derive(Debug, Clone, Deserialize)]
pub struct VlmGroundResponse {
    /// Whether element was found
    pub found: bool,
    /// X coordinate (0 if not found)
    pub x: i32,
    /// Y coordinate (0 if not found)
    pub y: i32,
    /// Confidence score 0.0–1.0
    pub confidence: f32,
    /// Human-readable description
    pub description: String,
    /// Inference latency in milliseconds
    pub latency_ms: f32,
}

/// VLM verification request payload
#[derive(Debug, Clone, Serialize)]
pub struct VlmVerifyRequest {
    pub before_screenshot: String,
    pub after_screenshot: String,
    pub expected_result: String,
}

/// VLM verification response
#[derive(Debug, Clone, Deserialize)]
pub struct VlmVerifyResponse {
    pub success: bool,
    pub confidence: f32,
    pub explanation: String,
    pub latency_ms: f32,
}

/// VLM download status response
#[derive(Debug, Clone, Deserialize)]
pub struct VlmStatusResponse {
    /// Whether VLM is available for use
    pub available: bool,
    /// Whether model is currently downloading
    pub downloading: bool,
    /// Download progress percent (0–100)
    pub download_percent: f32,
    /// Hardware tier detected
    pub hardware_tier: String,
    /// Selected model name
    pub model_name: String,
}

/// Error type for VLM bridge operations
#[derive(Debug, Clone)]
pub enum VlmBridgeError {
    /// Sidecar not connected
    SidecarUnavailable,
    /// VLM model not yet downloaded
    ModelNotDownloaded { progress: f32 },
    /// IPC communication error
    IpcError(String),
    /// Response parse error
    ParseError(String),
    /// Timeout waiting for VLM response
    Timeout,
}

impl std::fmt::Display for VlmBridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            VlmBridgeError::SidecarUnavailable => {
                write!(f, "VLM bridge: Python sidecar not connected")
            }
            VlmBridgeError::ModelNotDownloaded { progress } => {
                write!(
                    f,
                    "VLM model downloading ({progress:.0}%) — CUA in keyboard-only mode",
                )
            }
            VlmBridgeError::IpcError(msg) => write!(f, "VLM bridge IPC error: {msg}"),
            VlmBridgeError::ParseError(msg) => write!(f, "VLM response parse error: {msg}"),
            VlmBridgeError::Timeout => write!(f, "VLM inference timed out (60s)"),
        }
    }
}

/// Bridge to the Python VLM grounding engine.
///
/// All VLM calls are asynchronous and routed through the existing
/// Rust ↔ Python named-pipe IPC. This keeps the VLM processing
/// entirely in the Python sidecar while allowing Rust CUA code
/// to request grounding and verification.
pub struct VlmBridge {
    /// Named pipe path for sidecar IPC
    pipe_name: String,
    /// Timeout for VLM inference (60s for CPU mode, 10s for GPU)
    timeout: Duration,
}

impl Default for VlmBridge {
    fn default() -> Self {
        Self::new()
    }
}

impl VlmBridge {
    /// Create a new VLM bridge with default settings.
    pub fn new() -> Self {
        Self {
            pipe_name: r"\\.\pipe\kairo_sidecar".to_string(),
            timeout: Duration::from_secs(60),
        }
    }

    /// Create bridge with custom pipe and timeout.
    pub fn with_config(pipe_name: String, timeout: Duration) -> Self {
        Self { pipe_name, timeout }
    }

    /// Check if VLM is available for grounding.
    ///
    /// Returns false if:
    /// - Sidecar not connected
    /// - Model not yet downloaded (keyboard-only mode)
    /// - Ollama not running
    pub async fn is_available(&self) -> bool {
        if std::env::var("KAIRO_MOCK_ENIGO").is_ok() {
            return true;
        }
        match self.get_status().await {
            Ok(status) => status.available,
            Err(_) => false,
        }
    }

    /// Get VLM download and availability status.
    pub async fn get_status(&self) -> Result<VlmStatusResponse, VlmBridgeError> {
        let req_id = uuid::Uuid::new_v4().to_string();
        let request = serde_json::json!({
            "id": req_id,
            "action": "vlm_status",
        });
        let response_str = self.send_request(&request.to_string()).await?;

        let resp: serde_json::Value = serde_json::from_str(&response_str)
            .map_err(|e| VlmBridgeError::ParseError(e.to_string()))?;

        if resp.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
            if let Some(data) = resp.get("data") {
                serde_json::from_value(data.clone())
                    .map_err(|e| VlmBridgeError::ParseError(e.to_string()))
            } else {
                Err(VlmBridgeError::ParseError(
                    "Missing data field in successful response".to_string(),
                ))
            }
        } else {
            let err_msg = resp
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown sidecar error");
            Err(VlmBridgeError::IpcError(err_msg.to_string()))
        }
    }

    /// Ground a UI element from a screenshot.
    ///
    /// This is the primary VLM call for CUA. When UIA fails to find
    /// an element, this is called to use the VLM for coordinate resolution.
    ///
    /// # Arguments
    /// * `screenshot_path` - Path to the screenshot PNG
    /// * `description` - Natural language description (e.g., "Submit button")
    ///
    /// # Returns
    /// VlmGroundResponse with found=true and coordinates, or found=false.
    pub async fn ground_element(
        &self,
        screenshot_path: impl AsRef<Path>,
        description: &str,
    ) -> Result<VlmGroundResponse, VlmBridgeError> {
        let req_id = uuid::Uuid::new_v4().to_string();
        let payload = VlmGroundRequest {
            screenshot: screenshot_path.as_ref().to_string_lossy().to_string(),
            description: description.to_string(),
        };
        let req = serde_json::json!({
            "id": req_id,
            "action": "vlm_ground",
            "payload": payload,
        });

        let request_json =
            serde_json::to_string(&req).map_err(|e| VlmBridgeError::IpcError(e.to_string()))?;

        let response_str = self.send_request(&request_json).await?;

        let resp: serde_json::Value = serde_json::from_str(&response_str)
            .map_err(|e| VlmBridgeError::ParseError(e.to_string()))?;

        if resp.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
            if let Some(data) = resp.get("data") {
                serde_json::from_value(data.clone())
                    .map_err(|e| VlmBridgeError::ParseError(e.to_string()))
            } else {
                Err(VlmBridgeError::ParseError("Missing data field".to_string()))
            }
        } else {
            let err_msg = resp
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown sidecar error");
            Err(VlmBridgeError::IpcError(err_msg.to_string()))
        }
    }

    /// Semantically verify a CUA action's result.
    ///
    /// Compares before/after screenshots using the VLM to determine if
    /// the expected state change occurred. This replaces pixel-diff
    /// verification with true intent understanding.
    ///
    /// Example: "does the dialog actually say 'File Saved'?"
    pub async fn verify_action(
        &self,
        before_screenshot: impl AsRef<Path>,
        after_screenshot: impl AsRef<Path>,
        expected_result: &str,
    ) -> Result<VlmVerifyResponse, VlmBridgeError> {
        let req_id = uuid::Uuid::new_v4().to_string();
        let payload = VlmVerifyRequest {
            before_screenshot: before_screenshot.as_ref().to_string_lossy().to_string(),
            after_screenshot: after_screenshot.as_ref().to_string_lossy().to_string(),
            expected_result: expected_result.to_string(),
        };
        let req = serde_json::json!({
            "id": req_id,
            "action": "vlm_verify",
            "payload": payload,
        });

        let request_json =
            serde_json::to_string(&req).map_err(|e| VlmBridgeError::IpcError(e.to_string()))?;

        let response_str = self.send_request(&request_json).await?;

        let resp: serde_json::Value = serde_json::from_str(&response_str)
            .map_err(|e| VlmBridgeError::ParseError(e.to_string()))?;

        if resp.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
            if let Some(data) = resp.get("data") {
                serde_json::from_value(data.clone())
                    .map_err(|e| VlmBridgeError::ParseError(e.to_string()))
            } else {
                Err(VlmBridgeError::ParseError("Missing data field".to_string()))
            }
        } else {
            let err_msg = resp
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown sidecar error");
            Err(VlmBridgeError::IpcError(err_msg.to_string()))
        }
    }

    /// Send a JSON request to the sidecar via named pipe and return the response.
    async fn send_request(&self, request_json: &str) -> Result<String, VlmBridgeError> {
        use std::io::{Read, Write};

        let timeout = self.timeout;
        let pipe_name = self.pipe_name.clone();
        let request = format!("{request_json}\n");

        // Run pipe communication in a blocking thread to avoid blocking async runtime
        let result = tokio::task::spawn_blocking(move || {
            #[cfg(target_os = "windows")]
            {
                use std::fs::OpenOptions;

                let file = OpenOptions::new().read(true).write(true).open(&pipe_name);

                match file {
                    Ok(mut f) => {
                        f.write_all(request.as_bytes())
                            .map_err(|e| VlmBridgeError::IpcError(e.to_string()))?;

                        let mut response = String::new();
                        let mut buf = [0u8; 65536];
                        match f.read(&mut buf) {
                            Ok(n) => {
                                response = String::from_utf8_lossy(&buf[..n]).to_string();
                                Ok(response)
                            }
                            Err(e) => Err(VlmBridgeError::IpcError(e.to_string())),
                        }
                    }
                    Err(_) => Err(VlmBridgeError::SidecarUnavailable),
                }
            }

            #[cfg(not(target_os = "windows"))]
            {
                // Unix domain socket fallback for development/testing
                use std::os::unix::net::UnixStream;

                match UnixStream::connect("/tmp/kairo.sock") {
                    Ok(mut stream) => {
                        stream
                            .write_all(request.as_bytes())
                            .map_err(|e| VlmBridgeError::IpcError(e.to_string()))?;

                        let mut response = String::new();
                        let mut buf = [0u8; 65536];
                        match stream.read(&mut buf) {
                            Ok(n) => {
                                response = String::from_utf8_lossy(&buf[..n]).to_string();
                                Ok(response)
                            }
                            Err(e) => Err(VlmBridgeError::IpcError(e.to_string())),
                        }
                    }
                    Err(_) => Err(VlmBridgeError::SidecarUnavailable),
                }
            }
        })
        .await
        .map_err(|e| VlmBridgeError::IpcError(format!("Task join error: {e}")))?;

        // Apply timeout
        tokio::time::timeout(timeout, async { result })
            .await
            .map_err(|_| VlmBridgeError::Timeout)?
    }
}

/// Convenience function for one-shot VLM availability check
pub async fn vlm_is_available() -> bool {
    VlmBridge::new().is_available().await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vlm_ground_request_serializes() {
        let req = VlmGroundRequest {
            screenshot: "/tmp/screen.png".to_string(),
            description: "Submit button".to_string(),
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("Submit button"));
    }

    #[test]
    fn test_vlm_ground_response_deserializes() {
        let json = r#"{
            "found": true,
            "x": 840,
            "y": 450,
            "confidence": 0.97,
            "description": "Submit button found in bottom-right",
            "latency_ms": 1200.0
        }"#;
        let resp: VlmGroundResponse = serde_json::from_str(json).unwrap();
        assert!(resp.found);
        assert_eq!(resp.x, 840);
        assert_eq!(resp.y, 450);
        assert!((resp.confidence - 0.97).abs() < 0.001);
    }

    #[test]
    fn test_vlm_verify_response_deserializes() {
        let json = r#"{
            "success": true,
            "confidence": 0.95,
            "explanation": "Dialog shows 'File saved' confirmation",
            "latency_ms": 800.0
        }"#;
        let resp: VlmVerifyResponse = serde_json::from_str(json).unwrap();
        assert!(resp.success);
        assert!((resp.confidence - 0.95).abs() < 0.001);
    }

    #[test]
    fn test_vlm_error_display() {
        let err = VlmBridgeError::ModelNotDownloaded { progress: 45.3 };
        let msg = err.to_string();
        assert!(msg.contains("45%"));
        assert!(msg.contains("keyboard-only"));
    }
}
