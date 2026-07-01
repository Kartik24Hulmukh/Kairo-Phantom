use yrs::{Doc, GetString, Options, ReadTxn, Text, Transact, WriteTxn};

pub struct CrdtSession {
    /// The Yrs document (pure Rust Yjs)
    doc: Doc,
    /// AI client ID — used to track which changes came from AI
    pub ai_client_id: u64,
}

impl CrdtSession {
    /// Create a new session with the AI registered as a peer with the given clientID
    pub fn new(ai_client_id: u64) -> Self {
        let options = Options {
            client_id: ai_client_id,
            ..Default::default()
        };
        let doc = Doc::with_options(options);

        CrdtSession { doc, ai_client_id }
    }

    /// Insert human-typed text into the CRDT document.
    /// This represents the "human peer" state — used as AI context.
    pub fn insert_human_text(&self, text: &str) {
        let mut txn = self.doc.transact_mut();
        let content = txn.get_or_insert_text("content");

        let current_len = content.get_string(&txn).len() as u32;
        if current_len > 0 {
            content.remove_range(&mut txn, 0, current_len);
        }
        content.insert(&mut txn, 0, text);
        drop(txn);
    }

    pub fn insert_ai_text(&self, suggestion: &str) {
        let mut txn = self.doc.transact_mut();
        let ai_response = txn.get_or_insert_text("ai_suggestion");

        let current_len = ai_response.get_string(&txn).len() as u32;
        if current_len > 0 {
            ai_response.remove_range(&mut txn, 0, current_len);
        }
        ai_response.insert(&mut txn, 0, suggestion);
        drop(txn);
    }

    pub fn get_human_text(&self) -> String {
        let content = self.doc.get_or_insert_text("content");
        let txn = self.doc.transact();
        let s = content.get_string(&txn);
        drop(txn);
        s
    }

    /// Returns the Kairo system persona — sent as the system message to the AI.
    /// This defines WHO the AI is, not what the user wants.
    pub fn get_system_prompt(&self) -> &'static str {
        crate::ai::KAIRO_SYSTEM_PROMPT
    }

    /// Returns the user context — sent as the user message to the AI.
    /// This is the raw text the user wants processed.
    pub fn get_user_context(&self) -> String {
        self.get_human_text()
    }

    /// Get word count of current document
    pub fn word_count(&self) -> usize {
        self.get_human_text().split_whitespace().count()
    }

    /// Export CRDT state as binary (for syncing with @docscode/core)
    pub fn export_state(&self) -> Vec<u8> {
        let txn = self.doc.transact();
        txn.encode_state_as_update_v1(&Default::default())
    }
}
