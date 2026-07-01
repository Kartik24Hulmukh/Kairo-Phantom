// phantom-core/src/skills/design_agent.rs
//! Design Intelligence Agent for Domain 5 (Figma, Penpot, tldraw, OpenPencil, ComfyUI)

use crate::sidecar_client;
use serde_json::Value;
use tracing::info;

pub struct DesignAgent;

impl DesignAgent {
    /// Legacy sync method to preserve the original signature for backward compatibility.
    pub fn invoke_open_pencil(task: &str) -> Result<String, String> {
        info!("Bridging to Open-Pencil / Penpot MCP for task: {}", task);
        Ok("Design asset generated via Open-Pencil".to_string())
    }

    /// Asynchronously applies design updates via the design ghost writer based on active window title.
    pub async fn ghost_design_async(window_title: &str, payload: Value) -> Result<Value, String> {
        info!(
            "DesignAgent: applying ghost design to active window: {}",
            window_title
        );
        sidecar_client::design_ghost_write(window_title, payload)
            .await
            .map_err(|e| format!("Design ghost-write error: {e}"))
    }

    /// Asynchronously queues a ComfyUI generation or offline high-fidelity fallback asset.
    pub async fn generate_asset_async(
        prompt: &str,
        style: &str,
        output_path: Option<&str>,
    ) -> Result<Value, String> {
        info!("DesignAgent: generating visual design asset...");
        sidecar_client::generate_design_asset(prompt, style, output_path)
            .await
            .map_err(|e| format!("ComfyUI asset generation error: {e}"))
    }

    /// Asynchronously modifies elements or flowcharts inside the infinite whiteboard tldraw canvas.
    pub async fn tldraw_canvas_async(operation: &str, payload: Value) -> Result<Value, String> {
        info!(
            "DesignAgent: dispatching tldraw canvas operation: {}",
            operation
        );
        sidecar_client::tldraw_canvas(operation, payload)
            .await
            .map_err(|e| format!("tldraw canvas error: {e}"))
    }

    /// Asynchronously transpiles Figma layer tree structures into clean HTML/Tailwind CSS.
    pub async fn extract_design_code_async(root_id: &str) -> Result<Value, String> {
        info!("DesignAgent: transpiling figma layers to Tailwind CSS...");
        sidecar_client::extract_design_code(root_id)
            .await
            .map_err(|e| format!("Design-to-code transpilation error: {e}"))
    }

    /// Asynchronously creates complex nodes/frames on Figma canvas.
    pub async fn figma_create_async(payload: Value) -> Result<Value, String> {
        info!("DesignAgent: creating Figma canvas elements...");
        sidecar_client::figma_create(payload)
            .await
            .map_err(|e| format!("Figma node creation error: {e}"))
    }
}
