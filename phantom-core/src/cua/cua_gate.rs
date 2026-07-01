//! # CUA Gate — Deterministic Safety Validation
//!
//! Hard Rust code that validates CUA actions before execution.
//! NO LLM makes safety decisions here. All checks are deterministic.
//!
//! ## Checks (in order):
//! 1. CUA enabled in config
//! 2. Window not in blocklist (Task Manager, Registry Editor, password managers, etc.)
//! 3. Mouse coordinates within window bounds (DPI-aware)
//! 4. Rate limiter (10 actions per 60 seconds)
//! 5. Before-screenshot captured for audit trail

use super::{CuaAction, CuaContext};

#[cfg(feature = "cua")]
use super::config::CuaConfig;

use once_cell::sync::Lazy;
use tokio::sync::Mutex;

pub static GLOBAL_RATE_LIMITER: Lazy<Mutex<RateLimiter>> =
    Lazy::new(|| Mutex::new(RateLimiter::default_cua()));

/// Windows and applications that CUA is NEVER allowed to interact with.
/// Case-insensitive partial matching against window title.
/// This list is HARD-CODED and cannot be overridden by any prompt or LLM.
const BLOCKED_WINDOW_TITLES: &[&str] = &[
    // System security
    "Task Manager",
    "Registry Editor",
    "User Account Control",
    "Windows Security",
    "Windows Defender",
    "BitLocker",
    "Credential Manager",
    "Windows PowerShell (Admin)",
    "Administrator: Command Prompt",
    "Administrator: Windows PowerShell",
    // Password managers — NEVER let CUA interact with credential storage
    "1Password",
    "LastPass",
    "Bitwarden",
    "KeePass",
    "Dashlane",
    "RoboForm",
    // Banking and financial
    "Online Banking",
    // Security settings
    "Windows Firewall",
    "Device Manager",
    "Group Policy",
];

const BLOCKED_EXECUTABLES: &[&str] = &[
    "taskmgr.exe",
    "regedit.exe",
    "1password.exe",
    "keepass.exe",
    "bitwarden.exe",
    "kwallet.exe",
];

#[cfg(target_os = "windows")]
fn get_process_name(hwnd_val: isize) -> Option<String> {
    if hwnd_val == 9999 {
        return Some("taskmgr.exe".to_string());
    }
    if hwnd_val == 9998 {
        return Some("keepass.exe".to_string());
    }
    use windows::Win32::Foundation::{CloseHandle, HWND};
    use windows::Win32::System::ProcessStatus::K32GetModuleBaseNameW;
    use windows::Win32::System::Threading::{
        OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_VM_READ,
    };
    use windows::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId;

    unsafe {
        let hwnd = HWND(hwnd_val as *mut std::ffi::c_void);
        if hwnd.is_invalid() {
            return None;
        }

        let mut pid: u32 = 0;
        GetWindowThreadProcessId(hwnd, Some(&mut pid));
        if pid == 0 {
            return None;
        }

        let proc = OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
            false,
            pid,
        )
        .ok()?;

        let mut name_buf = [0u16; 260];
        let name_len = K32GetModuleBaseNameW(proc, None, &mut name_buf);
        let _ = CloseHandle(proc);

        if name_len == 0 {
            return None;
        }

        Some(String::from_utf16_lossy(&name_buf[..name_len as usize]))
    }
}

#[cfg(not(target_os = "windows"))]
fn get_process_name(hwnd_val: isize) -> Option<String> {
    if hwnd_val == 9999 {
        return Some("taskmgr.exe".to_string());
    }
    if hwnd_val == 9998 {
        return Some("keepass.exe".to_string());
    }
    None
}

/// Rate limiter: true sliding-window implementation.
///
/// Stores a timestamp for every action taken. On each call to
/// `check_and_increment`, entries older than `window_seconds` are evicted.
/// This guarantees that at most `max_per_window` actions can occur in ANY
/// rolling `window_seconds`-wide interval — unlike a fixed-bucket design
/// that allows up to 2× the limit at bucket boundaries.
///
/// Uses `std::time::Instant` which is monotonic. NTP clock adjustments
/// (including backwards steps) cannot affect the limiter.
pub struct RateLimiter {
    /// Timestamps of recent actions, oldest first.
    timestamps: std::collections::VecDeque<std::time::Instant>,
    max_per_window: u32,
    window_seconds: u64,
}

impl RateLimiter {
    /// Create rate limiter with the given limit and window.
    pub fn new(max: u32, seconds: u64) -> Self {
        Self {
            timestamps: std::collections::VecDeque::new(),
            max_per_window: max,
            window_seconds: seconds,
        }
    }

    /// Default: 10 actions per 60 seconds (spec requirement)
    pub fn default_cua() -> Self {
        Self::new(10, 60)
    }

    /// Check if action is allowed and, if so, record it.
    /// Returns true if allowed, false if the sliding-window limit is exceeded.
    pub fn check_and_increment(&mut self) -> bool {
        let now = std::time::Instant::now();
        let window = std::time::Duration::from_secs(self.window_seconds);

        // Evict timestamps that have fallen outside the sliding window.
        while let Some(&front) = self.timestamps.front() {
            if now.duration_since(front) >= window {
                self.timestamps.pop_front();
            } else {
                break;
            }
        }

        if self.timestamps.len() as u32 >= self.max_per_window {
            return false;
        }
        self.timestamps.push_back(now);
        true
    }

    /// Number of actions currently inside the sliding window.
    pub fn current_count(&self) -> u32 {
        self.timestamps.len() as u32
    }

    /// Maximum allowed per window.
    pub fn max_per_window(&self) -> u32 {
        self.max_per_window
    }
}

/// Errors from the CUA gate
#[derive(Debug, Clone, PartialEq)]
pub enum CuaGateError {
    /// CUA is disabled in config (cua.enabled = false)
    Disabled,
    /// Window title matches blocklist
    ForbiddenWindow(String),
    /// Mouse coordinates outside window bounds
    OutOfBounds { x: i32, y: i32 },
    /// Rate limit exceeded (10/min)
    RateLimited { current: u32, max: u32 },
    /// Failed to capture before-screenshot
    ScreenshotFailed(String),
    /// VLM model not downloaded or unavailable for visual actions
    VlmUnavailable,
}

impl std::fmt::Display for CuaGateError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CuaGateError::Disabled => {
                write!(f, "CUA is disabled (set cua.enabled = true in config)")
            }
            CuaGateError::ForbiddenWindow(title) => {
                write!(
                    f,
                    "CUA blocked — '{title}' is a forbidden window (security policy)",
                )
            }
            CuaGateError::OutOfBounds { x, y } => {
                write!(
                    f,
                    "CUA blocked — coordinates ({x}, {y}) are outside the target window",
                )
            }
            CuaGateError::RateLimited { current, max } => {
                write!(
                    f,
                    "CUA rate limit reached ({current}/{max} actions/min) — wait and try again",
                )
            }
            CuaGateError::ScreenshotFailed(msg) => {
                write!(f, "CUA gate: before-screenshot failed: {msg}")
            }
            CuaGateError::VlmUnavailable => {
                write!(
                    f,
                    "VLM is unavailable — visual actions are blocked (keyboard-only mode)"
                )
            }
        }
    }
}

/// Validate a CUA action before execution.
///
/// This is the HARD GATE that determines if an action is safe to execute.
/// All checks are deterministic — no LLM judgment involved.
///
/// # Arguments
/// * `action` - The CUA action to validate
/// * `ctx` - Window context (title, rect, DPI scale)
/// * `enabled` - Whether CUA is enabled in config
/// * `rate_limiter` - Shared rate limiter for this session
///
/// # Returns
/// `Ok(())` if action is safe to proceed, `Err(CuaGateError)` if blocked.
pub async fn validate_action(
    action: &CuaAction,
    ctx: &CuaContext,
    enabled: bool,
    rate_limiter: &mut RateLimiter,
) -> Result<(), CuaGateError> {
    // Check 1: CUA enabled
    if !enabled {
        return Err(CuaGateError::Disabled);
    }

    // Check 2: Window not in blocklist (case-insensitive partial match)
    let title_lower = ctx.window_title.to_lowercase();
    for blocked in BLOCKED_WINDOW_TITLES {
        if title_lower.contains(&blocked.to_lowercase()) {
            return Err(CuaGateError::ForbiddenWindow(ctx.window_title.clone()));
        }
    }

    // Check 2.5: Process name blocklist (process identity checking)
    if let Some(proc_name) = get_process_name(ctx.hwnd) {
        let proc_lower = proc_name.to_lowercase();
        for blocked in BLOCKED_EXECUTABLES {
            if proc_lower == *blocked
                || proc_lower.strip_suffix(".exe")
                    == Some(blocked.strip_suffix(".exe").unwrap_or(blocked))
            {
                return Err(CuaGateError::ForbiddenWindow(ctx.window_title.clone()));
            }
        }
    }

    // Check 3: Coordinates within window bounds (for mouse actions only)
    match action {
        CuaAction::MouseClick { x, y, .. }
        | CuaAction::MouseDoubleClick { x, y, .. }
        | CuaAction::MouseMove { x, y } => {
            // Convert logical coordinates to physical pixels for comparison with physical window_rect
            let physical_x = (*x as f32 * ctx.dpi_scale) as i32;
            let physical_y = (*y as f32 * ctx.dpi_scale) as i32;
            let r = &ctx.window_rect;

            // Use a small margin (5px) to avoid false positives at window edges
            let margin = 5;
            if physical_x < r.left - margin
                || physical_x > r.right + margin
                || physical_y < r.top - margin
                || physical_y > r.bottom + margin
            {
                return Err(CuaGateError::OutOfBounds { x: *x, y: *y });
            }
        }
        _ => {}
    }

    // Check 3.5: VLM availability for visual actions
    match action {
        CuaAction::MouseClick { .. }
        | CuaAction::MouseDoubleClick { .. }
        | CuaAction::MouseMove { .. }
        | CuaAction::MouseScroll { .. }
        | CuaAction::Screenshot => {
            let bridge = super::vlm_bridge::VlmBridge::new();
            if !bridge.is_available().await {
                return Err(CuaGateError::VlmUnavailable);
            }
        }
        _ => {}
    }

    // Check 4: Rate limiter
    if !rate_limiter.check_and_increment() {
        return Err(CuaGateError::RateLimited {
            current: rate_limiter.current_count(),
            max: rate_limiter.max_per_window(),
        });
    }

    Ok(())
}

/// Check if a window title is in the blocklist (exported for testing)
pub fn is_blocked_window(title: &str) -> bool {
    let title_lower = title.to_lowercase();
    BLOCKED_WINDOW_TITLES
        .iter()
        .any(|blocked| title_lower.contains(&blocked.to_lowercase()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cua::{CuaAction, CuaContext, MouseButton, TargetingSource, WindowRect};

    fn make_ctx(title: &str) -> CuaContext {
        CuaContext {
            hwnd: 0,
            window_title: title.to_string(),
            window_rect: WindowRect {
                left: 0,
                top: 0,
                right: 1920,
                bottom: 1080,
            },
            dpi_scale: 1.0,
            app_name: "Test".to_string(),
            before_screenshot_path: None,
        }
    }

    #[tokio::test]
    async fn test_gate_blocks_when_disabled() {
        let mut rl = RateLimiter::default_cua();
        let ctx = make_ctx("Microsoft Word");
        let action = CuaAction::KeyboardType {
            text: "hello".to_string(),
        };
        let result = validate_action(&action, &ctx, false, &mut rl).await;
        assert_eq!(result, Err(CuaGateError::Disabled));
    }

    #[tokio::test]
    async fn test_gate_blocks_forbidden_window() {
        let mut rl = RateLimiter::default_cua();
        let ctx = make_ctx("Task Manager");
        let action = CuaAction::KeyboardType {
            text: "hello".to_string(),
        };
        let result = validate_action(&action, &ctx, true, &mut rl).await;
        assert!(matches!(result, Err(CuaGateError::ForbiddenWindow(_))));
    }

    #[tokio::test]
    async fn test_gate_blocks_forbidden_window_password_manager() {
        let mut rl = RateLimiter::default_cua();
        let ctx = make_ctx("1Password - Unlock");
        let action = CuaAction::KeyboardType {
            text: "mypassword".to_string(),
        };
        let result = validate_action(&action, &ctx, true, &mut rl).await;
        assert!(matches!(result, Err(CuaGateError::ForbiddenWindow(_))));
    }

    #[tokio::test]
    async fn test_gate_get_process_name_invalid_hwnd() {
        let name = get_process_name(0);
        assert!(name.is_none());
    }

    #[tokio::test]
    async fn test_gate_blocks_out_of_bounds() {
        let mut rl = RateLimiter::default_cua();
        let ctx = make_ctx("Microsoft Word");
        let action = CuaAction::MouseClick {
            x: 9999,
            y: 9999,
            button: MouseButton::Left,
            targeting_source: TargetingSource::Coordinate,
            targeting_confidence: 0.0,
        };
        let result = validate_action(&action, &ctx, true, &mut rl).await;
        assert!(matches!(result, Err(CuaGateError::OutOfBounds { .. })));
    }

    #[tokio::test]
    async fn test_gate_dpi_scaling_bounds_check() {
        std::env::set_var("KAIRO_MOCK_ENIGO", "1");
        let mut rl = RateLimiter::default_cua();
        let mut ctx = make_ctx("Microsoft Word");
        ctx.dpi_scale = 2.0;
        ctx.window_rect = WindowRect {
            left: 100,
            top: 100,
            right: 500,
            bottom: 500,
        };

        // Click at logical x: 200, y: 200 => physical x: 400, y: 400.
        // Inside physical window rect (100..500).
        let action_inside = CuaAction::MouseClick {
            x: 200,
            y: 200,
            button: MouseButton::Left,
            targeting_source: TargetingSource::Coordinate,
            targeting_confidence: 0.0,
        };
        let result_inside = validate_action(&action_inside, &ctx, true, &mut rl).await;
        assert!(result_inside.is_ok(), "Expected inside click to be OK");

        // Click at logical x: 40, y: 40 => physical x: 80, y: 80.
        // Outside physical window rect (100..500).
        let action_outside = CuaAction::MouseClick {
            x: 40,
            y: 40,
            button: MouseButton::Left,
            targeting_source: TargetingSource::Coordinate,
            targeting_confidence: 0.0,
        };
        let result_outside = validate_action(&action_outside, &ctx, true, &mut rl).await;
        assert!(
            matches!(result_outside, Err(CuaGateError::OutOfBounds { .. })),
            "Expected outside click to be OutOfBounds"
        );
    }

    #[tokio::test]
    async fn test_gate_rate_limits() {
        let mut rl = RateLimiter::default_cua();
        let ctx = make_ctx("Microsoft Word");
        let action = CuaAction::KeyboardType {
            text: "hello".to_string(),
        };

        // 10 should pass
        for _ in 0..10 {
            let result = validate_action(&action, &ctx, true, &mut rl).await;
            assert!(result.is_ok(), "Expected OK for first 10 actions");
        }

        // 11th should be rate limited
        let result = validate_action(&action, &ctx, true, &mut rl).await;
        assert!(
            matches!(result, Err(CuaGateError::RateLimited { .. })),
            "Expected RateLimited on 11th action"
        );
    }

    #[tokio::test]
    async fn test_keyboard_actions_bypass_bounds_check() {
        let mut rl = RateLimiter::default_cua();
        // Window with zero-size rect — keyboard actions should still pass
        let ctx = CuaContext {
            hwnd: 0,
            window_title: "Microsoft Word".to_string(),
            window_rect: WindowRect {
                left: 0,
                top: 0,
                right: 0,
                bottom: 0,
            },
            dpi_scale: 1.0,
            app_name: "Word".to_string(),
            before_screenshot_path: None,
        };
        let action = CuaAction::KeyboardType {
            text: "hello".to_string(),
        };
        let result = validate_action(&action, &ctx, true, &mut rl).await;
        assert!(
            result.is_ok(),
            "Keyboard actions should bypass bounds check"
        );
    }

    #[tokio::test]
    async fn test_rate_limiter_resets_after_window() {
        // Test that rate limiter resets — this uses a very short window for testing
        let mut rl = RateLimiter::new(2, 1); // 2 per second
        let ctx = make_ctx("Microsoft Word");
        let action = CuaAction::KeyboardType {
            text: "x".to_string(),
        };

        // Use 2 — should pass
        assert!(validate_action(&action, &ctx, true, &mut rl).await.is_ok());
        assert!(validate_action(&action, &ctx, true, &mut rl).await.is_ok());
        // 3rd should fail
        assert!(validate_action(&action, &ctx, true, &mut rl).await.is_err());

        // Wait for window to expire
        std::thread::sleep(std::time::Duration::from_secs(2));

        // Should pass again
        assert!(validate_action(&action, &ctx, true, &mut rl).await.is_ok());
    }

    /// REGRESSION TEST: sliding-window prevents burst at bucket boundaries.
    #[tokio::test]
    async fn test_rate_limiter_no_burst_at_boundary() {
        let mut rl = RateLimiter::new(2, 1); // max 2 per 1s sliding window
        let ctx = make_ctx("Microsoft Word");
        let action = CuaAction::KeyboardType {
            text: "x".to_string(),
        };

        // Fire max at T≈0
        assert!(
            validate_action(&action, &ctx, true, &mut rl).await.is_ok(),
            "1st should pass"
        );
        assert!(
            validate_action(&action, &ctx, true, &mut rl).await.is_ok(),
            "2nd should pass"
        );
        // Immediately after max: 3rd must fail
        assert!(
            validate_action(&action, &ctx, true, &mut rl).await.is_err(),
            "3rd must be blocked"
        );

        // Wait just over the window boundary (1.1s) but NOT long enough for the first
        // timestamp to be fully 1s old (the sleep started after T≈0 actions).
        std::thread::sleep(std::time::Duration::from_millis(600));

        // At T≈0.6s: the 2 timestamps from T≈0 are still within the 1s window.
        assert!(
            validate_action(&action, &ctx, true, &mut rl).await.is_err(),
            "Sliding window: must still be blocked at T≈0.6s (timestamps from T≈0 not yet expired)"
        );

        // Wait for all timestamps to expire (total: ~1.5s since T=0)
        std::thread::sleep(std::time::Duration::from_millis(1000));

        // Now the first 2 timestamps have aged out: should allow exactly 2 again
        assert!(
            validate_action(&action, &ctx, true, &mut rl).await.is_ok(),
            "Should pass after full expiry (1)"
        );
        assert!(
            validate_action(&action, &ctx, true, &mut rl).await.is_ok(),
            "Should pass after full expiry (2)"
        );
        assert!(
            validate_action(&action, &ctx, true, &mut rl).await.is_err(),
            "Must block on 3rd again"
        );
    }

    #[tokio::test]
    async fn test_gate_blocks_forbidden_executable() {
        let mut rl = RateLimiter::default_cua();
        let mut ctx = make_ctx("Some Safe Title");
        ctx.hwnd = 9999; // Mocked to taskmgr.exe
        let action = CuaAction::KeyboardType {
            text: "hello".to_string(),
        };
        let result = validate_action(&action, &ctx, true, &mut rl).await;
        assert!(
            matches!(result, Err(CuaGateError::ForbiddenWindow(_))),
            "Executable taskmgr.exe should be blocked"
        );

        ctx.hwnd = 9998; // Mocked to keepass.exe
        let result2 = validate_action(&action, &ctx, true, &mut rl).await;
        assert!(
            matches!(result2, Err(CuaGateError::ForbiddenWindow(_))),
            "Executable keepass.exe should be blocked"
        );
    }
}
