//! Ollama Bootstrap — P0-A2
//! Silently detects and configures Ollama for offline AI.
//! Called at startup; model pull is non-blocking.

use tokio::time::Duration;

pub struct OllamaBootstrap;

impl OllamaBootstrap {
    /// Returns true if Ollama API is reachable.
    pub async fn is_running() -> bool {
        crate::config::get_client_builder()
            .build()
            .unwrap_or_default()
            .get("http://localhost:11434/api/tags")
            .timeout(Duration::from_secs(2))
            .send()
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false)
    }

    /// Pull a model in the background. Non-blocking — fires and forgets.
    pub async fn ensure_model(model: &str) -> anyhow::Result<()> {
        tracing::info!("🦙 Ensuring Ollama model: {}", model);
        let client = crate::config::get_client_builder()
            .build()
            .unwrap_or_default();
        let body = serde_json::json!({"name": model, "stream": false});
        let resp = client
            .post("http://localhost:11434/api/pull")
            .json(&body)
            .timeout(Duration::from_secs(600))
            .send()
            .await?;
        if resp.status().is_success() {
            tracing::info!("✅ Ollama model '{}' ready", model);
        } else {
            tracing::warn!("⚠️  Model pull returned: {}", resp.status());
        }
        Ok(())
    }

    /// Returns true if the given model is available locally in Ollama.
    pub async fn has_model(model: &str) -> bool {
        let client = match crate::config::get_client_builder().build() {
            Ok(c) => c,
            Err(_) => return false,
        };
        let resp = match client
            .get("http://localhost:11434/api/tags")
            .timeout(Duration::from_secs(2))
            .send()
            .await
        {
            Ok(r) => r,
            Err(_) => return false,
        };
        if !resp.status().is_success() {
            return false;
        }

        #[derive(serde::Deserialize)]
        struct OllamaTags {
            models: Vec<OllamaModel>,
        }
        #[derive(serde::Deserialize)]
        struct OllamaModel {
            name: String,
        }

        if let Ok(tags) = resp.json::<OllamaTags>().await {
            let target_base = model.split(':').next().unwrap_or(model);
            tags.models
                .iter()
                .any(|m| m.name == model || m.name == target_base || m.name.starts_with(model))
        } else {
            false
        }
    }

    /// Full bootstrap: detect → log → pull model in background.
    pub async fn bootstrap(default_model: &str) {
        if std::env::var("KAIRO_OFFLINE").unwrap_or_default() == "1" {
            if Self::is_running().await {
                tracing::info!(
                    "✅ Ollama running locally at http://localhost:11434 (offline mode)"
                );
            }
            return;
        }

        if Self::is_running().await {
            tracing::info!("✅ Ollama running at http://localhost:11434");
            let model = default_model.to_string();
            tokio::spawn(async move {
                if let Err(e) = Self::ensure_model(&model).await {
                    tracing::warn!("⚠️  Model pull failed: {}", e);
                }
            });
        } else {
            tracing::warn!(
                "⚠️  Ollama not detected. For offline AI: winget install Ollama.Ollama && ollama serve"
            );
        }
    }
}
