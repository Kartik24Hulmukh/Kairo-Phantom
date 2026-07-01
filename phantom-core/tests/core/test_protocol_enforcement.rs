// phantom-core/tests/core/test_protocol_enforcement.rs
//
// Phase 1 Gate Test — // Protocol Enforcement
//
// Validates that the PromptParser strictly enforces the // protocol.
// Per the Foundation-First Hardening Plan, Phase 1, Action 1:
//   "Return None for any selection that does not start with //, ///, //!, or //?"
//   "If parse() returns None, do NOTHING — no ghost overlay, no LLM call, no injection."

use phantom_core::command_protocol::CommandMode;
use phantom_core::prompt_parser::PromptParser;

/// PRIMARY GATE TEST: Non-// text must be completely rejected.
///
/// This is the exact test required by the hardening plan:
/// "Add a unit test: test_prompt_parser_ignores_non_command_text"
#[test]
fn test_prompt_parser_ignores_non_command_text() {
    let non_command_texts = [
        // Regular document text
        "The executive summary presents our Q4 results.",
        "Please review the attached proposal.",
        "Meeting notes from January 15th:",
        // Code without // prefix
        "let x = 5;",
        "function main() {",
        // Accidental triggers - user selected text and hit Alt+Ctrl+M
        "This is a long paragraph about the company's strategic vision for 2026.",
        "Introduction\n\nKairo Phantom is an AI ghost-writer.",
        // Empty / whitespace
        "",
        "   ",
        "\t\n",
        // Single slash (common mistake)
        "/ this is not a command",
        "// ",  // bare // with only space
        "//  ", // bare // with only spaces
        // Looks like a URL, not a command
        "https://example.com/page",
        "http://localhost:8080",
        // Has // in the MIDDLE, not at the start
        "See https://kairo.ai for details",
        "Follow the steps here: https://docs.kairo.ai/quickstart",
        // Common document content
        "TODO: update this section",
        "FIXME: broken link on line 42",
        "NOTE: this requires administrator access",
    ];

    for text in &non_command_texts {
        let result = PromptParser::parse(text);
        assert!(
            result.is_none(),
            "PROTOCOL GATE FAIL: PromptParser::parse({text:?}) returned Some but expected None.\n\
             This means the hot-path would incorrectly trigger an LLM call for regular document text."
        );
    }
}

/// Confirms that ALL valid // command prefixes are accepted.
#[test]
fn test_all_valid_command_prefixes_accepted() {
    let valid_commands = [
        "// rewrite this paragraph formally",
        "//! this is urgent, fix now",
        "//? what is the reading level of this text?",
        "// write a summary",
        "// think about the structure",
        "// design a landing page",
        "// check for errors",
        "// learn about this topic",
        "// read https://example.com",
        "// explain the concept above",
        "// health",
        "// kami pdf",
        "// kami slides: 5-slide pitch",
        "// kami revealjs",
        "// kami email",
        "// kami linkedin",
        "// kami epub",
        "// kami book",
        "// kami podcast",
        "// kami html",
        "// kami tweet",
        "// kami all",
        "// kami mindmap",
        "// kami flashcards",
        "// kami quiz",
        "// kami subtitles",
        "// redline this contract",
        "// track make the intro warmer",
        "// voice",
        "// screen",
        "// speak",
    ];

    for cmd in &valid_commands {
        let result = PromptParser::parse(cmd);
        assert!(
            result.is_some(),
            "PROTOCOL GATE FAIL: PromptParser::parse({cmd:?}) returned None but expected Some.\n\
             This means a valid // command would be silently dropped."
        );
        let parsed = result.unwrap();
        assert_ne!(
            parsed.mode,
            CommandMode::None,
            "Parsed mode must not be None for valid command: {cmd:?}"
        );
    }
}

/// Gate test: the // gate preserves instruction content precisely.
#[test]
fn test_protocol_gate_preserves_instruction() {
    struct Case {
        input: &'static str,
        expected_instruction: &'static str,
    }

    let cases = [
        Case {
            input: "// rewrite this intro paragraph in a more conversational tone",
            expected_instruction: "rewrite this intro paragraph in a more conversational tone",
        },
        Case {
            input: "//! fix the broken link on page 3 immediately",
            expected_instruction: "fix the broken link on page 3 immediately",
        },
        Case {
            input: "//? what is the approximate reading time for this document?",
            expected_instruction: "what is the approximate reading time for this document?",
        },
        Case {
            input: "// kami slides: Create a 5-slide pitch deck for Kairo Phantom",
            // PromptParser normalizes the ': ' separator that users naturally type after 'kami slides'
            expected_instruction: "Create a 5-slide pitch deck for Kairo Phantom",
        },
    ];

    for case in &cases {
        let result = PromptParser::parse(case.input).expect("Should parse successfully");
        assert_eq!(
            result.instruction, case.expected_instruction,
            "Instruction mismatch for input: {:?}",
            case.input
        );
    }
}

/// Gate test: leading/trailing whitespace in the // line is handled gracefully.
#[test]
fn test_protocol_gate_handles_whitespace() {
    let padded = "   // fix this typo in the intro   ";
    let result = PromptParser::parse(padded);
    assert!(
        result.is_some(),
        "Padded // command should parse successfully"
    );
    let parsed = result.unwrap();
    assert_eq!(parsed.instruction, "fix this typo in the intro");
}

/// Gate test: a // line embedded in multi-line text is extracted and validated.
/// This simulates the typical use case where extract_last_paragraph has already
/// extracted the // line from a longer document.
#[test]
fn test_protocol_gate_accepts_extracted_command_line() {
    // This is what extract_last_paragraph returns: just the // line, no surrounding context
    let extracted_lines = [
        "// Rewrite this section to emphasize the ROI",
        "// kami pdf",
        "//! urgent: the conclusion needs to reference Q4 data",
    ];

    for line in &extracted_lines {
        assert!(
            PromptParser::is_command(line),
            "Extracted // line should be recognized as a command: {line:?}"
        );
    }
}

/// Gate test: // in a URL at the start of text is NOT a command.
/// This covers an edge case where someone selects a URL line.
#[test]
fn test_protocol_gate_rejects_url_at_start() {
    let url_texts = ["https://kairo.ai", "http://localhost:8080/api"];

    for text in &url_texts {
        let result = PromptParser::parse(text);
        assert!(
            result.is_none(),
            "URL text {text:?} should not be parsed as a // command"
        );
    }
}
