// phantom-core/tests/test_offline_mode.rs

#[tokio::test]
async fn test_offline_mode_egress_blocking() {
    std::env::set_var("KAIRO_OFFLINE", "1");
    let client = phantom_core::config::get_client_builder()
        .timeout(std::time::Duration::from_millis(500))
        .build()
        .unwrap();

    // A request to a public external site should fail (either timed out or blocked/refused by dummy proxy)
    let res = client.get("https://www.google.com").send().await;
    assert!(
        res.is_err(),
        "Public egress request should fail under KAIRO_OFFLINE=1"
    );
}

#[tokio::test]
async fn test_capture_context_not_constant() {
    // Calling capture_context_lazy with a known prompt should return a DocumentContext
    // with that prompt, and not the hardcoded string "Active window context".
    let prompt = "test_prompt_12345";
    let ctx_result = phantom_core::pipeline::HotkeyPipeline::capture_context_lazy(prompt).await;
    assert!(ctx_result.is_ok(), "Context capture should succeed");
    let ctx = ctx_result.unwrap();
    assert_ne!(
        ctx.full_text, "Active window context",
        "Context should not be the hardcoded mock string"
    );
    assert_eq!(
        ctx.prompt_text, prompt,
        "Context should contain the passed prompt"
    );
}
