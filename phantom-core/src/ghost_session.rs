/// Ghost Session v1.0 — Phase 3: Full Interactive Copilot UX
/// Implements: streaming cancel (Esc), Tab accept, word-by-word accept (Ctrl+Right),
/// two alternatives (Alt+1/Alt+2), inline correction (Ctrl+/), agent-aware undo (Ctrl+Z),
/// confidence bands (High/Medium/Low), and Yjs CRDT peer mode.
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info};

// ─── Session State ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum SessionState {
    /// AI is streaming, ghost text is building
    Streaming,
    /// AI finished streaming, preview frozen for review
    Review,
    /// User accepted — text injected
    Accepted,
    /// User rejected — original text unchanged
    Cancelled,
    /// User requested correction — re-streaming with new prompt
    Correcting,
}

#[derive(Debug, Clone)]
pub enum ConfidenceBand {
    /// Strong prompt match, known context, low temperature → green glow
    High,
    /// Ambiguous prompt or mixed context → yellow glow, show alternatives prominently
    Medium,
    /// Low confidence, uncertain context → red glow, accept disabled
    Low,
}

impl ConfidenceBand {
    /// Compute confidence from prompt clarity and doc kind.
    pub fn compute(prompt: &str, doc_kind_name: &str) -> Self {
        let word_count = prompt.split_whitespace().count();
        let is_vague = prompt.len() < 20 || word_count < 4;
        let is_unknown_app = doc_kind_name == "Unknown";

        if is_vague && is_unknown_app {
            ConfidenceBand::Low
        } else if is_vague || is_unknown_app {
            ConfidenceBand::Medium
        } else {
            ConfidenceBand::High
        }
    }

    pub fn label(&self) -> &str {
        match self {
            ConfidenceBand::High => "HIGH",
            ConfidenceBand::Medium => "MEDIUM",
            ConfidenceBand::Low => "LOW",
        }
    }

    pub fn accepts_enabled(&self) -> bool {
        !matches!(self, ConfidenceBand::Low)
    }
}

// ─── History Entry (for agent-aware undo) ────────────────────────────────────

#[derive(Debug, Clone)]
pub struct HistoryEntry {
    pub before_text: String,
    pub after_text: String,
    pub prompt_char_count: usize,
    pub timestamp: std::time::Instant,
}

// ─── Ghost Buffer ─────────────────────────────────────────────────────────────

/// Holds the streamed tokens and tracks word-by-word acceptance.
#[derive(Debug, Default)]
pub struct GhostBuffer {
    /// The full generated text (both alternatives)
    pub text_a: String,
    pub text_b: String,
    /// Which alternative is currently selected (false = A, true = B)
    pub using_b: bool,
    /// How many characters the user has "word-accepted"
    pub accepted_chars: usize,
}

impl GhostBuffer {
    pub fn active_text(&self) -> &str {
        if self.using_b {
            &self.text_b
        } else {
            &self.text_a
        }
    }

    pub fn accepted_text(&self) -> &str {
        let text = self.active_text();
        &text[..self.accepted_chars.min(text.len())]
    }

    /// Accept the next word boundary
    pub fn accept_next_word(&mut self) {
        let text = self.active_text();
        let remaining = &text[self.accepted_chars..];
        // Find next word boundary (space after a non-space)
        let mut found = false;
        let mut i = 0;
        for (idx, ch) in remaining.char_indices() {
            if ch == ' ' && found {
                i = idx + 1;
                break;
            }
            if ch != ' ' {
                found = true;
            }
            i = idx + ch.len_utf8();
        }
        self.accepted_chars = (self.accepted_chars + i).min(text.len());
    }

    /// Un-accept the last word
    pub fn undo_last_word(&mut self) {
        let text = self.active_text();
        let accepted = &text[..self.accepted_chars];
        // Find last word boundary
        if let Some(pos) = accepted.rfind(' ') {
            self.accepted_chars = pos;
        } else {
            self.accepted_chars = 0;
        }
    }

    pub fn toggle_alternative(&mut self) {
        self.using_b = !self.using_b;
        // Reset word-by-word acceptance when switching
        self.accepted_chars = 0;
    }
}

// ─── Ghost Session ────────────────────────────────────────────────────────────

pub struct GhostSession {
    /// Token used to cancel the AI stream
    pub cancel_token: CancellationToken,
    /// The ghost text buffer (shared between streaming task and UI)
    pub buffer: Arc<Mutex<GhostBuffer>>,
    /// Undo history for agent-aware undo (Ctrl+Z)
    pub history: Vec<HistoryEntry>,
    /// Current state of the session
    pub state: SessionState,
    /// Confidence band
    pub confidence: ConfidenceBand,
    /// Original prompt (before erasure)
    pub original_prompt: String,
    /// Char count of the original prompt (for erasure)
    pub prompt_char_count: usize,
}

impl GhostSession {
    pub fn new(prompt: &str, prompt_char_count: usize, confidence: ConfidenceBand) -> Self {
        Self {
            cancel_token: CancellationToken::new(),
            buffer: Arc::new(Mutex::new(GhostBuffer::default())),
            history: Vec::new(),
            state: SessionState::Streaming,
            confidence,
            original_prompt: prompt.to_string(),
            prompt_char_count,
        }
    }

    /// Cancel the ongoing stream (user pressed Esc)
    pub fn cancel(&mut self) {
        info!("🛑 Ghost session cancelled by user (Esc)");
        self.cancel_token.cancel();
        self.state = SessionState::Cancelled;
    }

    /// Accept all text generated so far (Tab)
    pub fn accept_all(&mut self) -> String {
        let buf = self.buffer.blocking_lock();
        let text = buf.active_text().to_string();
        drop(buf);
        self.cancel_token.cancel(); // stop any remaining streaming
        self.state = SessionState::Accepted;
        text
    }

    /// Accept the next word only (Ctrl+Right)
    pub async fn accept_next_word(&self) {
        let mut buf = self.buffer.lock().await;
        buf.accept_next_word();
        debug!("Word accepted: {} chars total", buf.accepted_chars);
    }

    /// Un-accept last word (Ctrl+Left)
    pub async fn undo_last_word(&self) {
        let mut buf = self.buffer.lock().await;
        buf.undo_last_word();
    }

    /// Switch between alternative A and B (Alt+] or Alt+[)
    pub async fn toggle_alternative(&self) {
        let mut buf = self.buffer.lock().await;
        buf.toggle_alternative();
        info!(
            "🔄 Switched to alternative {}",
            if buf.using_b { "B" } else { "A" }
        );
    }

    /// Push a token to the primary stream buffer
    pub async fn push_token_a(&self, token: &str) {
        let mut buf = self.buffer.lock().await;
        buf.text_a.push_str(token);
    }

    /// Push a token to the secondary (alternative B) stream buffer
    pub async fn push_token_b(&self, token: &str) {
        let mut buf = self.buffer.lock().await;
        buf.text_b.push_str(token);
    }

    /// Store a history entry for agent-aware undo
    pub fn record_history(&mut self, before: &str, after: &str) {
        self.history.push(HistoryEntry {
            before_text: before.to_string(),
            after_text: after.to_string(),
            prompt_char_count: self.prompt_char_count,
            timestamp: std::time::Instant::now(),
        });
    }

    /// Get the most recent undo entry
    pub fn last_undo_entry(&self) -> Option<&HistoryEntry> {
        self.history.last()
    }

    /// Human-readable session status for overlay display
    pub fn status_line(&self) -> String {
        let buf = self.buffer.blocking_lock();
        let alt = if !buf.text_b.is_empty() {
            if buf.using_b {
                " [Alt B] "
            } else {
                " [Alt A] "
            }
        } else {
            ""
        };
        let confidence = self.confidence.label();
        let chars = buf.active_text().len();

        format!(
            "👻 Kairo Ghost{alt} | {chars} chars | Confidence: {confidence} | Tab=Accept  Esc=Cancel  Ctrl+/=Correct  Alt+]=Switch"
        )
    }

    /// Streams tokens with natural delay and jitter (60-120ms/char) to emulate realistic typing.
    pub async fn stream_with_natural_delay(&self, token: &str) {
        for ch in token.chars() {
            if self.cancel_token.is_cancelled() {
                break;
            }
            {
                let mut buf = self.buffer.lock().await;
                buf.text_a.push(ch);
            }
            let now_ns = std::time::SystemTime::now()
                .duration_since(std::time::SystemTime::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0);
            let delay_ms = 60 + (now_ns % 61) as u64; // 60 to 120 ms jitter
            tokio::time::sleep(std::time::Duration::from_millis(delay_ms)).await;
        }
    }
}

// ─── Yjs CRDT Peer Mode ───────────────────────────────────────────────────────

/// Represents Kairo's configuration for joining a Yjs collaborative document session.
#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct YjsConfig {
    pub enabled: bool,
    pub auto_detect: bool,
    pub sync_endpoint: String,
    /// Prefix for AI's clientID — shows up as "kairo-ai-<uuid>" in collaborator lists
    pub client_id_prefix: String,
    /// "ghost" | "tracked_changes" | "direct_injection"
    pub review_mode: String,
}

impl Default for YjsConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            auto_detect: true,
            sync_endpoint: "auto".into(),
            client_id_prefix: "kairo-ai-".into(),
            review_mode: "ghost".into(),
        }
    }
}

/// Manages the Kairo AI peer's connection to a Yjs document.
/// Uses the `yrs` crate (already in Cargo.toml) for CRDT operations.
pub struct YjsPeer {
    pub config: YjsConfig,
    /// The CRDT session from crdt.rs
    pub crdt_session: Arc<crate::crdt::CrdtSession>,
}

impl YjsPeer {
    pub fn new(config: YjsConfig, crdt_session: Arc<crate::crdt::CrdtSession>) -> Self {
        Self {
            config,
            crdt_session,
        }
    }

    /// Detect if the currently active app is a Yjs-powered web app
    /// (e.g., Notion, Google Docs, Linear, Tiptap-based editors)
    pub fn detect_yjs_app(window_title: &str, url: Option<&str>) -> bool {
        let title_lower = window_title.to_lowercase();
        let url_lower = url.unwrap_or("").to_lowercase();

        // Known Yjs-powered apps
        let yjs_apps = [
            "notion",
            "google docs",
            "tiptap",
            "linear.app",
            "liveblocks",
            "hocuspocus",
            "blocksuite",
        ];

        yjs_apps
            .iter()
            .any(|app| title_lower.contains(app) || url_lower.contains(app))
    }

    /// Write AI-generated text as CRDT ops into the shared document.
    /// All collaborators will see the AI's edits in real-time with the AI cursor.
    pub fn write_as_crdt_peer(&self, text: &str, position: u32) -> Result<(), String> {
        // Use the existing CrdtSession from crdt.rs
        self.crdt_session.insert_ai_text(text);
        info!(
            "📡 YjsPeer: wrote {} chars to CRDT at position {}",
            text.len(),
            position
        );
        Ok(())
    }

    /// Broadcast AI awareness state to all collaborators
    pub fn broadcast_thinking_state(&self, progress: f32) {
        // In a full implementation, this would send a Yjs Awareness update
        // with { status: 'thinking', progress: progress, clientID: "kairo-ai-{uuid}" }
        debug!(
            "📡 YjsPeer: broadcasting thinking state (progress: {:.0}%)",
            progress * 100.0
        );
    }
}

// ─── Undo Manager ────────────────────────────────────────────────────────────

/// Manages the undo stack for agent-aware undo (Ctrl+Z reverts entire AI operation).
pub struct UndoManager {
    entries: Vec<HistoryEntry>,
    redo_stack: Vec<HistoryEntry>,
}

impl UndoManager {
    pub fn new() -> Self {
        Self {
            entries: Vec::new(),
            redo_stack: Vec::new(),
        }
    }

    pub fn push(&mut self, entry: HistoryEntry) {
        self.entries.push(entry);
        self.redo_stack.clear(); // redo stack cleared on new action
    }

    /// Undo: returns the text to restore
    pub fn undo(&mut self) -> Option<&HistoryEntry> {
        if let Some(entry) = self.entries.pop() {
            self.redo_stack.push(entry);
            self.redo_stack.last()
        } else {
            None
        }
    }

    /// Redo: returns the text to re-apply
    pub fn redo(&mut self) -> Option<&HistoryEntry> {
        if let Some(entry) = self.redo_stack.pop() {
            self.entries.push(entry);
            self.entries.last()
        } else {
            None
        }
    }

    pub fn has_undo(&self) -> bool {
        !self.entries.is_empty()
    }
    pub fn has_redo(&self) -> bool {
        !self.redo_stack.is_empty()
    }
}

impl Default for UndoManager {
    fn default() -> Self {
        Self::new()
    }
}

// ─── Pipeline Progress (Layer 3 overlay integration) ──────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum PipelineLayer {
    IntentGate,
    Planning,
    AwaitingApproval,
    Generating,
    Streaming,
    Verifying,
    Complete,
}

impl PipelineLayer {
    pub fn overlay_label(&self) -> &str {
        match self {
            PipelineLayer::IntentGate => "🎯 Layer 1: Intent Gate",
            PipelineLayer::Planning => "📋 Layer 2: Planning Engine",
            PipelineLayer::AwaitingApproval => "⏳ Awaiting Plan Approval (Alt+Ctrl+M to execute)",
            PipelineLayer::Generating => "🧠 Routing Specialist Swarm",
            PipelineLayer::Streaming => "⚡ Layer 3: Injecting Content",
            PipelineLayer::Verifying => "🛡️ Scanning Compliance & Quality",
            PipelineLayer::Complete => "✅ Complete",
        }
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PipelineProgress {
    pub current_layer: PipelineLayer,
    pub current_step: Option<usize>,
    pub total_steps: Option<usize>,
    pub details: String,
}
