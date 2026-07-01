//! Domain 7: Export & Publishing — Kami Command Routing Tests
//! Tests for command parsing, format routing, and CommandMode enum coverage.

#[cfg(test)]
mod domain7_kami_tests {
    use phantom_core::command_protocol::CommandMode;

    // ─── CommandMode::from_prompt parsing ──────────────────────────────────────

    #[test]
    fn test_parse_kami_pdf() {
        let (mode, _content) = CommandMode::from_prompt("// kami pdf\nDocument content here");
        assert_eq!(mode, CommandMode::KamiPdf);
    }

    #[test]
    fn test_parse_kami_epub() {
        let (mode, _) = CommandMode::from_prompt("// kami epub\nDocument content");
        assert_eq!(mode, CommandMode::KamiEpub);
    }

    #[test]
    fn test_parse_kami_slides() {
        let (mode, _) = CommandMode::from_prompt("// kami slides\nDocument content");
        assert_eq!(mode, CommandMode::KamiSlides);
    }

    #[test]
    fn test_parse_kami_book() {
        let (mode, _) = CommandMode::from_prompt("// kami book\nDocument content");
        assert_eq!(mode, CommandMode::KamiBook);
    }

    #[test]
    fn test_parse_kami_email() {
        let (mode, _) = CommandMode::from_prompt("// kami email\nDocument content");
        assert_eq!(mode, CommandMode::KamiEmail);
    }

    #[test]
    fn test_parse_kami_linkedin() {
        let (mode, _) = CommandMode::from_prompt("// kami linkedin\nDocument content");
        assert_eq!(mode, CommandMode::KamiLinkedin);
    }

    #[test]
    fn test_parse_kami_tweet() {
        let (mode, _) = CommandMode::from_prompt("// kami tweet\nDocument content");
        assert_eq!(mode, CommandMode::KamiTweet);
    }

    #[test]
    fn test_parse_kami_tweet_thread_alias() {
        let (mode, _) = CommandMode::from_prompt("// kami tweet-thread\nDocument content");
        assert_eq!(mode, CommandMode::KamiTweet);
    }

    #[test]
    fn test_parse_kami_podcast() {
        let (mode, _) = CommandMode::from_prompt("// kami podcast\nDocument content");
        assert_eq!(mode, CommandMode::KamiPodcast);
    }

    #[test]
    fn test_parse_kami_podcast_local() {
        let (mode, _) = CommandMode::from_prompt("// kami podcast --local\nDocument content");
        assert_eq!(mode, CommandMode::KamiPodcastLocal);
    }

    #[test]
    fn test_parse_kami_subtitles() {
        let (mode, _) = CommandMode::from_prompt("// kami subtitles\nDocument content");
        assert_eq!(mode, CommandMode::KamiSubtitles);
    }

    #[test]
    fn test_parse_kami_quiz() {
        let (mode, _) = CommandMode::from_prompt("// kami quiz\nDocument content");
        assert_eq!(mode, CommandMode::KamiQuiz);
    }

    #[test]
    fn test_parse_kami_flashcards() {
        let (mode, _) = CommandMode::from_prompt("// kami flashcards\nDocument content");
        assert_eq!(mode, CommandMode::KamiFlashcards);
    }

    #[test]
    fn test_parse_kami_mindmap() {
        let (mode, _) = CommandMode::from_prompt("// kami mindmap\nDocument content");
        assert_eq!(mode, CommandMode::KamiMindmap);
    }

    #[test]
    fn test_parse_kami_html() {
        let (mode, _) = CommandMode::from_prompt("// kami html\nDocument content");
        assert_eq!(mode, CommandMode::KamiHtml);
    }

    #[test]
    fn test_parse_kami_all() {
        let (mode, _) = CommandMode::from_prompt("// kami all\nDocument content");
        assert_eq!(mode, CommandMode::KamiAll);
    }

    // ─── Specificity: podcast --local must resolve before podcast ──────────────

    #[test]
    fn test_podcast_local_before_podcast() {
        let (mode_local, _) = CommandMode::from_prompt("// kami podcast --local");
        let (mode_cloud, _) = CommandMode::from_prompt("// kami podcast");
        assert_eq!(mode_local, CommandMode::KamiPodcastLocal);
        assert_eq!(mode_cloud, CommandMode::KamiPodcast);
        assert_ne!(mode_local, mode_cloud);
    }

    // ─── Content extraction from multi-line prompts ────────────────────────────

    #[test]
    fn test_content_extracted_after_command_line() {
        let input = "// kami pdf\n# My Document\n\nThis is the content.";
        let (mode, content) = CommandMode::from_prompt(input);
        assert_eq!(mode, CommandMode::KamiPdf);
        // Content should not contain the // kami line
        assert!(!content.contains("// kami"));
        assert!(content.contains("My Document"));
    }

    // ─── Fallthrough to generic Kami ───────────────────────────────────────────

    #[test]
    fn test_generic_kami_fallback() {
        // A plain `// kami` without a known subcommand falls to generic Kami mode
        let (mode, _) = CommandMode::from_prompt("// kami\nDocument content");
        assert_eq!(mode, CommandMode::Kami);
    }

    // ─── is_command() returns true for all kami modes ──────────────────────────

    #[test]
    fn test_all_kami_modes_are_commands() {
        let kami_modes = vec![
            CommandMode::KamiPdf,
            CommandMode::KamiEpub,
            CommandMode::KamiSlides,
            CommandMode::KamiBook,
            CommandMode::KamiEmail,
            CommandMode::KamiLinkedin,
            CommandMode::KamiTweet,
            CommandMode::KamiPodcast,
            CommandMode::KamiPodcastLocal,
            CommandMode::KamiSubtitles,
            CommandMode::KamiQuiz,
            CommandMode::KamiFlashcards,
            CommandMode::KamiMindmap,
            CommandMode::KamiHtml,
            CommandMode::KamiAll,
            CommandMode::Kami,
        ];
        for mode in kami_modes {
            assert!(mode.is_command(), "Expected {mode:?} to be a command");
        }
    }

    // ─── system_hint() returns non-empty strings ───────────────────────────────

    #[test]
    fn test_all_kami_modes_have_system_hints() {
        let modes = vec![
            CommandMode::KamiPdf,
            CommandMode::KamiEpub,
            CommandMode::KamiSlides,
            CommandMode::KamiBook,
            CommandMode::KamiEmail,
            CommandMode::KamiLinkedin,
            CommandMode::KamiTweet,
            CommandMode::KamiPodcast,
            CommandMode::KamiPodcastLocal,
            CommandMode::KamiSubtitles,
            CommandMode::KamiQuiz,
            CommandMode::KamiFlashcards,
            CommandMode::KamiMindmap,
            CommandMode::KamiHtml,
            CommandMode::KamiAll,
        ];
        for mode in modes {
            let hint = mode.system_hint();
            assert!(!hint.is_empty(), "Empty system_hint for {mode:?}");
            assert!(
                hint.contains("KAMI"),
                "system_hint for {mode:?} should mention KAMI"
            );
        }
    }

    // ─── Non-kami commands are NOT affected ────────────────────────────────────

    #[test]
    fn test_non_kami_commands_unaffected() {
        let (mode, _) = CommandMode::from_prompt("//! urgent task");
        assert_eq!(mode, CommandMode::Urgent);

        let (mode2, _) = CommandMode::from_prompt("// think about this problem");
        assert_eq!(mode2, CommandMode::Think);

        let (mode3, _) = CommandMode::from_prompt("plain text no command");
        assert_eq!(mode3, CommandMode::None);
    }
}
