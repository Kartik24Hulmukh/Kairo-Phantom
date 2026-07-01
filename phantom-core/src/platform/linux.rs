// phantom-core/src/platform/linux.rs
//
// Linux Platform Implementation — Cross-Platform Hardening (Domain 11)

use super::{AccessibilityReader, CuaAction, CuaContext, PlatformCuaDriver, PlatformInjector};
use anyhow::Result;
use tracing::{info, warn};

// ── Shared subprocess helpers (always compiled, cfg-gated internally) ─────────

#[cfg(target_os = "linux")]
mod linux_impl {
    use std::process::Command;
    use tracing::{info, warn};

    /// Detect display server: X11 or Wayland.
    pub fn detect_display_server() -> &'static str {
        if std::env::var("WAYLAND_DISPLAY").is_ok() {
            "wayland"
        } else if std::env::var("DISPLAY").is_ok() {
            "x11"
        } else {
            "unknown"
        }
    }

    /// Get the focused window title on X11/Wayland.
    pub fn get_active_window_title() -> Option<String> {
        if let Ok(output) = Command::new("xdotool")
            .args(["getactivewindow", "getwindowname"])
            .output()
        {
            let s = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !s.is_empty() {
                return Some(s);
            }
        }

        if let Ok(output) = Command::new("wmctrl").args(["-l"]).output() {
            let lines = String::from_utf8_lossy(&output.stdout);
            if let Some(first_active) = lines.lines().last() {
                let parts: Vec<&str> = first_active.splitn(5, char::is_whitespace).collect();
                if parts.len() >= 5 {
                    return Some(parts[4..].join(" ").trim().to_string());
                }
            }
        }

        None
    }

    /// Get the focused application process name on Linux.
    pub fn get_active_process_name() -> Option<String> {
        let wid_out = Command::new("xdotool")
            .args(["getactivewindow"])
            .output()
            .ok()?;
        let wid = String::from_utf8_lossy(&wid_out.stdout).trim().to_string();
        if wid.is_empty() {
            return None;
        }

        let pid_out = Command::new("xdotool")
            .args(["getwindowpid", &wid])
            .output()
            .ok()?;
        let pid = String::from_utf8_lossy(&pid_out.stdout).trim().to_string();
        if pid.is_empty() {
            return None;
        }

        let comm = std::fs::read_to_string(format!("/proc/{pid}/comm")).ok()?;
        Some(comm.trim().to_string())
    }

    /// Get the focused element's text content.
    pub fn get_focused_text() -> anyhow::Result<String> {
        if let Some(text) = try_atspi_focused_text() {
            return Ok(text);
        }

        let original_clip = read_clipboard().unwrap_or_default();

        let server = detect_display_server();
        if server == "wayland" {
            let _ = Command::new("ydotool").args(["key", "ctrl+a"]).status();
            std::thread::sleep(std::time::Duration::from_millis(100));
            let _ = Command::new("ydotool").args(["key", "ctrl+c"]).status();
        } else {
            let _ = Command::new("xdotool").args(["key", "ctrl+a"]).status();
            std::thread::sleep(std::time::Duration::from_millis(100));
            let _ = Command::new("xdotool").args(["key", "ctrl+c"]).status();
        }
        std::thread::sleep(std::time::Duration::from_millis(100));

        let selected = read_clipboard().unwrap_or_default();

        if !original_clip.is_empty() {
            write_clipboard(&original_clip);
        }

        if server == "wayland" {
            let _ = Command::new("ydotool").args(["key", "End"]).status();
        } else {
            let _ = Command::new("xdotool").args(["key", "End"]).status();
        }

        Ok(selected)
    }

    fn try_atspi_focused_text() -> Option<String> {
        let bus_addr = std::env::var("AT_SPI_BUS_ADDRESS").ok().or_else(|| {
            Command::new("dbus-send")
                .args([
                    "--print-reply",
                    "--dest=org.a11y.Bus",
                    "/org/a11y/bus",
                    "org.a11y.Bus.GetAddress",
                ])
                .output()
                .ok()
                .filter(|o| o.status.success())
                .and_then(|o| {
                    let out = String::from_utf8_lossy(&o.stdout).to_string();
                    out.split_whitespace()
                        .find(|s| s.starts_with("\"unix:") || s.starts_with("\"tcp:"))
                        .map(|s| s.trim_matches('"').to_string())
                })
        })?;

        let result = Command::new("python3")
            .args([
                "-c",
                r#"
import sys
try:
    import pyatspi
    desktop = pyatspi.Registry.getDesktop(0)
    for app in desktop:
        for obj in pyatspi.findDescendant(app, lambda x: x.getState().contains(pyatspi.STATE_FOCUSED), False):
            text_iface = obj.queryText()
            print(text_iface.getText(0, -1))
            sys.exit(0)
except Exception as e:
    sys.exit(1)
"#
            ])
            .output()
            .ok()?;

        if result.status.success() {
            let text = String::from_utf8_lossy(&result.stdout).trim().to_string();
            if !text.is_empty() {
                return Some(text);
            }
        }
        None
    }

    /// AT-SPI2 ghost typing: inject text directly via the a11y text interface.
    /// No clipboard, no keystroke simulation — uses pyatspi's Text.insertText.
    /// Requires: AT-SPI2 bus (real desktop display + a11y bus).
    /// Returns false (loud) if no a11y bus is available — never silently succeeds.
    fn try_atspi_inject_text(text: &str) -> bool {
        let bus_addr = std::env::var("AT_SPI_BUS_ADDRESS").ok().or_else(|| {
            Command::new("dbus-send")
                .args([
                    "--print-reply",
                    "--dest=org.a11y.Bus",
                    "/org/a11y/bus",
                    "org.a11y.Bus.GetAddress",
                ])
                .output()
                .ok()
                .filter(|o| o.status.success())
                .and_then(|o| {
                    let out = String::from_utf8_lossy(&o.stdout).to_string();
                    out.split_whitespace()
                        .find(|s| s.starts_with("\"unix:") || s.starts_with("\"tcp:"))
                        .map(|s| s.trim_matches('"').to_string())
                })
        });

        if bus_addr.is_none() {
            warn!("[Linux/AT-SPI2] No a11y bus — cannot inject via AT-SPI2. Falling back to clipboard.");
            return false;
        }

        let escaped_text = text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n");
        let result = Command::new("python3")
            .args([
                "-c",
                &format!(r#"
import sys
try:
    import pyatspi
    desktop = pyatspi.Registry.getDesktop(0)
    for app in desktop:
        for obj in pyatspi.findDescendant(app, lambda x: x.getState().contains(pyatspi.STATE_FOCUSED), False):
            text_iface = obj.queryText()
            caret = text_iface.caretOffset
            text_iface.insertText(caret, '{escaped_text}', len('{escaped_text}'))
            sys.exit(0)
    sys.exit(1)
except Exception as e:
    sys.stderr.write(str(e))
    sys.exit(1)
"#)
            ])
            .output()
            .ok();

        match result {
            Some(r) if r.status.success() => true,
            Some(r) => {
                let err = String::from_utf8_lossy(&r.stderr);
                warn!("[Linux/AT-SPI2] inject failed: {}", err.trim());
                false
            }
            None => {
                warn!("[Linux/AT-SPI2] python3 not available for a11y injection");
                false
            }
        }
    }

    pub fn read_clipboard() -> Option<String> {
        let server = detect_display_server();
        if server == "wayland" {
            Command::new("wl-paste")
                .args(["--no-newline"])
                .output()
                .ok()
                .filter(|o| o.status.success())
                .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
        } else {
            Command::new("xclip")
                .args(["-selection", "clipboard", "-o"])
                .output()
                .ok()
                .filter(|o| o.status.success())
                .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
                .or_else(|| {
                    Command::new("xsel")
                        .args(["--clipboard", "--output"])
                        .output()
                        .ok()
                        .filter(|o| o.status.success())
                        .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
                })
        }
    }

    pub fn write_clipboard(text: &str) -> bool {
        let server = detect_display_server();
        let mut child = if server == "wayland" {
            match Command::new("wl-copy")
                .stdin(std::process::Stdio::piped())
                .spawn()
            {
                Ok(c) => c,
                Err(_) => return false,
            }
        } else {
            match Command::new("xclip")
                .args(["-selection", "clipboard"])
                .stdin(std::process::Stdio::piped())
                .spawn()
            {
                Ok(c) => c,
                Err(_) => {
                    match Command::new("xsel")
                        .args(["--clipboard", "--input"])
                        .stdin(std::process::Stdio::piped())
                        .spawn()
                    {
                        Ok(c) => c,
                        Err(e) => {
                            warn!("[Linux] No clipboard tool found: {}", e);
                            return false;
                        }
                    }
                }
            }
        };

        if let Some(stdin) = child.stdin.as_mut() {
            use std::io::Write;
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
        true
    }

    pub fn inject_text(text: &str) -> bool {
        // Try AT-SPI2 direct text insertion first (no clipboard, no keystrokes)
        if try_atspi_inject_text(text) {
            info!(
                "[Linux/AT-SPI2] Injected {} chars via a11y text interface",
                text.len()
            );
            return true;
        }

        // Fallback: clipboard + paste
        if !write_clipboard(text) {
            return false;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));

        let server = detect_display_server();
        if server == "wayland" {
            let status = Command::new("ydotool").args(["key", "ctrl+v"]).status();
            match status {
                Ok(s) if s.success() => {
                    info!("[Linux/Wayland] Injected {} chars", text.len());
                    true
                }
                _ => {
                    warn!("[Linux/Wayland] ydotool failed — install ydotool");
                    false
                }
            }
        } else {
            let status = Command::new("xdotool").args(["key", "ctrl+v"]).status();
            match status {
                Ok(s) if s.success() => {
                    info!("[Linux/X11] Injected {} chars via xdotool", text.len());
                    true
                }
                _ => {
                    warn!("[Linux/X11] xdotool failed — install xdotool");
                    false
                }
            }
        }
    }

    pub fn erase_chars(count: usize) -> bool {
        if count == 0 {
            return true;
        }
        let server = detect_display_server();
        if server == "wayland" {
            for _ in 0..count {
                let _ = Command::new("ydotool").args(["key", "BackSpace"]).status();
            }
            true
        } else {
            for _ in 0..count {
                let _ = Command::new("xdotool")
                    .args(["key", "--clearmodifiers", "BackSpace"])
                    .status();
            }
            true
        }
    }

    pub fn get_focused_pid() -> Option<i32> {
        let output = Command::new("xdotool")
            .args(["getactivewindow", "getwindowpid"])
            .output()
            .ok()?;
        String::from_utf8_lossy(&output.stdout)
            .trim()
            .parse::<i32>()
            .ok()
    }

    pub fn check_tools() -> Vec<String> {
        let mut missing = Vec::new();
        let server = detect_display_server();
        if server == "wayland" {
            if Command::new("ydotool").args(["--help"]).output().is_err() {
                missing.push("ydotool (sudo apt install ydotool)".into());
            }
            if Command::new("wl-copy")
                .args(["--version"])
                .output()
                .is_err()
            {
                missing.push("wl-clipboard (sudo apt install wl-clipboard)".into());
            }
        } else {
            if Command::new("xdotool").args(["version"]).output().is_err() {
                missing.push("xdotool (sudo apt install xdotool)".into());
            }
            if Command::new("xclip").args(["-version"]).output().is_err() {
                missing.push("xclip (sudo apt install xclip)".into());
            }
        }
        missing
    }
}

#[cfg(not(target_os = "linux"))]
mod linux_impl {
    pub fn detect_display_server() -> &'static str {
        "none"
    }
    pub fn get_active_window_title() -> Option<String> {
        None
    }
    pub fn get_active_process_name() -> Option<String> {
        None
    }
    pub fn get_focused_text() -> anyhow::Result<String> {
        anyhow::bail!("Linux platform only")
    }
    pub fn read_clipboard() -> Option<String> {
        None
    }
    pub fn write_clipboard(_: &str) -> bool {
        false
    }
    pub fn inject_text(_: &str) -> bool {
        false
    }
    pub fn erase_chars(_: usize) -> bool {
        false
    }
    pub fn get_focused_pid() -> Option<i32> {
        None
    }
    pub fn check_tools() -> Vec<String> {
        vec![]
    }
}

pub use linux_impl::*;

// ── LinuxAtspiReader — implements AccessibilityReader ─────────────────────────

pub struct LinuxAtspiReader;

impl LinuxAtspiReader {
    pub fn new() -> Self {
        LinuxAtspiReader
    }
}

impl Default for LinuxAtspiReader {
    fn default() -> Self {
        Self::new()
    }
}

impl crate::platform::AccessibilityReader for LinuxAtspiReader {
    fn get_focused_text(&self) -> anyhow::Result<String> {
        get_focused_text()
    }

    fn get_clipboard_text(&self) -> anyhow::Result<String> {
        read_clipboard().ok_or_else(|| {
            anyhow::anyhow!("No clipboard tool available (install xclip or wl-clipboard)")
        })
    }

    fn set_focused_text(&self, _text: &str) -> anyhow::Result<()> {
        anyhow::bail!("set_focused_text is not yet implemented on Linux")
    }
}

// ── LinuxInjector ─────────────────────────────────────────────────────────────

pub struct LinuxInjector;

impl LinuxInjector {
    pub fn new() -> Self {
        Self
    }
    pub fn inject(&self, text: &str) -> bool {
        inject_text(text)
    }
    pub fn erase(&self, n: usize) -> bool {
        erase_chars(n)
    }
    pub fn focused_pid(&self) -> Option<i32> {
        get_focused_pid()
    }
    pub fn display_server(&self) -> &'static str {
        detect_display_server()
    }
    pub fn missing_tools(&self) -> Vec<String> {
        check_tools()
    }
    pub fn active_window_title(&self) -> Option<String> {
        get_active_window_title()
    }
    pub fn active_process_name(&self) -> Option<String> {
        get_active_process_name()
    }
}

impl Default for LinuxInjector {
    fn default() -> Self {
        Self::new()
    }
}

// ─── Linux Platform Injector & CUA Driver (B-13 Stub) ─────────────────────────

pub struct LinuxPlatformInjector;

impl LinuxPlatformInjector {
    pub fn new() -> Self {
        LinuxPlatformInjector
    }
}

impl Default for LinuxPlatformInjector {
    fn default() -> Self {
        Self::new()
    }
}

impl PlatformInjector for LinuxPlatformInjector {
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

    /// Replace the current line with clipboard contents.
    ///
    /// Uses xdotool to send Home + Shift+End + Ctrl+V — the Linux equivalent
    /// of the Windows inject_replace_line implementation.  If xdotool is not
    /// installed or no display server is available, logs a loud error.
    fn inject_replace_line(&self) {
        // Verify xdotool is available before attempting keystroke injection
        let xdotool_check = std::process::Command::new("which").arg("xdotool").output();

        match xdotool_check {
            Ok(out) if out.status.success() => {
                tracing::info!("inject_replace_line: sending Home+Shift+End+Ctrl+V via xdotool");

                // Home — move cursor to start of line
                let _ = std::process::Command::new("xdotool")
                    .args(["key", "Home"])
                    .output();

                // Shift+End — select to end of line
                let _ = std::process::Command::new("xdotool")
                    .args(["key", "shift+End"])
                    .output();

                // Ctrl+V — paste clipboard over selection
                let _ = std::process::Command::new("xdotool")
                    .args(["key", "ctrl+v"])
                    .output();

                tracing::info!("inject_replace_line complete");
            }
            _ => {
                tracing::error!(
                    "inject_replace_line: xdotool not found or no display server. \
                     Linux ghost-typing requires xdotool and an active X11/Wayland session. \
                     Install with: apt install xdotool"
                );
            }
        }
    }

    /// Erase `count` characters from the current line.
    ///
    /// Uses xdotool to send Home + Shift+End + Delete — selecting the current
    /// line and deleting it.  The `count` parameter is logged but the
    /// implementation selects the entire line (matching the Windows behaviour
    /// which also uses line-level selection rather than per-character backspace).
    fn erase_prompt(&self, count: usize) {
        let xdotool_check = std::process::Command::new("which").arg("xdotool").output();

        match xdotool_check {
            Ok(out) if out.status.success() => {
                tracing::info!(
                    "erase_prompt({}) called — using Home+Shift+End+Delete via xdotool",
                    count
                );

                // Home — move cursor to start of line
                let _ = std::process::Command::new("xdotool")
                    .args(["key", "Home"])
                    .output();

                // Shift+End — select to end of line
                let _ = std::process::Command::new("xdotool")
                    .args(["key", "shift+End"])
                    .output();

                // Delete — remove selection
                let _ = std::process::Command::new("xdotool")
                    .args(["key", "Delete"])
                    .output();

                tracing::info!("erase_prompt complete");
            }
            _ => {
                tracing::error!(
                    "erase_prompt({}): xdotool not found or no display server. \
                     Linux ghost-typing requires xdotool and an active X11/Wayland session. \
                     Install with: apt install xdotool",
                    count
                );
            }
        }
    }
}

pub struct LinuxPlatformCuaDriver;

impl LinuxPlatformCuaDriver {
    pub fn new() -> Self {
        LinuxPlatformCuaDriver
    }
}

impl Default for LinuxPlatformCuaDriver {
    fn default() -> Self {
        Self::new()
    }
}

impl PlatformCuaDriver for LinuxPlatformCuaDriver {
    fn execute_driver(&self, _action: &CuaAction, _ctx: &CuaContext) -> Result<(), anyhow::Error> {
        Err(anyhow::anyhow!(
            "Linux CUA driver: Unsupported/Experimental"
        ))
    }
}
