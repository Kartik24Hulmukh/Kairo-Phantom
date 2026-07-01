//! Cross-Document Consistency Engine — P2.2
//! Compares the current document against past reference episodes in MemMachine.
//! Flags tone, terminology, and style inconsistencies.

use crate::memory::MemMachine;
use anyhow::Result;
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct ConsistencyReport {
    pub score: f32,          // 0.0 (inconsistent) – 1.0 (fully consistent)
    pub issues: Vec<String>, // human-readable inconsistency findings
    pub suggestions: Vec<String>,
}

impl ConsistencyReport {
    pub fn format_for_injection(&self) -> String {
        let grade = if self.score >= 0.85 {
            "✅ Excellent"
        } else if self.score >= 0.65 {
            "⚠️  Moderate"
        } else {
            "❌ Poor"
        };
        let mut out = format!(
            "📋 Document Consistency Report — {} ({:.0}%)\n\n",
            grade,
            self.score * 100.0
        );
        if self.issues.is_empty() {
            out.push_str("  No consistency issues detected.\n");
        } else {
            out.push_str("Issues found:\n");
            for issue in &self.issues {
                out.push_str(&format!("  • {issue}\n"));
            }
        }
        if !self.suggestions.is_empty() {
            out.push_str("\nSuggestions:\n");
            for s in &self.suggestions {
                out.push_str(&format!("  → {s}\n"));
            }
        }
        out
    }
}

pub struct ConsistencyEngine {
    mem: Arc<MemMachine>,
}

impl ConsistencyEngine {
    pub fn new(mem: Arc<MemMachine>) -> Self {
        Self { mem }
    }

    /// Compare document text against past MemMachine episodes for the given app context.
    pub async fn analyze(&self, text: &str, app_ctx: &str) -> Result<ConsistencyReport> {
        let past = self
            .mem
            .recall_contextualized(text, vec![app_ctx.to_string(), "global".to_string()], 10)
            .await
            .unwrap_or_default();

        if past.is_empty() {
            return Ok(ConsistencyReport {
                score: 1.0,
                issues: vec![],
                suggestions: vec![
                    "No past episodes yet — MemMachine will learn from this document.".into(),
                ],
            });
        }

        let mut issues = Vec::new();
        let mut suggestions = Vec::new();

        // --- Tone check ---
        let doc_formal = is_formal(text);
        let past_formal_count = past.iter().filter(|ep| is_formal(ep)).count();
        let past_casual_count = past.len() - past_formal_count;
        if doc_formal && past_casual_count > past_formal_count {
            issues.push("Tone shift: this document is more formal than your recent work.".into());
            suggestions
                .push("Consider a slightly more conversational tone for consistency.".into());
        } else if !doc_formal && past_formal_count > past_casual_count {
            issues.push("Tone shift: this document is more casual than your recent work.".into());
            suggestions.push("Consider elevating the formality level.".into());
        }

        // --- Bullet vs prose format ---
        let doc_bullets = bullet_ratio(text);
        let past_avg_bullets =
            past.iter().map(|ep| bullet_ratio(ep)).sum::<f32>() / past.len() as f32;
        if (doc_bullets - past_avg_bullets).abs() > 0.3 {
            if doc_bullets > past_avg_bullets {
                issues.push("Format shift: more bullet-heavy than your recent documents.".into());
            } else {
                issues.push("Format shift: more prose-heavy than your recent documents.".into());
            }
            suggestions.push(if past_avg_bullets > 0.3 {
                "Your recent docs favor bullet lists — consider restructuring key sections.".into()
            } else {
                "Your recent docs favor prose — consider reducing bullet count.".into()
            });
        }

        // --- Sentence length ---
        let doc_avg_len = avg_sentence_len(text);
        let past_avg_len =
            past.iter().map(|ep| avg_sentence_len(ep)).sum::<f32>() / past.len() as f32;
        if (doc_avg_len - past_avg_len).abs() > 8.0 {
            issues.push(format!(
                "Length shift: avg sentence is {doc_avg_len:.0} words vs your usual {past_avg_len:.0} words."
            ));
        }

        let score = if issues.is_empty() {
            1.0
        } else {
            (1.0f32 - issues.len() as f32 * 0.2).max(0.0)
        };

        Ok(ConsistencyReport {
            score,
            issues,
            suggestions,
        })
    }
}

fn is_formal(text: &str) -> bool {
    let contractions = [
        "don't", "can't", "won't", "it's", "i'm", "we're", "isn't", "i'll",
    ];
    !contractions.iter().any(|c| text.to_lowercase().contains(c))
}

fn bullet_ratio(text: &str) -> f32 {
    let bullet = text
        .lines()
        .filter(|l| {
            let t = l.trim();
            t.starts_with("• ") || t.starts_with("- ") || t.starts_with("* ")
        })
        .count();
    let total = text.lines().count().max(1);
    bullet as f32 / total as f32
}

fn avg_sentence_len(text: &str) -> f32 {
    let words = text.split_whitespace().count();
    let sentences = text
        .chars()
        .filter(|&c| c == '.' || c == '!' || c == '?')
        .count()
        .max(1);
    words as f32 / sentences as f32
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::MemMachine;
    use tempfile::tempdir;

    #[tokio::test]
    async fn test_consistency_no_past() {
        let d = tempdir().unwrap();
        let mem = Arc::new(MemMachine::new(d.path().to_path_buf()).unwrap());
        let engine = ConsistencyEngine::new(mem);
        let rep = engine
            .analyze("Hello world. This is a document.", "Microsoft Word")
            .await
            .unwrap();
        assert_eq!(rep.score, 1.0);
        assert_eq!(rep.issues.len(), 0);
    }

    #[test]
    fn test_is_formal() {
        assert!(is_formal("The parties shall not engage in any activity."));
        assert!(!is_formal("We don't want to do this."));
    }

    #[test]
    fn test_bullet_ratio() {
        let t = "• Point one\n• Point two\nSome prose\n• Point three";
        let r = bullet_ratio(t);
        assert!(r > 0.6, "Expected > 0.6, got {r}");
    }
}
