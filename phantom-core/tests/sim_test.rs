use phantom_core::ghost_session::{ConfidenceBand, GhostSession};

#[tokio::test]
async fn test_deterministic_ghost_session() {
    let session = GhostSession::new("test", 4, ConfidenceBand::High);

    // Simulate some async operations
    let handle = tokio::spawn(async move {
        // ... simulated streaming operations ...
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        session.prompt_char_count
    });

    let res = handle.await.unwrap();
    assert_eq!(res, 4);
}
