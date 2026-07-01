// Kairo Phantom — Cross-Platform Accessibility Layer
//
// Provides a unified trait for reading text from the focused UI element
// across Windows (UIAutomation), macOS (AXUIElement), and Linux (AT-SPI2).
// Each platform has its own implementation module, selected at compile time.
//
// Architecture inspired by xa11y's unified API design, but implemented
// natively using each platform's official accessibility APIs.

use crate::cua::{CuaAction, CuaContext};

/// The canonical accessibility reader trait.
/// Every platform implements this to extract text from the focused UI element.
pub trait AccessibilityReader: Send + Sync {
    /// Read the full text content of the currently focused UI element.
    /// Returns the text or an error if the element is not accessible.
    fn get_focused_text(&self) -> anyhow::Result<String>;

    /// Read text from the system clipboard as a fallback.
    fn get_clipboard_text(&self) -> anyhow::Result<String>;

    /// Set the text content of the currently focused UI element (direct field injection).
    fn set_focused_text(&self, text: &str) -> anyhow::Result<()>;
}

/// Abstract platform-specific keyboard/mouse input injection.
pub trait PlatformInjector: Send + Sync {
    fn set_clipboard(&self, text: &str) -> bool;
    fn get_clipboard(&self) -> Option<String>;
    fn send_char(&self, c: char);
    fn send_vk(&self, vk: u16);
    fn send_ctrl_v(&self);
    fn inject_via_value_pattern(&self, text: &str) -> bool;
    fn select_backward(&self, count: usize);
    fn focus_window(&self, hwnd: isize) -> bool;
    fn inject_replace_line(&self);
    fn erase_prompt(&self, count: usize);
}

/// Abstract platform-specific low-level CUA execution driver path.
pub trait PlatformCuaDriver: Send + Sync {
    fn execute_driver(&self, action: &CuaAction, ctx: &CuaContext) -> anyhow::Result<()>;
}

/// Construct the platform-appropriate AccessibilityReader at runtime.
pub fn new_reader() -> Box<dyn AccessibilityReader> {
    #[cfg(target_os = "windows")]
    {
        Box::new(windows::WindowsUiaReader::new())
    }
    #[cfg(target_os = "macos")]
    {
        Box::new(macos::MacOsAccessibilityReader::new())
    }
    #[cfg(target_os = "linux")]
    {
        Box::new(linux::LinuxAtspiReader::new())
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    {
        compile_error!("Kairo Phantom requires Windows, macOS, or Linux.")
    }
}

/// Construct the platform-appropriate PlatformInjector at runtime.
pub fn new_injector() -> Box<dyn PlatformInjector> {
    #[cfg(target_os = "windows")]
    {
        Box::new(windows::WindowsPlatformInjector::new())
    }
    #[cfg(target_os = "macos")]
    {
        Box::new(macos::MacOsPlatformInjector::new())
    }
    #[cfg(target_os = "linux")]
    {
        Box::new(linux::LinuxPlatformInjector::new())
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    {
        compile_error!("Kairo Phantom requires Windows, macOS, or Linux.")
    }
}

/// Construct the platform-appropriate PlatformCuaDriver at runtime.
pub fn new_cua_driver() -> Box<dyn PlatformCuaDriver> {
    #[cfg(target_os = "windows")]
    {
        Box::new(windows::WindowsPlatformCuaDriver::new())
    }
    #[cfg(target_os = "macos")]
    {
        Box::new(macos::MacOsPlatformCuaDriver::new())
    }
    #[cfg(target_os = "linux")]
    {
        Box::new(linux::LinuxPlatformCuaDriver::new())
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    {
        compile_error!("Kairo Phantom requires Windows, macOS, or Linux.")
    }
}

// ─── Platform Modules ─────────────────────────────────────────────────────────

#[cfg(target_os = "windows")]
pub mod windows;

#[cfg(target_os = "macos")]
pub mod macos;

#[cfg(target_os = "linux")]
pub mod linux;

// ─── Monitor enumeration (Windows) ──────────────────────────────────────────────

#[cfg(target_os = "windows")]
mod win_monitors {
    use crate::monitor::{MonitorInfo, MonitorLayout};
    use std::cell::RefCell;
    use windows::Win32::Foundation::{BOOL, LPARAM, RECT, TRUE};
    use windows::Win32::Graphics::Gdi::{
        EnumDisplayMonitors, GetMonitorInfoW, HDC, HMONITOR, MONITORINFO, MONITORINFOEXW,
    };
    // MONITORINFOF_PRIMARY is not re-exported by windows 0.58's Gdi module;
    // use the stable wingdi.h value (0x0000_0001).
    const MONITORINFOF_PRIMARY: u32 = 0x0000_0001;
    use windows::Win32::UI::HiDpi::{GetDpiForMonitor, MDT_EFFECTIVE_DPI};

    thread_local! {
        static ACC: RefCell<Vec<MonitorInfo>> = const { RefCell::new(Vec::new()) };
    }

    unsafe extern "system" fn cb(hmon: HMONITOR, _hdc: HDC, _rc: *mut RECT, _lp: LPARAM) -> BOOL {
        let mut info = MONITORINFOEXW::default();
        info.monitorInfo.cbSize = std::mem::size_of::<MONITORINFOEXW>() as u32;
        if GetMonitorInfoW(hmon, &mut info.monitorInfo as *mut MONITORINFO).as_bool() {
            let rc = info.monitorInfo.rcMonitor;
            let mut dpi_x: u32 = 96;
            let mut dpi_y: u32 = 96;
            let _ = GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI, &mut dpi_x, &mut dpi_y);
            let primary = (info.monitorInfo.dwFlags & MONITORINFOF_PRIMARY) != 0;
            ACC.with(|a| {
                a.borrow_mut().push(MonitorInfo {
                    id: format!(
                        "{}x{}+{}+{}",
                        rc.right - rc.left,
                        rc.bottom - rc.top,
                        rc.left,
                        rc.top
                    ),
                    x: rc.left,
                    y: rc.top,
                    width: rc.right - rc.left,
                    height: rc.bottom - rc.top,
                    scale: dpi_x as f64 / 96.0,
                    primary,
                })
            });
        }
        TRUE
    }

    pub fn enumerate() -> MonitorLayout {
        ACC.with(|a| a.borrow_mut().clear());
        unsafe {
            let _ = EnumDisplayMonitors(HDC::default(), None, Some(cb), LPARAM(0));
        }
        let monitors = ACC.with(|a| std::mem::take(&mut *a.borrow_mut()));
        MonitorLayout::new(monitors)
    }
}

/// Enumerate connected monitors (origin, size, per-monitor effective DPI scale)
/// via `EnumDisplayMonitors` + `GetMonitorInfoW` + `GetDpiForMonitor`.
#[cfg(target_os = "windows")]
pub fn enumerate_monitors() -> crate::monitor::MonitorLayout {
    win_monitors::enumerate()
}
