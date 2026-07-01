// phantom-core/src/pii_guard.rs
// PII Redaction Guard — Layer 3 of the 6-layer security stack
// Redacts Personally Identifiable Information before sending to any LLM backend.

use regex::Regex;
use tracing::warn;

pub struct PiiGuard {
    patterns: Vec<(PiiKind, Regex)>,
}

#[derive(Debug, Clone)]
pub enum PiiKind {
    Email,
    PhoneUs,
    CreditCard,
    SsnUs,
    IpAddress,
    ApiKey,
}

impl PiiKind {
    pub fn placeholder(&self) -> &'static str {
        match self {
            PiiKind::Email => "[EMAIL REDACTED]",
            PiiKind::PhoneUs => "[PHONE REDACTED]",
            PiiKind::CreditCard => "[CARD REDACTED]",
            PiiKind::SsnUs => "[SSN REDACTED]",
            PiiKind::IpAddress => "[IP REDACTED]",
            PiiKind::ApiKey => "[KEY REDACTED]",
        }
    }
}

impl PiiGuard {
    pub fn new() -> Self {
        let patterns = vec![
            // Email addresses
            (
                PiiKind::Email,
                Regex::new(r"(?i)[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}").unwrap(),
            ),
            // US phone numbers (various formats)
            (
                PiiKind::PhoneUs,
                Regex::new(r"(?:\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}").unwrap(),
            ),
            // Credit card numbers (Luhn-format, 13-19 digits with optional spaces/dashes)
            (
                PiiKind::CreditCard,
                Regex::new(r"\b(?:\d[ \-]?){13,19}\b").unwrap(),
            ),
            // US SSN
            (
                PiiKind::SsnUs,
                Regex::new(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b").unwrap(),
            ),
            // IP addresses
            (
                PiiKind::IpAddress,
                Regex::new(r"\b(?:\d{1,3}\.){3}\d{1,3}\b").unwrap(),
            ),
            // API keys (common patterns: sk-, Bearer, ghp_, etc.)
            (
                PiiKind::ApiKey,
                Regex::new(r"(?:sk-|Bearer\s+|ghp_|gho_|glpat-|xoxb-|xoxp-)[A-Za-z0-9_\-]{8,}")
                    .unwrap(),
            ),
        ];

        Self { patterns }
    }

    /// Redacts PII from the given text. Returns (redacted_text, was_redacted).
    pub fn redact(&self, text: &str) -> (String, bool) {
        let mut result = text.to_string();
        let mut redacted = false;

        for (kind, pattern) in &self.patterns {
            if pattern.is_match(&result) {
                warn!(
                    "⚠️  [PII GUARD] Detected {:?} — redacting before LLM call",
                    kind
                );
                result = pattern.replace_all(&result, kind.placeholder()).to_string();
                redacted = true;
            }
        }

        (result, redacted)
    }

    /// Scans output for any residual PII that may have been hallucinated or echoed.
    pub fn scan_output(&self, text: &str) -> Vec<String> {
        let mut findings = Vec::new();
        for (kind, pattern) in &self.patterns {
            if pattern.is_match(text) {
                findings.push(format!("{kind:?}"));
            }
        }
        findings
    }

    /// Returns true if the text appears safe (no PII detected).
    pub fn is_safe(&self, text: &str) -> bool {
        self.scan_output(text).is_empty()
    }
}

impl Default for PiiGuard {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_email_redaction() {
        let guard = PiiGuard::new();
        let (redacted, was) = guard.redact("Contact me at alice@example.com please.");
        assert!(was);
        assert!(redacted.contains("[EMAIL REDACTED]"));
        assert!(!redacted.contains("alice@example.com"));
    }

    #[test]
    fn test_api_key_redaction() {
        let guard = PiiGuard::new();
        let (redacted, was) = guard.redact("My key is sk-abc123def456ghijklmnopqrstuv");
        assert!(was);
        assert!(redacted.contains("[KEY REDACTED]"));
    }

    #[test]
    fn test_clean_text_passes() {
        let guard = PiiGuard::new();
        let (_, was) = guard.redact("Write a summary of quarterly results.");
        assert!(!was);
    }
}
