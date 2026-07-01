// uia.rs — backwards-compatibility shim
//
// The UIA implementation has been refactored into `platform/windows.rs`
// as part of the Kairo v3.0 cross-platform initiative.
//
// This module re-exports the platform implementation for any code
// still using the old `UiaReader` name.

// Re-export the Windows implementation under the old name for compatibility.
#[cfg(target_os = "windows")]
pub use crate::platform::windows::WindowsUiaReader as UiaReader;

// On non-Windows, export a stub that satisfies the type system during compilation.
#[cfg(not(target_os = "windows"))]
pub struct UiaReader;

#[cfg(not(target_os = "windows"))]
impl Default for UiaReader {
    fn default() -> Self {
        UiaReader
    }
}

#[cfg(not(target_os = "windows"))]
impl UiaReader {
    pub fn new() -> Self {
        UiaReader
    }
    pub fn get_focused_text(&self) -> anyhow::Result<String> {
        crate::platform::new_reader().get_focused_text()
    }
    pub fn get_clipboard_text(&self) -> anyhow::Result<String> {
        crate::platform::new_reader().get_clipboard_text()
    }
}
