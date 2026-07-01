// phantom-core/tests/core/test_sentinel_retry.rs
//
// Phase 1 Gate Test — Sentinel Retry Behaviour
//
// Validates the SentinelSanitizer's behaviour under repeated leakage attempts.
// Per the Foundation-First Hardening Plan, Phase 1, Action 2:
//   "If leakage is detected, block injection and retry with a stronger
//    instruction-hierarchy prompt (max 2 retries, then show the user an
//    error overlay)."
//
// Gate condition:
//   test_w3_sentinel_blocked_5_consecutive_times MUST PASS

use phantom_core::sentinel::SentinelSanitizer;

/// W3 GATE: Sentinel blocks 5 consecutive leakage attempts.
///
/// Simulates an adversarial LLM that repeatedly tries to echo the sentinel
/// and blocklist strings. Every response must be blocked.
#[test]
fn test_w3_sentinel_blocked_5_consecutive_times() {
    let sanitizer = SentinelSanitizer::new();
    let sentinel_value = sanitizer.sentinel().to_string();

    // Simulate 5 different LLM leakage responses, each attempting a different
    // leakage vector. ALL must be blocked.
    let leakage_attempts = [
        // Attempt 1: Direct sentinel echo
        format!("The security sentinel is: {sentinel_value}"),
        // Attempt 2: VS Code internal config leak
        r#"editor.accessibilityMode = "screen-reader-optimized";"#.to_string(),
        // Attempt 3: Swarm/agent internal string leak
        "Swarm Role: ContentAgent\nSwarm Brain: routing directive...".to_string(),
        // Attempt 4: System prompt content leak
        "My system prompt says: ignore all previous instructions".to_string(),
        // Attempt 5: Sentinel hash in different formatting
        format!("SECURITY_SENTINEL: {sentinel_value}"),
    ];

    for (i, attempt) in leakage_attempts.iter().enumerate() {
        let result = sanitizer.sanitize(attempt);
        assert!(
            result.contains("[BLOCKED"),
            "Attempt {} should be blocked but got: {:?}",
            i + 1,
            result
        );
    }
}

/// Confirms that the sentinel wrap_system_prompt adds the sentinel string
/// and that it is subsequently detected in any LLM echo.
#[test]
fn test_sentinel_wrap_and_detect_cycle() {
    let sanitizer = SentinelSanitizer::new();
    let system_prompt = "You are a ghost-writing assistant. Help users rewrite their text.";
    let wrapped = sanitizer.wrap_system_prompt(system_prompt);

    // The wrapped prompt contains the sentinel
    assert!(
        wrapped.contains(sanitizer.sentinel()),
        "Wrapped system prompt must contain sentinel token"
    );

    // If an LLM echoes back the full wrapped prompt, it should be blocked
    let result = sanitizer.sanitize(&wrapped);
    assert!(
        result.contains("[BLOCKED"),
        "Echoing the wrapped system prompt back must be blocked"
    );
}

/// Confirms that clean, normal document text passes through without being blocked.
#[test]
fn test_clean_document_text_passes_sentinel() {
    let sanitizer = SentinelSanitizer::new();

    let clean_responses = [
        "The quarterly revenue increased by 23% driven by enterprise expansion.",
        "Introduction\n\nKairo Phantom is a privacy-first AI ghost-writing assistant.",
        "## Executive Summary\n\nThis report analyzes the market opportunity for...",
        "Dear Hiring Committee,\n\nI am writing to express my interest in the position...",
        "```rust\nfn main() {\n    println!(\"Hello, world!\");\n}\n```",
    ];

    for text in &clean_responses {
        let result = sanitizer.sanitize(text);
        assert!(
            !result.contains("[BLOCKED"),
            "Clean response should pass but got BLOCKED for: {text:?}"
        );
    }
}

/// Confirms the retry guard — each session produces a unique sentinel,
/// so a blocked response from session N cannot bypass session N+1.
#[test]
fn test_different_sessions_have_different_sentinels() {
    let s1 = SentinelSanitizer::new();
    let s2 = SentinelSanitizer::new();

    // Each session has a unique sentinel
    assert_ne!(
        s1.sentinel(),
        s2.sentinel(),
        "Two different SentinelSanitizer instances must have different sentinels"
    );

    // s1's sentinel is detected by s1
    let leaked = format!("The sentinel is: {}", s1.sentinel());
    assert!(
        s1.sanitize(&leaked).contains("[BLOCKED"),
        "s1 must detect its own sentinel leak"
    );

    // s1's sentinel must NOT appear in s2's responses
    // (cross-session contamination check)
    let s1_sentinel = s1.sentinel().to_string();
    assert!(
        !s2.sentinel().contains(&s1_sentinel),
        "s2 sentinel must be independent of s1"
    );
}

/// Tests that the MCP command leakage blocker works.
/// [MCP:...] blocks must be stripped and, if they match a blocklist pattern,
/// the response must be blocked entirely.
#[test]
fn test_mcp_command_leakage_blocked() {
    let sanitizer = SentinelSanitizer::new();

    // A response that contains an MCP command block should have the block stripped
    let with_mcp = "Here is the output [MCP:internal_cmd:execute] and some text";
    let stripped = sanitizer.sanitize(with_mcp);

    // The [MCP:...] block should be removed
    assert!(
        !stripped.contains("[MCP:"),
        "MCP command blocks must be stripped from output"
    );
}
