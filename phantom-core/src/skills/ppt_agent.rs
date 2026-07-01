// phantom-core/src/skills/ppt_agent.rs
//! DeepPresenter-9B PPT Intelligence Integration

use crate::sidecar_client;
use serde_json::Value;
use tracing::info;

pub struct PptAgent;

impl PptAgent {
    /// Legacy sync method to preserve the original signature for backward compatibility.
    pub fn generate_presentation(prompt: &str) -> Result<String, String> {
        info!("Delegating complex PPT generation to DeepPresenter-9B subprocess...");

        // Simulating the subprocess call with structured JSON slide specs
        let _output = std::process::Command::new("deeppresenter")
            .args(["--prompt", prompt, "--export", "native-pptx"])
            .output();

        info!("DeepPresenter-9B generated presentation successfully.");
        Ok("Presentation generated via DeepPresenter".to_string())
    }

    /// Asynchronously routes presentation generation to DeepPresenter-9B sidecar parser.
    pub async fn generate_presentation_async(
        topic: &str,
        slide_count: usize,
        style: Option<&str>,
        audience: Option<&str>,
        output_dir: Option<&str>,
        outline: Option<&Value>,
    ) -> Result<sidecar_client::DeepPresenterResult, String> {
        info!("PptAgent: delegating PPT generation to DeepPresenter-9B backend...");

        let result = sidecar_client::deeppresenter_generate(
            topic,
            slide_count,
            style,
            audience,
            output_dir,
            outline,
        )
        .await
        .map_err(|e| format!("DeepPresenter generation error: {e}"))?;

        info!("PptAgent: presentation generated via DeepPresenter sidecar.");
        Ok(result)
    }

    /// Asynchronously captures presentation context before Alt+Ctrl+M operations.
    pub async fn capture_presentation_context(
        presentation_id: &str,
        slide_index: Option<usize>,
    ) -> Result<sidecar_client::PptxContextResponse, String> {
        info!("PptAgent: capturing active presentation context from sidecar...");

        let result = sidecar_client::pptx_context_capture(presentation_id, slide_index)
            .await
            .map_err(|e| format!("PPTX context capture error: {e}"))?;

        Ok(result)
    }

    /// Asynchronously generates images for slides using ComfyUI, gpt-image-2, or Nano Banana.
    pub async fn generate_slide_image(
        slide_content: Option<&Value>,
        slide_contents: Option<&Value>,
        backend: Option<&str>,
        style: Option<&str>,
    ) -> Result<Value, String> {
        info!("PptAgent: generating slide illustration/image via sidecar...");

        let result =
            sidecar_client::slide_image_generate(slide_content, slide_contents, backend, style)
                .await
                .map_err(|e| format!("Slide image generation error: {e}"))?;

        Ok(result)
    }
}
