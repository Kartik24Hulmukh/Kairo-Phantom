// phantom-core/tests/test_e2e_task_completion.rs
//
// Item 22 — E2E Task Completion CI Gate
//
// Runs synthetic task-completion scenarios against Kairo's core logic
// (offline, no real display session required) and publishes a
// `task_completion_rate.json` file.
//
// CI gate: the test fails if the completion rate falls below 80%.

use std::collections::HashMap;

/// The minimum required task completion rate.
const MIN_COMPLETION_RATE: f64 = 0.80;
/// Output path for the published JSON report.
const REPORT_PATH: &str = "task_completion_rate.json";

// ─── Task Scenario ────────────────────────────────────────────────────────────

#[derive(Debug)]
struct Scenario {
    name: &'static str,
    /// Run the scenario. Returns true = task completed, false = task failed.
    run: fn() -> bool,
}

// ─── Scenario Implementations ─────────────────────────────────────────────────

/// S1: Response Validator correctly blocks irrelevant response.
fn scenario_irrelevance_block() -> bool {
    use phantom_core::response_validator::{ResponseValidator, ValidationResult};
    let v = ResponseValidator::new();
    let result = v.validate(
        "Configure database centroids",
        "Yellow birds fly over green meadows fast",
    );
    matches!(result, ValidationResult::Irrelevant { .. })
}

/// S2: Response Validator correctly blocks hallucinated turns.
fn scenario_hallucination_block() -> bool {
    use phantom_core::response_validator::{ResponseValidator, ValidationResult};
    let v = ResponseValidator::new();
    let response = "Sure!\nUser: Can you help me?\nAssistant: Of course I can!";
    let result = v.validate("Write a summary", response);
    matches!(result, ValidationResult::HallucinatedTurns { .. })
}

/// S3: Truncated response blocked.
fn scenario_truncation_block() -> bool {
    use phantom_core::response_validator::{ResponseValidator, ValidationResult};
    let v = ResponseValidator::new();
    let result = v.validate("Write a 500 word essay", "Ok");
    matches!(result, ValidationResult::Truncated)
}

/// S4: Clean, relevant response passes.
fn scenario_clean_response_passes() -> bool {
    use phantom_core::response_validator::{ResponseValidator, ValidationResult};
    let v = ResponseValidator::new();
    let result = v.validate(
        "Write a summary",
        "Here is a concise summary of the key points.",
    );
    matches!(result, ValidationResult::Valid)
}

/// S5: Confidence engine abstains on low-signal input.
fn scenario_confidence_abstain() -> bool {
    use phantom_core::memory::feedback::ConfidenceEngine;
    let score = ConfidenceEngine::unified_confidence("Unknown", "", &[], 0, "hmm", 0.0, false);
    score.should_abstain
}

/// S6: Confidence engine does NOT abstain on rich context.
fn scenario_confidence_high_signal() -> bool {
    use phantom_core::memory::feedback::ConfidenceEngine;
    let score = ConfidenceEngine::unified_confidence(
        "Microsoft Word",
        "prose response here.",
        &[],
        1000,
        "write a summary",
        0.9,
        true,
    );
    !score.should_abstain
}

/// S7: Provenance receipt chain stays valid after multiple emissions.
fn scenario_receipt_chain_valid() -> bool {
    use tempfile::tempdir;
    let dir = match tempdir() {
        Ok(d) => d,
        Err(_) => return false,
    };
    let path = dir.path().join("receipts.jsonl");
    let identity = phantom_core::identity::AgentIdentity::generate("CIAgent", "ci");
    let log = phantom_core::identity::ReceiptLog::new(path);
    log.emit(&identity, "generate_response", "doc.docx", "ok");
    log.emit(&identity, "apply_edit", "doc.docx", "ok");
    log.emit(&identity, "generate_response", "slide.pptx", "rejected");
    log.verify_chain() == 0
}

/// S8: Provenance receipt tamper detection fires.
fn scenario_receipt_tamper_detected() -> bool {
    use tempfile::tempdir;
    let dir = match tempdir() {
        Ok(d) => d,
        Err(_) => return false,
    };
    let path = dir.path().join("receipts.jsonl");
    let identity = phantom_core::identity::AgentIdentity::generate("TamperCI", "ci");
    let log = phantom_core::identity::ReceiptLog::new(path.clone());
    log.emit(&identity, "action_a", "file.docx", "ok");
    log.emit(&identity, "action_b", "file.docx", "ok");

    // Corrupt second line
    let contents = std::fs::read_to_string(&path).unwrap_or_default();
    let mut lines: Vec<String> = contents.lines().map(|s| s.to_string()).collect();
    if lines.len() >= 2 {
        lines[1] = lines[1].replace("\"outcome\":\"ok\"", "\"outcome\":\"tampered\"");
        let new_contents = lines.join("\n") + "\n";
        if std::fs::write(&path, new_contents).is_err() {
            return false;
        }
        let log2 = phantom_core::identity::ReceiptLog::new(path);
        return log2.verify_chain() > 0;
    }
    false
}

/// S9: Audit chain TamperEvidentAuditLog stays clean after 2 entries.
fn scenario_audit_chain_clean() -> bool {
    use tempfile::tempdir;
    let dir = match tempdir() {
        Ok(d) => d,
        Err(_) => return false,
    };
    let path = dir.path().join("audit.jsonl");
    let identity = phantom_core::identity::AgentIdentity::generate("AuditCI", "ci");
    let log = phantom_core::identity::TamperEvidentAuditLog::new(path);
    log.append(&identity, "user1", "read", "file.docx", "allowed");
    log.append(&identity, "user1", "write", "file.docx", "allowed");
    log.verify_chain() == 0
}

/// S10: Constitution violation detected.
fn scenario_constitution_violation_detected() -> bool {
    use phantom_core::response_validator::{ResponseValidator, ValidationResult};
    let mut v = ResponseValidator::new();
    v.constitution = vec!["never say \"banana\"".to_string()];
    let result = v.validate("test", "This is a banana.");
    matches!(result, ValidationResult::ConstitutionViolation { .. })
}

// ─── CI Gate Test ─────────────────────────────────────────────────────────────

#[test]
fn test_task_completion_rate_ci_gate() {
    let scenarios: Vec<Scenario> = vec![
        Scenario {
            name: "irrelevance_block",
            run: scenario_irrelevance_block,
        },
        Scenario {
            name: "hallucination_block",
            run: scenario_hallucination_block,
        },
        Scenario {
            name: "truncation_block",
            run: scenario_truncation_block,
        },
        Scenario {
            name: "clean_response_passes",
            run: scenario_clean_response_passes,
        },
        Scenario {
            name: "confidence_abstain",
            run: scenario_confidence_abstain,
        },
        Scenario {
            name: "confidence_high_signal",
            run: scenario_confidence_high_signal,
        },
        Scenario {
            name: "receipt_chain_valid",
            run: scenario_receipt_chain_valid,
        },
        Scenario {
            name: "receipt_tamper_detected",
            run: scenario_receipt_tamper_detected,
        },
        Scenario {
            name: "audit_chain_clean",
            run: scenario_audit_chain_clean,
        },
        Scenario {
            name: "constitution_violation",
            run: scenario_constitution_violation_detected,
        },
    ];

    let total = scenarios.len();
    let mut results: HashMap<String, bool> = HashMap::new();

    for s in &scenarios {
        let passed = (s.run)();
        println!(
            "[E2E CI] {} → {}",
            s.name,
            if passed { "PASS" } else { "FAIL" }
        );
        results.insert(s.name.to_string(), passed);
    }

    let passed = results.values().filter(|&&v| v).count();
    let rate = passed as f64 / total as f64;

    // Publish task_completion_rate.json
    let report = serde_json::json!({
        "total_scenarios": total,
        "passed": passed,
        "failed": total - passed,
        "completion_rate": rate,
        "min_required": MIN_COMPLETION_RATE,
        "gate_passed": rate >= MIN_COMPLETION_RATE,
        "results": results,
        "generated_at": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
    });

    let json_str = serde_json::to_string_pretty(&report).unwrap_or_default();
    std::fs::write(REPORT_PATH, &json_str).expect("Failed to write task_completion_rate.json");

    println!(
        "\n📊 E2E Task Completion Rate: {}/{} = {:.1}% (min required: {:.0}%)",
        passed,
        total,
        rate * 100.0,
        MIN_COMPLETION_RATE * 100.0
    );
    println!("📄 Report written to: {REPORT_PATH}");

    // CI gate — fail if below threshold
    assert!(
        rate >= MIN_COMPLETION_RATE,
        "❌ E2E task completion rate {:.1}% is below the minimum required {:.0}%. \
         See {} for details.",
        rate * 100.0,
        MIN_COMPLETION_RATE * 100.0,
        REPORT_PATH
    );
}
