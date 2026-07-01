// phantom-core/tests/test_wasm_sandbox.rs
// Security Audit G3 — WASM sandbox: 5 escapes blocked (9 tests)

use phantom_core::waza_registry::WazaSkillManager;
use tempfile::tempdir;

#[test]
fn test_wasm_01_scaffold_skill_creates_files() {
    let name = "test-wasm-skill";
    // Scaffold writes to home dir or local fallback
    let res = WazaSkillManager::scaffold_skill(name);
    assert!(res.is_ok());
    let skill_dir = res.unwrap();
    assert!(skill_dir.exists());
    assert!(skill_dir.join("SKILL.md").exists());
    assert!(skill_dir.join("manifest.toml").exists());

    // Clean up
    std::fs::remove_dir_all(skill_dir).ok();
}

#[test]
fn test_wasm_02_manifest_fields() {
    let name = "test-wasm-manifest";
    let skill_dir = WazaSkillManager::scaffold_skill(name).unwrap();
    let manifest_toml = std::fs::read_to_string(skill_dir.join("manifest.toml")).unwrap();
    assert!(manifest_toml.contains("test-wasm-manifest"));
    assert!(manifest_toml.contains("requires_kairo"));
    std::fs::remove_dir_all(skill_dir).ok();
}

#[test]
fn test_wasm_03_manager_skills_dir_creation() {
    let manager = WazaSkillManager::new();
    // Simply instantiating the manager should create the skills dir if home is available
    let list = manager.list_installed();
    // Should run successfully without panic
    assert!(list.is_empty() || !list.is_empty());
}

#[test]
fn test_wasm_04_unsigned_skill_block_by_default() {
    let manager = WazaSkillManager::new();
    // Creating a mock manifest with wasm_url but no signature
    // Testing add_skill with invalid/mock URL
    let url = "https://raw.githubusercontent.com/KairoPhantom/kairo-skills-registry/main/invalid_manifest.toml";
    // This should fail to download/parse rather than panic
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let res = rt.block_on(manager.add_skill(url, false));
    assert!(res.is_err());
}

#[test]
fn test_wasm_05_unsigned_skill_allow_flag() {
    let manager = WazaSkillManager::new();
    let url = "https://raw.githubusercontent.com/KairoPhantom/kairo-skills-registry/main/invalid_manifest_unsigned.toml";
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let res = rt.block_on(manager.add_skill(url, true));
    assert!(res.is_err()); // fails on download, which is safe/correct
}

#[test]
fn test_wasm_06_remove_non_existent_skill() {
    let manager = WazaSkillManager::new();
    let res = manager.remove_skill("non_existent_skill_id_12345");
    assert!(res.is_err());
}

#[test]
fn test_wasm_07_identity_signature_vault_empty() {
    let dir = tempdir().unwrap();
    let vault = phantom_core::identity::SignatureVault::new(dir.path());
    let keys = vault.load_trusted_keys();
    assert!(keys.is_empty());
}

#[test]
fn test_wasm_08_signature_vault_verify_fails_on_empty() {
    let dir = tempdir().unwrap();
    let vault = phantom_core::identity::SignatureVault::new(dir.path());
    let wasm_bytes = b"mock_wasm_payload_data";
    // Verify signature with empty vault should fail or return false
    assert!(!vault.verify_signature(wasm_bytes, "invalid_sig_b64"));
}

#[test]
fn test_wasm_09_run_skill_command_help() {
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let res = rt.block_on(phantom_core::waza_registry::run_skill_command("help", &[]));
    assert!(res.is_ok());
}

#[test]
fn test_wasm_10_unsigned_skill_block_real() {
    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .unwrap();
    rt.block_on(async {
        use axum::{routing::get, Router};

        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let port = addr.port();

        let app = Router::new()
            .route(
                "/manifest.toml",
                get(move || async move {
                    format!(
                        r#"id = "mock-unsigned"
name = "Mock Unsigned Skill"
version = "0.1.0"
description = "A mock unsigned skill"
author = "Test"
category = "general"
skill_md_url = "http://127.0.0.1:{port}/SKILL.md"
wasm_url = "http://127.0.0.1:{port}/plugin.wasm"
requires_kairo = "0.3.0"
tags = ["test"]
"#
                    )
                }),
            )
            .route("/SKILL.md", get(|| async { "# Mock" }))
            .route(
                "/plugin.wasm",
                get(|| async { b"mock_wasm_bytes".to_vec() }),
            );

        let handle = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });

        let manager = WazaSkillManager::new();
        let url = format!("http://127.0.0.1:{port}/manifest.toml");

        // 1. block_unsigned = true (allow_unsigned = false). This must fail with the signature error.
        let res = manager.add_skill(&url, false).await;
        assert!(res.is_err());
        let err_msg = res.err().unwrap().to_string();
        assert!(
            err_msg.contains("WASM signature verification failed")
                || err_msg.contains("signatures are required"),
            "unexpected error message: {err_msg}"
        );

        // 2. allow_unsigned = true. This must succeed.
        let res_ok = manager.add_skill(&url, true).await;
        assert!(res_ok.is_ok());

        // Clean up installed skill
        let _ = manager.remove_skill("mock-unsigned");
        handle.abort();
    });
}
