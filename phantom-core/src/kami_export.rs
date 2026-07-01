use chrono::Utc;
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, PartialEq)]
pub enum KamiCommand {
    // Domain 7: Export & Publishing (sidecar-delegated)
    Pdf,
    Epub,
    Slides,
    Book,
    Email,
    LinkedIn,
    TweetThread,
    Podcast,
    PodcastLocal,
    Subtitles,
    Quiz,
    Flashcards,
    Mindmap,
    Html,
    All,
    PressRelease,
    // Legacy / inline-handled
    Notion,
    Summary,
    Translate(String),
    Proofread,
}

pub struct CommandParser;

impl CommandParser {
    pub fn detect(text: &str) -> Option<(KamiCommand, String)> {
        let lines: Vec<&str> = text.lines().collect();
        if let Some(first_line) = lines.first() {
            if first_line.starts_with("// kami ") {
                let cmd_str = first_line.strip_prefix("// kami ").unwrap_or("").trim();
                let parts: Vec<&str> = cmd_str.split_whitespace().collect();
                if parts.is_empty() {
                    return None;
                }

                let command = match parts[0].to_lowercase().as_str() {
                    "pdf" => KamiCommand::Pdf,
                    "epub" => KamiCommand::Epub,
                    "slides" | "revealjs" => KamiCommand::Slides,
                    "book" => KamiCommand::Book,
                    "email" => KamiCommand::Email,
                    "linkedin" => KamiCommand::LinkedIn,
                    "tweet" | "tweet-thread" => KamiCommand::TweetThread,
                    "podcast" => {
                        if parts.contains(&"--local") {
                            KamiCommand::PodcastLocal
                        } else {
                            KamiCommand::Podcast
                        }
                    }
                    "subtitles" => KamiCommand::Subtitles,
                    "quiz" => KamiCommand::Quiz,
                    "flashcards" => KamiCommand::Flashcards,
                    "mindmap" => KamiCommand::Mindmap,
                    "html" => KamiCommand::Html,
                    "all" => KamiCommand::All,
                    "press-release" => KamiCommand::PressRelease,
                    "notion" => KamiCommand::Notion,
                    "summary" => KamiCommand::Summary,
                    "translate" => {
                        let lang = if parts.len() > 1 {
                            parts[1].to_string()
                        } else {
                            "Spanish".to_string()
                        };
                        KamiCommand::Translate(lang)
                    }
                    "proofread" => KamiCommand::Proofread,
                    _ => return None,
                };

                let content = lines[1..].join("\n");
                return Some((command, content));
            }
        }
        None
    }
}

pub struct KamiExporter;

impl KamiExporter {
    pub async fn execute(command: KamiCommand, content: String) -> Result<(), String> {
        let docs_dir = dirs::document_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("Kairo Exports");
        fs::create_dir_all(&docs_dir).map_err(|e| e.to_string())?;

        let title = content
            .lines()
            .find(|l| l.starts_with("# "))
            .map(|l| l.trim_start_matches('#').trim().to_string())
            .unwrap_or_else(|| "Kairo Export".to_string());

        match command {
            // ── Sidecar-delegated Domain 7 formats ──────────────────────────
            KamiCommand::Pdf => {
                Self::show_toast("Kairo: exporting as professional PDF...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "pdf",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("PDF exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Epub => {
                Self::show_toast("Kairo: exporting as EPUB e-book...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "epub",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("EPUB exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Slides => {
                Self::show_toast("Kairo: exporting as RevealJS slides...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "slides",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Slides exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Book => {
                Self::show_toast("Kairo: exporting as HTML book...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "book",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Book exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Email => {
                Self::show_toast("Kairo: formatting as email...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "email",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Email copied to clipboard");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::LinkedIn => {
                Self::show_toast("Kairo: formatting for LinkedIn...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "linkedin",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("LinkedIn post copied");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::TweetThread => {
                Self::show_toast("Kairo: formatting tweet thread...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "tweet",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Tweet thread copied");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Podcast => {
                Self::show_toast("Kairo: generating podcast dialogue (cloud)...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "podcast",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Podcast exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::PodcastLocal => {
                Self::show_toast("Kairo: generating local podcast dialogue...");
                let mut args = HashMap::new();
                args.insert("local".to_string(), "true".to_string());
                let result =
                    crate::sidecar_client::kami_export_sidecar("podcast", &args, &content, &title)
                        .await
                        .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Local podcast exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Subtitles => {
                Self::show_toast("Kairo: generating subtitles...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "subtitles",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Subtitles exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Quiz => {
                Self::show_toast("Kairo: generating quiz...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "quiz",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Quiz generated");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Flashcards => {
                Self::show_toast("Kairo: generating flashcards...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "flashcards",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Flashcards generated");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Mindmap => {
                Self::show_toast("Kairo: generating mind map...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "mindmap",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Mind map generated");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Html => {
                Self::show_toast("Kairo: exporting as HTML...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "html",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("HTML exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::All => {
                Self::show_toast("Kairo: batch exporting all formats...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "all",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("All formats exported");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::PressRelease => {
                Self::show_toast("Kairo: formatting as press release...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "press_release",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Press release copied");
                Self::show_toast(notif);
                Ok(())
            }
            KamiCommand::Summary => {
                Self::show_toast("Kairo: generating summary...");
                let result = crate::sidecar_client::kami_export_sidecar(
                    "summary",
                    &HashMap::new(),
                    &content,
                    &title,
                )
                .await
                .map_err(|e| e.to_string())?;
                let notif = result
                    .get("notification")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Summary exported");
                Self::show_toast(notif);
                Ok(())
            }
            // ── Legacy inline handlers ───────────────────────────────────────
            KamiCommand::Notion => {
                Self::show_toast("Kairo: copying to Notion clipboard...");
                Self::copy_to_clipboard(&content);
                Ok(())
            }
            KamiCommand::Translate(lang) => {
                Self::show_toast(&format!("Kairo: translating to {lang}..."));
                Self::copy_to_clipboard(&format!("[Kairo Translation to {lang}]\n\n{content}"));
                Ok(())
            }
            KamiCommand::Proofread => {
                Self::show_toast("Kairo: proofreading...");
                Self::copy_to_clipboard(&format!("[Kairo Proofread]\n\n{content}"));
                Ok(())
            }
        }
    }

    fn get_export_path(ext: &str) -> PathBuf {
        let timestamp = Utc::now().format("%Y%m%d_%H%M%S");
        dirs::document_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("Kairo Exports")
            .join(format!("kairo-export-{timestamp}.{ext}"))
    }

    fn show_toast(msg: &str) {
        // Production: integrates with toast_notification.rs or system tray.
        // For CLI/test: write to stderr so it doesn't pollute stdout.
        eprintln!("[KAIRO] {msg}");
    }

    fn copy_to_clipboard(text: &str) {
        #[cfg(target_os = "windows")]
        {
            use std::process::Command;
            // Use PowerShell here-string to avoid escaping issues with double-quotes inside text.
            let ps_script = format!("Set-Clipboard -Value @\"\n{text}\n\"@");
            let _ = Command::new("powershell")
                .args(["-NoProfile", "-NonInteractive", "-Command", &ps_script])
                .output();
        }
        #[cfg(not(target_os = "windows"))]
        {
            eprintln!(
                "[KAIRO clipboard] {}...",
                &text[..std::cmp::min(text.len(), 60)]
            );
        }
    }
}
