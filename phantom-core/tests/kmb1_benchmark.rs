//! KMB-1 Kairo Memory Benchmark — Industry-standard memory evaluation
//! P1-C1: The MMLU of document AI memory evaluation.
//!
//! Run: cargo test --test kmb1_benchmark -- --nocapture
//!
//! Scores Kairo's memory on 3 axes:
//!   F: Format recall (bullet vs prose preference)
//!   T: Tone recall (formal vs casual)
//!   L: Length recall (concise vs detailed)
//! Final KMB-1 = mean(F, T, L). Target: ≥ 0.90

use phantom_core::memory::MemMachine;
use std::path::PathBuf;
use tempfile::tempdir;

const TARGET_SCORE: f64 = 0.90;

/// Seed a format preference and measure recall precision.
async fn kmb1_format_recall(mem: &MemMachine) -> f64 {
    let app_ctx = "Microsoft Word";
    // Teach: bullet format preference
    for i in 0..10 {
        let _ = mem
            .remember(
                &format!(
                    "User strongly prefers bullet points in executive summaries (session {i})"
                ),
                Some("• Point 1\n• Point 2\n• Point 3"),
                app_ctx,
                Some("format_preference"),
                true,
                vec!["kmb1", "format", "bullet"],
            )
            .await;
    }

    // Query
    let recalled = mem
        .recall_contextualized(
            "format preference bullet points",
            vec!["format_preference".to_string(), app_ctx.to_string()],
            5,
        )
        .await
        .unwrap_or_default();

    if recalled.is_empty() {
        return 0.0;
    }
    let hits = recalled
        .iter()
        .filter(|ep| ep.to_lowercase().contains("bullet"))
        .count();
    hits as f64 / recalled.len() as f64
}

/// Seed a tone preference and measure recall precision.
async fn kmb1_tone_recall(mem: &MemMachine) -> f64 {
    let app_ctx = "Legal Document";
    for i in 0..10 {
        let _ = mem
            .remember(
                &format!("User writes in strictly formal tone for legal documents (session {i})"),
                Some("Pursuant to the agreement dated herein, the parties shall..."),
                app_ctx,
                Some("tone_preference"),
                true,
                vec!["kmb1", "tone", "formal"],
            )
            .await;
    }

    let recalled = mem
        .recall_contextualized(
            "tone formal legal writing",
            vec!["tone_preference".to_string(), app_ctx.to_string()],
            5,
        )
        .await
        .unwrap_or_default();

    if recalled.is_empty() {
        return 0.0;
    }
    let hits = recalled
        .iter()
        .filter(|ep| ep.to_lowercase().contains("formal"))
        .count();
    hits as f64 / recalled.len() as f64
}

/// Seed a length preference and measure recall precision.
async fn kmb1_length_recall(mem: &MemMachine) -> f64 {
    let app_ctx = "Microsoft PowerPoint";
    for i in 0..10 {
        let _ = mem.remember(
            &format!("User requires concise bullet points for slide content, max 25 words (session {i})"),
            Some("• Key point\n• Brief takeaway\n• Action item"),
            app_ctx,
            Some("length_preference"),
            true,
            vec!["kmb1", "length", "concise"],
        ).await;
    }

    let recalled = mem
        .recall_contextualized(
            "length preference concise slide",
            vec!["length_preference".to_string(), app_ctx.to_string()],
            5,
        )
        .await
        .unwrap_or_default();

    if recalled.is_empty() {
        return 0.0;
    }
    let hits = recalled
        .iter()
        .filter(|ep| ep.to_lowercase().contains("concise"))
        .count();
    hits as f64 / recalled.len() as f64
}

#[tokio::test]
async fn kmb1_full_benchmark() {
    let dir = tempdir().unwrap();
    let mem = MemMachine::new(dir.path().to_path_buf()).unwrap();

    println!("\n🏆 KMB-1: Kairo Memory Benchmark 1.0");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("  Sessions per sub-benchmark: 10");
    println!("  Target: ≥ {:.0}%\n", TARGET_SCORE * 100.0);

    let f_score = kmb1_format_recall(&mem).await;
    let t_score = kmb1_tone_recall(&mem).await;
    let l_score = kmb1_length_recall(&mem).await;
    let kmb1_score = (f_score + t_score + l_score) / 3.0;

    println!(
        "  F (Format Recall):  {:.4} ({:.1}%)",
        f_score,
        f_score * 100.0
    );
    println!(
        "  T (Tone Recall):    {:.4} ({:.1}%)",
        t_score,
        t_score * 100.0
    );
    println!(
        "  L (Length Recall):  {:.4} ({:.1}%)",
        l_score,
        l_score * 100.0
    );
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!(
        "  KMB-1 Score:        {:.4} ({:.1}%)",
        kmb1_score,
        kmb1_score * 100.0
    );

    let passed = kmb1_score >= TARGET_SCORE;
    println!("  Result: {}", if passed { "✅ PASS" } else { "❌ FAIL" });

    let leaderboard = serde_json::json!({
        "benchmark": "KMB-1",
        "version": "1.0",
        "model": "Kairo Phantom MemMachine",
        "kmb1_score": kmb1_score,
        "f_format_recall": f_score,
        "t_tone_recall": t_score,
        "l_length_recall": l_score,
        "sessions_per_axis": 10,
    });
    println!(
        "\n📊 Leaderboard entry:\n{}",
        serde_json::to_string_pretty(&leaderboard).unwrap()
    );

    assert!(
        passed,
        "KMB-1 score {kmb1_score:.4} below target {TARGET_SCORE:.2}. MemMachine recall needs improvement."
    );
}

#[tokio::test]
async fn kmb1_cold_start_baseline() {
    let dir = tempdir().unwrap();
    let mem = MemMachine::new(dir.path().to_path_buf()).unwrap();

    // Cold-start: no seeding → zero results
    let recalled = mem
        .recall_contextualized(
            "format preference",
            vec!["format_preference".to_string()],
            5,
        )
        .await
        .unwrap_or_default();

    assert_eq!(
        recalled.len(),
        0,
        "Cold start returned {} episodes — expected 0",
        recalled.len()
    );
    println!("✅ KMB-1 cold-start: correctly returns 0 episodes");
}

#[tokio::test]
async fn kmb1_decay_resistance() {
    // Stored memories must survive 10+ additional unrelated episodes
    let dir = tempdir().unwrap();
    let mem = MemMachine::new(dir.path().to_path_buf()).unwrap();

    // Plant the target memory
    let _ = mem
        .remember(
            "User prefers bullet points — DECAY TEST",
            None,
            "Microsoft Word",
            Some("format_preference"),
            true,
            vec!["kmb1", "decay-test"],
        )
        .await;

    // Flood with noise
    for i in 0..20 {
        let _ = mem
            .remember(
                &format!("Unrelated content about topic {i} that should not interfere"),
                None,
                "Notepad",
                None,
                false,
                vec!["noise"],
            )
            .await;
    }

    // The planted memory should still be recalled
    let recalled = mem
        .recall_contextualized(
            "bullet points format",
            vec![
                "format_preference".to_string(),
                "Microsoft Word".to_string(),
            ],
            5,
        )
        .await
        .unwrap_or_default();

    let found = recalled.iter().any(|r| r.contains("DECAY TEST"));
    assert!(
        found,
        "Memory decay test failed — target memory not recalled after {} noise episodes",
        20
    );
    println!("✅ KMB-1 decay resistance: target memory survives 20 noise episodes");
}
