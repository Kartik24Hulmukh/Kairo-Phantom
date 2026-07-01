/// Windows UIAutomation implementation of the AccessibilityReader trait.
/// Uses UIAutomation TextPattern (primary) and ValuePattern (fallback)
/// to read text from the focused application element.
///
/// This is the production-ready Windows implementation.
/// For cross-platform support, see platform/mod.rs.
use anyhow::{Context, Result};
use std::time::Duration;
use uiautomation::core::UIAutomation;

use super::{AccessibilityReader, CuaAction, CuaContext, PlatformCuaDriver, PlatformInjector};

pub struct WindowsUiaReader;

impl Default for WindowsUiaReader {
    fn default() -> Self {
        Self::new()
    }
}

impl WindowsUiaReader {
    pub fn new() -> Self {
        WindowsUiaReader
    }
}

impl AccessibilityReader for WindowsUiaReader {
    /// Get the full text of the currently focused UI element via UIAutomation.
    fn get_focused_text(&self) -> Result<String> {
        let automation =
            UIAutomation::new().context("Failed to initialize Windows UIAutomation")?;

        let focused = automation
            .get_focused_element()
            .context("No focused element found — click on a text field first")?;

        // Primary: TextPattern — works for rich text editors
        if let Ok(pat) = focused.get_pattern::<uiautomation::patterns::UITextPattern>() {
            if let Ok(range) = pat.get_document_range() {
                if let Ok(text) = range.get_text(-1) {
                    if !text.is_empty() {
                        return Ok(text);
                    }
                }
            }
        }

        // Secondary: ValuePattern — works for simple inputs
        if let Ok(pat) = focused.get_pattern::<uiautomation::patterns::UIValuePattern>() {
            if let Ok(val) = pat.get_value() {
                if !val.is_empty() {
                    return Ok(val);
                }
            }
        }

        Ok(String::new())
    }

    /// Set the text of the currently focused UI element directly via UIAutomation ValuePattern.
    fn set_focused_text(&self, text: &str) -> Result<()> {
        let automation =
            UIAutomation::new().context("Failed to initialize Windows UIAutomation")?;

        let focused = automation
            .get_focused_element()
            .context("No focused element found")?;

        if let Ok(pat) = focused.get_pattern::<uiautomation::patterns::UIValuePattern>() {
            pat.set_value(text)
                .context("Failed to set value via ValuePattern")?;
            return Ok(());
        }

        anyhow::bail!("ValuePattern not supported on focused element")
    }

    /// Read text from the Windows clipboard using Win32 API.
    fn get_clipboard_text(&self) -> Result<String> {
        unsafe {
            use windows::Win32::System::DataExchange::{
                CloseClipboard, GetClipboardData, OpenClipboard,
            };
            use windows::Win32::System::Memory::{GlobalLock, GlobalUnlock};

            OpenClipboard(None)?;
            let handle = GetClipboardData(13u32)?; // CF_UNICODETEXT
            let hglobal = windows::Win32::Foundation::HGLOBAL(handle.0 as _);
            let ptr = GlobalLock(hglobal) as *const u16;
            if ptr.is_null() {
                let _ = CloseClipboard();
                return Ok(String::new());
            }
            let mut len = 0;
            while *ptr.add(len) != 0 {
                len += 1;
            }
            let slice = std::slice::from_raw_parts(ptr, len);
            let text = String::from_utf16_lossy(slice);
            let _ = GlobalUnlock(hglobal);
            let _ = CloseClipboard();
            Ok(text)
        }
    }
}

// ─── Windows Platform Injector ──────────────────────────────────────────────

pub struct WindowsPlatformInjector;

impl WindowsPlatformInjector {
    pub fn new() -> Self {
        WindowsPlatformInjector
    }
}

impl Default for WindowsPlatformInjector {
    fn default() -> Self {
        Self::new()
    }
}

impl PlatformInjector for WindowsPlatformInjector {
    fn get_clipboard(&self) -> Option<String> {
        use windows::Win32::Foundation::HGLOBAL;
        use windows::Win32::System::DataExchange::{
            CloseClipboard, GetClipboardData, OpenClipboard,
        };
        use windows::Win32::System::Memory::{GlobalLock, GlobalUnlock};

        unsafe {
            for attempt in 0..5 {
                if OpenClipboard(None).is_ok() {
                    let handle = GetClipboardData(13); // CF_UNICODETEXT
                    if let Ok(handle) = handle {
                        let hglobal = HGLOBAL(handle.0 as _);
                        let ptr = GlobalLock(hglobal) as *const u16;
                        if !ptr.is_null() {
                            let mut len = 0;
                            while *ptr.add(len) != 0 {
                                len += 1;
                            }
                            let slice = std::slice::from_raw_parts(ptr, len);
                            let text = String::from_utf16_lossy(slice);
                            let _ = GlobalUnlock(hglobal);
                            let _ = CloseClipboard();
                            return Some(text);
                        }
                    }
                    let _ = CloseClipboard();
                }
                std::thread::sleep(Duration::from_millis(20));
            }
            None
        }
    }

    fn set_clipboard(&self, text: &str) -> bool {
        use windows::Win32::Foundation::HANDLE;
        use windows::Win32::System::DataExchange::{
            CloseClipboard, EmptyClipboard, OpenClipboard, SetClipboardData,
        };
        use windows::Win32::System::Memory::{
            GlobalAlloc, GlobalLock, GlobalUnlock, GMEM_MOVEABLE,
        };

        let wide: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
        let byte_count = wide.len() * 2;

        unsafe {
            for attempt in 0..5 {
                if OpenClipboard(None).is_ok() {
                    let _ = EmptyClipboard();
                    let h_mem = GlobalAlloc(GMEM_MOVEABLE, byte_count);
                    if let Ok(h_mem) = h_mem {
                        let ptr = GlobalLock(h_mem) as *mut u16;
                        if !ptr.is_null() {
                            std::ptr::copy_nonoverlapping(wide.as_ptr(), ptr, wide.len());
                            let _ = GlobalUnlock(h_mem);
                            let result = SetClipboardData(13, HANDLE(h_mem.0));
                            let _ = CloseClipboard();
                            if result.is_ok() {
                                return true;
                            }
                        } else {
                            let _ = CloseClipboard();
                        }
                    } else {
                        let _ = CloseClipboard();
                    }
                }
                std::thread::sleep(Duration::from_millis(20));
            }
            false
        }
    }

    fn send_char(&self, c: char) {
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE,
            VIRTUAL_KEY,
        };
        let code = c as u16;
        let inputs = [
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VIRTUAL_KEY(0),
                        wScan: code,
                        dwFlags: KEYEVENTF_UNICODE,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VIRTUAL_KEY(0),
                        wScan: code,
                        dwFlags: KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
        ];
        unsafe {
            SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        }
    }

    fn send_vk(&self, vk: u16) {
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
            VIRTUAL_KEY,
        };
        let inputs = [
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VIRTUAL_KEY(vk),
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VIRTUAL_KEY(vk),
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
        ];
        unsafe {
            SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        }
    }

    fn send_ctrl_v(&self) {
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
            VIRTUAL_KEY, VK_CONTROL,
        };
        let inputs = [
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_CONTROL,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VIRTUAL_KEY(0x56),
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VIRTUAL_KEY(0x56),
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_CONTROL,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
        ];
        unsafe {
            SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        }
    }

    fn inject_via_value_pattern(&self, text: &str) -> bool {
        use uiautomation::core::UIAutomation;
        if let Ok(automation) = UIAutomation::new() {
            if let Ok(focused) = automation.get_focused_element() {
                if let Ok(pat) = focused.get_pattern::<uiautomation::patterns::UIValuePattern>() {
                    if pat.set_value(text).is_ok() {
                        return true;
                    }
                }
            }
        }
        false
    }

    fn select_backward(&self, count: usize) {
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
            VK_LEFT, VK_SHIFT,
        };
        if count == 0 {
            return;
        }
        let mut inputs = Vec::with_capacity(2 + count * 2);
        inputs.push(INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VK_SHIFT,
                    wScan: 0,
                    dwFlags: KEYBD_EVENT_FLAGS(0),
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        });
        for _ in 0..count {
            inputs.push(INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_LEFT,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            });
            inputs.push(INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_LEFT,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            });
        }
        inputs.push(INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: VK_SHIFT,
                    wScan: 0,
                    dwFlags: KEYEVENTF_KEYUP,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        });
        unsafe {
            SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
        }
    }

    fn focus_window(&self, hwnd: isize) -> bool {
        use windows::Win32::Foundation::HWND;
        use windows::Win32::UI::WindowsAndMessaging::{
            BringWindowToTop, GetForegroundWindow, SetForegroundWindow,
        };
        let h = HWND(hwnd as *mut std::ffi::c_void);
        unsafe {
            let fg = GetForegroundWindow();
            if fg.0 != h.0 {
                let _ = BringWindowToTop(h);
                let _ = SetForegroundWindow(h);
                return true;
            }
        }
        false
    }

    fn inject_replace_line(&self) {
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
            VK_END, VK_SHIFT,
        };
        tracing::info!("Sending Home + Shift+End + Ctrl+V (select line → paste)");

        // Home: go to beginning of current line
        self.send_vk(0x24); // VK_HOME
        std::thread::sleep(Duration::from_millis(50));

        // Shift+End: select to end of line
        let shift_end = [
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_SHIFT,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_END,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_END,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_SHIFT,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
        ];
        unsafe {
            SendInput(&shift_end, std::mem::size_of::<INPUT>() as i32);
        }
        std::thread::sleep(Duration::from_millis(50));

        // Ctrl+V: paste (replaces selection)
        self.send_ctrl_v();
        std::thread::sleep(Duration::from_millis(50));

        tracing::info!("inject_replace_line complete");
    }

    fn erase_prompt(&self, count: usize) {
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
            VK_END, VK_SHIFT,
        };
        if count == 0 {
            return;
        }
        tracing::info!(
            "erase_prompt({}) called — using Home+Shift+End+Delete instead of backspaces",
            count
        );

        self.send_vk(0x24); // VK_HOME
        std::thread::sleep(Duration::from_millis(20));

        let shift_end = [
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_SHIFT,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_END,
                        wScan: 0,
                        dwFlags: KEYBD_EVENT_FLAGS(0),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_END,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
            INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VK_SHIFT,
                        wScan: 0,
                        dwFlags: KEYEVENTF_KEYUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            },
        ];
        unsafe {
            SendInput(&shift_end, std::mem::size_of::<INPUT>() as i32);
        }
        std::thread::sleep(Duration::from_millis(20));
        self.send_vk(0x2E); // VK_DELETE
    }
}

// ─── Windows Platform CUA Driver ───────────────────────────────────────────

pub struct WindowsPlatformCuaDriver;

impl WindowsPlatformCuaDriver {
    pub fn new() -> Self {
        WindowsPlatformCuaDriver
    }
}

impl Default for WindowsPlatformCuaDriver {
    fn default() -> Self {
        Self::new()
    }
}

impl PlatformCuaDriver for WindowsPlatformCuaDriver {
    fn execute_driver(&self, action: &CuaAction, ctx: &CuaContext) -> anyhow::Result<()> {
        use std::process::Command;
        let driver_path = self
            .find_cua_driver()
            .ok_or_else(|| anyhow::anyhow!("cua-driver binary not found"))?;
        let result = match action {
            CuaAction::MouseClick { x, y, .. } => {
                let scaled_x = (*x as f32 * ctx.dpi_scale) as i32;
                let scaled_y = (*y as f32 * ctx.dpi_scale) as i32;
                Command::new(&driver_path)
                    .args(["click", &scaled_x.to_string(), &scaled_y.to_string()])
                    .output()
            }
            CuaAction::KeyboardType { text } => Command::new(&driver_path)
                .args(["type", "--text", text])
                .output(),
            CuaAction::MouseMove { x, y } => {
                let scaled_x = (*x as f32 * ctx.dpi_scale) as i32;
                let scaled_y = (*y as f32 * ctx.dpi_scale) as i32;
                Command::new(&driver_path)
                    .args(["move", &scaled_x.to_string(), &scaled_y.to_string()])
                    .output()
            }
            _ => {
                return Ok(());
            }
        };

        match result {
            Ok(output) if output.status.success() => Ok(()),
            Ok(output) => Err(anyhow::anyhow!(
                "cua-driver failed: {}",
                String::from_utf8_lossy(&output.stderr),
            )),
            Err(e) => Err(anyhow::anyhow!(e)),
        }
    }
}

impl WindowsPlatformCuaDriver {
    fn find_cua_driver(&self) -> Option<std::path::PathBuf> {
        let candidates = [
            dirs::data_local_dir().map(|d| {
                d.join("Programs")
                    .join("Cua")
                    .join("cua-driver")
                    .join("bin")
                    .join("cua-driver.exe")
            }),
            dirs::home_dir().map(|h| h.join(".cua").join("bin").join("cua-driver.exe")),
            Some(std::path::PathBuf::from(
                "C:/Program Files/cua-driver/cua-driver.exe",
            )),
            Some(std::path::PathBuf::from(
                "C:/ProgramData/cua-driver/cua-driver.exe",
            )),
        ];

        for candidate in candidates.into_iter().flatten() {
            if candidate.exists() {
                return Some(candidate);
            }
        }

        // Also check PATH
        if let Ok(output) = std::process::Command::new("where")
            .arg("cua-driver")
            .output()
        {
            if output.status.success() {
                let path = String::from_utf8_lossy(&output.stdout);
                let first_line = path.lines().next().unwrap_or("").trim().to_string();
                if !first_line.is_empty() {
                    return Some(std::path::PathBuf::from(first_line));
                }
            }
        }

        None
    }
}
