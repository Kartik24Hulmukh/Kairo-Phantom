use base64::Engine as _;
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use std::fs;
use std::process::Command;

pub struct FactsVerifier;

fn is_vacuous_command(cmd_str: &str) -> bool {
    let lower = cmd_str.to_lowercase();
    if lower.contains("--version") || cmd_str.contains("-V") {
        return true;
    }
    for word in cmd_str.split_whitespace() {
        let w = word.trim_matches(|c: char| !c.is_alphanumeric());
        if w == "true" || w == "echo" {
            return true;
        }
    }
    false
}

fn parse_pem_to_der(pem: &str) -> Result<Vec<u8>, String> {
    let mut in_block = false;
    let mut base64_str = String::new();
    for line in pem.lines() {
        let line = line.trim();
        if line.starts_with("-----BEGIN") {
            in_block = true;
        } else if line.starts_with("-----END") {
            in_block = false;
        } else if in_block {
            base64_str.push_str(line);
        }
    }
    if base64_str.is_empty() {
        return Err("No PEM block found".to_string());
    }
    let der = base64::engine::general_purpose::STANDARD
        .decode(base64_str.as_bytes())
        .map_err(|e| format!("Failed to decode base64: {e}"))?;
    Ok(der)
}

fn verify_oracles_signature() -> Result<(), String> {
    let root = if std::path::Path::new("../Kairo.facts").exists() {
        ".."
    } else {
        "."
    };

    let sidecar_dir = std::path::Path::new(root)
        .join("kairo-sidecar")
        .join("sidecar");
    let oracles_path = sidecar_dir.join("oracles.py");
    let pub_path = sidecar_dir.join("oracles.py.pub");
    let sig_path = sidecar_dir.join("oracles.py.sig");

    if !oracles_path.exists() {
        return Err("Module oracles.py is missing!".to_string());
    }
    if !pub_path.exists() {
        return Err("Public key oracles.py.pub is missing!".to_string());
    }
    if !sig_path.exists() {
        return Err("Signature oracles.py.sig is missing!".to_string());
    }

    let oracles_bytes =
        fs::read(&oracles_path).map_err(|e| format!("Failed to read oracles.py: {e}"))?;
    let pub_bytes =
        fs::read(&pub_path).map_err(|e| format!("Failed to read oracles.py.pub: {e}"))?;
    let sig_bytes =
        fs::read(&sig_path).map_err(|e| format!("Failed to read oracles.py.sig: {e}"))?;

    let pub_pem =
        String::from_utf8(pub_bytes).map_err(|e| format!("Invalid public key encoding: {e}"))?;

    let der_bytes = parse_pem_to_der(&pub_pem)?;
    if der_bytes.len() < 32 {
        return Err("Invalid public key DER length".to_string());
    }
    let raw_pub_bytes = &der_bytes[der_bytes.len() - 32..];

    let verifying_key = VerifyingKey::try_from(raw_pub_bytes)
        .map_err(|e| format!("Failed to parse public key: {e}"))?;

    let signature =
        Signature::from_slice(&sig_bytes).map_err(|e| format!("Failed to parse signature: {e}"))?;

    verifying_key
        .verify(&oracles_bytes, &signature)
        .map_err(|e| format!("Oracles signature verification failed: {e}"))?;

    Ok(())
}

impl FactsVerifier {
    pub fn verify_all() -> Result<bool, String> {
        if let Err(e) = verify_oracles_signature() {
            println!("Verification FAILED: Cryptographic signature verification failed: {e}");
            return Ok(false);
        }

        let facts_path = if std::path::Path::new("../Kairo.facts").exists() {
            "../Kairo.facts"
        } else {
            "Kairo.facts"
        };
        let content = fs::read_to_string(facts_path)
            .map_err(|e| format!("Failed to read {facts_path}: {e}"))?;

        let mut implemented = 0;
        let mut specs = 0;
        let mut drafts = 0;
        let mut _passed = 0;
        let mut _failed = 0;

        let mut current_fact_type = "";

        for line in content.lines() {
            let line = line.trim();
            if line.starts_with("@implemented:") {
                implemented += 1;
                current_fact_type = "implemented";
            } else if line.starts_with("@spec:") {
                specs += 1;
                current_fact_type = "spec";
            } else if line.starts_with("@draft:") {
                drafts += 1;
                current_fact_type = "draft";
            } else if line.starts_with("command:") && current_fact_type == "implemented" {
                let cmd_str = line.trim_start_matches("command:").trim();
                if cmd_str.is_empty() || is_vacuous_command(cmd_str) {
                    println!("Verification FAILED: Vacuous or empty command found: '{cmd_str}'");
                    _failed += 1;
                } else {
                    let parts: Vec<&str> = cmd_str.split_whitespace().collect();
                    if !parts.is_empty() {
                        let mut cmd = Command::new(parts[0]);
                        cmd.args(&parts[1..]);
                        match cmd.status() {
                            Ok(status) if status.success() => _passed += 1,
                            _ => _failed += 1,
                        }
                    }
                }
            }
        }

        let total_valid = implemented + specs + drafts;
        let readiness = if total_valid > 0 {
            (implemented as f64 / total_valid as f64) * 100.0
        } else {
            0.0
        };

        println!("Kairo Phantom v4.0: {implemented}/{total_valid} facts implemented, {specs} specs in progress, {drafts} drafts. Production readiness: {readiness:.1}%.");

        if implemented < 35 {
            println!("Verification FAILED: Implemented facts count is {implemented} (need >= 35).");
            return Ok(false);
        }
        if total_valid < 40 {
            println!("Verification FAILED: Total facts count is {total_valid} (need >= 40).");
            return Ok(false);
        }
        if _failed > 0 {
            println!("Verification FAILED: {_failed} commands failed.");
            Ok(false)
        } else {
            println!("Verification PASSED.");
            Ok(true)
        }
    }
}
