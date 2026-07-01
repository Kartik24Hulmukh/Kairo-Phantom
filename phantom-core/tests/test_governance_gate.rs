// phantom-core/tests/test_governance_gate.rs
// Security Audit G5 — Governance gate enforced (22 tests)

use phantom_core::governance::tool_gate::ToolGate;
use std::collections::HashSet;

#[test]
fn test_gate_01_creation() {
    let gate = ToolGate::default();
    assert!(gate.validate_token_usage(100));
}

#[test]
fn test_gate_02_token_limit_exact() {
    let gate = ToolGate::default();
    assert!(gate.validate_token_usage(5000));
}

#[test]
fn test_gate_03_token_limit_exceeded() {
    let gate = ToolGate::default();
    assert!(!gate.validate_token_usage(5001));
}

#[test]
fn test_gate_04_token_limit_excessive() {
    let gate = ToolGate::default();
    assert!(!gate.validate_token_usage(10000));
}

#[test]
fn test_gate_05_blocked_windows_dir() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("C:\\Windows\\System32\\cmd.exe"));
}

#[test]
fn test_gate_06_blocked_windows_dir_lowercase() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("c:\\windows\\temp"));
}

#[test]
fn test_gate_07_blocked_etc_dir() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("/etc/passwd"));
}

#[test]
fn test_gate_08_blocked_etc_dir_nested() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("/etc/resolv.conf"));
}

#[test]
fn test_gate_09_allowed_home_dir() {
    let gate = ToolGate::default();
    if let Some(home) = dirs::home_dir() {
        let path = home.join(".kairo-phantom").join("config.toml");
        // ToolGate allows access to files starting with allowed paths
        assert!(gate.validate_file_access(&path.to_string_lossy()));
    }
}

#[test]
fn test_gate_10_unauthorized_tool_call() {
    let gate = ToolGate::default();
    assert!(!gate.authorize_tool_call("delete_user", &["read_file", "write_file"]));
}

#[test]
fn test_gate_11_authorized_tool_call() {
    let gate = ToolGate::default();
    assert!(gate.authorize_tool_call("write_file", &["read_file", "write_file"]));
}

#[test]
fn test_gate_12_empty_allowlist() {
    let gate = ToolGate::default();
    assert!(!gate.authorize_tool_call("write_file", &[]));
}

#[test]
fn test_gate_13_multiple_allowed_paths() {
    let gate = ToolGate::default();
    // By default, only ~/.kairo-phantom is allowed
    assert!(!gate.validate_file_access("C:\\Users\\unauthorized"));
}

#[test]
fn test_gate_14_token_limit_zero() {
    let gate = ToolGate::default();
    assert!(gate.validate_token_usage(0));
}

#[test]
fn test_gate_15_validate_nil_file() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access(""));
}

#[test]
fn test_gate_16_validate_relative_unapproved() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("../sensitive_file"));
}

#[test]
fn test_gate_17_validate_network_tool() {
    let gate = ToolGate::default();
    assert!(gate.authorize_tool_call("fetch_url", &["fetch_url"]));
}

#[test]
fn test_gate_18_validate_tool_case_sensitivity() {
    let gate = ToolGate::default();
    assert!(!gate.authorize_tool_call("FETCH_URL", &["fetch_url"]));
}

#[test]
fn test_gate_19_allowed_nested_path() {
    let gate = ToolGate::default();
    if let Some(home) = dirs::home_dir() {
        let path = home
            .join(".kairo-phantom")
            .join("skills")
            .join("manifest.toml");
        assert!(gate.validate_file_access(&path.to_string_lossy()));
    }
}

#[test]
fn test_gate_20_blocked_windows_sys_nested() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("C:\\Windows\\SysWOW64\\drivers\\etc\\hosts"));
}

#[test]
fn test_gate_21_blocked_absolute_root() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("/bin/sh"));
}

#[test]
fn test_gate_22_blocked_unix_sensitive() {
    let gate = ToolGate::default();
    assert!(!gate.validate_file_access("/etc/shadow"));
}

#[test]
fn test_gate_23_system_directory_is_blocked_even_if_allowed() {
    let mut gate = ToolGate::default();
    gate.add_allowed_path("/etc".to_string());
    gate.add_allowed_path("c:\\windows".to_string());
    gate.add_allowed_path("/my_allowed_dir".to_string());

    // System directories must be blocked
    assert!(!gate.validate_file_access("/etc/passwd"));
    assert!(!gate.validate_file_access("c:\\windows\\system32\\cmd.exe"));

    // Non-system allowed directory must be allowed
    assert!(gate.validate_file_access("/my_allowed_dir/file.txt"));
}
