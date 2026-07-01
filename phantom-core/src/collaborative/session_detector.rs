/// Detects Yjs‑powered collaborative sessions from active application context.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollaborativeSession {
    pub app_name: String,
    pub doc_id: String,
    pub sync_endpoint: Option<String>,
    pub provider_type: SyncProviderType,
    pub detected: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SyncProviderType {
    WebSocket, // y-websocket, hocuspocus
    WebRTC,    // y-webrtc (P2P)
    YSweet,    // y-sweet (S3-persisted)
    Local,     // Local document (no sync)
    Unknown,
}

impl CollaborativeSession {
    /// Detect if the active application is a Yjs‑powered collaborative
    /// session and extract document ID and sync endpoint.
    pub async fn detect(window_title: &str, browser_url: Option<&str>) -> Option<Self> {
        // Google Docs
        if let Some(url) = browser_url {
            if url.contains("docs.google.com/document/d/") {
                let doc_id = extract_google_doc_id(url);
                return Some(CollaborativeSession {
                    app_name: "Google Docs".into(),
                    doc_id,
                    sync_endpoint: None, // Google Docs uses its own sync
                    provider_type: SyncProviderType::WebSocket,
                    detected: true,
                });
            }
        }

        // Notion
        if window_title.contains("Notion") || browser_url.is_some_and(|u| u.contains("notion.so")) {
            let doc_id = extract_notion_page_id(window_title, browser_url);
            return Some(CollaborativeSession {
                app_name: "Notion".into(),
                doc_id,
                sync_endpoint: None,
                provider_type: SyncProviderType::WebSocket,
                detected: true,
            });
        }

        // Tiptap / Hocuspocus editors
        if let Some(url) = browser_url {
            // Detect y-websocket or hocuspocus provider in page
            // via JavaScript injection or URL pattern
            if let Some(endpoint) = detect_ws_provider(url) {
                return Some(CollaborativeSession {
                    app_name: "Tiptap Collaborative Editor".into(),
                    doc_id: generate_doc_id(url),
                    sync_endpoint: Some(endpoint),
                    provider_type: SyncProviderType::WebSocket,
                    detected: true,
                });
            }
        }

        // AFFiNE
        if window_title.contains("AFFiNE") {
            return Some(CollaborativeSession {
                app_name: "AFFiNE".into(),
                doc_id: extract_affine_doc_id(window_title),
                sync_endpoint: None,
                provider_type: SyncProviderType::WebSocket,
                detected: true,
            });
        }

        // Etherpad
        if let Some(url) = browser_url {
            if url.contains("/p/") {
                return Some(CollaborativeSession {
                    app_name: "Etherpad".into(),
                    doc_id: extract_etherpad_pad_id(url),
                    sync_endpoint: None,
                    provider_type: SyncProviderType::WebSocket,
                    detected: true,
                });
            }
        }

        // Penpot (design collaboration)
        if window_title.contains("Penpot") {
            return Some(CollaborativeSession {
                app_name: "Penpot".into(),
                doc_id: extract_penpot_file_id(window_title),
                sync_endpoint: Some("ws://localhost:4400/ws".into()),
                provider_type: SyncProviderType::WebSocket,
                detected: true,
            });
        }

        None
    }
}

// Helper functions (platform‑specific implementations needed):
pub fn extract_google_doc_id(url: &str) -> String {
    if let Some(pos) = url.find("document/d/") {
        let remaining = &url[pos + 11..];
        if let Some(end) = remaining.find('/') {
            return remaining[..end].to_string();
        }
        return remaining.to_string();
    }
    "default_doc".to_string()
}

pub fn extract_notion_page_id(title: &str, url: Option<&str>) -> String {
    if let Some(u) = url {
        if let Some(last_slash) = u.rfind('/') {
            let end = &u[last_slash + 1..];
            if let Some(query) = end.find('?') {
                return end[..query].to_string();
            }
            return end.to_string();
        }
    }
    title.replace(' ', "-").to_lowercase()
}

pub fn extract_affine_doc_id(title: &str) -> String {
    title.replace(' ', "-").to_lowercase()
}

pub fn extract_etherpad_pad_id(url: &str) -> String {
    if let Some(pos) = url.find("/p/") {
        let remaining = &url[pos + 3..];
        if let Some(end) = remaining.find('/') {
            return remaining[..end].to_string();
        }
        return remaining.to_string();
    }
    "default_pad".to_string()
}

pub fn extract_penpot_file_id(title: &str) -> String {
    title.replace(' ', "-").to_lowercase()
}

pub fn detect_ws_provider(url: &str) -> Option<String> {
    if url.contains("tiptap.dev") || url.contains("collab.tiptap.dev") {
        return Some("wss://collab.tiptap.dev".to_string());
    }
    None
}

pub fn generate_doc_id(url: &str) -> String {
    if let Some(pos) = url.rfind('/') {
        return url[pos + 1..].to_string();
    }
    "tiptap_doc".to_string()
}
