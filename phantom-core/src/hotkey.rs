// phantom-core/src/hotkey.rs
//
// Cross-Platform Hotkey Detection — Domain 11: Cross-Platform Hardening
//
// ── Windows ──────────────────────────────────────────────────────────────────
// Uses WH_KEYBOARD_LL (low-level keyboard hook) for maximum compatibility
// with Office apps that intercept Alt before RegisterHotKey can fire.
//
// DESIGN: We ONLY suppress the 'M'/'V' key when Alt is held.
// We NEVER touch Alt key events — they pass through completely.
//
// WHY:
//   - RegisterHotKey fails when Word intercepts Alt for its ribbon first
//   - WH_KEYBOARD_LL fires before any app sees the keys
//   - Suppressing ONLY 'M'/'V' (not Alt) means Alt naturally releases itself
//   - Alt-up passes through → Windows clears Alt state → NO STUCK KEYS
//   - Ribbon might activate briefly, but injection re-focuses Word body
//
// ── macOS / Linux ────────────────────────────────────────────────────────────
// Uses `rdev::listen()` (already in Cargo.toml) which provides global keyboard
// events on macOS (via CGEvent tap) and Linux (via X11 / evdev).
//
// Hotkeys: Alt+Ctrl+M (ghost-write), Alt+V (voice), Alt+Shift+M (screen context)

use once_cell::sync::Lazy;
use std::sync::atomic::{AtomicBool, AtomicIsize, Ordering};
use std::sync::Mutex;
use tokio::sync::mpsc::Sender;
use tracing::{error, info, warn};

use crate::PhantomEvent;

// ── Shared state (all platforms) ─────────────────────────────────────────────

static GLOBAL_TX: Lazy<Mutex<Option<Sender<PhantomEvent>>>> = Lazy::new(|| Mutex::new(None));
static ALT_PRESSED: AtomicBool = AtomicBool::new(false);
static SHIFT_PRESSED: AtomicBool = AtomicBool::new(false);
static CONTROL_PRESSED: AtomicBool = AtomicBool::new(false);

/// HWND of the window that had focus when Alt+Ctrl+M fired (Windows only).
/// On non-Windows platforms this is always 0.
pub static CAPTURED_HWND: AtomicIsize = AtomicIsize::new(0);
pub static SKILL_SAVE_PENDING: AtomicBool = AtomicBool::new(false);
pub static CUA_PENDING: AtomicBool = AtomicBool::new(false);

// ── HotkeyWatcher — platform-agnostic entry point ────────────────────────────

pub struct HotkeyWatcher {
    hotkey_str: String,
    tx: Sender<PhantomEvent>,
}

impl HotkeyWatcher {
    pub fn new(hotkey_str: String, tx: Sender<PhantomEvent>) -> Self {
        HotkeyWatcher { hotkey_str, tx }
    }

    pub fn get_captured_hwnd() -> isize {
        CAPTURED_HWND.load(Ordering::SeqCst)
    }

    pub fn run(self) {
        {
            let mut guard = GLOBAL_TX.lock().unwrap();
            *guard = Some(self.tx.clone());
        }
        info!("⌨️  Installing keyboard hook (Target: {})", self.hotkey_str);

        #[cfg(windows)]
        Self::run_windows(self.hotkey_str);

        #[cfg(not(windows))]
        Self::run_rdev();
    }

    // ── Windows: WH_KEYBOARD_LL ───────────────────────────────────────────────

    #[cfg(windows)]
    fn run_windows(hotkey_str: String) {
        use windows::Win32::UI::WindowsAndMessaging::{
            CallNextHookEx, DispatchMessageW, GetMessageW, SetWindowsHookExW, TranslateMessage,
            UnhookWindowsHookEx, MSG, WH_KEYBOARD_LL,
        };

        std::thread::spawn(move || unsafe {
            let h_hook = SetWindowsHookExW(WH_KEYBOARD_LL, Some(low_level_keyboard_proc), None, 0)
                .expect("Failed to install WH_KEYBOARD_LL hook");

            info!("✅ Keyboard hook active (Windows WH_KEYBOARD_LL). Listening for Alt+Ctrl+M.");
            info!("   Alt events pass through unmodified — no stuck key risk.");

            let mut msg = MSG::default();
            while GetMessageW(&mut msg, None, 0, 0).as_bool() {
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }

            UnhookWindowsHookEx(h_hook).ok();
            info!("🔑 Keyboard hook removed.");
        });
    }

    // ── macOS / Linux: rdev global listener ─────────────────────────────────

    #[cfg(not(windows))]
    fn run_rdev() {
        use rdev::{listen, EventType, Key};

        std::thread::spawn(move || {
            info!("✅ Keyboard hook active (rdev cross-platform). Listening for Alt+Ctrl+M.");

            // rdev::listen blocks the thread and calls the callback for every event.
            // We cannot return a Result from listen's callback, so we use the atomics.
            if let Err(e) = listen(move |event| {
                match event.event_type {
                    // Track modifier key state
                    EventType::KeyPress(Key::Alt) | EventType::KeyPress(Key::AltGr) => {
                        ALT_PRESSED.store(true, Ordering::SeqCst);
                    }
                    EventType::KeyRelease(Key::Alt) | EventType::KeyRelease(Key::AltGr) => {
                        ALT_PRESSED.store(false, Ordering::SeqCst);
                    }
                    EventType::KeyPress(Key::ShiftLeft) | EventType::KeyPress(Key::ShiftRight) => {
                        SHIFT_PRESSED.store(true, Ordering::SeqCst);
                    }
                    EventType::KeyRelease(Key::ShiftLeft)
                    | EventType::KeyRelease(Key::ShiftRight) => {
                        SHIFT_PRESSED.store(false, Ordering::SeqCst);
                    }
                    EventType::KeyPress(Key::ControlLeft)
                    | EventType::KeyPress(Key::ControlRight) => {
                        CONTROL_PRESSED.store(true, Ordering::SeqCst);
                    }
                    EventType::KeyRelease(Key::ControlLeft)
                    | EventType::KeyRelease(Key::ControlRight) => {
                        CONTROL_PRESSED.store(false, Ordering::SeqCst);
                    }

                    EventType::KeyPress(key) => {
                        if CUA_PENDING.load(Ordering::SeqCst) {
                            let is_modifier = matches!(
                                key,
                                Key::Alt
                                    | Key::AltGr
                                    | Key::ShiftLeft
                                    | Key::ShiftRight
                                    | Key::ControlLeft
                                    | Key::ControlRight
                            );
                            if !is_modifier {
                                if key == Key::Tab {
                                    info!("🎯 Intercepted Tab keypress for CUA approval (rdev)!");
                                    CUA_PENDING.store(false, Ordering::SeqCst);
                                    send_event(PhantomEvent::CuaApproved);
                                } else if key == Key::Escape {
                                    info!("❌ CUA cancelled by Escape keypress (rdev).");
                                    CUA_PENDING.store(false, Ordering::SeqCst);
                                    send_event(PhantomEvent::CuaCancelled);
                                } else {
                                    info!(
                                        "❌ CUA cancelled because user pressed another key (rdev)."
                                    );
                                    CUA_PENDING.store(false, Ordering::SeqCst);
                                    send_event(PhantomEvent::CuaCancelled);
                                }
                                return;
                            }
                        }

                        if SKILL_SAVE_PENDING.load(Ordering::SeqCst) {
                            let is_modifier = matches!(
                                key,
                                Key::Alt
                                    | Key::AltGr
                                    | Key::ShiftLeft
                                    | Key::ShiftRight
                                    | Key::ControlLeft
                                    | Key::ControlRight
                            );
                            if !is_modifier {
                                if key == Key::Tab {
                                    info!("🎯 Intercepted Tab keypress (rdev)!");
                                    SKILL_SAVE_PENDING.store(false, Ordering::SeqCst);
                                    send_event(PhantomEvent::SkillSaveApproved);
                                } else {
                                    info!("❌ Skill save cancelled because user pressed another key (rdev).");
                                    SKILL_SAVE_PENDING.store(false, Ordering::SeqCst);
                                    send_event(PhantomEvent::SkillSaveCancelled);
                                }
                                return;
                            }
                        }

                        let alt = ALT_PRESSED.load(Ordering::SeqCst);
                        let shift = SHIFT_PRESSED.load(Ordering::SeqCst);
                        let ctrl = CONTROL_PRESSED.load(Ordering::SeqCst);

                        // Ctrl+Shift+Z → Undo
                        if ctrl && shift && key == Key::KeyZ {
                            info!("↩️ Ctrl+Shift+Z detected (rdev)! Undo triggered.");
                            send_event(PhantomEvent::UndoPressed);
                        }
                        // Alt+Shift+M → Screen Context (must check before Alt+Ctrl+M)
                        else if alt && shift && key == Key::KeyM {
                            info!("📸 Alt+Shift+M detected (rdev)! Screen Context triggered.");
                            send_event(PhantomEvent::ScreenContextPressed);
                        }
                        // Alt+V → Voice Dictation
                        else if alt && key == Key::KeyV {
                            info!("🎤 Alt+V detected (rdev)! Voice Dictation triggered.");
                            send_event(PhantomEvent::VoicePressed);
                        }
                        // Alt+Ctrl+M (no Shift) → Ghost-Write
                        else if alt && ctrl && !shift && key == Key::KeyM {
                            info!("🔥 Alt+Ctrl+M detected (rdev)! Ghost-Write triggered.");
                            send_event(PhantomEvent::HotkeyPressed);
                        }
                    }
                    _ => {}
                }
            }) {
                error!("[rdev] Global keyboard listener error: {:?}", e);
                warn!("On Linux, rdev requires X11 (DISPLAY env var) or root for evdev.");
                warn!("On macOS, you may need to grant Accessibility permission.");
            }
        });
    }
}

// ── Helper: send PhantomEvent to main loop ────────────────────────────────────

fn send_event(event: PhantomEvent) {
    if let Ok(guard) = GLOBAL_TX.try_lock() {
        if let Some(tx) = guard.as_ref() {
            let _ = tx.blocking_send(event);
        }
    }
}

// ── Windows: Low-Level Keyboard Hook Callback ─────────────────────────────────
//
// This function is only compiled on Windows. It captures the exact HWND that
// was focused when Alt+Ctrl+M fired — critical for the injector to type into the
// correct window.

#[cfg(windows)]
use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
#[cfg(windows)]
use windows::Win32::UI::Input::KeyboardAndMouse::{
    VK_CONTROL, VK_LCONTROL, VK_LMENU, VK_LSHIFT, VK_MENU, VK_RCONTROL, VK_RMENU, VK_RSHIFT,
    VK_SHIFT,
};
#[cfg(windows)]
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, GetForegroundWindow, HC_ACTION, KBDLLHOOKSTRUCT, WM_KEYDOWN, WM_SYSKEYDOWN,
};

#[cfg(windows)]
unsafe extern "system" fn low_level_keyboard_proc(
    code: i32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    if code != HC_ACTION as i32 {
        return CallNextHookEx(None, code, wparam, lparam);
    }

    let kbd = *(lparam.0 as *const KBDLLHOOKSTRUCT);
    let msg = wparam.0 as u32;
    let is_down = msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN;
    let is_up = msg == 0x0101 /* WM_KEYUP */ || msg == 0x0105 /* WM_SYSKEYUP */;

    // Track Alt state — but PASS THROUGH all Alt events unchanged.
    // Not consuming Alt-up is what prevents Alt from getting stuck.
    let is_alt_vk = kbd.vkCode == VK_MENU.0 as u32
        || kbd.vkCode == VK_LMENU.0 as u32
        || kbd.vkCode == VK_RMENU.0 as u32;

    if is_alt_vk {
        ALT_PRESSED.store(is_down, Ordering::SeqCst);
        return CallNextHookEx(None, code, wparam, lparam);
    }

    // Track Shift state (same principle — pass through, only track)
    let is_shift_vk = kbd.vkCode == VK_SHIFT.0 as u32
        || kbd.vkCode == VK_LSHIFT.0 as u32
        || kbd.vkCode == VK_RSHIFT.0 as u32;

    if is_shift_vk {
        SHIFT_PRESSED.store(is_down, Ordering::SeqCst);
        return CallNextHookEx(None, code, wparam, lparam);
    }

    // Track Ctrl state (same principle — pass through, only track)
    let is_ctrl_vk = kbd.vkCode == VK_CONTROL.0 as u32
        || kbd.vkCode == VK_LCONTROL.0 as u32
        || kbd.vkCode == VK_RCONTROL.0 as u32;

    if is_ctrl_vk {
        CONTROL_PRESSED.store(is_down, Ordering::SeqCst);
        return CallNextHookEx(None, code, wparam, lparam);
    }

    if CUA_PENDING.load(Ordering::SeqCst) && is_down {
        if kbd.vkCode == 0x09 {
            // Tab
            info!("🎯 Intercepted Tab keypress for CUA approval!");
            CUA_PENDING.store(false, Ordering::SeqCst);
            send_event(PhantomEvent::CuaApproved);
            return LRESULT(1); // Suppress Tab keystroke
        } else if kbd.vkCode == 0x1B {
            // Esc
            info!("❌ CUA cancelled by user pressing Escape.");
            CUA_PENDING.store(false, Ordering::SeqCst);
            send_event(PhantomEvent::CuaCancelled);
            return LRESULT(1); // Suppress Esc keystroke
        } else {
            info!("❌ CUA cancelled because user pressed another key.");
            CUA_PENDING.store(false, Ordering::SeqCst);
            send_event(PhantomEvent::CuaCancelled);
        }
    }

    if SKILL_SAVE_PENDING.load(Ordering::SeqCst) && is_down {
        if kbd.vkCode == 0x09 {
            info!("🎯 Intercepted Tab keypress for dynamic skill save approval!");
            SKILL_SAVE_PENDING.store(false, Ordering::SeqCst);
            send_event(PhantomEvent::SkillSaveApproved);
            return LRESULT(1); // Suppress Tab keystroke
        } else {
            info!("❌ Skill save cancelled because user pressed another key.");
            SKILL_SAVE_PENDING.store(false, Ordering::SeqCst);
            send_event(PhantomEvent::SkillSaveCancelled);
        }
    }

    // ── Ctrl+Shift+Z: Undo last injection ──────────────────────────────
    if kbd.vkCode == 0x5A /* Z */ && is_down
       && CONTROL_PRESSED.load(Ordering::SeqCst)
       && SHIFT_PRESSED.load(Ordering::SeqCst)
    {
        let hwnd: HWND = GetForegroundWindow();
        CAPTURED_HWND.store(hwnd.0 as isize, Ordering::SeqCst);
        info!(
            "↩️ Ctrl+Shift+Z detected! Triggering Undo. HWND={:?}",
            hwnd.0
        );
        send_event(PhantomEvent::UndoPressed);
        return LRESULT(1); // Suppress 'Z'
    }

    // ── Alt+Shift+M: Screen Context (must check BEFORE Alt+Ctrl+M) ─────────────
    if kbd.vkCode == 0x4D
        && is_down
        && ALT_PRESSED.load(Ordering::SeqCst)
        && SHIFT_PRESSED.load(Ordering::SeqCst)
    {
        let hwnd: HWND = GetForegroundWindow();
        CAPTURED_HWND.store(hwnd.0 as isize, Ordering::SeqCst);
        info!(
            "📸 Alt+Shift+M detected! Screen Context → HWND={:?}",
            hwnd.0
        );
        send_event(PhantomEvent::ScreenContextPressed);
        return LRESULT(1); // Suppress 'M'
    }

    // ── Alt+V: Voice Dictation ─────────────────────────────────────────────
    if kbd.vkCode == 0x56 /* V */ && is_down && ALT_PRESSED.load(Ordering::SeqCst) {
        let hwnd: HWND = GetForegroundWindow();
        CAPTURED_HWND.store(hwnd.0 as isize, Ordering::SeqCst);
        info!("🎤 Alt+V detected! Voice Dictation → HWND={:?}", hwnd.0);
        send_event(PhantomEvent::VoicePressed);
        return LRESULT(1); // Suppress 'V'
    }

    // ── Alt+Ctrl+M: Ghost-Write (CUA 1000x hotkey) ─────────────────────────
    if kbd.vkCode == 0x4D
        && is_down
        && ALT_PRESSED.load(Ordering::SeqCst)
        && CONTROL_PRESSED.load(Ordering::SeqCst)
        && !SHIFT_PRESSED.load(Ordering::SeqCst)
    // NOT Alt+Shift+M
    {
        let hwnd: HWND = GetForegroundWindow();
        CAPTURED_HWND.store(hwnd.0 as isize, Ordering::SeqCst);
        info!("🔥 Alt+Ctrl+M detected! HWND={:?}", hwnd.0);
        send_event(PhantomEvent::HotkeyPressed);
        return LRESULT(1); // SUPPRESS ONLY 'M'
    }

    // MEMMACHINE_TAB_HOOK: On Tab approval, record interaction for style learning
    // Send IPC message: {"event": "tab_approved", "domain": domain, "timestamp": ...}
    // This triggers MemorySeeder.record_interaction() in the Python sidecar

    // All other keys pass through unchanged
    CallNextHookEx(None, code, wparam, lparam)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_atomic_state_initial_values() {
        assert!(!ALT_PRESSED.load(Ordering::SeqCst));
        assert!(!SHIFT_PRESSED.load(Ordering::SeqCst));
        assert_eq!(CAPTURED_HWND.load(Ordering::SeqCst), 0);
        assert!(!SKILL_SAVE_PENDING.load(Ordering::SeqCst));
    }

    #[test]
    fn test_skill_save_pending_toggle() {
        assert!(!SKILL_SAVE_PENDING.load(Ordering::SeqCst));
        SKILL_SAVE_PENDING.store(true, Ordering::SeqCst);
        assert!(SKILL_SAVE_PENDING.load(Ordering::SeqCst));
        SKILL_SAVE_PENDING.store(false, Ordering::SeqCst);
        assert!(!SKILL_SAVE_PENDING.load(Ordering::SeqCst));
    }

    #[test]
    fn test_hotkey_watcher_construction() {
        let (tx, _rx) = tokio::sync::mpsc::channel(10);
        let watcher = HotkeyWatcher::new("Alt+Ctrl+M".to_string(), tx);
        assert_eq!(watcher.hotkey_str, "Alt+Ctrl+M");
    }

    #[test]
    fn test_get_captured_hwnd_returns_zero_initially() {
        CAPTURED_HWND.store(0, Ordering::SeqCst);
        assert_eq!(HotkeyWatcher::get_captured_hwnd(), 0);
    }
}
