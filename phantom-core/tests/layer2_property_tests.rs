use phantom_core::config::PhantomConfig;
use phantom_core::document_context::DocumentContext;
use phantom_core::ghost_session::ConfidenceBand;
use phantom_core::swarm::SwarmOrchestrator;
/// ============================================================
/// LAYER 2: Property-Based Tests — Swarm Brain + GhostSession
/// proptest: random inputs, universally-held invariants
/// ============================================================
use proptest::prelude::*;

// ──────────────────────────────────────────────────────────────
// Property 1: Swarm routing is DETERMINISTIC
//   Same input always selects same agent — no non-determinism
// ──────────────────────────────────────────────────────────────
proptest! {
    #![proptest_config(ProptestConfig::with_cases(2000))]

    #[test]
    fn swarm_routing_is_deterministic(
        app_name in "[a-zA-Z0-9_ ]{1,64}",
        doc_text in "\\PC{0,2000}",
        prompt   in "\\PC{1,200}"
    ) {
        let _cfg = PhantomConfig::default();
        let mut orch1 = SwarmOrchestrator::new_for_test();
        let mut orch2 = SwarmOrchestrator::new_for_test();

        let ctx1 = DocumentContext::from_plain_text(&app_name, &doc_text, &prompt);
        let ctx2 = DocumentContext::from_plain_text(&app_name, &doc_text, &prompt);

        let agent1 = orch1.select_agent(&ctx1);
        let agent2 = orch2.select_agent(&ctx2);

        prop_assert_eq!(agent1, agent2,
            "Swarm routing must be deterministic for same input: app='{}' prompt='{}'",
            app_name, prompt);
    }

    // ──────────────────────────────────────────────────────────
    // Property 3: ConfidenceBand compute() covers all branches
    //   without panic on any (prompt_len, doc_kind) combination
    // ──────────────────────────────────────────────────────────
    #[test]
    fn confidence_band_never_panics(
        prompt in "\\PC{0,500}",
        doc_kind in prop::sample::select(vec!["Word", "PowerPoint", "CodeFile", "Unknown", "PlainText"])
    ) {
        let _band = ConfidenceBand::compute(&prompt, doc_kind);
    }

    // ──────────────────────────────────────────────────────────
    // Property 4: Config TOML round-trip is lossless
    //   serialize → deserialize → must equal original
    // ──────────────────────────────────────────────────────────
    #[test]
    fn config_roundtrip_lossless(
        hotkey in "[a-z+]{3,20}",
        delay in 0u64..500u64
    ) {
        use phantom_core::config::PhantomConfig;
        let mut cfg = PhantomConfig::default();
        cfg.hotkey = hotkey.clone();
        cfg.typing_delay_ms = delay;

        let serialized = toml::to_string_pretty(&cfg).expect("serialize");
        let deserialized: PhantomConfig = toml::from_str(&serialized).expect("deserialize");

        prop_assert_eq!(deserialized.hotkey, hotkey);
        prop_assert_eq!(deserialized.typing_delay_ms, delay);
    }
}

// ──────────────────────────────────────────────────────────────
// Property 2: DocumentContext NEVER panics on any UTF-8 input
//   Runs in its own block with 200 cases to keep CI fast.
//   10k chars × 200 cases = 2M chars — sufficient coverage.
// ──────────────────────────────────────────────────────────────
proptest! {
    #![proptest_config(ProptestConfig::with_cases(200))]

    #[test]
    fn document_context_never_panics(
        text in "\\PC{0,10000}"
    ) {
        // Must not panic regardless of content (Unicode, null bytes, extreme length)
        let _ctx = DocumentContext::from_plain_text("TestApp", &text, "test prompt");
    }
}
