use phantom_core::collaborative::session_detector::{CollaborativeSession, SyncProviderType};
use phantom_core::collaborative::yrs_peer::KairoCollaborativePeer;
use serde_json::Value;
use std::sync::Arc;
use yrs::updates::decoder::Decode;
use yrs::{Array, Doc, GetString, Map, ReadTxn, Text, Transact, WriteTxn};

#[tokio::test]
async fn test_kairo_peer_unique_client_id() {
    let peer = KairoCollaborativePeer::new();

    // Verify unique client ID format
    assert!(peer.client_id.starts_with("kairo-ai-"));
    println!("✅ Unique AI Peer client_id verified: {}", peer.client_id);
}

#[tokio::test]
async fn test_ghost_write_inserts_with_attribution() {
    let peer = KairoCollaborativePeer::new();

    // Initial document should be empty
    let initial = peer.get_document_text();
    assert!(initial.is_empty());

    // Ghost-write text at index 0
    peer.ghost_write("Hello from Kairo AI Peer", 0).await;

    // Verify text content
    let text = peer.get_document_text();
    assert_eq!(text, "Hello from Kairo AI Peer");

    // Verify proposal tracking
    assert_eq!(peer.total_edits(), 1);

    let txn = peer.doc.transact();
    let prop_str: String = peer.proposals.get(&txn, 0).unwrap().to_string(&txn);

    let prop_json: Value = serde_json::from_str(&prop_str).unwrap();
    assert_eq!(prop_json["type"], "ai_edit");
    assert_eq!(prop_json["client_id"], peer.client_id);
    assert_eq!(prop_json["position"], 0);
    assert_eq!(prop_json["length"], "Hello from Kairo AI Peer".len());
    assert_eq!(prop_json["content"], "Hello from Kairo AI Peer");
    assert_eq!(prop_json["status"], "proposed");

    // Verify metadata updates
    let total_edits_val = peer.metadata.get(&txn, "total_edits").unwrap();
    let total_edits_f64: f64 = total_edits_val.try_into().unwrap();
    assert_eq!(total_edits_f64, 1.0);

    assert!(peer.metadata.get(&txn, "last_edit_at").is_some());
    println!("✅ Ghost-write with permanent attribution & proposals array verified.");
}

#[tokio::test]
async fn test_awareness_state_broadcasts() {
    let peer = KairoCollaborativePeer::new();

    // Initial state check
    let state = peer.awareness_state().await;
    assert_eq!(state["name"], "Kairo AI");
    assert_eq!(state["color"], "#6C5CE7"); // Kairo purple
    assert_eq!(state["status"], "online");
    assert_eq!(state["client_id"], peer.client_id);

    // Transition state
    peer.set_awareness_status("thinking...").await;

    let updated_state = peer.awareness_state().await;
    assert_eq!(updated_state["status"], "thinking...");
    println!("✅ Awareness status updates verified successfully.");
}

#[tokio::test]
async fn test_multiple_edits_tracked_individually() {
    let peer = KairoCollaborativePeer::new();

    peer.ghost_write("First edit.", 0).await;
    peer.ghost_write(" Second edit.", 11).await;

    let text = peer.get_document_text();
    assert_eq!(text, "First edit. Second edit.");
    assert_eq!(peer.total_edits(), 2);

    let txn = peer.doc.transact();
    let total_edits_val = peer.metadata.get(&txn, "total_edits").unwrap();
    let total_edits_f64: f64 = total_edits_val.try_into().unwrap();
    assert_eq!(total_edits_f64, 2.0);

    println!("✅ Multiple edits tracked individually verified.");
}

#[tokio::test]
async fn test_concurrent_edits_merge_correctly() {
    // Spawn two peers representing AI and human
    let mut peer1 = KairoCollaborativePeer::new();
    let mut peer2 = KairoCollaborativePeer::new();

    // Connect them using local mock sync
    peer1
        .connect("ws://localhost:1234", "doc-123")
        .await
        .unwrap();
    peer2
        .connect("ws://localhost:1234", "doc-123")
        .await
        .unwrap();

    // AI peer writes
    peer1.ghost_write("AI text. ", 0).await;

    // Export state update from Peer 1 and apply to Peer 2
    let update_bytes = peer1
        .doc
        .transact()
        .encode_state_as_update_v1(&Default::default());
    {
        let mut txn = peer2.doc.transact_mut();
        let update = yrs::Update::decode_v1(&update_bytes).unwrap();
        txn.apply_update(update).unwrap();
    }

    // Peer 2 (human) writes at a different position
    let doc_len = peer2.get_document_text().len();
    peer2.ghost_write("Human text.", doc_len).await;

    // Export update back from Peer 2 to Peer 1
    let update_bytes2 = peer2
        .doc
        .transact()
        .encode_state_as_update_v1(&Default::default());
    {
        let mut txn = peer1.doc.transact_mut();
        let update = yrs::Update::decode_v1(&update_bytes2).unwrap();
        txn.apply_update(update).unwrap();
    }

    // Both peers must converge to the same text
    let text1 = peer1.get_document_text();
    let text2 = peer2.get_document_text();
    assert_eq!(text1, "AI text. Human text.");
    assert_eq!(text2, "AI text. Human text.");
    println!("✅ Peer-to-peer merging of concurrent updates verified.");
}

#[tokio::test]
async fn test_collaborative_session_detection() {
    // Notion URL / Title
    let app1 = CollaborativeSession::detect(
        "My Workspace - Notion",
        Some("https://www.notion.so/my-page"),
    )
    .await;
    assert!(app1.is_some());
    let session1 = app1.unwrap();
    assert_eq!(session1.app_name, "Notion");
    assert!(session1.detected);

    // Google Docs URL
    let app2 = CollaborativeSession::detect(
        "Meeting Notes - Google Docs",
        Some("https://docs.google.com/document/d/1A2B3C4D5E/edit"),
    )
    .await;
    assert!(app2.is_some());
    let session2 = app2.unwrap();
    assert_eq!(session2.app_name, "Google Docs");
    assert_eq!(session2.doc_id, "1A2B3C4D5E");
    assert_eq!(session2.provider_type, SyncProviderType::WebSocket);
    assert!(session2.detected);

    // Tiptap Editor
    let app3 =
        CollaborativeSession::detect("Tiptap App", Some("https://collab.tiptap.dev/p/room-123"))
            .await;
    assert!(app3.is_some());
    let session3 = app3.unwrap();
    assert_eq!(session3.app_name, "Tiptap Collaborative Editor");
    assert_eq!(
        session3.sync_endpoint,
        Some("wss://collab.tiptap.dev".to_string())
    );
    assert_eq!(session3.doc_id, "room-123");
    assert!(session3.detected);

    // Unknown app
    let app4 = CollaborativeSession::detect("Calculators", Some("https://calculator.net")).await;
    assert!(app4.is_none());
    println!("✅ Collaborative session detection patterns verified.");
}
