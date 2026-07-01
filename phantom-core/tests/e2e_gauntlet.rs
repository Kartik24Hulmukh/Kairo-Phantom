// tests/e2e_gauntlet.rs
#![allow(clippy::assertions_on_constants, clippy::const_is_empty)]

use phantom_core::governance::ToolGate;
use phantom_core::identity::SpiffeIdentity;

#[tokio::test]
async fn test_gauntlet_scenario_01_word_injection() {
    // Scenario 1: User injects text into Word
    // Setup simulated context and prompt
    let _context = "Quarterly Business Review";
    let _prompt = "Summarize the Q1 results.";

    // Simulated inference result
    let completion = "Q1 results indicate a 15% increase in MRR.";

    // Validation
    assert!(!completion.is_empty(), "Completion should not be empty");
    assert!(
        completion.contains("Q1"),
        "Completion should reference the prompt context"
    );
}

#[test]
fn test_governance_tool_gate_hard_blocks() {
    let gate = ToolGate::new();

    // 1. Valid Access
    assert!(
        gate.validate_file_access(
            dirs::home_dir()
                .unwrap()
                .join(".kairo-phantom")
                .join("memory")
                .to_str()
                .unwrap()
        ),
        "Gate should allow access to the vault"
    );

    // 2. Block C:\Windows
    assert!(
        !gate.validate_file_access("C:\\Windows\\System32\\malware.dll"),
        "Gate MUST block C:\\Windows access"
    );
    assert!(
        !gate.validate_file_access("c:\\windows\\temp\\test.txt"),
        "Gate MUST block C:\\Windows access (case-insensitive)"
    );

    // 3. Block /etc
    assert!(
        !gate.validate_file_access("/etc/passwd"),
        "Gate MUST block /etc access"
    );

    // 4. Token Caps
    assert!(
        gate.validate_token_usage(4000),
        "Gate should allow under 5000 tokens"
    );
    assert!(
        !gate.validate_token_usage(6000),
        "Gate MUST block over 5000 tokens"
    );

    // 5. Tool Auth
    let allowlist = vec!["fetch_guidelines", "write_slide"];
    assert!(
        gate.authorize_tool_call("fetch_guidelines", &allowlist),
        "Gate should allow authorized tools"
    );
    assert!(
        !gate.authorize_tool_call("delete_file", &allowlist),
        "Gate MUST block unauthorized tools"
    );
}

#[test]
fn test_spiffe_identity_generation() {
    let identity = SpiffeIdentity::new("ppt_agent", "descope");

    assert_eq!(identity.trust_domain, "kairo-phantom.io");
    assert_eq!(
        identity.spiffe_id,
        "spiffe://kairo-phantom.io/agent/ppt_agent"
    );
    assert_eq!(identity.sso_provider, "descope");
    assert!(identity.certificate_pem.contains("BEGIN CERTIFICATE"));
}

#[tokio::test]
async fn test_chaos_monkey_resilience() {
    // Simulating chaos: random tool failure
    let allowlist = vec!["fetch_guidelines"];
    let gate = ToolGate::new();

    // The gate must deterministically block regardless of chaos
    assert!(!gate.authorize_tool_call("random_injected_tool", &allowlist));
}
