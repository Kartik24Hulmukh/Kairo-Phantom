//! Section Summarizer — P2.4
//! Uses DocumentContext outline structure to summarize selected sections into 3 bullets.
//! Triggered when docKind is any and user types "summarize" or "summary".

use crate::document_context::DocumentContext;
use anyhow::Result;

pub struct SectionSummarizer;

impl SectionSummarizer {
    /// Build an LLM prompt that leverages the full document structure.
    pub fn build_summary_prompt(doc: &DocumentContext, user_request: &str) -> String {
        let outline_preview = if doc.outline.is_empty() {
            "No outline detected — summarizing full document text.".to_string()
        } else {
            doc.outline
                .iter()
                .take(10)
                .map(|s| {
                    format!(
                        "  {} {}",
                        "  ".repeat((s.level as usize).saturating_sub(1)),
                        s.text
                    )
                })
                .collect::<Vec<_>>()
                .join("\n")
        };

        let word_count = doc.full_text.split_whitespace().count();
        let char_limit = 3000usize;
        let context_text = if doc.full_text.len() > char_limit {
            format!(
                "{}... [truncated — {} total words]",
                &doc.full_text[..char_limit],
                word_count
            )
        } else {
            doc.full_text.clone()
        };

        format!(
            "You are summarizing a {doc_type} document.\n\n\
             DOCUMENT STRUCTURE:\n{outline}\n\n\
             DOCUMENT TEXT:\n{text}\n\n\
             USER REQUEST: {request}\n\n\
             INSTRUCTIONS:\n\
             - Summarize the content into EXACTLY 3 bullet points\n\
             - Each bullet must be ≤ 25 words\n\
             - Capture the 3 most important insights or actions\n\
             - Use the same register/tone as the document\n\
             - Format: • [bullet]\n\
             Output ONLY the 3 bullets. No preamble.",
            doc_type = doc.doc_kind.human_name(),
            outline = outline_preview,
            text = context_text,
            request = user_request,
        )
    }

    /// Detect if a user prompt is requesting a summary.
    pub fn is_summary_request(prompt: &str) -> bool {
        let keywords = [
            "summarize",
            "summary",
            "tldr",
            "tl;dr",
            "key points",
            "bullet points",
            "3 bullets",
            "highlights",
            "brief",
            "digest",
        ];
        let pl = prompt.to_lowercase();
        keywords.iter().any(|k| pl.contains(k))
    }

    /// Post-process LLM output — ensure exactly 3 bullets in correct format.
    pub fn normalize_bullets(raw: &str) -> String {
        let bullets: Vec<&str> = raw
            .lines()
            .map(|l| l.trim())
            .filter(|l| {
                l.starts_with("• ")
                    || l.starts_with("- ")
                    || l.starts_with("* ")
                    || (l.starts_with(char::is_numeric) && l.contains(". "))
            })
            .collect();

        if bullets.is_empty() {
            // Try to extract sentences as bullets
            let sentences: Vec<&str> = raw
                .split('.')
                .map(|s| s.trim())
                .filter(|s| s.len() > 15)
                .collect();
            return sentences
                .iter()
                .take(3)
                .enumerate()
                .map(|(i, s)| format!("• {s}"))
                .collect::<Vec<_>>()
                .join("\n");
        }

        bullets
            .iter()
            .take(3)
            .map(|b| {
                // Normalize bullet char
                let text = b.trim_start_matches(|c: char| !c.is_alphabetic());
                format!("• {}", text.trim())
            })
            .collect::<Vec<_>>()
            .join("\n")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_summary_request() {
        assert!(SectionSummarizer::is_summary_request(
            "Can you summarize this?"
        ));
        assert!(SectionSummarizer::is_summary_request("Give me tldr"));
        assert!(SectionSummarizer::is_summary_request(
            "What are the key points?"
        ));
        assert!(!SectionSummarizer::is_summary_request(
            "Rewrite this in formal tone"
        ));
    }

    #[test]
    fn test_normalize_bullets_with_bullets() {
        let raw = "• First key insight from the document\n• Second important finding here\n• Third action required";
        let out = SectionSummarizer::normalize_bullets(raw);
        let lines: Vec<&str> = out.lines().collect();
        assert_eq!(lines.len(), 3);
        assert!(lines[0].starts_with("• "));
    }

    #[test]
    fn test_normalize_bullets_from_prose() {
        let raw = "The report shows declining margins. Revenue fell by 12% YoY. Operational costs increased substantially this quarter.";
        let out = SectionSummarizer::normalize_bullets(raw);
        assert!(!out.is_empty());
    }

    #[test]
    fn test_normalize_trims_to_3() {
        let raw = "• One\n• Two\n• Three\n• Four\n• Five";
        let out = SectionSummarizer::normalize_bullets(raw);
        let lines: Vec<&str> = out.lines().filter(|l| !l.is_empty()).collect();
        assert_eq!(lines.len(), 3, "Should cap at 3 bullets");
    }
}
