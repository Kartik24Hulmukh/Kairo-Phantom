// phantom-core/src/pipeline.rs

use crate::document_context::DocumentContext;
use enigo::{Enigo, Keyboard, Settings};
use futures_util::StreamExt;
use reqwest::Client;
use std::time::Duration;
use tokio::time::sleep;
use tokio_util::sync::CancellationToken;

/// Manages pre-warmed connections for sub-100ms LLM latency.
pub struct HotkeyPipeline {
    client: Client,
    endpoint: String,
}

impl HotkeyPipeline {
    pub fn new(endpoint: String) -> Self {
        // Pre-warm TCP pool: keep-alive prevents TLS handshake on hotkey press
        let client = Client::builder()
            .pool_idle_timeout(Duration::from_secs(300))
            .pool_max_idle_per_host(10)
            .tcp_keepalive(Duration::from_secs(60))
            .build()
            .expect("Failed to build HTTP client");

        Self { client, endpoint }
    }

    /// Pre-warm by sending a dummy HEAD or generic request (fire and forget)
    pub async fn prewarm(&self) {
        let _ = self.client.get(&self.endpoint).send().await;
    }

    /// Parallel context capture and API request setup using tokio::join!
    pub async fn parallel_capture_and_request(
        &self,
        prompt: String,
        cancel_token: CancellationToken,
    ) -> Result<(), String> {
        // Run UIA capture and LLM request concurrently
        let (capture_result, request_result) = tokio::join!(
            Self::capture_context_lazy(&prompt),
            self.initiate_stream(prompt.clone(), cancel_token.clone())
        );

        let mut stream = request_result?;
        let _context = capture_result?;

        let mut injector = StreamInjector::new();

        // Process stream
        while let Some(chunk) = stream.next().await {
            if cancel_token.is_cancelled() {
                break;
            }
            if let Ok(chunk_bytes) = chunk {
                let text = String::from_utf8_lossy(&chunk_bytes).to_string();
                injector.inject_chunk(&text).await;
            }
        }

        injector.flush().await;
        Ok(())
    }

    pub async fn capture_context_lazy(prompt: &str) -> Result<DocumentContext, String> {
        let (app_name, window_title) = crate::context::ContextEngine::new().get_active_app_info();
        let reader = crate::platform::new_reader();

        // 1. UIA fallback
        if let Ok(uia_text) = reader.get_focused_text() {
            let uia_trimmed = uia_text.trim();
            // Check if VS Code returned its inaccessibility warning
            let is_inaccessible = ["VS Code", "accessibility", "Screen Reader", "VSCode"]
                .iter()
                .any(|s| uia_trimmed.contains(s));
            if !uia_trimmed.is_empty() && !is_inaccessible {
                tracing::info!("📖 UIA read: {} chars", uia_trimmed.len());
                let mut ctx = DocumentContext::from_plain_text(&app_name, &uia_text, prompt);
                ctx.app_name = Some(app_name.clone());
                return Ok(ctx);
            }
        }

        // 2. Clipboard fallback
        if let Ok(clip_text) = reader.get_clipboard_text() {
            let clip_trimmed = clip_text.trim();
            if !clip_trimmed.is_empty() {
                tracing::info!("📋 Clipboard read: {} chars", clip_trimmed.len());
                let mut ctx = DocumentContext::from_plain_text(&app_name, &clip_text, prompt);
                ctx.app_name = Some(app_name.clone());
                return Ok(ctx);
            }
        }

        // 3. Screenshot OCR fallback
        let ocr_config = crate::config::ScreenContextConfig::default();
        let ocr_engine = crate::screen_context::ScreenContextEngine::new(ocr_config);
        if let Ok(screen_ctx) = ocr_engine
            .capture_and_extract(&app_name, &window_title)
            .await
        {
            let ocr_trimmed = screen_ctx.vasp_output.trim();
            if !ocr_trimmed.is_empty() {
                tracing::info!("📸 Screenshot OCR read: {} chars", ocr_trimmed.len());
                let mut ctx =
                    DocumentContext::from_plain_text(&app_name, &screen_ctx.vasp_output, prompt);
                ctx.app_name = Some(app_name.clone());
                return Ok(ctx);
            }
        }

        // 4. Prompt-only fallback
        if !prompt.trim().is_empty() {
            tracing::info!("📝 Prompt-only fallback used");
            let mut ctx = DocumentContext::from_plain_text(&app_name, prompt, prompt);
            ctx.app_name = Some(app_name.clone());
            return Ok(ctx);
        }

        // Total failure
        crate::toast_notification::show_error_toast(
            "Kairo context capture failed. Please make sure target app is active.",
        );
        Err("Total context capture failure".to_string())
    }

    async fn initiate_stream(
        &self,
        prompt: String,
        cancel_token: CancellationToken,
    ) -> Result<impl futures_util::Stream<Item = reqwest::Result<bytes::Bytes>>, String> {
        let request = self.client.post(&self.endpoint).json(&serde_json::json!({
            "prompt": prompt,
            "stream": true
        }));

        let response = request.send().await.map_err(|e| e.to_string())?;
        Ok(response.bytes_stream())
    }
}

/// Batches keystrokes into 5-character chunks with a 16ms delay.
pub struct StreamInjector {
    enigo: Enigo,
    buffer: String,
}

impl Default for StreamInjector {
    fn default() -> Self {
        Self::new()
    }
}

impl StreamInjector {
    pub fn new() -> Self {
        Self {
            enigo: Enigo::new(&Settings::default()).expect("Failed to initialize Enigo"),
            buffer: String::new(),
        }
    }

    pub async fn inject_chunk(&mut self, text: &str) {
        self.buffer.push_str(text);

        while self.buffer.len() >= 5 {
            let chunk: String = self.buffer.drain(..5).collect();
            let _ = self.enigo.text(&chunk);
            sleep(Duration::from_millis(16)).await;
        }
    }

    pub async fn flush(&mut self) {
        if !self.buffer.is_empty() {
            let _ = self.enigo.text(&self.buffer);
            self.buffer.clear();
        }
    }
}
