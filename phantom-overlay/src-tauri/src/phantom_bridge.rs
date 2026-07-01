//! PhantomBridge — connects the Tauri overlay to the phantom-core engine
//! via HTTP IPC on localhost:7437 (the phantom-core daemon port)

use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};

const PHANTOM_PORT: u16 = 7437;

#[derive(Serialize)]
struct MaterializeRequest {
    context: Option<String>,
}

#[derive(Deserialize)]
struct MaterializeResponse {
    suggestion: String,
    #[allow(dead_code)]
    word_count: usize,
}

pub struct PhantomBridge;

impl PhantomBridge {
    /// Call phantom-core to read UIA, get AI suggestion, and ghost-type it
    pub async fn materialize() -> Result<String> {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()?;

        let resp = client
            .post(format!("http://127.0.0.1:{PHANTOM_PORT}/materialize"))
            .json(&MaterializeRequest { context: None })
            .send()
            .await?
            .json::<MaterializeResponse>()
            .await?;

        Ok(resp.suggestion)
    }

    /// Ping phantom-core to check if it's running
    #[allow(dead_code)]
    pub async fn ping() -> bool {
        let client = Client::new();
        client
            .get(format!("http://127.0.0.1:{PHANTOM_PORT}/health"))
            .timeout(std::time::Duration::from_secs(1))
            .send()
            .await
            .is_ok()
    }
}
