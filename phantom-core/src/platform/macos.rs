use super::{AccessibilityReader, CuaAction, CuaContext, PlatformCuaDriver, PlatformInjector};
use anyhow::{anyhow, Result};
/// macOS Platform Injection — Advancement 2
/// Background ghost injection via CGEventPostToPid.
/// No focus stealing, no cursor jumping — pure background magic.
use tracing::{debug, info, warn};

#[cfg(target_os = "macos")]
mod macos_impl {
    use std::process::Command;
    use tracing::{info, warn};

    /// Get the PID of the currently focused application via AppleScript.
    pub fn get_focused_pid() -> Option<i32> {
        let output = Command::new("osascript")
            .args(["-e", "tell application \"System Events\" to get unix id of first process whose frontmost is true"])
            .output().ok()?;
        let s = String::from_utf8_lossy(&output.stdout).trim().to_string();
        s.parse::<i32>().ok()
    }

    /// Get the bundle ID of the frontmost app (for fingerprinting).
    pub fn get_focused_bundle_id() -> Option<String> {
        let output = Command::new("osascript")
            .args(["-e", "id of app (path to frontmost application as text)"])
            .output()
            .ok()?;
        let s = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if s.is_empty() {
            None
        } else {
            Some(s)
        }
    }

    use core_graphics::event::{CGEvent, CGEventFlags, CGEventType, CGKeyCode};
    use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};

    /// Map a character to a CGKeyCode and flags.
    fn char_to_keycode(c: char) -> Option<(CGKeyCode, CGEventFlags)> {
        match c {
            'a'..='z' => Some(((c as u16) - ('a' as u16), CGEventFlags::empty())),
            'A'..='Z' => Some(((c as u16) - ('A' as u16), CGEventFlags::CGEventFlagShift)),
            ' ' => Some((0x31, CGEventFlags::empty())),
            '\n' => Some((0x24, CGEventFlags::empty())),
            _ => None,
        }
    }

    /// Inject text into the focused process via CGEventPostToPid.
    pub fn inject_text_via_clipboard(text: &str) -> bool {
        let mut child = match std::process::Command::new("pbcopy")
            .stdin(std::process::Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                warn!("[macOS] pbcopy failed: {}", e);
                return false;
            }
        };

        if let Some(stdin) = child.stdin.as_mut() {
            use std::io::Write;
            if stdin.write_all(text.as_bytes()).is_err() {
                warn!("[macOS] Failed to write to pbcopy stdin");
                return false;
            }
        }
        let _ = child.wait();

        std::thread::sleep(std::time::Duration::from_millis(30));

        let pid = match get_focused_pid() {
            Some(p) => p,
            None => return false,
        };

        let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).unwrap();

        let mut v_down = CGEvent::new_keyboard_event(source.clone(), 0x09, true).unwrap();
        v_down.set_flags(CGEventFlags::CGEventFlagCommand);

        let mut v_up = CGEvent::new_keyboard_event(source, 0x09, false).unwrap();
        v_up.set_flags(CGEventFlags::CGEventFlagCommand);

        v_down.post_to_pid(pid);
        std::thread::sleep(std::time::Duration::from_millis(5));
        v_up.post_to_pid(pid);

        info!(
            "[macOS] Injected {} chars via CGEventPostToPid(Cmd+V) to PID {}",
            text.len(),
            pid
        );
        true
    }

    pub fn send_keystroke_applescript(key: &str, _modifiers: &[&str]) -> bool {
        let pid = match get_focused_pid() {
            Some(p) => p,
            None => return false,
        };

        let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).unwrap();
        let keycode = match key {
            "delete" => 0x33,
            "return" => 0x24,
            "escape" => 0x35,
            _ => return false,
        };

        let event_down = CGEvent::new_keyboard_event(source.clone(), keycode, true).unwrap();
        let event_up = CGEvent::new_keyboard_event(source, keycode, false).unwrap();

        event_down.post_to_pid(pid);
        std::thread::sleep(std::time::Duration::from_millis(2));
        event_up.post_to_pid(pid);

        true
    }

    pub fn erase_chars(count: usize) -> bool {
        let pid = match get_focused_pid() {
            Some(p) => p,
            None => return false,
        };

        let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).unwrap();

        for _ in 0..count {
            let event_down = CGEvent::new_keyboard_event(source.clone(), 0x33, true).unwrap();
            let event_up = CGEvent::new_keyboard_event(source.clone(), 0x33, false).unwrap();

            event_down.post_to_pid(pid);
            event_up.post_to_pid(pid);
            std::thread::sleep(std::time::Duration::from_millis(1));
        }

        true
    }

    pub fn check_accessibility_permission() -> bool {
        let pid = std::process::id() as i32;
        let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).unwrap();
        if let Ok(event) = CGEvent::new_keyboard_event(source, 0xFF, true) {
            event.post_to_pid(pid);
            true
        } else {
            false
        }
    }
}

#[cfg(not(target_os = "macos"))]
mod macos_impl {
    pub fn get_focused_pid() -> Option<i32> {
        None
    }
    pub fn get_focused_bundle_id() -> Option<String> {
        None
    }
    pub fn inject_text_via_clipboard(_: &str) -> bool {
        false
    }
    pub fn send_keystroke_applescript(_: &str, _: &[&str]) -> bool {
        false
    }
    pub fn erase_chars(_: usize) -> bool {
        false
    }
    pub fn check_accessibility_permission() -> bool {
        false
    }
}

pub use macos_impl::*;

/// macOS-specific injector that wraps all platform capabilities.
pub struct MacOsInjector;

impl Default for MacOsInjector {
    fn default() -> Self {
        Self::new()
    }
}

impl MacOsInjector {
    pub fn new() -> Self {
        Self
    }
    pub fn inject(&self, text: &str) -> bool {
        inject_text_via_clipboard(text)
    }
    pub fn erase(&self, count: usize) -> bool {
        erase_chars(count)
    }
    pub fn has_permission(&self) -> bool {
        check_accessibility_permission()
    }
    pub fn focused_app(&self) -> Option<String> {
        get_focused_bundle_id()
    }
}

/// macOS implementation of the AccessibilityReader trait using AXUIElement.
pub struct MacOsAccessibilityReader;

impl Default for MacOsAccessibilityReader {
    fn default() -> Self {
        Self::new()
    }
}

impl MacOsAccessibilityReader {
    pub fn new() -> Self {
        Self
    }
}

#[cfg(target_os = "macos")]
impl AccessibilityReader for MacOsAccessibilityReader {
    fn get_focused_text(&self) -> Result<String> {
        // macos-accessibility-client 0.0.2 only exposes application_is_trusted_with_prompt();
        // use AppleScript to read the frontmost app's selected text as a fallback.
        let output = std::process::Command::new("osascript")
            .args(["-e", "tell application \"System Events\" to get value of UI element 1 of text area 1 of window 1 of (first process whose frontmost is true)"])
            .output();
        match output {
            Ok(o) if o.status.success() => {
                Ok(String::from_utf8_lossy(&o.stdout).trim().to_string())
            }
            _ => Err(anyhow!("Could not read focused text via AppleScript")),
        }
    }

    fn get_clipboard_text(&self) -> Result<String> {
        let mut child = std::process::Command::new("pbpaste")
            .stdout(std::process::Stdio::piped())
            .spawn()?;

        let output = child.wait_with_output()?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            Err(anyhow!("pbpaste failed"))
        }
    }

    fn set_focused_text(&self, _text: &str) -> Result<()> {
        Err(anyhow!(
            "macOS set_focused_text via AXUIElement not yet implemented"
        ))
    }
}

#[cfg(not(target_os = "macos"))]
impl AccessibilityReader for MacOsAccessibilityReader {
    fn get_focused_text(&self) -> Result<String> {
        Err(anyhow!(
            "macOS accessibility is not supported on this platform"
        ))
    }
    fn get_clipboard_text(&self) -> Result<String> {
        Err(anyhow!("macOS clipboard is not supported on this platform"))
    }
    fn set_focused_text(&self, _text: &str) -> Result<()> {
        Err(anyhow!(
            "macOS accessibility is not supported on this platform"
        ))
    }
}

// ─── macOS Platform Injector & CUA Driver (B-13 Stub) ─────────────────────────

pub struct MacOsPlatformInjector;

impl MacOsPlatformInjector {
    pub fn new() -> Self {
        MacOsPlatformInjector
    }
}

impl Default for MacOsPlatformInjector {
    fn default() -> Self {
        Self::new()
    }
}

impl PlatformInjector for MacOsPlatformInjector {
    fn set_clipboard(&self, _text: &str) -> bool {
        false
    }
    fn get_clipboard(&self) -> Option<String> {
        None
    }
    fn send_char(&self, _c: char) {}
    fn send_vk(&self, _vk: u16) {}
    fn send_ctrl_v(&self) {}
    fn inject_via_value_pattern(&self, _text: &str) -> bool {
        false
    }
    fn select_backward(&self, _count: usize) {}
    fn focus_window(&self, _hwnd: isize) -> bool {
        false
    }
    fn inject_replace_line(&self) {
        // macOS: Cmd+Left (Home) + Shift+Cmd+Right (End) + Cmd+V
        if let Some(pid) = macos_impl::get_focused_pid() {
            let source = core_graphics::event_source::CGEventSource::new(
                core_graphics::event_source::CGEventSourceStateID::HIDSystemState,
            )
            .ok();
            if let Some(source) = source {
                // Cmd+Left
                let mut home_down =
                    core_graphics::event::CGEvent::new_keyboard_event(source.clone(), 0x7B, true)
                        .ok();
                if let Some(e) = home_down.as_mut() {
                    e.set_flags(core_graphics::event::CGEventFlags::CGEventFlagCommand);
                    e.post_to_pid(pid);
                }
                let mut home_up =
                    core_graphics::event::CGEvent::new_keyboard_event(source.clone(), 0x7B, false)
                        .ok();
                if let Some(e) = home_up.as_mut() {
                    e.set_flags(core_graphics::event::CGEventFlags::CGEventFlagCommand);
                    e.post_to_pid(pid);
                }
                std::thread::sleep(std::time::Duration::from_millis(30));
                // Shift+Cmd+Right
                let mut end_down =
                    core_graphics::event::CGEvent::new_keyboard_event(source.clone(), 0x7C, true)
                        .ok();
                if let Some(e) = end_down.as_mut() {
                    e.set_flags(
                        core_graphics::event::CGEventFlags::CGEventFlagCommand
                            | core_graphics::event::CGEventFlags::CGEventFlagShift,
                    );
                    e.post_to_pid(pid);
                }
                let mut end_up =
                    core_graphics::event::CGEvent::new_keyboard_event(source.clone(), 0x7C, false)
                        .ok();
                if let Some(e) = end_up.as_mut() {
                    e.set_flags(
                        core_graphics::event::CGEventFlags::CGEventFlagCommand
                            | core_graphics::event::CGEventFlags::CGEventFlagShift,
                    );
                    e.post_to_pid(pid);
                }
                std::thread::sleep(std::time::Duration::from_millis(30));
                // Cmd+V
                let mut v_down =
                    core_graphics::event::CGEvent::new_keyboard_event(source.clone(), 0x09, true)
                        .ok();
                if let Some(e) = v_down.as_mut() {
                    e.set_flags(core_graphics::event::CGEventFlags::CGEventFlagCommand);
                    e.post_to_pid(pid);
                }
                let mut v_up =
                    core_graphics::event::CGEvent::new_keyboard_event(source, 0x09, false).ok();
                if let Some(e) = v_up.as_mut() {
                    e.set_flags(core_graphics::event::CGEventFlags::CGEventFlagCommand);
                    e.post_to_pid(pid);
                }
            }
        }
    }
    fn erase_prompt(&self, count: usize) {
        if count == 0 {
            return;
        }
        macos_impl::erase_chars(count);
    }
}

pub struct MacOsPlatformCuaDriver;

impl MacOsPlatformCuaDriver {
    pub fn new() -> Self {
        MacOsPlatformCuaDriver
    }
}

impl Default for MacOsPlatformCuaDriver {
    fn default() -> Self {
        Self::new()
    }
}

impl PlatformCuaDriver for MacOsPlatformCuaDriver {
    fn execute_driver(&self, _action: &CuaAction, _ctx: &CuaContext) -> Result<(), anyhow::Error> {
        Err(anyhow!("macOS CUA driver: Unsupported/Experimental"))
    }
}
