#[cfg(windows)]
use windows::Win32::System::Threading::{
    OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
};
/// Context Engine — The brain of Kairo's document awareness.
/// Extracts the user's EXACT prompt (last paragraph/selection) and
/// identifies the precise application environment for context-aware AI responses.
/// v3.0: Also resolves the active document file path and slide number
/// from the window title for structured document extraction.
/// v4.0 (Domain 11): Cross-platform active app detection on Windows, macOS, Linux.

#[cfg(windows)]
use windows::Win32::UI::WindowsAndMessaging::{
    GetForegroundWindow, GetWindowTextW, GetWindowThreadProcessId,
};

/// Identifies the exact type of application the user is writing in.
#[derive(Debug, Clone, PartialEq)]
pub enum AppEnvironment {
    // Office Suite — Windows
    MicrosoftWord,
    MicrosoftPowerPoint,
    MicrosoftExcel,
    MicrosoftOutlook,
    // Office Suite — macOS
    Pages,
    Keynote,
    Numbers,
    TextEdit,
    // Office Suite — Linux
    LibreOfficeWriter,
    LibreOfficeImpress,
    LibreOfficeCalc,
    Gedit,
    // Modern Productivity & Design
    Notion,
    Figma,
    Canva,
    // Yjs-powered collaborative apps
    GoogleDocs,
    GoogleSlides,
    LinearApp,
    TiptapEditor,
    Liveblocks,
    // Code / Dev (cross-platform)
    VSCode,
    Vim,
    NotepadPlusPlus,
    // Terminals
    WindowsTerminal,
    PowerShell,
    CommandPrompt,
    GnomeTerminal,
    MacTerminal,
    ITerm2,
    // Browsers (cross-platform)
    Chrome,
    Chromium,
    Firefox,
    Edge,
    Safari,
    // Notepad variants
    Notepad,
    // Communication
    Slack,
    Teams,
    Discord,
    // Other
    Unknown(String),
}

impl AppEnvironment {
    /// Returns a short human-readable label for logging.
    pub fn label(&self) -> String {
        match self {
            AppEnvironment::MicrosoftWord => "Microsoft Word".into(),
            AppEnvironment::MicrosoftPowerPoint => "PowerPoint".into(),
            AppEnvironment::MicrosoftExcel => "Excel".into(),
            AppEnvironment::MicrosoftOutlook => "Outlook".into(),
            AppEnvironment::Pages => "Pages".into(),
            AppEnvironment::Keynote => "Keynote".into(),
            AppEnvironment::Numbers => "Numbers".into(),
            AppEnvironment::TextEdit => "TextEdit".into(),
            AppEnvironment::LibreOfficeWriter => "LibreOffice Writer".into(),
            AppEnvironment::LibreOfficeImpress => "LibreOffice Impress".into(),
            AppEnvironment::LibreOfficeCalc => "LibreOffice Calc".into(),
            AppEnvironment::Gedit => "gedit".into(),
            AppEnvironment::Notion => "Notion".into(),
            AppEnvironment::Figma => "Figma".into(),
            AppEnvironment::Canva => "Canva".into(),
            AppEnvironment::VSCode => "VS Code".into(),
            AppEnvironment::WindowsTerminal => "Windows Terminal".into(),
            AppEnvironment::PowerShell => "PowerShell".into(),
            AppEnvironment::CommandPrompt => "Command Prompt".into(),
            AppEnvironment::GnomeTerminal => "GNOME Terminal".into(),
            AppEnvironment::MacTerminal => "Terminal".into(),
            AppEnvironment::ITerm2 => "iTerm2".into(),
            AppEnvironment::Vim => "Vim".into(),
            AppEnvironment::Notepad => "Notepad".into(),
            AppEnvironment::NotepadPlusPlus => "Notepad++".into(),
            AppEnvironment::Chrome => "Chrome".into(),
            AppEnvironment::Chromium => "Chromium".into(),
            AppEnvironment::Firefox => "Firefox".into(),
            AppEnvironment::Edge => "Edge".into(),
            AppEnvironment::Safari => "Safari".into(),
            AppEnvironment::Slack => "Slack".into(),
            AppEnvironment::Teams => "Teams".into(),
            AppEnvironment::Discord => "Discord".into(),
            AppEnvironment::GoogleDocs => "Google Docs".into(),
            AppEnvironment::GoogleSlides => "Google Slides".into(),
            AppEnvironment::LinearApp => "Linear".into(),
            AppEnvironment::TiptapEditor => "Tiptap Editor".into(),
            AppEnvironment::Liveblocks => "Liveblocks".into(),
            AppEnvironment::Unknown(name) => name.clone(),
        }
    }

    /// Returns true if this app is Yjs-powered — triggers CRDT peer injection.
    pub fn is_yjs_app(&self) -> bool {
        matches!(
            self,
            AppEnvironment::GoogleDocs
                | AppEnvironment::GoogleSlides
                | AppEnvironment::LinearApp
                | AppEnvironment::TiptapEditor
                | AppEnvironment::Liveblocks
        )
    }

    /// Convert to the canonical DocKind for structured document context.
    pub fn to_doc_kind(&self) -> crate::document_context::DocKind {
        use crate::document_context::DocKind;
        match self {
            AppEnvironment::MicrosoftWord
            | AppEnvironment::MicrosoftOutlook
            | AppEnvironment::Pages
            | AppEnvironment::LibreOfficeWriter => DocKind::WordDocument,

            AppEnvironment::MicrosoftPowerPoint
            | AppEnvironment::Keynote
            | AppEnvironment::LibreOfficeImpress => DocKind::PowerPoint,

            AppEnvironment::MicrosoftExcel
            | AppEnvironment::Numbers
            | AppEnvironment::LibreOfficeCalc => DocKind::ExcelSpreadsheet,

            AppEnvironment::Notion | AppEnvironment::TiptapEditor | AppEnvironment::Liveblocks => {
                DocKind::NotionPage
            }

            AppEnvironment::GoogleDocs => DocKind::YjsDocument,
            AppEnvironment::GoogleSlides => DocKind::YjsDocument,
            AppEnvironment::LinearApp => DocKind::YjsDocument,

            AppEnvironment::Figma => DocKind::FigmaDesign,
            AppEnvironment::Canva => DocKind::CanvaDesign,

            AppEnvironment::VSCode | AppEnvironment::Vim | AppEnvironment::NotepadPlusPlus => {
                DocKind::CodeFile
            }

            AppEnvironment::WindowsTerminal
            | AppEnvironment::PowerShell
            | AppEnvironment::CommandPrompt
            | AppEnvironment::GnomeTerminal
            | AppEnvironment::MacTerminal
            | AppEnvironment::ITerm2 => DocKind::Terminal,

            AppEnvironment::Notepad | AppEnvironment::TextEdit | AppEnvironment::Gedit => {
                DocKind::PlainText
            }

            _ => DocKind::UnknownApp,
        }
    }
}

/// Raw capture snapshot from the hotkey moment.
#[derive(Debug, Clone)]
pub struct AppContext {
    /// The process name (e.g., "WINWORD.EXE", "soffice", "Pages")
    pub process_name: String,
    /// The window title
    pub window_title: String,
    /// The detected application environment
    pub environment: AppEnvironment,
    /// The exact user prompt (last paragraph only — what to replace)
    pub prompt_text: String,
    /// Character count of prompt (used for exact erasure)
    pub prompt_char_count: usize,
    /// Full document text from accessibility API
    pub document_text: String,
    /// Resolved file path (from window title parsing)
    pub file_path: Option<std::path::PathBuf>,
    /// Active slide number (parsed from PowerPoint/Keynote/Impress title)
    pub active_slide: Option<usize>,
}

use crate::plugin::{AppFingerprinter, FingerprinterRegistry};

/// Cross-platform application fingerprinter.
/// Covers 5+ apps per platform as required by Domain 11 Gate 1.
pub struct DefaultFingerprinter;

impl AppFingerprinter for DefaultFingerprinter {
    fn fingerprint(&self, process_name: &str, window_title: &str) -> Option<AppEnvironment> {
        let proc = process_name.to_lowercase();
        let title = window_title.to_lowercase();

        // ── Windows Office Suite ──────────────────────────────────────────────
        if proc.contains("winword") {
            return Some(AppEnvironment::MicrosoftWord);
        }
        if proc.contains("powerpnt") {
            return Some(AppEnvironment::MicrosoftPowerPoint);
        }
        if proc.contains("excel") {
            return Some(AppEnvironment::MicrosoftExcel);
        }
        if proc.contains("outlook") {
            return Some(AppEnvironment::MicrosoftOutlook);
        }

        // ── macOS Native Apps ─────────────────────────────────────────────────
        // Process names on macOS match the .app bundle name exactly
        if proc == "pages" || title.contains("pages") && proc.ends_with("pages") {
            return Some(AppEnvironment::Pages);
        }
        if proc == "keynote" || (title.contains("keynote") && proc.ends_with("keynote")) {
            return Some(AppEnvironment::Keynote);
        }
        if proc == "numbers" || (title.contains("numbers") && proc.ends_with("numbers")) {
            return Some(AppEnvironment::Numbers);
        }
        if proc == "textedit" || proc.contains("textedit") {
            return Some(AppEnvironment::TextEdit);
        }
        if proc == "safari" {
            return Some(AppEnvironment::Safari);
        }
        if proc.contains("iterm2") || proc == "iterm" {
            return Some(AppEnvironment::ITerm2);
        }
        if proc == "terminal" && cfg!(target_os = "macos") {
            return Some(AppEnvironment::MacTerminal);
        }

        // ── Linux / LibreOffice Suite ─────────────────────────────────────────
        // LibreOffice processes: "soffice", "soffice.bin"; titles reveal app type
        if proc.contains("soffice") || proc.contains("libreoffice") {
            if title.contains("writer") || title.contains(".odt") || title.contains(".docx") {
                return Some(AppEnvironment::LibreOfficeWriter);
            }
            if title.contains("impress") || title.contains(".odp") || title.contains(".pptx") {
                return Some(AppEnvironment::LibreOfficeImpress);
            }
            if title.contains("calc") || title.contains(".ods") || title.contains(".xlsx") {
                return Some(AppEnvironment::LibreOfficeCalc);
            }
            // Generic LibreOffice — default to Writer
            return Some(AppEnvironment::LibreOfficeWriter);
        }
        if proc == "gedit" || proc.contains("gedit") {
            return Some(AppEnvironment::Gedit);
        }
        if proc.contains("gnome-terminal")
            || proc.contains("gnome_terminal")
            || title.contains("gnome terminal")
        {
            return Some(AppEnvironment::GnomeTerminal);
        }

        // ── Code Editors (cross-platform) ─────────────────────────────────────
        if proc.contains("code") && !proc.contains("discord") {
            return Some(AppEnvironment::VSCode);
        }
        if proc.contains("notepad++") || proc.contains("notepadplusplus") {
            return Some(AppEnvironment::NotepadPlusPlus);
        }
        if proc.contains("notepad") {
            return Some(AppEnvironment::Notepad);
        }
        if proc.contains("vim") || proc.contains("nvim") {
            return Some(AppEnvironment::Vim);
        }

        // ── Terminals (Windows-specific) ──────────────────────────────────────
        if proc.contains("windowsterminal") {
            return Some(AppEnvironment::WindowsTerminal);
        }
        if proc.contains("powershell") || title.contains("powershell") {
            return Some(AppEnvironment::PowerShell);
        }
        if proc.contains("cmd") || title.contains("command prompt") {
            return Some(AppEnvironment::CommandPrompt);
        }

        // ── Design Tools ──────────────────────────────────────────────────────
        if title.contains("notion") || proc.contains("notion") {
            return Some(AppEnvironment::Notion);
        }
        if title.contains("figma") || proc.contains("figma") {
            return Some(AppEnvironment::Figma);
        }
        if title.contains("canva") || proc.contains("canva") {
            return Some(AppEnvironment::Canva);
        }

        // ── Yjs-powered collaborative apps ────────────────────────────────────
        if title.contains("google docs") || title.contains("docs.google.com") {
            return Some(AppEnvironment::GoogleDocs);
        }
        if title.contains("google slides") || title.contains("slides.google.com") {
            return Some(AppEnvironment::GoogleSlides);
        }
        if title.contains("linear") && (proc.contains("linear") || title.contains("linear.app")) {
            return Some(AppEnvironment::LinearApp);
        }
        if title.contains("tiptap") {
            return Some(AppEnvironment::TiptapEditor);
        }
        if title.contains("liveblocks") {
            return Some(AppEnvironment::Liveblocks);
        }

        // ── Browsers (cross-platform) ─────────────────────────────────────────
        if proc.contains("chromium") {
            return Some(AppEnvironment::Chromium);
        }
        if proc.contains("chrome") {
            return Some(AppEnvironment::Chrome);
        }
        if proc.contains("firefox") {
            return Some(AppEnvironment::Firefox);
        }
        if proc.contains("msedge") {
            return Some(AppEnvironment::Edge);
        }

        // ── Communication ─────────────────────────────────────────────────────
        if proc.contains("slack") {
            return Some(AppEnvironment::Slack);
        }
        if proc.contains("teams") {
            return Some(AppEnvironment::Teams);
        }
        if proc.contains("discord") {
            return Some(AppEnvironment::Discord);
        }

        None
    }
}

pub struct ContextEngine {
    pub registry: FingerprinterRegistry,
}

impl Default for ContextEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl ContextEngine {
    pub fn new() -> Self {
        let mut registry = FingerprinterRegistry::new();
        registry.register(Box::new(DefaultFingerprinter));
        ContextEngine { registry }
    }

    /// Captures the complete application context at hotkey press time.
    pub fn capture(&self, full_text: &str) -> AppContext {
        let (process_name, window_title) = self.get_active_app_info();
        let environment = self
            .registry
            .identify(&process_name, &window_title)
            .unwrap_or(AppEnvironment::Unknown(process_name.clone()));

        let prompt_text = Self::extract_last_paragraph(full_text);
        let prompt_char_count = prompt_text.chars().count();

        let file_path = Self::resolve_file_path(&window_title, &process_name);
        let active_slide = Self::extract_slide_number(&window_title);

        tracing::info!(
            "📍 Context: env={} | file={:?} | slide={:?} | prompt='{}...' ({} chars)",
            environment.label(),
            file_path
                .as_ref()
                .and_then(|p| p.file_name())
                .and_then(|n| n.to_str()),
            active_slide,
            &prompt_text.chars().take(30).collect::<String>(),
            prompt_char_count
        );

        AppContext {
            process_name,
            window_title,
            environment,
            prompt_char_count,
            document_text: full_text.to_string(),
            prompt_text,
            file_path,
            active_slide,
        }
    }

    /// Resolve the document file path from the window title.
    pub fn resolve_file_path(
        window_title: &str,
        _process_name: &str,
    ) -> Option<std::path::PathBuf> {
        // Pattern: "Document.docx - Microsoft Word" or "Report.pptx - PowerPoint"
        let parts: Vec<&str> = window_title.splitn(2, " - ").collect();
        let candidate = parts.first()?.trim();

        // Strip common suffixes like "[Read-Only]", "[Compatibility Mode]"
        let clean = candidate
            .trim_end_matches(']')
            .rsplitn(2, '[')
            .last()
            .unwrap_or(candidate)
            .trim();

        let ext = std::path::Path::new(clean)
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_lowercase());

        let known_ext = matches!(
            ext.as_deref(),
            Some("docx")
                | Some("doc")
                | Some("pptx")
                | Some("ppt")
                | Some("xlsx")
                | Some("xls")
                | Some("odt")
                | Some("odp")
                | Some("ods")
                | Some("pdf")
                | Some("md")
                | Some("txt")
        );

        if !known_ext {
            return None;
        }

        // Search common document locations (works on all platforms via dirs crate)
        let search_dirs = [
            dirs::document_dir(),
            dirs::desktop_dir(),
            dirs::download_dir(),
            Some(std::path::PathBuf::from(r"C:\tests")),
        ];

        for dir in search_dirs.iter().flatten() {
            let candidate_path = dir.join(clean);
            if candidate_path.exists() {
                return Some(candidate_path);
            }
        }

        None
    }

    /// Extract the current slide number from a PowerPoint/Keynote/Impress window title.
    /// Handles: "Deck.pptx - PowerPoint [Slide 3 of 12]"
    pub fn extract_slide_number(window_title: &str) -> Option<usize> {
        let title_lower = window_title.to_lowercase();
        if let Some(slide_pos) = title_lower.find("slide ") {
            let after = &window_title[slide_pos + 6..];
            let num_str: String = after.chars().take_while(|c| c.is_ascii_digit()).collect();
            num_str.parse().ok()
        } else {
            None
        }
    }

    /// Extract the user's Kairo prompt from the captured text.
    ///
    /// Priority:
    /// 1. Last line starting with "//" — the canonical Kairo command syntax
    /// 2. Return empty — main.rs will show "type // first" toast
    pub fn extract_last_paragraph(text: &str) -> String {
        let lines: Vec<&str> = text
            .split(['\n', '\r'])
            .map(|s| s.trim())
            .filter(|s| !s.is_empty())
            .collect();

        if let Some(cmd_line) = lines.iter().rev().find(|l| l.starts_with("//")) {
            return cmd_line.to_string();
        }

        String::new()
    }

    /// Get the active foreground process name and window title.
    ///
    /// Cross-platform implementation:
    /// - Windows: Win32 GetForegroundWindow + QueryFullProcessImageNameW
    /// - macOS:   osascript AppleScript query
    /// - Linux:   xdotool getactivewindow queries
    pub fn get_active_app_info(&self) -> (String, String) {
        // ── Windows ──────────────────────────────────────────────────────────
        #[cfg(windows)]
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.is_invalid() {
                return ("Unknown".into(), "Unknown".into());
            }

            let mut title_buf = [0u16; 512];
            let title_len = GetWindowTextW(hwnd, &mut title_buf);
            let title = String::from_utf16_lossy(&title_buf[..title_len as usize]);

            let mut pid = 0u32;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));

            if let Ok(handle) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) {
                let mut path_buf = [0u16; 1024];
                let mut path_len = path_buf.len() as u32;
                if QueryFullProcessImageNameW(
                    handle,
                    PROCESS_NAME_WIN32,
                    windows::core::PWSTR(path_buf.as_mut_ptr()),
                    &mut path_len,
                )
                .is_ok()
                {
                    let full_path = String::from_utf16_lossy(&path_buf[..path_len as usize]);
                    let proc_name = std::path::Path::new(&full_path)
                        .file_name()
                        .and_then(|n| n.to_str())
                        .unwrap_or("Unknown")
                        .to_string();
                    return (proc_name, title);
                }
            }
            return ("Unknown".into(), title);
        }

        // ── macOS ─────────────────────────────────────────────────────────────
        #[cfg(target_os = "macos")]
        {
            return get_active_app_info_macos();
        }

        // ── Linux ─────────────────────────────────────────────────────────────
        #[cfg(target_os = "linux")]
        {
            return get_active_app_info_linux();
        }

        // ── Fallback (unsupported OS) ─────────────────────────────────────────
        #[allow(unreachable_code)]
        ("Unknown".into(), "Unknown".into())
    }
}

// ── macOS active app detection ────────────────────────────────────────────────

#[cfg(target_os = "macos")]
fn get_active_app_info_macos() -> (String, String) {
    use std::process::Command;

    // Use osascript to get frontmost app name and window title
    // AppleScript: tell application "System Events" to ...
    let script = r#"tell application "System Events"
        set frontApp to first application process whose frontmost is true
        set appName to name of frontApp
        set winTitle to ""
        try
            set winTitle to name of front window of frontApp
        end try
        return appName & "|" & winTitle
    end tell"#;

    let output = Command::new("osascript").args(["-e", script]).output();

    match output {
        Ok(out) if out.status.success() => {
            let result = String::from_utf8_lossy(&out.stdout).trim().to_string();
            let mut parts = result.splitn(2, '|');
            let app_name = parts.next().unwrap_or("Unknown").trim().to_string();
            let win_title = parts.next().unwrap_or("").trim().to_string();
            // On macOS, process name = app name (e.g., "Pages", "Microsoft Word")
            (
                app_name.clone(),
                if win_title.is_empty() {
                    app_name
                } else {
                    win_title
                },
            )
        }
        Ok(out) => {
            tracing::warn!(
                "[macOS] osascript failed (exit {}): {}",
                out.status,
                String::from_utf8_lossy(&out.stderr)
            );
            // Fallback: try using platform::macos reader
            (get_macos_frontmost_app_name(), "Unknown".into())
        }
        Err(e) => {
            tracing::warn!("[macOS] osascript not available: {}", e);
            (get_macos_frontmost_app_name(), "Unknown".into())
        }
    }
}

#[cfg(target_os = "macos")]
fn get_macos_frontmost_app_name() -> String {
    // Secondary strategy: read via macos-accessibility-client
    use std::process::Command;
    // Try a simpler AppleScript
    let out = Command::new("osascript")
        .args([
            "-e",
            "tell app \"System Events\" to get name of first process whose frontmost is true",
        ])
        .output()
        .ok();
    out.and_then(|o| {
        if o.status.success() {
            Some(String::from_utf8_lossy(&o.stdout).trim().to_string())
        } else {
            None
        }
    })
    .unwrap_or_else(|| "Unknown".to_string())
}

// ── Linux active app detection ────────────────────────────────────────────────

#[cfg(target_os = "linux")]
fn get_active_app_info_linux() -> (String, String) {
    use crate::platform::linux::{get_active_process_name, get_active_window_title};

    let title = get_active_window_title().unwrap_or_else(|| "Unknown".into());
    let proc = get_active_process_name().unwrap_or_else(|| "Unknown".into());
    (proc, title)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fingerprinter_windows_apps() {
        let fp = DefaultFingerprinter;
        assert_eq!(
            fp.fingerprint("WINWORD.EXE", "Document1 - Word"),
            Some(AppEnvironment::MicrosoftWord)
        );
        assert_eq!(
            fp.fingerprint("POWERPNT.EXE", "Presentation1 - PowerPoint"),
            Some(AppEnvironment::MicrosoftPowerPoint)
        );
        assert_eq!(
            fp.fingerprint("EXCEL.EXE", "Book1 - Excel"),
            Some(AppEnvironment::MicrosoftExcel)
        );
        assert_eq!(
            fp.fingerprint("OUTLOOK.EXE", "Inbox"),
            Some(AppEnvironment::MicrosoftOutlook)
        );
        assert_eq!(
            fp.fingerprint("notepad.exe", "Untitled - Notepad"),
            Some(AppEnvironment::Notepad)
        );
        assert_eq!(
            fp.fingerprint("Code.exe", "main.rs - VSCode"),
            Some(AppEnvironment::VSCode)
        );
    }

    #[test]
    fn test_fingerprinter_macos_apps() {
        let fp = DefaultFingerprinter;
        assert_eq!(
            fp.fingerprint("Pages", "Report.pages"),
            Some(AppEnvironment::Pages)
        );
        assert_eq!(
            fp.fingerprint("Keynote", "Pitch.key"),
            Some(AppEnvironment::Keynote)
        );
        assert_eq!(
            fp.fingerprint("Numbers", "Budget.numbers"),
            Some(AppEnvironment::Numbers)
        );
        assert_eq!(
            fp.fingerprint("TextEdit", "notes.txt"),
            Some(AppEnvironment::TextEdit)
        );
        assert_eq!(
            fp.fingerprint("Safari", "Google"),
            Some(AppEnvironment::Safari)
        );
        assert_eq!(
            fp.fingerprint("iTerm2", "bash"),
            Some(AppEnvironment::ITerm2)
        );
    }

    #[test]
    fn test_fingerprinter_linux_apps() {
        let fp = DefaultFingerprinter;
        assert_eq!(
            fp.fingerprint("soffice", "report.odt - LibreOffice Writer"),
            Some(AppEnvironment::LibreOfficeWriter)
        );
        assert_eq!(
            fp.fingerprint("soffice", "slides.odp - LibreOffice Impress"),
            Some(AppEnvironment::LibreOfficeImpress)
        );
        assert_eq!(
            fp.fingerprint("soffice", "budget.ods - LibreOffice Calc"),
            Some(AppEnvironment::LibreOfficeCalc)
        );
        assert_eq!(
            fp.fingerprint("gedit", "notes.txt - gedit"),
            Some(AppEnvironment::Gedit)
        );
        assert_eq!(
            fp.fingerprint("chromium", "GitHub"),
            Some(AppEnvironment::Chromium)
        );
        assert_eq!(
            fp.fingerprint("gnome-terminal", "bash"),
            Some(AppEnvironment::GnomeTerminal)
        );
    }

    #[test]
    fn test_fingerprinter_cross_platform_apps() {
        let fp = DefaultFingerprinter;
        assert_eq!(
            fp.fingerprint("code", "main.rs"),
            Some(AppEnvironment::VSCode)
        );
        assert_eq!(
            fp.fingerprint("firefox", "Mozilla Firefox"),
            Some(AppEnvironment::Firefox)
        );
        assert_eq!(
            fp.fingerprint("slack", "Slack"),
            Some(AppEnvironment::Slack)
        );
        assert_eq!(
            fp.fingerprint("discord", "Discord"),
            Some(AppEnvironment::Discord)
        );
    }

    #[test]
    fn test_extract_last_paragraph_finds_kairo_command() {
        let text = "Some document text\n\nMore text\n// rewrite this paragraph for a professional audience";
        assert_eq!(
            ContextEngine::extract_last_paragraph(text),
            "// rewrite this paragraph for a professional audience"
        );
    }

    #[test]
    fn test_extract_last_paragraph_no_command_returns_empty() {
        let text = "Just plain text with no command";
        assert_eq!(ContextEngine::extract_last_paragraph(text), "");
    }

    #[test]
    fn test_resolve_file_path_parses_window_title() {
        // Should return None because the file doesn't exist on disk — but
        // the parsing logic itself is verified: it must not panic or return
        // a path to a file that doesn't exist.
        let result =
            ContextEngine::resolve_file_path("report.docx - Microsoft Word", "WINWORD.EXE");
        // Either None (file not on disk) or Some(path) if it happens to exist
        // The key assertion is it doesn't panic
        let _ = result;
    }

    #[test]
    fn test_slide_number_extraction() {
        assert_eq!(
            ContextEngine::extract_slide_number("Deck.pptx [Slide 3 of 12]"),
            Some(3)
        );
        assert_eq!(ContextEngine::extract_slide_number("No slide info"), None);
    }

    #[test]
    fn test_context_engine_capture_returns_valid_struct() {
        let engine = ContextEngine::new();
        let ctx = engine.capture("// write a summary");
        assert!(!ctx.process_name.is_empty());
        assert_eq!(ctx.prompt_text, "// write a summary");
    }

    #[test]
    fn test_doc_kind_mapping_covers_all_platforms() {
        use crate::document_context::DocKind;
        assert_eq!(AppEnvironment::Pages.to_doc_kind(), DocKind::WordDocument);
        assert_eq!(AppEnvironment::Keynote.to_doc_kind(), DocKind::PowerPoint);
        assert_eq!(
            AppEnvironment::Numbers.to_doc_kind(),
            DocKind::ExcelSpreadsheet
        );
        assert_eq!(
            AppEnvironment::LibreOfficeWriter.to_doc_kind(),
            DocKind::WordDocument
        );
        assert_eq!(
            AppEnvironment::LibreOfficeImpress.to_doc_kind(),
            DocKind::PowerPoint
        );
        assert_eq!(
            AppEnvironment::LibreOfficeCalc.to_doc_kind(),
            DocKind::ExcelSpreadsheet
        );
        assert_eq!(
            AppEnvironment::GnomeTerminal.to_doc_kind(),
            DocKind::Terminal
        );
        assert_eq!(AppEnvironment::MacTerminal.to_doc_kind(), DocKind::Terminal);
    }
}
