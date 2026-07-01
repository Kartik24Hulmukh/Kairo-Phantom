/// Image Pipeline v1.0 — Phase 1 of Kairo Phantom v3.0
/// Implements: gpt-image-1 (OpenAI), Ollama Diffuser (local SD/FLUX), ImageRouter
/// The ImageRouter selects the best backend based on document context and offline preferences.
use anyhow::{Context, Result};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use crate::document_context::{DocKind, DocumentContext};

// ─── ImageResult ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct ImageResult {
    /// Base64-encoded PNG/JPEG data (without data URI prefix)
    pub base64_data: String,
    /// MIME type (image/png or image/jpeg)
    pub mime_type: String,
    /// The enhanced prompt actually used
    pub prompt_used: String,
    /// Which backend generated it
    pub backend_used: String,
}

impl ImageResult {
    /// Returns the raw bytes of the image
    pub fn decode_bytes(&self) -> Result<Vec<u8>> {
        BASE64
            .decode(&self.base64_data)
            .context("Failed to decode image base64")
    }

    /// Returns a data URI suitable for HTML/CSS embedding
    pub fn as_data_uri(&self) -> String {
        format!("data:{};base64,{}", self.mime_type, self.base64_data)
    }
}

// ─── ImageSize Config ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageGenerationConfig {
    /// OpenAI API key (for gpt-image-1)
    pub openai_api_key: Option<String>,
    /// Ollama base URL (for local SD/FLUX)
    pub ollama_base_url: Option<String>,
    /// Force offline-only (never call cloud APIs)
    pub offline_only: bool,
    /// Image size for cloud generation
    pub image_size: String,
    /// Image quality for cloud generation
    pub image_quality: String,
}

impl Default for ImageGenerationConfig {
    fn default() -> Self {
        Self {
            openai_api_key: None,
            ollama_base_url: Some("http://localhost:11434".into()),
            offline_only: false,
            image_size: "1024x1024".into(),
            image_quality: "standard".into(),
        }
    }
}

// ─── OpenAI Image Backend (gpt-image-1) ──────────────────────────────────────

pub struct OpenAiImageBackend {
    client: Client,
    api_key: String,
    /// "gpt-image-1" or "gpt-image-1-mini"
    model: String,
    size: String,
    quality: String,
}

#[derive(Serialize)]
struct OpenAiImageRequest<'a> {
    model: &'a str,
    prompt: &'a str,
    n: u32,
    size: &'a str,
    quality: &'a str,
    response_format: &'a str,
}

#[derive(Deserialize)]
struct OpenAiImageResponse {
    data: Vec<OpenAiImageData>,
}

#[derive(Deserialize)]
struct OpenAiImageData {
    b64_json: Option<String>,
    url: Option<String>,
}

impl OpenAiImageBackend {
    pub fn new(api_key: String, model: String, size: String, quality: String) -> Self {
        Self {
            client: Client::builder()
                .timeout(std::time::Duration::from_secs(120))
                .build()
                .unwrap_or_default(),
            api_key,
            model,
            size,
            quality,
        }
    }

    pub async fn generate(&self, prompt: &str) -> Result<ImageResult> {
        info!(
            "🎨 OpenAI Image ({}) generating: {}...",
            self.model,
            &prompt[..prompt.len().min(60)]
        );

        let req = OpenAiImageRequest {
            model: &self.model,
            prompt,
            n: 1,
            size: &self.size,
            quality: &self.quality,
            response_format: "b64_json",
        };

        let resp = self
            .client
            .post("https://api.openai.com/v1/images/generations")
            .bearer_auth(&self.api_key)
            .json(&req)
            .send()
            .await
            .context("OpenAI Image API request failed")?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("OpenAI Image API error {status}: {body}");
        }

        let data: OpenAiImageResponse = resp
            .json()
            .await
            .context("Failed to parse OpenAI image response")?;

        let b64 = data
            .data
            .into_iter()
            .next()
            .and_then(|d| d.b64_json)
            .context("No image data in OpenAI response")?;

        info!("✅ OpenAI Image generated ({} bytes b64)", b64.len());

        Ok(ImageResult {
            base64_data: b64,
            mime_type: "image/png".into(),
            prompt_used: prompt.to_string(),
            backend_used: self.model.clone(),
        })
    }
}

// ─── Ollama Diffuser Backend (Local Stable Diffusion / FLUX) ─────────────────

pub struct OllamaDiffuserBackend {
    client: Client,
    base_url: String,
    model: String,
}

#[derive(Serialize)]
struct OllamaGenerateRequest<'a> {
    model: &'a str,
    prompt: &'a str,
    stream: bool,
}

#[derive(Deserialize)]
struct OllamaGenerateResponse {
    #[serde(default)]
    images: Vec<String>,
    #[serde(default)]
    response: String,
}

impl OllamaDiffuserBackend {
    pub fn new(base_url: String, model: String) -> Self {
        Self {
            client: Client::builder()
                .timeout(std::time::Duration::from_secs(300)) // SD is slow locally
                .build()
                .unwrap_or_default(),
            base_url,
            model,
        }
    }

    pub async fn generate(&self, prompt: &str) -> Result<ImageResult> {
        info!(
            "🖼️  Ollama Diffuser ({}) generating locally: {}...",
            self.model,
            &prompt[..prompt.len().min(60)]
        );

        let req = OllamaGenerateRequest {
            model: &self.model,
            prompt,
            stream: false,
        };

        let url = format!("{}/api/generate", self.base_url);
        let resp = self
            .client
            .post(&url)
            .json(&req)
            .send()
            .await
            .context("Ollama Diffuser request failed")?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Ollama Diffuser error {status}: {body}");
        }

        let data: OllamaGenerateResponse = resp
            .json()
            .await
            .context("Failed to parse Ollama response")?;

        // Ollama image models return images in the `images` array
        let b64 = data
            .images
            .into_iter()
            .next()
            .context("No image in Ollama response (is this a vision-capable model?)")?;

        info!("✅ Ollama Diffuser generated ({} bytes b64)", b64.len());

        Ok(ImageResult {
            base64_data: b64,
            mime_type: "image/png".into(),
            prompt_used: prompt.to_string(),
            backend_used: format!("ollama/{}", self.model),
        })
    }

    pub async fn health_check(&self) -> bool {
        let url = format!("{}/api/tags", self.base_url);
        self.client
            .get(&url)
            .timeout(std::time::Duration::from_secs(3))
            .send()
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false)
    }
}

// ─── ImageRouter — Context-Aware Routing ─────────────────────────────────────

pub struct ImageRouter {
    cloud_hq: Option<OpenAiImageBackend>, // gpt-image-1 (high quality)
    cloud_mini: Option<OpenAiImageBackend>, // gpt-image-1-mini (fast/cheap)
    local: Option<OllamaDiffuserBackend>, // Ollama SD/FLUX
    config: ImageGenerationConfig,
}

impl ImageRouter {
    pub fn new(config: ImageGenerationConfig) -> Self {
        let cloud_hq = config
            .openai_api_key
            .as_deref()
            .filter(|k| !k.is_empty())
            .map(|key| {
                OpenAiImageBackend::new(
                    key.to_string(),
                    "gpt-image-1".into(),
                    config.image_size.clone(),
                    config.image_quality.clone(),
                )
            });

        let cloud_mini = config
            .openai_api_key
            .as_deref()
            .filter(|k| !k.is_empty())
            .map(|key| {
                OpenAiImageBackend::new(
                    key.to_string(),
                    "gpt-image-1-mini".into(),
                    "512x512".into(),
                    "standard".into(),
                )
            });

        let local = config.ollama_base_url.as_deref().map(|url| {
            OllamaDiffuserBackend::new(
                url.to_string(),
                "stable-diffusion".into(), // or "flux", configurable
            )
        });

        Self {
            cloud_hq,
            cloud_mini,
            local,
            config,
        }
    }

    /// Build a context-enriched prompt from the document context.
    fn enhance_prompt(&self, prompt: &str, ctx: &DocumentContext) -> String {
        let context_hint = match ctx.doc_kind {
            DocKind::PowerPoint | DocKind::OpenDocumentPresentation => {
                if ctx.active_slide == Some(0) {
                    "Professional title slide hero image. High impact, corporate. "
                } else {
                    "Professional presentation slide illustration. Clean, modern, corporate. "
                }
            }
            DocKind::WordDocument | DocKind::OpenDocumentText => {
                "Professional document illustration. Subtle, editorial, high resolution. "
            }
            DocKind::FigmaDesign | DocKind::CanvaDesign => {
                "Modern UI/UX illustration. Clean design. Flat or minimal style. "
            }
            _ => "",
        };

        format!("{context_hint}{prompt}")
    }

    /// Generate an image, routing to the best available backend.
    pub async fn generate(&self, prompt: &str, ctx: &DocumentContext) -> Result<ImageResult> {
        let enhanced = self.enhance_prompt(prompt, ctx);
        debug!(
            "ImageRouter: enhanced prompt = {}",
            &enhanced[..enhanced.len().min(100)]
        );

        // RULE: Offline-only → always use local
        if self.config.offline_only {
            return self.local_generate(&enhanced).await;
        }

        // RULE: Title slide (slide 0) → use best cloud model
        if matches!(
            ctx.doc_kind,
            DocKind::PowerPoint | DocKind::OpenDocumentPresentation
        ) && ctx.active_slide == Some(0)
        {
            if let Some(cloud) = &self.cloud_hq {
                match cloud.generate(&enhanced).await {
                    Ok(r) => return Ok(r),
                    Err(e) => warn!("Cloud HQ failed: {} — falling back to local", e),
                }
            }
        }

        // RULE: Quick icon/thumbnail → use mini
        let is_icon =
            prompt.contains("icon") || prompt.contains("logo") || prompt.contains("thumbnail");
        if is_icon {
            if let Some(mini) = &self.cloud_mini {
                match mini.generate(&enhanced).await {
                    Ok(r) => return Ok(r),
                    Err(e) => warn!("Cloud mini failed: {} — falling back to local", e),
                }
            }
        }

        // DEFAULT: Try local first, cloud HQ as fallback
        match self.local_generate(&enhanced).await {
            Ok(r) => Ok(r),
            Err(local_err) => {
                warn!(
                    "Local generation failed: {} — trying cloud fallback",
                    local_err
                );
                if let Some(cloud) = &self.cloud_hq {
                    cloud.generate(&enhanced).await
                } else if let Some(mini) = &self.cloud_mini {
                    mini.generate(&enhanced).await
                } else {
                    Err(local_err)
                        .context("All image backends failed and no cloud fallback configured")
                }
            }
        }
    }

    async fn local_generate(&self, prompt: &str) -> Result<ImageResult> {
        if let Some(local) = &self.local {
            local.generate(prompt).await
        } else {
            anyhow::bail!("No local image backend configured")
        }
    }

    /// Check if any backend is available
    pub async fn is_available(&self) -> bool {
        if !self.config.offline_only && (self.cloud_hq.is_some() || self.cloud_mini.is_some()) {
            return true;
        }
        if let Some(local) = &self.local {
            return local.health_check().await;
        }
        false
    }
}

// ─── Gemini Imagen 3 Backend ──────────────────────────────────────────────────

pub struct GeminiImagenBackend {
    client: Client,
    api_key: String,
    model: String,
}

impl GeminiImagenBackend {
    pub fn new(api_key: String, fast: bool) -> Self {
        Self {
            client: Client::builder()
                .timeout(std::time::Duration::from_secs(90))
                .build()
                .unwrap_or_default(),
            api_key,
            model: if fast {
                "imagen-3.0-fast-generate-001".into()
            } else {
                "imagen-3.0-generate-002".into()
            },
        }
    }

    pub async fn generate(&self, prompt: &str) -> Result<ImageResult> {
        info!(
            "🎨 Gemini Imagen ({}) generating: {}...",
            self.model,
            &prompt[..prompt.len().min(60)]
        );
        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:predict?key={}",
            self.model, self.api_key
        );

        let body = serde_json::json!({
            "instances": [{ "prompt": prompt }],
            "parameters": { "sampleCount": 1 }
        });

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .context("Gemini Imagen request failed")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Gemini Imagen error {status}: {body}");
        }

        let json: serde_json::Value = resp.json().await.context("Gemini Imagen parse failed")?;

        let b64 = json["predictions"][0]["bytesBase64Encoded"]
            .as_str()
            .context("No image data in Gemini Imagen response")?
            .to_string();

        info!("✅ Gemini Imagen generated ({} bytes b64)", b64.len());
        Ok(ImageResult {
            base64_data: b64,
            mime_type: "image/png".into(),
            prompt_used: prompt.to_string(),
            backend_used: format!("gemini-{}", self.model),
        })
    }
}

// ─── Clipboard Image Injector ─────────────────────────────────────────────────

/// Copy generated images to Windows clipboard or macOS pbcopy so the user
/// can Ctrl+V into Word, PowerPoint, Figma, Canva, Google Slides — any app.
pub struct ClipboardImageInjector;

impl ClipboardImageInjector {
    /// Write raw bytes to a deterministic temp file path. Returns the path.
    pub fn write_to_temp_file(image_result: &ImageResult) -> Result<std::path::PathBuf> {
        let bytes = image_result.decode_bytes()?;
        let ext = if image_result.mime_type.contains("jpeg") {
            "jpg"
        } else {
            "png"
        };
        let path = std::env::temp_dir().join(format!("kairo_generated_image.{ext}"));
        std::fs::write(&path, &bytes)?;
        info!("🖼️  Image written to temp: {:?}", path);
        Ok(path)
    }

    /// Copy image to clipboard via PowerShell (Windows — no extra native deps).
    #[cfg(target_os = "windows")]
    pub fn copy_to_clipboard(image_result: &ImageResult) -> Result<()> {
        let path = Self::write_to_temp_file(image_result)?;
        let path_str = path.to_string_lossy().replace('\'', "''");
        let script = format!(
            "Add-Type -AssemblyName System.Windows.Forms; \
             [System.Windows.Forms.Clipboard]::SetImage(\
             [System.Drawing.Image]::FromFile('{path_str}'))"
        );
        let status = std::process::Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", &script])
            .status()
            .context("PowerShell clipboard copy failed")?;
        if status.success() {
            info!("📋 Image copied to clipboard via PowerShell");
        } else {
            warn!("⚠️  PowerShell clipboard returned non-zero; temp file still available");
        }
        Ok(())
    }

    #[cfg(not(target_os = "windows"))]
    pub fn copy_to_clipboard(image_result: &ImageResult) -> Result<()> {
        let path = Self::write_to_temp_file(image_result)?;
        let p = path.to_string_lossy();
        let script = format!(
            "osascript -e 'set the clipboard to (read (POSIX file \"{p}\") as PNG picture)'"
        );
        std::process::Command::new("sh")
            .arg("-c")
            .arg(&script)
            .status()
            .ok();
        info!("📋 Image copied to macOS clipboard");
        Ok(())
    }

    /// Write image to clipboard as plain PNG path (fallback for Linux via xclip)
    #[cfg(target_os = "linux")]
    pub fn copy_to_clipboard_linux(image_result: &ImageResult) -> Result<()> {
        let path = Self::write_to_temp_file(image_result)?;
        let p = path.to_string_lossy();
        std::process::Command::new("sh")
            .arg("-c")
            .arg(format!("xclip -selection clipboard -t image/png < '{p}'"))
            .status()
            .ok();
        Ok(())
    }
}

// ─── Word Image Injector (python-docx) ───────────────────────────────────────

/// Insert a generated image into a .docx at the end, or at cursor, via python-docx.
pub struct WordImageInjector;

impl WordImageInjector {
    /// Append image to the end of a Word document using python-docx.
    pub fn inject_into_docx(docx_path: &str, image_path: &str, width_cm: f32) -> Result<()> {
        let script = format!(
            "from docx import Document; from docx.shared import Cm; import sys\n\
             doc = Document(r'{docx_path}')\n\
             doc.add_picture(r'{image_path}', width=Cm({width_cm}))\n\
             doc.save(r'{docx_path}')\n\
             print('OK')"
        );
        let tmp = std::env::temp_dir().join("kairo_inject_word_img.py");
        std::fs::write(&tmp, &script)?;
        let out = std::process::Command::new("python")
            .arg(&tmp)
            .output()
            .context("python not found — install Python and python-docx")?;
        if out.status.success() {
            info!("📄 Image injected into Word: {}", docx_path);
            Ok(())
        } else {
            let e = String::from_utf8_lossy(&out.stderr);
            Err(anyhow::anyhow!("Word injection failed: {e}"))
        }
    }
}

// ─── generate_and_inject: smart dispatcher ───────────────────────────────────

impl ImageRouter {
    /// Generate image then automatically inject via the best method for the doc kind.
    ///
    /// Returns `(ImageResult, injection_method_label)` for logging/telemetry.
    pub async fn generate_and_inject(
        &self,
        prompt: &str,
        context: &DocumentContext,
        docx_path: Option<&str>,
    ) -> Result<(ImageResult, String)> {
        let result = self.generate(prompt, context).await?;

        let method = match context.doc_kind {
            DocKind::WordDocument => {
                if let Some(path) = docx_path {
                    let img = ClipboardImageInjector::write_to_temp_file(&result)?;
                    WordImageInjector::inject_into_docx(path, &img.to_string_lossy(), 14.0).ok();
                    "word-python-docx".into()
                } else {
                    ClipboardImageInjector::copy_to_clipboard(&result).ok();
                    "clipboard".into()
                }
            }
            DocKind::PowerPoint | DocKind::OpenDocumentPresentation => {
                // Write temp file (pptx bridge picks it up) AND copy to clipboard
                ClipboardImageInjector::write_to_temp_file(&result).ok();
                ClipboardImageInjector::copy_to_clipboard(&result).ok();
                "clipboard+temp-file".into()
            }
            DocKind::FigmaDesign | DocKind::CanvaDesign => {
                // Return base64 for MCP bridge — no clipboard needed
                "mcp-figma-base64".into()
            }
            _ => {
                ClipboardImageInjector::copy_to_clipboard(&result).ok();
                "clipboard".into()
            }
        };

        info!("🚀 Image inject method: {}", method);
        Ok((result, method))
    }
}

// ─── Legacy write_image_to_clipboard shim ────────────────────────────────────

#[cfg(windows)]
pub fn write_image_to_clipboard(png_bytes: &[u8]) -> Result<()> {
    let tmp_path = std::env::temp_dir().join("kairo_generated_image.png");
    std::fs::write(&tmp_path, png_bytes)?;
    info!(
        "Image staged at: {} — use Insert > Image in your app",
        tmp_path.display()
    );
    Ok(())
}

#[cfg(not(windows))]
pub fn write_image_to_clipboard(_png_bytes: &[u8]) -> Result<()> {
    anyhow::bail!("write_image_to_clipboard: use ClipboardImageInjector instead")
}
