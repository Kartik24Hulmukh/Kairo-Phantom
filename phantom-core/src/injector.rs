/// Real cross-platform keyboard injector — uses PlatformInjector for actual text injection.
/// v2.0 PRODUCTION REWRITE:
/// - Removed backspace-based erase_prompt (unreliable: backspaces miss document body focus)
/// - New strategy: Home + Shift+End + Ctrl+V (select current line → replace with paste)
/// - Added click_to_focus() via mouse_event to click document body before sending keys
/// - Clipboard is always set BEFORE focus switch to avoid clipboard race
use std::thread;
use std::time::Duration;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum SpeedProfile {
    Ghost,
    FastHuman,
    Natural,
    Readable,
}

pub struct HumanizedInjector {
    pub profile: SpeedProfile,
    delay_ms: u64,
    platform_injector: Box<dyn crate::platform::PlatformInjector>,
}

impl HumanizedInjector {
    pub fn new(delay_ms: u64) -> Self {
        let profile = if delay_ms == 0 {
            SpeedProfile::Ghost
        } else if delay_ms < 30 {
            SpeedProfile::FastHuman
        } else if delay_ms < 100 {
            SpeedProfile::Natural
        } else {
            SpeedProfile::Readable
        };
        Self {
            profile,
            delay_ms,
            platform_injector: crate::platform::new_injector(),
        }
    }

    // ─── Core: Send a single Unicode character via PlatformInjector ──────────

    fn send_char(&self, c: char) {
        self.platform_injector.send_char(c);
    }

    // ─── Core: Send a virtual key down+up ────────────────────────────────────

    fn send_vk(&self, vk: u16) {
        self.platform_injector.send_vk(vk);
    }

    // ─── Production Injection Strategy ───────────────────────────────────────
    //
    // THE CORRECT APPROACH FOR ALL DESKTOP APPS:
    //
    //   1. Set clipboard = AI response  (BEFORE focusing the window)
    //   2. BringWindowToTop + SetForegroundWindow
    //   3. Wait 300ms for OS to fully grant keyboard focus to document body
    //   4. Send HOME  → move cursor to beginning of the prompt line
    //   5. Send Shift+END → select entire line (the // prompt)
    //   6. Send Ctrl+V  → paste replaces the selection
    //
    // This completely eliminates backspace-based erasure which requires the
    // text cursor to be in exactly the right position with full keyboard focus.
    // Select-line-then-paste is atomic and focus-position-independent.

    /// PRIMARY injection method: set clipboard FIRST (before focus switch),
    /// then caller does BringWindowToTop + 300ms sleep, then calls inject_replace_line().
    pub fn prepare_clipboard(&self, text: &str) -> bool {
        if !self.platform_injector.set_clipboard(text) {
            tracing::warn!("Clipboard set failed");
            return false;
        }
        tracing::info!("Clipboard ready: {} chars", text.len());
        true
    }

    /// SECONDARY injection: select the current line and replace it with clipboard content.
    /// Call this AFTER window focus is confirmed (300ms+ after SetForegroundWindow).
    ///
    /// Sequence: Home → Shift+End → (optional: Delete) → Ctrl+V
    pub fn inject_replace_line(&self) {
        self.platform_injector.inject_replace_line();
    }

    pub fn inject_via_value_pattern(&self, text: &str) -> bool {
        self.platform_injector.inject_via_value_pattern(text)
    }

    /// All-in-one: set clipboard + select line + paste.
    /// This is the main entry point called from main.rs ghost session handler.
    /// Caller must have already called BringWindowToTop + SetForegroundWindow + 300ms sleep.
    pub fn inject_via_clipboard(&self, text: &str) -> bool {
        if text.is_empty() {
            return true;
        }

        let _guard = CLIPBOARD_MUTEX.lock().unwrap();

        // Try direct UIAutomation ValuePattern set first (e.g. browser input fields)
        if self.inject_via_value_pattern(text) {
            return true;
        }

        // Save original clipboard
        let original_clipboard = Self::get_clipboard();

        // Step 1: Set clipboard FIRST
        if !self.platform_injector.set_clipboard(text) {
            tracing::warn!("Clipboard set failed, trying SendInput char-by-char");
            self.type_text_sendinput(text);
            return true;
        }
        thread::sleep(Duration::from_millis(30));

        // Step 2: Select current line (Home + Shift+End) then paste (Ctrl+V)
        self.inject_replace_line();

        // Step 3: Wait and restore original clipboard
        thread::sleep(Duration::from_millis(150));
        if let Some(orig) = original_clipboard {
            if !self.platform_injector.set_clipboard(&orig) {
                tracing::warn!("Failed to restore original clipboard content");
            } else {
                tracing::info!("Clipboard restored to original content");
            }
        }

        for word in text.split_whitespace().take(5) {
            tracing::debug!("Injected: {}", word);
        }
        tracing::info!("inject_via_clipboard complete ({} chars)", text.len());
        true
    }

    /// Legacy: erase N chars via backspace. Kept for compatibility but
    /// this is NO LONGER CALLED in the main ghost session flow.
    pub fn erase_prompt(&self, count: usize) {
        self.platform_injector.erase_prompt(count);
    }

    /// Type text — always via clipboard for reliability.
    pub fn type_text(&self, text: &str) {
        if text.is_empty() {
            return;
        }
        tracing::info!("type_text: {} chars via clipboard", text.len());
        self.inject_via_clipboard(text);
    }

    /// Fallback: type char by char using SendInput (Unicode).
    /// Only used when clipboard fails.
    fn type_text_sendinput(&self, text: &str) {
        let delay = match self.profile {
            SpeedProfile::Ghost => 0,
            SpeedProfile::FastHuman => 15,
            _ => 25,
        };
        for c in text.chars() {
            self.send_char(c);
            if delay > 0 {
                thread::sleep(Duration::from_millis(delay));
            }
        }
    }

    /// Get clipboard content.
    pub fn get_clipboard() -> Option<String> {
        let injector = crate::platform::new_injector();
        injector.get_clipboard()
    }

    /// Set clipboard content.
    pub fn set_clipboard(text: &str) -> bool {
        let injector = crate::platform::new_injector();
        injector.set_clipboard(text)
    }

    /// Send Ctrl+V keystroke.
    fn send_ctrl_v() {
        let injector = crate::platform::new_injector();
        injector.send_ctrl_v();
    }

    /// Escape any ribbon/menu mode.
    pub fn escape_ribbon_mode(&self) {
        // Intentionally a no-op. Double-ESC was destroying Word document state.
    }

    /// Undo ghost char — no-op (hook consumes the key).
    pub fn undo_ghost_char(&self) {}

    // Legacy async API (kept for compatibility)
    pub async fn inject_char(
        &mut self,
        c: char,
        cancel: &tokio_util::sync::CancellationToken,
    ) -> bool {
        if cancel.is_cancelled() {
            return false;
        }
        self.send_char(c);
        true
    }

    pub async fn inject_stream(
        &mut self,
        text: &str,
        cancel: &tokio_util::sync::CancellationToken,
    ) {
        for c in text.chars() {
            if !self.inject_char(c, cancel).await {
                break;
            }
        }
    }

    pub fn select_backward(count: usize) {
        let injector = crate::platform::new_injector();
        injector.select_backward(count);
    }

    pub fn record_injection(original_text: &str, injected_text: &str, hwnd: isize) {
        if let Ok(mut buffer) = UNDO_BUFFER.lock() {
            buffer.push(UndoRecord {
                original_text: original_text.to_string(),
                injected_text: injected_text.to_string(),
                hwnd,
                timestamp: std::time::Instant::now(),
            });
            if buffer.len() > UNDO_BUFFER_LIMIT {
                buffer.remove(0);
            }
            tracing::info!("Recorded injection for undo. Buffer size: {}", buffer.len());
        }
    }

    pub fn perform_undo() -> bool {
        let record = {
            let mut buffer = match UNDO_BUFFER.lock() {
                Ok(b) => b,
                Err(_) => return false,
            };
            buffer.pop()
        };

        if let Some(record) = record {
            tracing::info!("Performing undo for hwnd: {}", record.hwnd);

            let injector = crate::platform::new_injector();

            // Focus the window
            if injector.focus_window(record.hwnd) {
                thread::sleep(Duration::from_millis(200));
            }

            // Save current clipboard
            let original_clipboard = injector.get_clipboard();

            // Set clipboard to original text
            let _ = injector.set_clipboard(&record.original_text);
            thread::sleep(Duration::from_millis(30));

            // Select back injected_text character count
            let char_count = record.injected_text.chars().count();
            injector.select_backward(char_count);
            thread::sleep(Duration::from_millis(50));

            // Paste (replaces selection with original_text)
            injector.send_ctrl_v();
            thread::sleep(Duration::from_millis(150));

            // Restore clipboard
            if let Some(orig) = original_clipboard {
                let _ = injector.set_clipboard(&orig);
            }

            tracing::info!("Undo execution complete");
            true
        } else {
            tracing::warn!("No undo records available");
            false
        }
    }
}

#[derive(Debug, Clone)]
pub struct UndoRecord {
    pub original_text: String,
    pub injected_text: String,
    pub hwnd: isize,
    pub timestamp: std::time::Instant,
}

use once_cell::sync::Lazy;
use std::sync::Mutex;

pub static UNDO_BUFFER: Lazy<Mutex<Vec<UndoRecord>>> = Lazy::new(|| Mutex::new(Vec::new()));
const UNDO_BUFFER_LIMIT: usize = 10;

pub static CLIPBOARD_MUTEX: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));
