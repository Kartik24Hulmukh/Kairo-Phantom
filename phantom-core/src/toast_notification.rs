//! Toast Notification — P0-B2
//! Custom topmost, click-through GDI-rendered overlay window for premium visual feedback.
//! Replaces native system balloon notifications with a sleek dark-mode card near the text cursor.

use once_cell::sync::Lazy;
use std::sync::atomic::{AtomicBool, AtomicIsize, Ordering};
use std::sync::Arc;
use std::sync::Mutex;

// ─── Shared State for Custom Overlay ──────────────────────────────────────────

#[derive(Clone, Copy, Debug)]
pub enum OverlayColor {
    Info,    // Blue/Indigo
    Success, // Green
    Error,   // Red
}

struct OverlayData {
    title: String,
    body: String,
    color_type: OverlayColor,
    duration_ms: u32,
}

static PENDING_OVERLAY_DATA: Lazy<Mutex<Option<OverlayData>>> = Lazy::new(|| Mutex::new(None));
static OVERLAY_HWND: AtomicIsize = AtomicIsize::new(0);
#[cfg(windows)]
const WM_SHOWOVERLAY: u32 = windows::Win32::UI::WindowsAndMessaging::WM_USER + 2;
#[cfg(not(windows))]
const WM_SHOWOVERLAY: u32 = 0;

// ─── Native Windows Balloon Notification Backend ──────────────────────────────
// Keep original balloon code as fallback or for tray icon registration if needed.

#[cfg(windows)]
mod win_balloon {
    use once_cell::sync::OnceCell;
    use std::sync::Mutex;

    use windows::core::PCWSTR;
    use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, WPARAM};
    use windows::Win32::UI::Shell::{
        Shell_NotifyIconW, NIF_ICON, NIF_INFO, NIF_MESSAGE, NIF_TIP, NIM_ADD, NIM_MODIFY,
        NOTIFYICONDATAW, NOTIFYICONDATAW_0,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DefWindowProcW, LoadIconW, RegisterClassW, CS_HREDRAW, CS_VREDRAW,
        IDI_APPLICATION, WINDOW_EX_STYLE, WM_USER, WNDCLASSW, WS_OVERLAPPEDWINDOW,
    };

    #[repr(u32)]
    #[derive(Clone, Copy)]
    pub enum BalloonIcon {
        Info = 0x00000001,
        Warning = 0x00000002,
    }

    const WM_TRAYICON: u32 = WM_USER + 1;
    static TRAY_STATE: OnceCell<Mutex<TrayState>> = OnceCell::new();

    struct TrayState {
        hwnd: HWND,
        icon_added: bool,
    }

    unsafe impl Send for TrayState {}

    pub fn encode_wide<const N: usize>(s: &str) -> [u16; N] {
        let mut buf = [0u16; N];
        for (i, unit) in s.encode_utf16().take(N - 1).enumerate() {
            buf[i] = unit;
        }
        buf
    }

    unsafe extern "system" fn wnd_proc(
        hwnd: HWND,
        msg: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) }
    }

    fn create_hidden_hwnd() -> HWND {
        unsafe {
            let class_name = encode_wide::<64>("KairoPhantomTrayClass");

            let wc = WNDCLASSW {
                style: CS_HREDRAW | CS_VREDRAW,
                lpfnWndProc: Some(wnd_proc),
                hInstance: HINSTANCE::default(),
                lpszClassName: PCWSTR(class_name.as_ptr()),
                ..Default::default()
            };
            RegisterClassW(&wc);

            CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                PCWSTR(class_name.as_ptr()),
                PCWSTR::null(),
                WS_OVERLAPPEDWINDOW,
                0,
                0,
                0,
                0,
                HWND::default(),
                None,
                HINSTANCE::default(),
                None,
            )
            .unwrap_or(HWND::default())
        }
    }

    pub fn show_balloon(title: &str, message: &str, icon: BalloonIcon) {
        let state = TRAY_STATE.get_or_init(|| {
            Mutex::new(TrayState {
                hwnd: create_hidden_hwnd(),
                icon_added: false,
            })
        });

        let Ok(mut guard) = state.lock() else {
            return;
        };
        let hwnd = guard.hwnd;
        if hwnd == HWND::default() {
            return;
        }

        unsafe {
            let h_icon = LoadIconW(HINSTANCE::default(), IDI_APPLICATION).unwrap_or_default();

            let mut nid = NOTIFYICONDATAW {
                cbSize: std::mem::size_of::<NOTIFYICONDATAW>() as u32,
                hWnd: hwnd,
                uID: 1,
                uFlags: NIF_ICON | NIF_MESSAGE | NIF_TIP | NIF_INFO,
                uCallbackMessage: WM_TRAYICON,
                hIcon: h_icon,
                szTip: encode_wide::<128>("Kairo Phantom"),
                szInfo: encode_wide::<256>(message),
                szInfoTitle: encode_wide::<64>(title),
                Anonymous: NOTIFYICONDATAW_0::default(),
                ..Default::default()
            };
            nid.dwInfoFlags = windows::Win32::UI::Shell::NOTIFY_ICON_INFOTIP_FLAGS(icon as u32);

            if !guard.icon_added {
                let _ = Shell_NotifyIconW(NIM_ADD, &nid);
                guard.icon_added = true;
            } else {
                let _ = Shell_NotifyIconW(NIM_MODIFY, &nid);
            }
        }
    }
}

// ─── Custom GDI Overlay UI Implementation ──────────────────────────────────────

#[cfg(windows)]
fn get_target_position() -> (i32, i32) {
    use windows::Win32::Foundation::{HWND, POINT};
    use windows::Win32::Graphics::Gdi::ClientToScreen;
    use windows::Win32::UI::WindowsAndMessaging::{
        GetCursorPos, GetForegroundWindow, GetGUIThreadInfo, GetWindowThreadProcessId,
        GUITHREADINFO,
    };

    unsafe {
        let active_hwnd = GetForegroundWindow();
        if active_hwnd != HWND::default() {
            let thread_id = GetWindowThreadProcessId(active_hwnd, None);
            let mut gui = GUITHREADINFO::default();
            gui.cbSize = std::mem::size_of::<GUITHREADINFO>() as u32;
            if GetGUIThreadInfo(thread_id, &mut gui).is_ok() && gui.hwndCaret != HWND::default() {
                let mut pt = POINT {
                    x: gui.rcCaret.left,
                    y: gui.rcCaret.bottom,
                };
                if ClientToScreen(gui.hwndCaret, &mut pt).as_bool() && (pt.x != 0 || pt.y != 0) {
                    return (pt.x + 15, pt.y + 15);
                }
            }
        }
        let mut pt = POINT::default();
        if GetCursorPos(&mut pt).is_ok() {
            return (pt.x + 15, pt.y + 15);
        }
        (100, 100)
    }
}

#[cfg(windows)]
unsafe extern "system" fn overlay_wnd_proc(
    hwnd: windows::Win32::Foundation::HWND,
    msg: u32,
    wparam: windows::Win32::Foundation::WPARAM,
    lparam: windows::Win32::Foundation::LPARAM,
) -> windows::Win32::Foundation::LRESULT {
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::{COLORREF, HWND, LPARAM, LRESULT, WPARAM};
    use windows::Win32::Graphics::Gdi::{
        BeginPaint, CreateFontW, CreateSolidBrush, DeleteObject, DrawTextW, EndPaint, FillRect,
        InvalidateRect, SelectObject, SetBkMode, SetTextColor, DT_LEFT, DT_NOPREFIX, DT_WORDBREAK,
        HBRUSH, HDC, HFONT, PAINTSTRUCT, TRANSPARENT,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        DefWindowProcW, KillTimer, SetTimer, SetWindowPos, ShowWindow, HWND_TOPMOST,
        SWP_NOACTIVATE, SWP_SHOWWINDOW, SW_HIDE,
    };

    match msg {
        windows::Win32::UI::WindowsAndMessaging::WM_PAINT => {
            let mut ps = PAINTSTRUCT::default();
            let hdc = BeginPaint(hwnd, &mut ps);

            // Draw background (#181825 in BBGGRR -> 0x00251818)
            let bg_brush = CreateSolidBrush(COLORREF(0x00251818));
            let mut rect = ps.rcPaint;
            FillRect(hdc, &rect, bg_brush);
            let _ = DeleteObject(bg_brush);

            let msg_data = PENDING_OVERLAY_DATA.lock().unwrap();
            if let Some(ref data) = *msg_data {
                // Accent indicator bar on the left (6px wide)
                let accent_color = match data.color_type {
                    OverlayColor::Info => COLORREF(0x00fa8989),    // #89b4fa
                    OverlayColor::Success => COLORREF(0x00a1e3a6), // #a6e3a1
                    OverlayColor::Error => COLORREF(0x00a88bf3),   // #f38ba8
                };
                let accent_brush = CreateSolidBrush(accent_color);
                let accent_rect = windows::Win32::Foundation::RECT {
                    left: 0,
                    top: 0,
                    right: 6,
                    bottom: rect.bottom,
                };
                FillRect(hdc, &accent_rect, accent_brush);
                let _ = DeleteObject(accent_brush);

                // Draw title
                let font_name: Vec<u16> = "Segoe UI\0".encode_utf16().collect();
                let font_title = CreateFontW(
                    16,
                    0,
                    0,
                    0,
                    700,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    PCWSTR(font_name.as_ptr()),
                );
                let old_font = SelectObject(hdc, font_title);
                let _ = SetBkMode(hdc, TRANSPARENT);
                let _ = SetTextColor(hdc, COLORREF(0x00f4d6cd)); // #cdd6f4

                let mut title_rect = windows::Win32::Foundation::RECT {
                    left: 16,
                    top: 10,
                    right: rect.right - 10,
                    bottom: 30,
                };
                let mut wide_title: Vec<u16> = data.title.encode_utf16().collect();
                let _ = DrawTextW(hdc, &mut wide_title, &mut title_rect, DT_LEFT | DT_NOPREFIX);
                let _ = SelectObject(hdc, old_font);
                let _ = DeleteObject(font_title);

                // Draw body text
                let font_body = CreateFontW(
                    13,
                    0,
                    0,
                    0,
                    400,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    PCWSTR(font_name.as_ptr()),
                );
                let old_font = SelectObject(hdc, font_body);
                let _ = SetTextColor(hdc, COLORREF(0x00c8adad)); // #a6adc8

                let mut body_rect = windows::Win32::Foundation::RECT {
                    left: 16,
                    top: 32,
                    right: rect.right - 10,
                    bottom: rect.bottom - 5,
                };
                let mut wide_body: Vec<u16> = data.body.encode_utf16().collect();
                let _ = DrawTextW(
                    hdc,
                    &mut wide_body,
                    &mut body_rect,
                    DT_LEFT | DT_WORDBREAK | DT_NOPREFIX,
                );

                let _ = SelectObject(hdc, old_font);
                let _ = DeleteObject(font_body);
            }

            // Border outline (#cba6f7 in BBGGRR -> 0x00f7a6cb)
            let border_brush = CreateSolidBrush(COLORREF(0x00f7a6cb));
            windows::Win32::Graphics::Gdi::FrameRect(hdc, &rect, border_brush);
            let _ = DeleteObject(border_brush);

            let _ = EndPaint(hwnd, &ps);
            LRESULT(0)
        }
        WM_SHOWOVERLAY => {
            let duration = if let Some(ref data) = *PENDING_OVERLAY_DATA.lock().unwrap() {
                data.duration_ms
            } else {
                3000
            };

            let (x, y) = get_target_position();

            let _ = SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                x,
                y,
                320,
                80,
                SWP_NOACTIVATE | SWP_SHOWWINDOW,
            );

            let _ = InvalidateRect(hwnd, None, true);

            let _ = KillTimer(hwnd, 1);
            let _ = SetTimer(hwnd, 1, duration, None);
            LRESULT(0)
        }
        windows::Win32::UI::WindowsAndMessaging::WM_TIMER => {
            let _ = KillTimer(hwnd, wparam.0);
            let _ = ShowWindow(hwnd, SW_HIDE);
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

#[cfg(windows)]
fn spawn_overlay_thread() {
    std::thread::spawn(|| unsafe {
        use windows::core::PCWSTR;
        use windows::Win32::Foundation::{COLORREF, HINSTANCE, HWND};
        use windows::Win32::UI::WindowsAndMessaging::{
            CreateWindowExW, DispatchMessageW, GetMessageW, PostMessageW, RegisterClassW,
            SetLayeredWindowAttributes, TranslateMessage, CS_HREDRAW, CS_VREDRAW, LWA_ALPHA, MSG,
            WNDCLASSW, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_POPUP,
        };

        let class_name = win_balloon::encode_wide::<64>("KairoOverlayWindowClass");
        let wc = WNDCLASSW {
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(overlay_wnd_proc),
            hInstance: HINSTANCE::default(),
            lpszClassName: PCWSTR(class_name.as_ptr()),
            ..Default::default()
        };
        RegisterClassW(&wc);

        let font_title_name: Vec<u16> = "Kairo Overlay\0".encode_utf16().collect();
        let hwnd = CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW,
            PCWSTR(class_name.as_ptr()),
            PCWSTR(font_title_name.as_ptr()),
            WS_POPUP,
            100,
            100,
            320,
            80,
            HWND::default(),
            None,
            HINSTANCE::default(),
            None,
        )
        .unwrap_or(HWND::default());

        if hwnd == HWND::default() {
            tracing::error!("Failed to create overlay window");
            return;
        }

        let _ = SetLayeredWindowAttributes(hwnd, COLORREF(0), 235, LWA_ALPHA);
        OVERLAY_HWND.store(hwnd.0 as isize, Ordering::SeqCst);

        let _ = PostMessageW(
            hwnd,
            WM_SHOWOVERLAY,
            windows::Win32::Foundation::WPARAM(0),
            windows::Win32::Foundation::LPARAM(0),
        );

        let mut msg = MSG::default();
        while GetMessageW(&mut msg, None, 0, 0).as_bool() {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    });
}

pub fn show_overlay(title: &str, body: &str, color: OverlayColor, duration_ms: u32) {
    tracing::info!("Overlay ({}): {}", title, body);
    #[cfg(windows)]
    {
        {
            let mut data = PENDING_OVERLAY_DATA.lock().unwrap();
            *data = Some(OverlayData {
                title: title.to_string(),
                body: body.to_string(),
                color_type: color,
                duration_ms,
            });
        }

        let hwnd_val = OVERLAY_HWND.load(Ordering::SeqCst);
        if hwnd_val == 0 {
            spawn_overlay_thread();
            // Wait for window creation
            for _ in 0..10 {
                let h = OVERLAY_HWND.load(Ordering::SeqCst);
                if h != 0 {
                    unsafe {
                        let _ = windows::Win32::UI::WindowsAndMessaging::PostMessageW(
                            windows::Win32::Foundation::HWND(h as *mut std::ffi::c_void),
                            WM_SHOWOVERLAY,
                            windows::Win32::Foundation::WPARAM(0),
                            windows::Win32::Foundation::LPARAM(0),
                        );
                    }
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(30));
            }
        } else {
            unsafe {
                let _ = windows::Win32::UI::WindowsAndMessaging::PostMessageW(
                    windows::Win32::Foundation::HWND(hwnd_val as *mut std::ffi::c_void),
                    WM_SHOWOVERLAY,
                    windows::Win32::Foundation::WPARAM(0),
                    windows::Win32::Foundation::LPARAM(0),
                );
            }
        }
    }
}

// ─── Public API ───────────────────────────────────────────────────────────────

/// Show a Windows overlay notification for a PAHF clarification request.
pub fn show_clarification_toast(question: &str) {
    show_overlay(
        "Clarification Required ❓",
        question,
        OverlayColor::Info,
        5000,
    );
}

/// Show a completion overlay when Kairo finishes generating.
pub fn show_completion_toast(chars_injected: usize, agent_name: &str) {
    let body = format!("{agent_name} injected {chars_injected} characters");
    show_overlay("Generation Complete ✅", &body, OverlayColor::Success, 4000);
}

/// Show a progress overlay for long-running operations.
pub fn show_progress_toast(message: &str) {
    show_overlay("Kairo Assistant 🧠", message, OverlayColor::Info, 3000);
}

/// Show an error overlay for failures and warnings.
pub fn show_error_toast(message: &str) {
    show_overlay("Error Encountered ❌", message, OverlayColor::Error, 5000);
}

// ─── V4: Streaming Indicator (Pulsing Ghost Icon) ─────────────────────────────

pub fn start_streaming_indicator(agent_id: &str, timeout_secs: u64) -> Arc<AtomicBool> {
    let stop_flag = Arc::new(AtomicBool::new(false));
    let stop_clone = stop_flag.clone();
    let agent_label = agent_id.to_string();

    tracing::info!(
        "👻 Streaming indicator: starting (agent={}, timeout={}s)",
        agent_id,
        timeout_secs
    );

    std::thread::spawn(move || {
        let frames = ["👻", "👁", "💫", "✨"];
        let mut frame_idx = 0usize;
        let start = std::time::Instant::now();
        let timeout = std::time::Duration::from_secs(timeout_secs);

        while !stop_clone.load(Ordering::Relaxed) && start.elapsed() < timeout {
            let icon = frames[frame_idx % frames.len()];
            tracing::debug!(
                "[StreamingIndicator] {} Kairo AI ({}) — generating...",
                icon,
                agent_label
            );

            #[cfg(windows)]
            {
                let _ = std::process::Command::new("powershell")
                    .args([
                        "-NoProfile",
                        "-NonInteractive",
                        "-WindowStyle",
                        "Hidden",
                        "-Command",
                        &format!(
                            "$Host.UI.RawUI.WindowTitle = '{icon} Kairo Phantom — {agent_label} generating…'"
                        ),
                    ])
                    .spawn();
            }

            frame_idx += 1;
            std::thread::sleep(std::time::Duration::from_millis(500));
        }

        tracing::info!("👻 Streaming indicator: stopped (agent={})", agent_label);

        #[cfg(windows)]
        {
            let _ = std::process::Command::new("powershell")
                .args([
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    "$Host.UI.RawUI.WindowTitle = 'Kairo Phantom'",
                ])
                .spawn();
        }
    });

    stop_flag
}

// ─── V4: Agent Selection Debug Logger ─────────────────────────────────────────

pub fn log_agent_selection(agent_id: &str, score: u8, doc_kind: &str, prompt_preview: &str) {
    let kairo_dir = dirs::home_dir().unwrap_or_default().join(".kairo-phantom");
    let log_path = kairo_dir.join("agent_debug.jsonl");

    let timestamp = chrono::Utc::now().to_rfc3339();
    let safe_prompt = prompt_preview
        .chars()
        .take(120)
        .collect::<String>()
        .replace('"', "'");

    let entry = format!(
        r#"{{"ts":"{timestamp}","agent":"{agent_id}","score":{score},"doc_kind":"{doc_kind}","prompt":"{safe_prompt}"}}"#
    );

    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
    {
        use std::io::Write;
        let _ = writeln!(file, "{entry}");
    }

    tracing::debug!("[AgentDebug] {}", entry);
}

// ─── Periodic Health Checks ──────────────────────────────────────────────────

#[cfg(windows)]
fn check_vlm_availability() -> bool {
    if let Some(home) = dirs::home_dir() {
        let cache_dir = home.join(".kairo-phantom").join("models");
        let model_3b = cache_dir.join("qwen2.5-vl-3b-instruct-Q4_K_M.gguf");
        let model_7b = cache_dir.join("qwen2.5-vl-7b-instruct-Q4_K_M.gguf");

        let is_3b_ok = model_3b.exists()
            && model_3b
                .metadata()
                .map(|m| m.len() > 100_000_000)
                .unwrap_or(false);
        let is_7b_ok = model_7b.exists()
            && model_7b
                .metadata()
                .map(|m| m.len() > 100_000_000)
                .unwrap_or(false);

        is_3b_ok || is_7b_ok
    } else {
        false
    }
}

#[cfg(windows)]
fn check_driver_status() -> bool {
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
            return true;
        }
    }

    if let Ok(output) = std::process::Command::new("where")
        .arg("cua-driver")
        .output()
    {
        if output.status.success() {
            return true;
        }
    }

    false
}

#[cfg(windows)]
fn check_enigo_status() -> bool {
    use enigo::{Enigo, Settings};
    Enigo::new(&Settings::default()).is_ok()
}

pub fn start_periodic_health_checks() {
    #[cfg(windows)]
    {
        std::thread::spawn(move || {
            use std::time::Duration;
            // Wait 5 seconds after startup to perform the first check
            std::thread::sleep(Duration::from_secs(5));
            loop {
                let vlm_ok = check_vlm_availability();
                let driver_ok = check_driver_status();
                let enigo_ok = check_enigo_status();

                let title = "Kairo System Health 🟢";
                let mut body = String::new();
                let mut color = OverlayColor::Success;

                if !vlm_ok || !driver_ok || !enigo_ok {
                    let mut err_title = "Kairo Health Alert ⚠️".to_string();
                    color = OverlayColor::Error;

                    if !vlm_ok {
                        body.push_str("• VLM (Qwen2.5-VL) model is missing/downloading.\n");
                    }
                    if !driver_ok {
                        body.push_str("• CUA Driver binary was not found.\n");
                    }
                    if !enigo_ok {
                        body.push_str("• Keyboard/Mouse emulation is failing.\n");
                    }
                    show_overlay(&err_title, &body, color, 4000);
                } else {
                    body.push_str("• VLM (Qwen2.5-VL) Active\n• CUA Driver Active\n• Keyboard/Mouse Emulation Active");
                    show_overlay(title, &body, color, 4000);
                }

                std::thread::sleep(Duration::from_secs(60));
            }
        });
    }
}
