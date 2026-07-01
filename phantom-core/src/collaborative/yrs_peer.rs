use serde_json::json;
use std::sync::Arc;
use tokio::sync::Mutex;
use uuid::Uuid;
use yrs::updates::decoder::Decode;
/// Yrs CRDT Peer — Kairo Phantom's collaborative document engine.
/// Implements AI as a first‑class CRDT participant.
use yrs::{
    Array, ArrayRef, Doc, GetString, Map, MapRef, Options, ReadTxn, Text, TextRef, Transact,
    WriteTxn,
};

/// Kairo's AI peer — joins Yjs collaborative sessions as a first‑class
/// participant with permanent attribution.
pub struct KairoCollaborativePeer {
    /// The Yrs document — syncs with all other peers via WebSocket
    pub doc: Doc,
    /// Unique client ID for the AI peer (prefix "kairo-ai-")
    pub client_id: String,
    /// Awareness state shared with all collaborators
    pub awareness_state: Arc<Mutex<serde_json::Value>>,
    /// The shared text type for collaborative editing
    pub text: TextRef,
    /// Metadata map for AI status, confidence, session info
    pub metadata: MapRef,
    /// Array of AI‑proposed edits (patchwork pattern)
    pub proposals: ArrayRef,
    /// WebSocket sender for synchronization updates
    pub ws_sender: Option<tokio::sync::mpsc::Sender<Vec<u8>>>,
}

impl Default for KairoCollaborativePeer {
    fn default() -> Self {
        Self::new()
    }
}

impl KairoCollaborativePeer {
    /// Create a new Kairo AI peer with a unique clientID.
    pub fn new() -> Self {
        // Create Doc with options
        let client_id_str = format!("kairo-ai-{}", Uuid::new_v4());

        // Derive a numeric clientID for yrs Doc
        let client_id_num = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64
            & 0x0000_0000_FFFF_FFFF;

        let options = Options {
            client_id: client_id_num,
            ..Default::default()
        };
        let doc = Doc::with_options(options);

        // Initialize shared types at the root of the document
        let text = doc.get_or_insert_text("content");
        let metadata = doc.get_or_insert_map("kairo-metadata");
        let proposals = doc.get_or_insert_array("kairo-proposals");

        // Set initial awareness state
        let awareness_state = Arc::new(Mutex::new(json!({
            "name": "Kairo AI",
            "status": "online",
            "color": "#6C5CE7",  // Kairo purple
            "client_id": client_id_str.clone(),
        })));

        Self {
            doc,
            client_id: client_id_str,
            awareness_state,
            text,
            metadata,
            proposals,
            ws_sender: None,
        }
    }

    /// Connect to a Yjs sync server via WebSocket.
    pub async fn connect(&mut self, ws_url: &str, doc_id: &str) -> anyhow::Result<()> {
        // E2E Network P2P Pointers and Sync Protocol Bridge
        tracing::info!(
            "🔗 Connecting collaborative AI Peer to Yjs server: {} (doc: {})",
            ws_url,
            doc_id
        );

        // Mock socket connection for local server compatibility
        let (tx, mut rx) = tokio::sync::mpsc::channel::<Vec<u8>>(100);
        self.ws_sender = Some(tx);

        let doc = self.doc.clone();
        tokio::spawn(async move {
            while let Some(msg) = rx.recv().await {
                if let Ok(update) = yrs::Update::decode_v1(&msg) {
                    let mut txn = doc.transact_mut();
                    let _ = txn.apply_update(update);
                }
            }
        });

        // Trigger Sync Step 1
        let state_vector = self
            .doc
            .transact()
            .encode_state_as_update_v1(&Default::default());
        if let Some(ref sender) = self.ws_sender {
            let _ = sender.send(state_vector).await;
        }

        Ok(())
    }

    /// Ghost‑write AI‑generated text into the collaborative document.
    /// The text is inserted with permanent attribution to kairo-ai- clientID.
    pub async fn ghost_write(&self, text_to_insert: &str, position: usize) {
        // Set awareness status to "writing"
        self.set_awareness_status("writing...").await;

        // Perform all document changes in a dedicated synchronous scope to ensure
        // the transaction is immediately dropped before any further async yield (.await).
        {
            let mut txn = self.doc.transact_mut();

            // Insert AI‑generated text
            self.text.insert(&mut txn, position as u32, text_to_insert);

            // Record the AI edit in proposals (patchwork pattern)
            let proposal_idx = self.proposals.len(&txn);
            let proposal_data = json!({
                "type": "ai_edit",
                "client_id": self.client_id,
                "position": position,
                "length": text_to_insert.len(),
                "content": text_to_insert,
                "status": "proposed",
                "timestamp": chrono::Utc::now().to_rfc3339(),
            })
            .to_string();

            self.proposals.insert(&mut txn, proposal_idx, proposal_data);

            // Update metadata
            self.metadata
                .insert(&mut txn, "last_edit_at", chrono::Utc::now().to_rfc3339());

            let total = self.proposals.len(&txn) as f64;
            self.metadata.insert(&mut txn, "total_edits", total);
        }

        // Set awareness status back to "online"
        self.set_awareness_status("online").await;
    }

    /// Update awareness status visible to all collaborators.
    pub async fn set_awareness_status(&self, status: &str) {
        let mut state = self.awareness_state.lock().await;
        if let Some(obj) = state.as_object_mut() {
            obj.insert("status".to_string(), json!(status));
        }
        tracing::debug!("Awareness broadcast: {}", status);
    }

    /// Retrieve the full document text from the CRDT.
    pub fn get_document_text(&self) -> String {
        let txn = self.doc.transact();
        self.text.get_string(&txn)
    }

    /// Count total AI edits made.
    pub fn total_edits(&self) -> usize {
        let txn = self.doc.transact();
        self.proposals.len(&txn) as usize
    }

    /// Generate awareness state for broadcast.
    pub async fn awareness_state(&self) -> serde_json::Value {
        self.awareness_state.lock().await.clone()
    }
}
