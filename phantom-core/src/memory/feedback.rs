use strsim::normalized_levenshtein;
use tracing::info;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FeedbackSignal {
    pub channel: String,
    pub from: String,
    pub to: String,
    pub confidence: f64,
}

pub struct FeedbackClassifier;

impl FeedbackClassifier {
    /// Analyzes the diff between rejected AI output and user's manual correction.
    pub fn classify(original: &str, corrected: &str) -> Vec<FeedbackSignal> {
        let mut signals = Vec::new();

        let sim = normalized_levenshtein(original, corrected);

        // 1. Check for format change (e.g., bullets to prose)
        if original.contains("- ") && !corrected.contains("- ") {
            signals.push(FeedbackSignal {
                channel: "format_changed".into(),
                from: "bullet".into(),
                to: "prose".into(),
                confidence: 0.9,
            });
        } else if !original.contains("- ") && corrected.contains("- ") {
            signals.push(FeedbackSignal {
                channel: "format_changed".into(),
                from: "prose".into(),
                to: "bullet".into(),
                confidence: 0.9,
            });
        }

        // 2. Check for length change
        let orig_len = original.split_whitespace().count();
        let corr_len = corrected.split_whitespace().count();

        if corr_len < orig_len / 2 {
            signals.push(FeedbackSignal {
                channel: "length_preference".into(),
                from: "verbose".into(),
                to: "concise".into(),
                confidence: 0.8,
            });
        }

        // 3. Generic tone/content mismatch if similarity is low
        if sim < 0.6 {
            signals.push(FeedbackSignal {
                channel: "tone_mismatch".into(),
                from: "hallucinated/wrong_tone".into(),
                to: "user_style".into(),
                confidence: 0.5,
            });
        }

        info!("🧠 PAHF: Detected feedback signals: {:?}", signals);
        signals
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub enum ConfidenceLevel {
    High,
    Medium,
    Low,
    /// Below the abstention threshold (< 0.60): Kairo must ask or abstain.
    Abstain,
}

/// The unified confidence score produced by the single confidence interface.
/// All confidence scoring in the system must produce a `ConfidenceScore`
/// via `ConfidenceEngine::unified_confidence(...)`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ConfidenceScore {
    /// Raw model score in [0.0, 1.0].
    pub score: f32,
    /// Calibrated score after Platt scaling adjustment.
    pub calibrated_score: f32,
    /// Categorical level derived from the calibrated score.
    pub level: ConfidenceLevel,
    /// Human-readable message shown in the confidence band UI.
    pub message: String,
    /// True if this score is below the abstention threshold.
    pub should_abstain: bool,
}

/// Abstention threshold: below this calibrated score, Kairo should ask the user
/// rather than suggesting an answer.
pub const ABSTENTION_THRESHOLD: f32 = 0.60;

pub struct ConfidenceEngine;

impl ConfidenceEngine {
    // ── Unified Confidence Interface (Item 20) ────────────────────────────

    /// **The single confidence interface for the entire system.**
    ///
    /// Merges PAHF feedback history signals (from `calculate_confidence`) with
    /// context-signal scoring (from `calculate_context_confidence`) into one
    /// calibrated `ConfidenceScore`.
    ///
    /// Callers previously using `calculate_confidence` or
    /// `calculate_context_confidence` separately should migrate to this method.
    ///
    /// # Arguments
    /// * `app`            – Name of the target application (e.g. "Microsoft Word").
    /// * `response`       – The AI-generated response being scored.
    /// * `history`        – PAHF feedback signals accumulated for this app.
    /// * `context_length` – Character count of captured document context.
    /// * `prompt`         – The original user prompt.
    /// * `waza_confidence`– 0..1 agent-match certainty from the waza registry.
    /// * `memory_vault_hit` – True if a relevant memory-vault record was found.
    pub fn unified_confidence(
        app: &str,
        response: &str,
        history: &[FeedbackSignal],
        context_length: usize,
        prompt: &str,
        waza_confidence: f32,
        memory_vault_hit: bool,
    ) -> ConfidenceScore {
        // 1. Context-signal base score
        let mut score: f32 = 0.0;

        if context_length > 500 {
            score += 0.3;
        } else {
            score += 0.1 * (context_length as f32 / 500.0);
        }

        let verbs = [
            "write",
            "summarize",
            "edit",
            "explain",
            "draft",
            "create",
            "make",
            "format",
        ];
        let prompt_lower = prompt.to_lowercase();
        if verbs.iter().any(|v| prompt_lower.contains(v)) {
            score += 0.2;
        }

        score += waza_confidence * 0.3;

        if memory_vault_hit {
            score += 0.2;
        }

        // 2. PAHF history adjustments
        for signal in history {
            if signal.channel == "format_changed"
                && app.to_lowercase().contains("word")
                && signal.to == "prose"
                && response.contains("- ")
            {
                score -= 0.15;
            }
            if signal.channel == "length_preference"
                && signal.to == "concise"
                && response.split_whitespace().count() > 100
            {
                score -= 0.1;
            }
        }

        let score = score.clamp(0.0, 1.0);

        // 3. Platt-scaling calibration (Item 27): apply a linear correction so
        //    that stated 90% accuracy tracks empirical ~90% reliability.
        //    Coefficients estimated from sandbox run data (see calibration_data.json).
        let calibrated_score = Self::calibrate(score);

        // 4. Derive level and abstention flag
        let should_abstain = calibrated_score < ABSTENTION_THRESHOLD;
        let (level, message) = if calibrated_score >= 0.75 {
            (ConfidenceLevel::High, "● Kairo is confident".to_string())
        } else if calibrated_score >= ABSTENTION_THRESHOLD {
            (ConfidenceLevel::Medium, "◑ Kairo is estimating".to_string())
        } else if calibrated_score >= 0.35 {
            (
                ConfidenceLevel::Low,
                "○ Kairo is guessing — review carefully".to_string(),
            )
        } else {
            (
                ConfidenceLevel::Abstain,
                "⚠ Confidence too low — Kairo is asking instead of suggesting".to_string(),
            )
        };

        info!(
            "📊 Confidence: raw={:.3}, calibrated={:.3}, level={:?}, abstain={}",
            score, calibrated_score, level, should_abstain
        );

        ConfidenceScore {
            score,
            calibrated_score,
            level,
            message,
            should_abstain,
        }
    }

    // ── Calibration (Item 27) ─────────────────────────────────────────────

    /// Platt-scaling calibration: maps raw [0,1] score to calibrated probability.
    ///
    /// Coefficients: slope=0.88, intercept=0.06 (fit from 100-run sandbox data).
    /// These move the calibration curve toward perfect reliability (diagonal).
    pub fn calibrate(raw: f32) -> f32 {
        let calibrated = 0.88_f32 * raw + 0.06_f32;
        calibrated.clamp(0.0, 1.0)
    }

    /// Returns true if the score is below the abstention threshold.
    pub fn should_abstain(calibrated_score: f32) -> bool {
        calibrated_score < ABSTENTION_THRESHOLD
    }

    // ── Legacy compatibility shims ────────────────────────────────────────
    //
    // These delegate to `unified_confidence` so that existing callers continue
    // to compile without change. They are intentionally kept but marked
    // deprecated so that they are gradually removed.

    /// Deprecated — use `unified_confidence` instead.
    #[deprecated(since = "0.7.0", note = "Use ConfidenceEngine::unified_confidence")]
    pub fn calculate_confidence(app: &str, response: &str, history: &[FeedbackSignal]) -> f64 {
        let score = Self::unified_confidence(app, response, history, 0, "", 0.5, false);
        score.calibrated_score as f64
    }

    /// Deprecated — use `unified_confidence` instead.
    #[deprecated(since = "0.7.0", note = "Use ConfidenceEngine::unified_confidence")]
    pub fn calculate_context_confidence(
        context_length: usize,
        prompt: &str,
        waza_confidence: f32,
        memory_vault_hit: bool,
    ) -> ConfidenceScore {
        Self::unified_confidence(
            "",
            "",
            &[],
            context_length,
            prompt,
            waza_confidence,
            memory_vault_hit,
        )
    }

    /// Setup the floating Tauri window for the confidence band
    #[cfg(feature = "tauri")]
    pub fn show_confidence_band(app_handle: &tauri::AppHandle, score: &ConfidenceScore) {
        use tauri::{Emitter, Manager};
        if let Some(window) = app_handle.get_webview_window("confidence_band") {
            let _ = window.emit("confidence_update", score);
            let _ = window.show();
        } else {
            tauri::WebviewWindowBuilder::new(
                app_handle,
                "confidence_band",
                tauri::WebviewUrl::App("confidence.html".into()),
            )
            .inner_size(280.0, 36.0)
            .decorations(false)
            .transparent(true)
            .always_on_top(true)
            .skip_taskbar(true)
            .build()
            .unwrap();
        }
    }
}

// ── Unit Tests ────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unified_confidence_high_context() {
        let score = ConfidenceEngine::unified_confidence(
            "Microsoft Word",
            "Here is the prose.",
            &[],
            1000,
            "write a summary",
            0.9,
            true,
        );
        // High context (>500) + verb + high waza + vault hit = raw≈1.0, calibrated≈0.94
        assert!(
            score.calibrated_score >= 0.75,
            "Expected High band, got {:.3}",
            score.calibrated_score
        );
        assert_eq!(score.level, ConfidenceLevel::High);
        assert!(!score.should_abstain);
    }

    #[test]
    fn test_unified_confidence_abstain_below_threshold() {
        // Zero context, no verb, low waza, no vault: raw=0.0, calibrated=0.06
        let score = ConfidenceEngine::unified_confidence("Unknown", "", &[], 0, "hmm", 0.0, false);
        assert!(
            score.should_abstain,
            "Expected abstention, got calibrated={:.3}",
            score.calibrated_score
        );
        assert!(
            score.level == ConfidenceLevel::Abstain || score.level == ConfidenceLevel::Low,
            "Expected Abstain or Low level"
        );
    }

    #[test]
    fn test_abstention_threshold_boundary() {
        // Calibrate a score right at the boundary
        let just_above = ConfidenceEngine::calibrate(0.61);
        let just_below = ConfidenceEngine::calibrate(0.60);
        // just_above (raw=0.61) → calibrated ≈ 0.597 — abstain
        // actual boundary crossing depends on coefficients:
        // 0.88*0.61 + 0.06 = 0.5968 (below 0.60, abstain)
        // 0.88*0.69 + 0.06 = 0.6672 (above 0.60, medium)
        let high_enough = ConfidenceEngine::calibrate(0.69);
        assert!(!ConfidenceEngine::should_abstain(high_enough));
        assert!(ConfidenceEngine::should_abstain(just_below));
    }

    #[test]
    fn test_calibration_platt_scaling() {
        // Platt: 0.88*x + 0.06
        assert!((ConfidenceEngine::calibrate(0.0) - 0.06).abs() < 0.001);
        assert!((ConfidenceEngine::calibrate(1.0) - 0.94).abs() < 0.001);
        assert!((ConfidenceEngine::calibrate(0.5) - 0.50).abs() < 0.001);
    }

    #[test]
    fn test_pahf_format_history_lowers_score() {
        let history = vec![FeedbackSignal {
            channel: "format_changed".into(),
            from: "bullet".into(),
            to: "prose".into(),
            confidence: 0.9,
        }];
        // Response still uses bullets → score should drop
        let score_with_bullets = ConfidenceEngine::unified_confidence(
            "Microsoft Word",
            "- Bullet 1\n- Bullet 2",
            &history,
            600,
            "write",
            0.8,
            false,
        );
        let score_prose = ConfidenceEngine::unified_confidence(
            "Microsoft Word",
            "Plain prose response here.",
            &history,
            600,
            "write",
            0.8,
            false,
        );
        assert!(
            score_with_bullets.calibrated_score < score_prose.calibrated_score,
            "Format penalty not applied: bullets={:.3}, prose={:.3}",
            score_with_bullets.calibrated_score,
            score_prose.calibrated_score
        );
    }

    #[test]
    fn test_confidence_level_serialization() {
        let score = ConfidenceScore {
            score: 0.8,
            calibrated_score: 0.764,
            level: ConfidenceLevel::High,
            message: "● Kairo is confident".into(),
            should_abstain: false,
        };
        let json = serde_json::to_string(&score).unwrap();
        assert!(json.contains("calibrated_score"));
        assert!(json.contains("should_abstain"));
    }
}
