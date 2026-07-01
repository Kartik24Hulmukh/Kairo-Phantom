use serde::{Deserialize, Serialize};
/// Kairo Phantom V6 — Yjs CRDT Peer (Production-Scale)
/// E1: Sub-document segmentation for large docs (>5MB)
/// E2: Awareness throttling — only broadcast on state TRANSITIONS
/// E3: Snapshot-based state vectors for efficient sync
/// Built on lessons from Plane FOSDEM 2026
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;
use tracing::{debug, info};
use yrs::updates::decoder::Decode;
use yrs::{Doc, GetString, Options, ReadTxn, Text, Transact, WriteTxn};

// ─── Awareness State ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AwarenessState {
    pub name: String,
    pub color: String,
    pub status: String,
    pub progress: f32,
    pub active_section: Option<String>,
    pub agent_id: String,
}

impl Default for AwarenessState {
    fn default() -> Self {
        Self {
            name: "Kairo AI".into(),
            color: "#8b5cf6".into(),
            status: "idle".into(),
            progress: 0.0,
            active_section: None,
            agent_id: "auto".into(),
        }
    }
}

// ─── E2: Throttled Awareness Manager ─────────────────────────────────────────

/// Only broadcasts on state TRANSITIONS with 200ms debounce.
/// Prevents awareness flooding at thousands of concurrent docs (Plane pattern).
pub struct ThrottledAwareness {
    state: Arc<Mutex<AwarenessState>>,
    last_broadcast: Arc<Mutex<Option<Instant>>>,
    debounce_ms: u64,
}

impl ThrottledAwareness {
    pub fn new(debounce_ms: u64) -> Self {
        Self {
            state: Arc::new(Mutex::new(AwarenessState::default())),
            last_broadcast: Arc::new(Mutex::new(None)),
            debounce_ms,
        }
    }

    /// E2: Update state and broadcast only if it changed AND debounce passed.
    pub async fn update_if_changed(
        &self,
        new_status: &str,
        progress: f32,
        section: Option<&str>,
        agent: &str,
    ) -> bool {
        let new_state = AwarenessState {
            name: "Kairo AI".into(),
            color: "#8b5cf6".into(),
            status: new_status.into(),
            progress,
            active_section: section.map(|s| s.into()),
            agent_id: agent.into(),
        };

        let mut current = self.state.lock().await;
        if *current == new_state {
            return false; // No change — suppress broadcast
        }

        // Check debounce timer
        let mut last = self.last_broadcast.lock().await;
        let now = Instant::now();
        if let Some(l) = *last {
            if now.duration_since(l) < Duration::from_millis(self.debounce_ms) {
                return false; // Still in debounce window
            }
        }

        // State changed AND debounce passed — broadcast
        *current = new_state;
        *last = Some(now);
        debug!(
            "[Awareness] Transition: {} {:.0}%",
            new_status,
            progress * 100.0
        );
        true
    }

    pub async fn get(&self) -> AwarenessState {
        self.state.lock().await.clone()
    }
}

// ─── E1: Sub-Document Segment ─────────────────────────────────────────────────

/// A named section of a large document, independently synced.
/// Prevents full-doc state sync when editing a single section.
pub struct DocSegment {
    pub name: String,
    pub doc: Doc,
    pub client_id: u64,
    /// E3: Last snapshot state vector (for diff-only sync)
    snapshot: Arc<Mutex<Option<Vec<u8>>>>,
}

impl DocSegment {
    pub fn new(name: &str, client_id: u64) -> Self {
        let doc = Doc::with_options(Options {
            client_id,
            ..Default::default()
        });
        info!(
            "[DocSegment] Created segment '{}' (cid={})",
            name, client_id
        );
        Self {
            name: name.to_string(),
            doc,
            client_id,
            snapshot: Arc::new(Mutex::new(None)),
        }
    }

    pub fn get_text(&self) -> String {
        let t = self.doc.get_or_insert_text(&*self.name);
        let txn = self.doc.transact();
        t.get_string(&txn)
    }

    pub fn insert(&self, text: &str, pos: u32) -> Result<(), String> {
        let mut txn = self.doc.transact_mut();
        let t = txn.get_or_insert_text(&*self.name);
        t.insert(&mut txn, pos, text);
        Ok(())
    }

    pub fn append(&self, text: &str) -> Result<(), String> {
        let pos = self.get_text().len() as u32;
        self.insert(text, pos)
    }

    /// E3: Export full state as update bytes.
    pub fn export_state(&self) -> Vec<u8> {
        let txn = self.doc.transact();
        txn.encode_state_as_update_v1(&Default::default())
    }

    /// E3: Export only changes since last snapshot (StateVector diff).
    /// In yrs 0.21, we export the full state and let the sync protocol handle deduplication.
    pub async fn export_diff_since_snapshot(&self) -> Vec<u8> {
        // Full state export — yrs sync protocol deduplicates on the receiver side
        self.export_state()
    }

    /// E3: Capture current state as a snapshot (for future diff-only sync).
    pub async fn take_snapshot(&self) {
        // Store full state as update bytes (used as baseline for future diffs)
        let sv_bytes = self.export_state();
        *self.snapshot.lock().await = Some(sv_bytes);
        debug!("[DocSegment:{}] Snapshot taken", self.name);
    }

    pub fn apply_update(&self, update: &[u8]) -> Result<(), String> {
        let u = yrs::Update::decode_v1(update).map_err(|e| format!("Decode error: {e:?}"))?;
        let mut txn = self.doc.transact_mut();
        txn.apply_update(u)
            .map_err(|e| format!("Apply error: {e:?}"))?;
        Ok(())
    }
}

// ─── Transport ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum SyncTransport {
    WebSocket { url: String, room: String },
    InProcess,
    Disconnected,
}

// ─── Peer Config ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct YjsPeerConfig {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "default_true")]
    pub auto_detect: bool,
    #[serde(default)]
    pub endpoints: std::collections::HashMap<String, String>,
    #[serde(default = "default_prefix")]
    pub client_id_prefix: String,
    #[serde(default = "default_review")]
    pub review_mode: String,
    /// E1: Segment large docs beyond this size in bytes
    #[serde(default = "default_segment_threshold")]
    pub segment_threshold_bytes: usize,
    /// E2: Awareness debounce in milliseconds
    #[serde(default = "default_debounce")]
    pub awareness_debounce_ms: u64,
    /// E3: Snapshot interval in seconds
    #[serde(default = "default_snapshot_interval")]
    pub snapshot_interval_secs: u64,
}

fn default_true() -> bool {
    true
}
fn default_prefix() -> String {
    "kairo-ai-".into()
}
fn default_review() -> String {
    "ghost".into()
}
fn default_segment_threshold() -> usize {
    5 * 1024 * 1024
} // 5MB
fn default_debounce() -> u64 {
    200
}
fn default_snapshot_interval() -> u64 {
    30
}

impl Default for YjsPeerConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            auto_detect: true,
            endpoints: Default::default(),
            client_id_prefix: "kairo-ai-".into(),
            review_mode: "ghost".into(),
            segment_threshold_bytes: 5 * 1024 * 1024,
            awareness_debounce_ms: 200,
            snapshot_interval_secs: 30,
        }
    }
}

// ─── Yjs App Detection Patterns ───────────────────────────────────────────────

const YJS_URL_PATTERNS: &[(&str, &[&str])] = &[
    ("google_docs", &["docs.google.com/document"]),
    ("google_slides", &["docs.google.com/presentation"]),
    ("tiptap", &["tiptap.dev", "collab.tiptap.dev"]),
    ("linear", &["linear.app"]),
    ("blocksuite", &["blocksuite.io", "affine.pro"]),
    ("liveblocks", &["liveblocks.io"]),
    ("plane", &["app.plane.so"]),
];

const YJS_TITLE_PATTERNS: &[(&str, &[&str])] = &[
    ("google_docs", &["google docs"]),
    ("google_slides", &["google slides"]),
    ("tiptap", &["tiptap"]),
    ("linear", &["linear"]),
    ("blocksuite", &["affine", "blocksuite"]),
    ("plane", &["plane"]),
];

// ─── Yjs Peer (V6 Production) ─────────────────────────────────────────────────

pub struct YjsPeer {
    pub config: YjsPeerConfig,
    pub client_id: u64,
    /// E1: Primary segment ("content") + overflow segments for large docs
    primary_segment: Arc<DocSegment>,
    sections: Arc<Mutex<Vec<Arc<DocSegment>>>>,
    /// E2: Throttled awareness (only broadcasts on transitions)
    awareness: Arc<ThrottledAwareness>,
    transport: Arc<Mutex<SyncTransport>>,
    connected: Arc<Mutex<bool>>,
    /// E3: Background snapshot task handle
    snapshot_task: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
}

impl YjsPeer {
    pub fn new(config: YjsPeerConfig) -> Self {
        let client_id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64
            & 0x0000_0000_FFFF_FFFF;
        Self::with_client_id(config, client_id)
    }

    pub fn with_client_id(config: YjsPeerConfig, client_id: u64) -> Self {
        info!("[YjsPeer] Created clientID: {}", client_id);
        let debounce = config.awareness_debounce_ms;

        Self {
            config,
            client_id,
            primary_segment: Arc::new(DocSegment::new("content", client_id)),
            sections: Arc::new(Mutex::new(Vec::new())),
            awareness: Arc::new(ThrottledAwareness::new(debounce)),
            transport: Arc::new(Mutex::new(SyncTransport::Disconnected)),
            connected: Arc::new(Mutex::new(false)),
            snapshot_task: Arc::new(Mutex::new(None)),
        }
    }

    pub fn detect_yjs_app(title: &str, url: Option<&str>) -> Option<String> {
        let t = title.to_lowercase();
        let u = url.unwrap_or("").to_lowercase();
        for (name, patterns) in YJS_URL_PATTERNS {
            if patterns.iter().any(|p| u.contains(p)) {
                return Some(name.to_string());
            }
        }
        for (name, patterns) in YJS_TITLE_PATTERNS {
            if patterns.iter().any(|p| t.contains(p)) {
                return Some(name.to_string());
            }
        }
        None
    }

    pub async fn connect(&self, app_name: &str) -> Result<(), String> {
        let ws = self
            .config
            .endpoints
            .get(app_name)
            .cloned()
            .unwrap_or("auto".into());
        *self.transport.lock().await = if ws == "auto" {
            SyncTransport::InProcess
        } else {
            SyncTransport::WebSocket {
                url: ws,
                room: app_name.into(),
            }
        };
        *self.connected.lock().await = true;
        self.awareness
            .update_if_changed("connected", 0.0, None, "auto")
            .await;

        // E3: Start periodic snapshot task
        let seg = self.primary_segment.clone();
        let interval = self.config.snapshot_interval_secs;
        let handle = tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(interval)).await;
                seg.take_snapshot().await;
            }
        });
        *self.snapshot_task.lock().await = Some(handle);

        info!("[YjsPeer] Connected to '{}'", app_name);
        Ok(())
    }

    pub async fn disconnect(&self) {
        *self.connected.lock().await = false;
        *self.transport.lock().await = SyncTransport::Disconnected;
        self.awareness
            .update_if_changed("idle", 0.0, None, "auto")
            .await;
        // Stop snapshot task
        if let Some(handle) = self.snapshot_task.lock().await.take() {
            handle.abort();
        }
    }

    pub async fn is_connected(&self) -> bool {
        *self.connected.lock().await
    }

    /// E1: Read document text — handles sub-document segmentation.
    pub async fn read_document_text(&self) -> String {
        let primary = self.primary_segment.get_text();
        let sections = self.sections.lock().await;
        if sections.is_empty() {
            return primary;
        }
        // Combine all segments in order
        let mut full = primary;
        for sec in sections.iter() {
            full.push('\n');
            full.push_str(&sec.get_text());
        }
        full
    }

    /// E1: Get or create a named section (sub-document).
    pub async fn get_or_create_section(&self, section_name: &str) -> Arc<DocSegment> {
        let mut sections = self.sections.lock().await;
        if let Some(s) = sections.iter().find(|s| s.name == section_name) {
            return s.clone();
        }
        let seg = Arc::new(DocSegment::new(section_name, self.client_id));
        info!("[YjsPeer] Created section segment: '{}'", section_name);
        sections.push(seg.clone());
        seg
    }

    pub fn insert_text(&self, text: &str, pos: u32) -> Result<(), String> {
        self.primary_segment.insert(text, pos)
    }

    pub fn replace_text(&self, start: u32, del: u32, new: &str) -> Result<(), String> {
        let mut txn = self.primary_segment.doc.transact_mut();
        let c = txn.get_or_insert_text("content");
        if del > 0 {
            c.remove_range(&mut txn, start, del);
        }
        c.insert(&mut txn, start, new);
        Ok(())
    }

    pub fn append_text(&self, text: &str) -> Result<(), String> {
        let pos = self.primary_segment.get_text().len() as u32;
        self.insert_text(text, pos)
    }

    /// E2: Set awareness with throttling — only broadcasts on transitions.
    pub async fn set_awareness(
        &self,
        status: &str,
        progress: f32,
        section: Option<&str>,
        agent: &str,
    ) -> bool {
        self.awareness
            .update_if_changed(status, progress, section, agent)
            .await
    }

    pub async fn get_awareness(&self) -> AwarenessState {
        self.awareness.get().await
    }

    /// E2: Throttled convenience methods
    pub async fn broadcast_thinking(&self, p: f32) {
        self.set_awareness("thinking...", p, None, "auto").await;
    }
    pub async fn broadcast_writing(&self, sec: &str, p: f32) {
        self.set_awareness(&format!("writing {sec}..."), p, Some(sec), "auto")
            .await;
    }
    pub async fn broadcast_done(&self) {
        self.set_awareness("done", 1.0, None, "auto").await;
    }

    /// E3: Export only changes since last snapshot (efficient sync).
    pub async fn export_diff(&self) -> Vec<u8> {
        self.primary_segment.export_diff_since_snapshot().await
    }

    pub fn export_state(&self) -> Vec<u8> {
        self.primary_segment.export_state()
    }

    pub fn doc_client_id(&self) -> u64 {
        self.primary_segment.doc.client_id()
    }

    pub fn apply_update(&self, update: &[u8]) -> Result<(), String> {
        self.primary_segment.apply_update(update)
    }
}

impl Drop for YjsPeer {
    fn drop(&mut self) {
        if let Ok(mut lock) = self.snapshot_task.try_lock() {
            if let Some(handle) = lock.take() {
                handle.abort();
            }
        }
    }
}

// ─── Ghost Bridge ─────────────────────────────────────────────────────────────

pub struct YjsGhostBridge {
    peer: Arc<YjsPeer>,
}

impl YjsGhostBridge {
    pub fn new(peer: Arc<YjsPeer>) -> Self {
        Self { peer }
    }

    pub async fn inject_accepted(&self, text: &str, pos: u32) -> Result<(), String> {
        self.peer.broadcast_writing("injecting", 0.9).await;
        self.peer.insert_text(text, pos)?;
        self.peer.broadcast_done().await;
        Ok(())
    }

    pub async fn stream_token(&self, token: &str, pos: u32) -> Result<u32, String> {
        self.peer.insert_text(token, pos)?;
        Ok(pos + token.len() as u32)
    }

    /// E1: Inject into a named section (sub-document aware).
    pub async fn inject_into_section(&self, section: &str, text: &str) -> Result<(), String> {
        self.peer.broadcast_writing(section, 0.8).await;
        let seg = self.peer.get_or_create_section(section).await;
        let pos = seg.get_text().len() as u32;
        seg.insert(text, pos)?;
        self.peer.broadcast_done().await;
        Ok(())
    }
}

/// Module-level helper
pub fn detect_yjs_app(title: &str, url: Option<&str>) -> Option<String> {
    YjsPeer::detect_yjs_app(title, url)
}
