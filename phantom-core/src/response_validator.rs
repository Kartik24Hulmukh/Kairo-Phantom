// phantom-core/src/response_validator.rs
// Response Validator — Layer 4 of the 6-layer security stack
// Detects hallucinated multi-turn conversation patterns and verifies
// that AI responses are actually relevant to the user's prompt.

use regex::Regex;
use tracing::warn;

pub struct ResponseValidator {
    roleplay_patterns: Vec<Regex>,
    pub constitution: Vec<String>,
}

#[derive(Debug, PartialEq)]
pub enum ValidationResult {
    /// Response is clean and relevant
    Valid,
    /// Response contains hallucinated conversation turns
    HallucinatedTurns { found: String },
    /// Response is completely unrelated to the user's prompt (low lexical overlap)
    Irrelevant { overlap_score: f32 },
    /// Response is suspiciously short or empty
    Truncated,
    /// Response violates Kairo constitution
    ConstitutionViolation { rule: String },
}

impl ValidationResult {
    pub fn is_valid(&self) -> bool {
        matches!(self, ValidationResult::Valid)
    }

    pub fn reason(&self) -> String {
        match self {
            Self::Valid => "OK".into(),
            Self::HallucinatedTurns { found } => {
                format!("Hallucinated conversation turn detected: '{found}'")
            }
            Self::Irrelevant { overlap_score } => {
                format!("Low prompt-response overlap: {:.1}%", overlap_score * 100.0)
            }
            Self::Truncated => "Response appears truncated or empty".into(),
            Self::ConstitutionViolation { rule } => format!("Constitution violation: '{rule}'"),
        }
    }
}

pub fn load_constitution() -> Vec<String> {
    if let Ok(path) = std::env::var("KAIRO_CONSTITUTION_PATH") {
        if let Ok(content) = std::fs::read_to_string(path) {
            return content
                .lines()
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect();
        }
    }

    if let Some(home) = dirs::home_dir() {
        let path = home.join(".kairo-phantom").join("constitution.txt");
        if let Ok(content) = std::fs::read_to_string(path) {
            return content
                .lines()
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect();
        }
    }

    vec![
        "never fabricate a citation".to_string(),
        "never weaken indemnity without flagging".to_string(),
        "never send data off-device offline".to_string(),
    ]
}

impl ResponseValidator {
    pub fn new() -> Self {
        // Patterns that indicate the LLM is roleplaying a conversation
        let roleplay_patterns = vec![
            Regex::new(r"(?m)^\[?User\]?:").unwrap(),
            Regex::new(r"(?m)^\[?Assistant\]?:").unwrap(),
            Regex::new(r"(?m)^\[?Human\]?:").unwrap(),
            Regex::new(r"(?m)^\[?AI\]?:").unwrap(),
            Regex::new(r"(?m)^\[?System\]?:").unwrap(),
            // Example conversation pattern: "User: ... \n Assistant: ..."
            Regex::new(r"(?ms)User:.*?Assistant:").unwrap(),
            // GPT self-conversation pattern
            Regex::new(r"(?i)<\|im_start\|>").unwrap(),
            Regex::new(r"(?i)<\|im_end\|>").unwrap(),
        ];

        let constitution = load_constitution();

        Self {
            roleplay_patterns,
            constitution,
        }
    }

    /// Validates an AI response against the original user prompt.
    pub fn validate(&self, user_prompt: &str, response: &str) -> ValidationResult {
        // Check for empty/truncated response
        if response.trim().len() < 5 {
            return ValidationResult::Truncated;
        }

        // Check for hallucinated conversation turns
        for pattern in &self.roleplay_patterns {
            if let Some(m) = pattern.find(response) {
                let found = m.as_str().to_string();
                warn!(
                    "⚠️  [RESPONSE VALIDATOR] Hallucinated turn detected: '{}'",
                    &found
                );
                return ValidationResult::HallucinatedTurns { found };
            }
        }

        // Check for constitution violations
        let response_lower = response.to_lowercase();
        for rule in &self.constitution {
            if rule.contains('"') {
                // Find all quoted substrings
                let mut inside = false;
                let mut current_quote = String::new();
                let mut violated = false;
                for c in rule.chars() {
                    if c == '"' {
                        if inside {
                            let quote_lower = current_quote.to_lowercase();
                            if !quote_lower.is_empty() && response_lower.contains(&quote_lower) {
                                violated = true;
                                break;
                            }
                            current_quote.clear();
                            inside = false;
                        } else {
                            inside = true;
                        }
                    } else if inside {
                        current_quote.push(c);
                    }
                }
                if violated {
                    return ValidationResult::ConstitutionViolation { rule: rule.clone() };
                }
            } else {
                let rule_lower = rule.to_lowercase();
                // Specific check for "never fabricate a citation"
                if rule_lower.contains("never fabricate a citation")
                    && (response_lower.contains("fabricated citation")
                        || response_lower.contains("fake citation"))
                {
                    return ValidationResult::ConstitutionViolation { rule: rule.clone() };
                }
                // Specific check for "never weaken indemnity without flagging"
                if rule_lower.contains("never weaken indemnity")
                    && (response_lower.contains("weaken indemnity")
                        || response_lower.contains("weakened indemnity"))
                {
                    return ValidationResult::ConstitutionViolation { rule: rule.clone() };
                }
                // Specific check for "never send data off-device offline"
                if rule_lower.contains("never send data off-device")
                    && (response_lower.contains("send data off-device")
                        || response_lower.contains("sending data off-device"))
                {
                    return ValidationResult::ConstitutionViolation { rule: rule.clone() };
                }

                let prefix = if rule_lower.starts_with("never ") {
                    Some("never ")
                } else if rule_lower.starts_with("no ") {
                    Some("no ")
                } else {
                    None
                };

                if let Some(pref) = prefix {
                    let phrase = &rule_lower[pref.len()..];
                    if response_lower.contains(phrase) {
                        return ValidationResult::ConstitutionViolation { rule: rule.clone() };
                    }
                }
            }
        }

        // Lexical overlap check — basic NLI proxy
        let overlap = self.compute_lexical_overlap(user_prompt, response);
        // Only flag if prompt is substantive (>20 chars) and overlap is very low
        if user_prompt.len() > 20 && overlap < 0.05 {
            warn!("⚠️  [RESPONSE VALIDATOR] Low overlap ({:.1}%) between prompt and response - blocking response", overlap * 100.0);
            return ValidationResult::Irrelevant {
                overlap_score: overlap,
            };
        }

        ValidationResult::Valid
    }

    /// Computes lexical overlap between prompt and response as a fraction.
    fn compute_lexical_overlap(&self, prompt: &str, response: &str) -> f32 {
        let clean_prompt = prompt.to_lowercase();
        let clean_response = response.to_lowercase();

        let prompt_words: std::collections::HashSet<String> = clean_prompt
            .split_whitespace()
            .map(|w| w.trim_matches(|c: char| c.is_ascii_punctuation() || c.is_whitespace()))
            .filter(|w| !w.is_empty())
            .map(String::from)
            .collect();
        let response_words: std::collections::HashSet<String> = clean_response
            .split_whitespace()
            .map(|w| w.trim_matches(|c: char| c.is_ascii_punctuation() || c.is_whitespace()))
            .filter(|w| !w.is_empty())
            .map(String::from)
            .collect();

        if prompt_words.is_empty() {
            return 1.0; // Empty prompt → any response is valid
        }

        let intersection = prompt_words.intersection(&response_words).count();
        intersection as f32 / prompt_words.len() as f32
    }

    /// Quick check — returns true if the response is safe to use.
    pub fn is_safe(&self, user_prompt: &str, response: &str) -> bool {
        self.validate(user_prompt, response).is_valid()
    }
}

impl Default for ResponseValidator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_clean_response_passes() {
        let v = ResponseValidator::new();
        let result = v.validate(
            "Write a summary",
            "Here is a concise summary of the key points.",
        );
        assert_eq!(result, ValidationResult::Valid);
    }

    #[test]
    fn test_hallucinated_turn_detected() {
        let v = ResponseValidator::new();
        let response = "Sure!\nUser: Can you help me?\nAssistant: Of course I can!";
        let result = v.validate("Write a summary", response);
        assert!(matches!(result, ValidationResult::HallucinatedTurns { .. }));
    }

    #[test]
    fn test_truncated_response_detected() {
        let v = ResponseValidator::new();
        let result = v.validate("Write a 500 word essay", "Ok");
        assert_eq!(result, ValidationResult::Truncated);
    }

    #[test]
    fn test_irrelevant_response_blocked() {
        let v = ResponseValidator::new();
        let result = v.validate(
            "Configure database centroids",
            "Yellow birds fly over green meadows fast",
        );
        assert!(matches!(result, ValidationResult::Irrelevant { .. }));
        assert!(!result.is_valid());
    }

    #[test]
    fn test_constitution_validation() {
        let v = ResponseValidator::new();
        // Test "never fabricate a citation"
        let result1 = v.validate("test", "Here is a fabricated citation for you.");
        assert!(matches!(
            result1,
            ValidationResult::ConstitutionViolation { .. }
        ));

        // Test "never send data off-device offline"
        let result2 = v.validate(
            "test",
            "I will send data off-device offline to the servers.",
        );
        assert!(matches!(
            result2,
            ValidationResult::ConstitutionViolation { .. }
        ));

        // Test custom constitution via env/file or mock
        let mut custom_v = ResponseValidator::new();
        custom_v.constitution = vec!["never say \"banana\"".to_string()];
        let result3 = custom_v.validate("test", "This is a banana.");
        assert!(matches!(
            result3,
            ValidationResult::ConstitutionViolation { .. }
        ));
    }
}
