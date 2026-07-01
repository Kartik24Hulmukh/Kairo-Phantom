// phantom-core/src/prompt_parser.rs
//
// PromptParser — strict // protocol enforcement for Kairo Phantom.
//
// Implements Phase 1 Action 1 of the Foundation-First Hardening Plan:
// "Modify PromptParser::parse() to return None for any selection that does
//  not start with //, ///, //!, or //?"
//
// This is the authoritative gateway for the ghost-write hot-path.
// If parse() returns None, the HotkeyPressed handler MUST do NOTHING
// — no ghost overlay, no LLM call, no injection.

use crate::command_protocol::CommandMode;

/// The result of a successful // protocol parse.
#[derive(Debug, Clone, PartialEq)]
pub struct ParsedPrompt {
    /// Which command mode was detected (GhostWrite, Urgent, Query, etc.)
    pub mode: CommandMode,
    /// The instruction text stripped of the // prefix and mode keyword.
    pub instruction: String,
    /// The raw // line exactly as typed by the user.
    pub raw_line: String,
}

/// Strict // protocol parser.
///
/// This is the single place in the codebase that decides whether
/// Alt+Ctrl+M should activate the AI pipeline or silently abort.
pub struct PromptParser;

impl PromptParser {
    /// Parse a candidate text string and return `Some(ParsedPrompt)` only
    /// if it is a valid Kairo command (starts with `//`, `///`, `//!`, or `//?`).
    ///
    /// Returns `None` for:
    /// - Empty strings
    /// - Strings that don't start with `//` after trimming
    /// - Strings that are ONLY `//` with no meaningful instruction
    ///
    /// The HotkeyPressed handler MUST call this on `extract_last_paragraph()`
    /// output and abort silently if the result is `None`.
    pub fn parse(text: &str) -> Option<ParsedPrompt> {
        let trimmed = text.trim();

        // Gate 1: Must have at least 3 characters (`// ` minimum) and start with `//`
        if trimmed.len() < 2 {
            return None;
        }

        if !trimmed.starts_with("//") {
            return None;
        }

        // Gate 2: Must have meaningful content after the `//` prefix.
        // A bare `//` or `// ` with only whitespace is not a valid command.
        let (mode, instruction) = CommandMode::from_prompt(trimmed);

        let meaningful = !instruction.trim().is_empty();
        if !meaningful && mode == CommandMode::GhostWrite {
            // `//` with no instruction text — not a valid command
            return None;
        }

        Some(ParsedPrompt {
            mode,
            // Normalize: strip a leading ': ' separator that users naturally write after mode keywords.
            // e.g. `// kami slides: Create a pitch` → instruction becomes `Create a pitch` not `: Create a pitch`
            instruction: instruction
                .trim()
                .trim_start_matches(':')
                .trim()
                .to_string(),
            raw_line: trimmed.to_string(),
        })
    }

    /// Convenience: returns `true` if the text is a valid // command.
    /// Used by the hotkey handler for the fast-path check.
    pub fn is_command(text: &str) -> bool {
        Self::parse(text).is_some()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::command_protocol::CommandMode;

    /// Phase 1 Gate Test: non-// text must be rejected.
    #[test]
    fn test_prompt_parser_ignores_non_command_text() {
        // Normal document text — must return None
        let cases = [
            "Hello world",
            "This is a sentence.",
            "The quick brown fox",
            "  Leading spaces only  ",
            "",
            "   ",
            "/ single slash",
            "Single word",
            "Fix this bug: the loop is broken",
            "TODO: improve performance",
            "  A long paragraph that has been selected by accident when the\n  user pressed Alt+Ctrl+M without typing //",
        ];

        for text in &cases {
            let result = PromptParser::parse(text);
            assert!(
                result.is_none(),
                "PromptParser::parse({text:?}) should return None but returned {result:?}"
            );
        }
    }

    #[test]
    fn test_prompt_parser_accepts_double_slash_commands() {
        // Valid // commands — must return Some
        let valid_cases = [
            (
                "// rewrite this paragraph more formally",
                CommandMode::GhostWrite,
            ),
            ("//! urgent fix the intro", CommandMode::Urgent),
            ("//? what is the word count?", CommandMode::Query),
            ("// think about this architecture", CommandMode::Think),
            ("// kami slides: 5-slide pitch", CommandMode::KamiSlides),
            ("// kami pdf", CommandMode::KamiPdf),
            ("// write a cover letter", CommandMode::Write),
            ("// design a landing page layout", CommandMode::Design),
            ("// check this for factual errors", CommandMode::Check),
            ("// learn about quantum computing", CommandMode::Learn),
            ("// health", CommandMode::Health),
            ("// redline this contract", CommandMode::Redline),
        ];

        for (text, expected_mode) in &valid_cases {
            let result = PromptParser::parse(text);
            assert!(
                result.is_some(),
                "PromptParser::parse({text:?}) should return Some but returned None"
            );
            let parsed = result.unwrap();
            assert_eq!(
                parsed.mode, *expected_mode,
                "Wrong mode for {:?}: expected {:?}, got {:?}",
                text, expected_mode, parsed.mode
            );
        }
    }

    #[test]
    fn test_prompt_parser_bare_double_slash_is_rejected() {
        // A bare `//` with nothing after is NOT a valid command
        assert!(PromptParser::parse("//").is_none());
        assert!(PromptParser::parse("//  ").is_none());
    }

    #[test]
    fn test_prompt_parser_trims_whitespace() {
        let result = PromptParser::parse("   // fix this paragraph   ");
        assert!(result.is_some());
        let parsed = result.unwrap();
        assert_eq!(parsed.instruction, "fix this paragraph");
    }

    #[test]
    fn test_prompt_parser_extracts_correct_instruction() {
        let result =
            PromptParser::parse("// kami slides: Create a 5-slide pitch for Kairo Phantom");
        assert!(result.is_some());
        let parsed = result.unwrap();
        assert_eq!(parsed.mode, CommandMode::KamiSlides);
        assert_eq!(
            parsed.instruction,
            "Create a 5-slide pitch for Kairo Phantom"
        );
    }

    #[test]
    fn test_is_command_returns_false_for_regular_text() {
        assert!(!PromptParser::is_command("This is regular text"));
        assert!(!PromptParser::is_command("Not a command"));
        assert!(!PromptParser::is_command("// ")); // bare // with space
        assert!(PromptParser::is_command("// rewrite this"));
        assert!(PromptParser::is_command("//! critical fix"));
    }
}
