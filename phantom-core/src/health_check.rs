//! Document Health Check — P2-A1
//! Triggered when user presses Alt+Ctrl+M with no text selection.
//! Analyzes entire document for: passive voice, brand deviation, consistency issues.

use crate::document_context::DocumentContext;

#[derive(Debug, Clone)]
pub struct HealthIssue {
    pub category: HealthCategory,
    pub severity: &'static str, // "error" | "warning" | "suggestion"
    pub description: String,
    pub location_hint: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum HealthCategory {
    PassiveVoice,
    BrandDeviation,
    Consistency,
    ReadabilityScore,
    StructureIssue,
}

pub struct DocumentHealthChecker;

impl DocumentHealthChecker {
    /// Run a full health check on the document. Returns a formatted report.
    pub fn check(doc: &DocumentContext) -> HealthReport {
        let text = &doc.full_text;
        let mut issues = Vec::new();

        // 1. Passive voice detection
        issues.extend(Self::detect_passive_voice(text));

        // 2. Consistency checks (duplicate headings, inconsistent capitalization)
        issues.extend(Self::check_consistency(doc));

        // 3. Structure issues (missing title, no paragraphs, etc.)
        issues.extend(Self::check_structure(doc));

        // 4. Readability estimate
        let readability = Self::flesch_reading_ease(text);

        HealthReport {
            issues,
            word_count: text.split_whitespace().count(),
            sentence_count: Self::count_sentences(text),
            readability_score: readability,
        }
    }

    fn detect_passive_voice(text: &str) -> Vec<HealthIssue> {
        // Common passive voice patterns: "is/are/was/were/been/being + past participle"
        let passive_patterns = [
            "is being",
            "are being",
            "was being",
            "were being",
            "has been",
            "have been",
            "had been",
            "will be",
            "would be",
            "should be",
            "could be",
            "may be",
            "might be",
            "is done",
            "was done",
            "are done",
            "were done",
            "is made",
            "was made",
            "is given",
            "was given",
            "is used",
            "was used",
            "is shown",
            "was shown",
            "is considered",
            "was considered",
            "is known",
            "was known",
        ];

        let text_lower = text.to_lowercase();
        let mut issues = Vec::new();

        for pattern in &passive_patterns {
            if text_lower.contains(pattern) {
                issues.push(HealthIssue {
                    category: HealthCategory::PassiveVoice,
                    severity: "suggestion",
                    description: format!(
                        "Passive voice detected: \"{pattern}\" — consider active voice"
                    ),
                    location_hint: None,
                });
                if issues.len() >= 5 {
                    break;
                } // Cap at 5 to avoid noise
            }
        }

        issues
    }

    fn check_consistency(doc: &DocumentContext) -> Vec<HealthIssue> {
        let mut issues = Vec::new();

        // Check for duplicate headings
        let mut seen_headings = std::collections::HashSet::new();
        for item in &doc.outline {
            let heading_lower = item.text.to_lowercase();
            if !seen_headings.insert(heading_lower.clone()) {
                issues.push(HealthIssue {
                    category: HealthCategory::Consistency,
                    severity: "warning",
                    description: format!("Duplicate heading: \"{}\"", item.text),
                    location_hint: Some(item.text.clone()),
                });
            }
        }

        // Check mixed capitalization in short spans (ALL CAPS vs Title Case)
        let all_caps_count = doc
            .full_text
            .split_whitespace()
            .filter(|w| w.len() > 3 && w.chars().all(|c| c.is_uppercase() || !c.is_alphabetic()))
            .count();
        if all_caps_count > 10 {
            issues.push(HealthIssue {
                category: HealthCategory::Consistency,
                severity: "suggestion",
                description: format!(
                    "Heavy use of ALL CAPS ({all_caps_count} words) — consider title case for professional tone"
                ),
                location_hint: None,
            });
        }

        issues
    }

    fn check_structure(doc: &DocumentContext) -> Vec<HealthIssue> {
        let mut issues = Vec::new();
        let text = &doc.full_text;

        if text.trim().is_empty() {
            issues.push(HealthIssue {
                category: HealthCategory::StructureIssue,
                severity: "error",
                description: "Document appears to be empty".to_string(),
                location_hint: None,
            });
            return issues;
        }

        // No headings in a long document
        if doc.outline.is_empty() && text.split_whitespace().count() > 500 {
            issues.push(HealthIssue {
                category: HealthCategory::StructureIssue,
                severity: "suggestion",
                description:
                    "Long document (500+ words) has no headings — consider adding structure"
                        .to_string(),
                location_hint: None,
            });
        }

        // Very short document
        let word_count = text.split_whitespace().count();
        if word_count < 50 {
            issues.push(HealthIssue {
                category: HealthCategory::StructureIssue,
                severity: "info",
                description: format!("Short document ({word_count} words) — is this a draft?"),
                location_hint: None,
            });
        }

        issues
    }

    fn count_sentences(text: &str) -> usize {
        text.chars()
            .filter(|&c| c == '.' || c == '!' || c == '?')
            .count()
            .max(1)
    }

    /// Flesch Reading Ease (simplified). >60 = easy, <30 = very hard.
    fn flesch_reading_ease(text: &str) -> f32 {
        let words: Vec<&str> = text.split_whitespace().collect();
        let word_count = words.len();
        if word_count == 0 {
            return 100.0;
        }

        let sentence_count = Self::count_sentences(text);
        let syllable_count: usize = words.iter().map(|w| Self::count_syllables(w)).sum();

        let asl = word_count as f32 / sentence_count as f32; // avg sentence length
        let asw = syllable_count as f32 / word_count as f32; // avg syllables per word
        206.835 - (1.015 * asl) - (84.6 * asw)
    }

    fn count_syllables(word: &str) -> usize {
        let word = word.to_lowercase();
        let vowels = ['a', 'e', 'i', 'o', 'u'];
        let chars: Vec<char> = word.chars().collect();
        let mut count = 0;
        let mut prev_vowel = false;
        for &c in &chars {
            let is_vowel = vowels.contains(&c);
            if is_vowel && !prev_vowel {
                count += 1;
            }
            prev_vowel = is_vowel;
        }
        // Remove silent 'e' at end
        if word.ends_with('e') && count > 1 {
            count -= 1;
        }
        count.max(1)
    }
}

#[derive(Debug)]
pub struct HealthReport {
    pub issues: Vec<HealthIssue>,
    pub word_count: usize,
    pub sentence_count: usize,
    pub readability_score: f32,
}

impl HealthReport {
    /// Format the health report as a human-readable string for injection.
    pub fn format(&self) -> String {
        let readability_label = match self.readability_score as i32 {
            90..=200 => "Very Easy",
            70..=89 => "Easy",
            60..=69 => "Standard",
            50..=59 => "Fairly Difficult",
            30..=49 => "Difficult",
            _ => "Very Difficult",
        };

        let mut out = format!(
            "📋 Document Health Report\n\
             ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\
             Words: {}  |  Sentences: {}  |  Readability: {} ({:.0})\n\n",
            self.word_count, self.sentence_count, readability_label, self.readability_score
        );

        if self.issues.is_empty() {
            out.push_str("✅ No issues found — document looks healthy!\n");
        } else {
            let errors: Vec<_> = self
                .issues
                .iter()
                .filter(|i| i.severity == "error")
                .collect();
            let warnings: Vec<_> = self
                .issues
                .iter()
                .filter(|i| i.severity == "warning")
                .collect();
            let suggestions: Vec<_> = self
                .issues
                .iter()
                .filter(|i| i.severity == "suggestion" || i.severity == "info")
                .collect();

            if !errors.is_empty() {
                out.push_str(&format!("❌ {} Error(s):\n", errors.len()));
                for e in &errors {
                    out.push_str(&format!("  • {}\n", e.description));
                }
                out.push('\n');
            }
            if !warnings.is_empty() {
                out.push_str(&format!("⚠️  {} Warning(s):\n", warnings.len()));
                for w in &warnings {
                    out.push_str(&format!("  • {}\n", w.description));
                }
                out.push('\n');
            }
            if !suggestions.is_empty() {
                out.push_str(&format!("💡 {} Suggestion(s):\n", suggestions.len()));
                for s in &suggestions {
                    out.push_str(&format!("  • {}\n", s.description));
                }
            }
        }
        out
    }
}
