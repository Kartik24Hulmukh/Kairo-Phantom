use phantom_core::config::PhantomConfig;
/// ============================================================
/// LAYER 1: Unit Tests — Core Module Isolation
///
/// Tests each internal function in isolation without
/// external dependencies (Ollama, UIA, clipboard)
/// ============================================================
use phantom_core::ghost_session::{ConfidenceBand, GhostSession, SessionState};
use std::sync::atomic::Ordering;

// ─── ConfidenceBand ───────────────────────────────────────────

#[test]
fn unit_confidence_low_for_vague_unknown() {
    let band = ConfidenceBand::compute("ok", "Unknown");
    assert!(matches!(band, ConfidenceBand::Low));
}

#[test]
fn unit_confidence_medium_for_vague_known() {
    let band = ConfidenceBand::compute("write", "Word");
    assert!(matches!(band, ConfidenceBand::Medium));
}

#[test]
fn unit_confidence_medium_for_clear_unknown() {
    let band = ConfidenceBand::compute(
        "rewrite this paragraph in a professional tone for a board meeting",
        "Unknown",
    );
    assert!(matches!(band, ConfidenceBand::Medium));
}

#[test]
fn unit_confidence_high_for_clear_known() {
    let band = ConfidenceBand::compute(
        "add three bullet points summarizing the key risks identified in this document",
        "Word",
    );
    assert!(matches!(band, ConfidenceBand::High));
}

// ─── GhostSession ─────────────────────────────────────────────

#[test]
fn unit_ghost_session_starts_streaming() {
    let s = GhostSession::new("test prompt", 11, ConfidenceBand::High);
    assert!(matches!(s.state, SessionState::Streaming));
}

#[test]
fn unit_ghost_session_preserves_prompt() {
    let prompt = "write a haiku about Rust";
    let s = GhostSession::new(prompt, prompt.len(), ConfidenceBand::High);
    assert_eq!(s.original_prompt, prompt);
    assert_eq!(s.prompt_char_count, prompt.len());
}

#[test]
fn unit_ghost_session_cancellation_token_works() {
    let s = GhostSession::new("test", 4, ConfidenceBand::Low);
    assert!(!s.cancel_token.is_cancelled());
    s.cancel_token.cancel();
    assert!(s.cancel_token.is_cancelled());
}

#[test]
fn unit_ghost_session_empty_prompt() {
    // Edge case: empty prompt must not panic
    let s = GhostSession::new("", 0, ConfidenceBand::Low);
    assert_eq!(s.prompt_char_count, 0);
    assert_eq!(s.original_prompt, "");
}

#[test]
fn unit_ghost_session_unicode_prompt() {
    let prompt = "写一首关于编程的诗 🦀🔥";
    let s = GhostSession::new(prompt, prompt.len(), ConfidenceBand::High);
    assert_eq!(s.original_prompt, prompt);
}

#[test]
fn unit_ghost_session_very_long_prompt() {
    let prompt = "a".repeat(100_000);
    let s = GhostSession::new(&prompt, prompt.len(), ConfidenceBand::High);
    assert_eq!(s.prompt_char_count, 100_000);
}

// ─── Config ───────────────────────────────────────────────────

#[test]
fn unit_config_default_is_ollama() {
    let cfg = PhantomConfig::default();
    assert_eq!(cfg.model.provider, "ollama");
}

#[test]
fn unit_config_default_has_model_name() {
    let cfg = PhantomConfig::default();
    assert!(cfg.model.model_name.is_some());
}

#[test]
fn unit_config_swarm_disabled_by_default() {
    let cfg = PhantomConfig::default();
    assert!(!cfg.swarm.enabled, "Swarm must be opt-in, not default");
}

#[test]
fn unit_config_serialization_no_panic() {
    let cfg = PhantomConfig::default();
    let result = toml::to_string_pretty(&cfg);
    assert!(
        result.is_ok(),
        "Default config must serialize without error"
    );
}

// ─── DocumentGraph ─────────────────────────────────────────────

struct MockDocumentGraphBackend {
    call_count: std::sync::atomic::AtomicUsize,
}

#[async_trait::async_trait]
impl phantom_core::ai::AiBackend for MockDocumentGraphBackend {
    async fn complete(&self, _system: &str, _user: &str) -> anyhow::Result<String> {
        let count = self
            .call_count
            .fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        if count == 0 {
            Ok(r#"[
                {"name": "Rust Language", "entity_type": "company", "relation": "subject"}
            ]"#
            .to_string())
        } else {
            Ok(r#"[
                {"name": "Cpp Language", "entity_type": "company", "relation": "subject"}
            ]"#
            .to_string())
        }
    }

    async fn stream_complete(
        &self,
        _system: &str,
        _user: &str,
        _tx: tokio::sync::mpsc::Sender<String>,
    ) -> anyhow::Result<()> {
        Ok(())
    }
}

#[tokio::test]
async fn unit_document_graph_reindexing_on_modification() {
    use phantom_core::memory::document_graph::DocumentGraph;
    use rusqlite::params;
    use std::fs::File;
    use std::io::Write;
    use std::sync::Arc;
    use tempfile::tempdir;

    let dir = tempdir().unwrap();
    let db_path = dir.path().join("test_graph.db");
    let docs_dir = dir.path().join("docs");
    std::fs::create_dir_all(&docs_dir).unwrap();

    let backend = Arc::new(MockDocumentGraphBackend {
        call_count: std::sync::atomic::AtomicUsize::new(0),
    });
    let doc_graph = DocumentGraph::new(db_path.clone(), backend).unwrap();

    // 1. Create a document file
    let file_path = docs_dir.join("doc1.txt");
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(b"Initial content referencing Rust Language.")
            .unwrap();
    }

    // 2. Index the directory
    doc_graph.index_directory(&docs_dir).await.unwrap();

    // 3. Query the entities to confirm they are indexed
    let entities = doc_graph.list_entities().unwrap();
    assert!(
        entities.contains("Rust Language"),
        "Should contain Rust Language entity initially: {entities}"
    );

    // 4. Modify the document content
    {
        let mut file = File::create(&file_path).unwrap();
        file.write_all(b"Modified content referencing C++ language.")
            .unwrap();
    }

    // 5. Index the directory again
    doc_graph.index_directory(&docs_dir).await.unwrap();

    // 6. Verify that it was re-indexed (meaning the database stored content is updated).
    let conn = rusqlite::Connection::open(&db_path).unwrap();
    let content: String = conn
        .query_row(
            "SELECT content FROM nodes WHERE node_type = 'document'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert!(
        content.contains("C++ language"),
        "Document content should be updated to C++ language, but was: {content}"
    );

    // Verify edges are deleted and replaced:
    let mut stmt = conn
        .prepare("SELECT target FROM edges WHERE source = ?1")
        .unwrap();
    let edge_targets: Vec<String> = stmt
        .query_map(params![file_path.to_string_lossy().to_string()], |row| {
            row.get(0)
        })
        .unwrap()
        .collect::<Result<Vec<String>, _>>()
        .unwrap();

    assert_eq!(edge_targets.len(), 1);
    assert_eq!(edge_targets[0], "entity:cpp-language");
}
