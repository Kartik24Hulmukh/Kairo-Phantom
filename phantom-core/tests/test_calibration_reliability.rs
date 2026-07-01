// phantom-core/tests/test_calibration_reliability.rs
//
// Item 27 — Calibrated Uncertainty & Reliability Output
//
// Produces:
//   1. calibration_data.json — raw and calibrated scores with accuracy buckets
//   2. reliability_report.md  — markdown table of calibration data
//   3. Validates Platt-scaling coefficients keep the diagonal close

use phantom_core::memory::feedback::ConfidenceEngine;

/// Output path for calibration JSON
const CALIBRATION_JSON: &str = "calibration_data.json";
/// Output path for markdown report
const CALIBRATION_REPORT: &str = "reliability_report.md";

/// Synthetic calibration dataset: (raw_confidence, was_accurate)
/// Represents a sample of 100 simulated Kairo predictions.
/// These are deterministic synthetic runs — no real LLM calls.
fn calibration_dataset() -> Vec<(f32, bool)> {
    vec![
        // Low confidence scenarios — mostly inaccurate
        (0.05, false),
        (0.10, false),
        (0.12, true),
        (0.15, false),
        (0.18, false),
        (0.20, true),
        (0.22, false),
        (0.25, true),
        (0.28, false),
        (0.30, true),
        (0.32, false),
        (0.35, false),
        (0.37, true),
        (0.40, true),
        (0.42, false),
        (0.44, true),
        (0.45, true),
        (0.48, false),
        (0.50, true),
        (0.50, true),
        // Medium confidence — mixed
        (0.52, true),
        (0.54, true),
        (0.55, false),
        (0.58, true),
        (0.60, true),
        (0.62, true),
        (0.63, false),
        (0.65, true),
        (0.67, true),
        (0.68, true),
        (0.70, false),
        (0.72, true),
        (0.73, true),
        (0.74, true),
        (0.75, true),
        (0.76, false),
        (0.77, true),
        (0.78, true),
        (0.79, true),
        (0.80, true),
        // High confidence — mostly accurate
        (0.80, true),
        (0.82, true),
        (0.83, true),
        (0.84, false),
        (0.85, true),
        (0.86, true),
        (0.87, true),
        (0.88, true),
        (0.89, true),
        (0.90, false),
        (0.90, true),
        (0.91, true),
        (0.92, true),
        (0.93, true),
        (0.94, true),
        (0.95, true),
        (0.96, true),
        (0.97, true),
        (0.98, true),
        (0.99, true),
        // Additional medium-range samples for richer calibration curve
        (0.30, false),
        (0.35, true),
        (0.40, true),
        (0.45, false),
        (0.50, false),
        (0.55, true),
        (0.60, true),
        (0.65, true),
        (0.70, true),
        (0.75, true),
        (0.80, true),
        (0.85, true),
        (0.90, true),
        (0.92, true),
        (0.95, true),
        (0.97, true),
        (0.20, false),
        (0.25, false),
        (0.30, true),
        (0.35, false),
        (0.40, true),
        (0.45, true),
        (0.50, true),
        (0.55, true),
        (0.60, true),
        (0.65, true),
        (0.70, true),
        (0.75, false),
        (0.80, true),
        (0.85, true),
        (0.88, true),
        (0.92, true),
        (0.10, false),
        (0.15, false),
        (0.20, false),
        (0.30, true),
        (0.40, false),
        (0.50, true),
        (0.60, true),
        (0.70, true),
    ]
}

/// Group scores into bins and compute empirical accuracy per bin.
fn compute_reliability_bins(data: &[(f32, bool)]) -> Vec<(f32, f32, usize)> {
    let n_bins = 10usize;
    let mut bins: Vec<(f64, usize, usize)> = vec![(0.0, 0, 0); n_bins];

    for &(raw, accurate) in data {
        let calibrated = ConfidenceEngine::calibrate(raw);
        let bin_idx = ((calibrated * n_bins as f32) as usize).min(n_bins - 1);
        bins[bin_idx].0 += calibrated as f64;
        bins[bin_idx].2 += 1; // total in bucket
        if accurate {
            bins[bin_idx].1 += 1; // correct in bucket
        }
    }

    bins.into_iter()
        .enumerate()
        .filter(|(_, (_, _, total))| *total > 0)
        .map(|(i, (sum, correct, total))| {
            let mean_conf = (sum / total as f64) as f32;
            let accuracy = correct as f32 / total as f32;
            (mean_conf, accuracy, total)
        })
        .collect()
}

#[test]
fn test_calibration_generates_reliability_data() {
    let data = calibration_dataset();
    let bins = compute_reliability_bins(&data);

    assert!(!bins.is_empty(), "Reliability bins should not be empty");

    // Build JSON report
    let bin_json: Vec<serde_json::Value> = bins
        .iter()
        .map(|(conf, acc, n)| {
            serde_json::json!({
                "mean_confidence": conf,
                "empirical_accuracy": acc,
                "sample_count": n,
                "calibration_error": (conf - acc).abs(),
            })
        })
        .collect();

    // Compute ECE (Expected Calibration Error)
    let total_samples: usize = bins.iter().map(|(_, _, n)| *n).sum();
    let ece: f32 = bins
        .iter()
        .map(|(conf, acc, n)| (conf - acc).abs() * (*n as f32 / total_samples as f32))
        .sum();

    let report_json = serde_json::json!({
        "calibration_method": "platt_scaling",
        "coefficients": { "slope": 0.88, "intercept": 0.06 },
        "abstention_threshold": 0.60,
        "total_samples": total_samples,
        "expected_calibration_error": ece,
        "bins": bin_json,
        "generated_at": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
    });

    let json_str = serde_json::to_string_pretty(&report_json).unwrap();
    std::fs::write(CALIBRATION_JSON, &json_str).expect("Failed to write calibration_data.json");

    // Build Markdown report
    let mut md = String::new();
    md.push_str("# Kairo Phantom — Confidence Calibration Report\n\n");
    md.push_str("## Calibration Method: Platt Scaling\n\n");
    md.push_str("**Coefficients:** slope=0.88, intercept=0.06  \n");
    md.push_str("**Abstention Threshold:** 60%  \n");
    md.push_str(&format!(
        "**Expected Calibration Error (ECE):** {ece:.4}  \n\n"
    ));
    md.push_str("## Reliability Diagram Data\n\n");
    md.push_str("| Bin | Mean Confidence | Empirical Accuracy | Δ (Cal. Error) | Samples |\n");
    md.push_str("|-----|----------------|--------------------|----------------|---------|\n");
    for (i, (conf, acc, n)) in bins.iter().enumerate() {
        md.push_str(&format!(
            "| {:2} | {:.1}% | {:.1}% | {:.1}% | {} |\n",
            i + 1,
            conf * 100.0,
            acc * 100.0,
            (conf - acc).abs() * 100.0,
            n
        ));
    }
    md.push_str("\n## Interpretation\n\n");
    md.push_str("A perfectly calibrated model has mean confidence ≈ empirical accuracy per bin.\n");
    md.push_str("ECE < 5% is considered well-calibrated. ");
    md.push_str(&format!("Current ECE = **{:.2}%**.\n\n", ece * 100.0));
    md.push_str("## Abstention Threshold\n\n");
    md.push_str(
        "Kairo abstains (asks the user instead of suggesting) when `calibrated_score < 60%`.\n",
    );
    md.push_str("This is enforced in `memory::feedback::ConfidenceEngine::unified_confidence`.\n");

    std::fs::write(CALIBRATION_REPORT, &md).expect("Failed to write reliability_report.md");

    println!("\n📊 Calibration Report:");
    println!("  Total samples: {total_samples}");
    println!("  ECE: {:.4} ({:.2}%)", ece, ece * 100.0);
    println!("  Bins: {}", bins.len());
    println!("  Written to: {CALIBRATION_JSON} and {CALIBRATION_REPORT}");

    // Assert ECE is reasonable (< 25% — generous bound for synthetic data)
    assert!(
        ece < 0.25,
        "Expected Calibration Error {:.2}% is too high — calibration coefficients need adjustment.",
        ece * 100.0
    );
}

#[test]
fn test_calibration_platt_coefficients_sanity() {
    // After calibration: raw=0.9 → calibrated≈0.852 (close to empirical ~85-90%)
    let cal_90 = ConfidenceEngine::calibrate(0.9);
    assert!(
        (0.8..=0.95).contains(&cal_90),
        "Calibrated 90% raw should be in [80%, 95%], got {:.1}%",
        cal_90 * 100.0
    );

    // raw=0.0 → calibrated=0.06 (non-zero floor from intercept)
    let cal_0 = ConfidenceEngine::calibrate(0.0);
    assert!(
        (cal_0 - 0.06).abs() < 0.01,
        "Expected floor ≈6%, got {:.1}%",
        cal_0 * 100.0
    );

    // raw=1.0 → calibrated=0.94 (ceiling from slope+intercept)
    let cal_100 = ConfidenceEngine::calibrate(1.0);
    assert!(
        (cal_100 - 0.94).abs() < 0.01,
        "Expected ceiling ≈94%, got {:.1}%",
        cal_100 * 100.0
    );
}
