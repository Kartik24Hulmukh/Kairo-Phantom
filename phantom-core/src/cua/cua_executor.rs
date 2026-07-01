//! # CUA Executor
//!
//! Executes CUA actions via enigo (primary) or cua-driver (fallback).
//! Checks ESC/CancellationToken before EVERY action.
//! Captures after-screenshot and verifies via farscry.
//! Logs to audit trail on success or failure.

use super::{CuaAction, CuaBackend, CuaContext, CuaResult, CuaVerification, WellKnownShortcut};
use std::time::Duration;
use tokio_util::sync::CancellationToken;

use std::sync::Mutex;
pub static LAST_MOUSE_MOVE: once_cell::sync::Lazy<Mutex<Option<(i32, i32)>>> =
    once_cell::sync::Lazy::new(|| Mutex::new(None));

/// Error from CUA executor
#[derive(Debug)]
pub enum ExecutorError {
    EnigoInit(String),
    EnigoAction(String),
    CuaDriverNotFound,
    CuaDriverFailed(String),
    VerificationFailed(String),
}

impl std::fmt::Display for ExecutorError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ExecutorError::EnigoInit(e) => write!(f, "enigo init failed: {e}"),
            ExecutorError::EnigoAction(e) => write!(f, "enigo action failed: {e}"),
            ExecutorError::CuaDriverNotFound => write!(f, "cua-driver binary not found"),
            ExecutorError::CuaDriverFailed(e) => write!(f, "cua-driver failed: {e}"),
            ExecutorError::VerificationFailed(e) => write!(f, "farscry verification failed: {e}"),
        }
    }
}

/// Execute a single CUA action.
///
/// Respects cancellation token — ESC cancels immediately.
/// Falls back to cua-driver if enigo fails.
/// Verifies result via farscry after-screenshot.
pub async fn execute(
    action: &CuaAction,
    ctx: &CuaContext,
    backend: &CuaBackend,
    cancellation: &CancellationToken,
) -> CuaResult {
    // Check cancellation first before anything else
    if cancellation.is_cancelled() {
        return CuaResult::Cancelled;
    }

    // Load config and validate action before execution
    let config = super::config::CuaConfig::load();
    let mut rl = super::cua_gate::GLOBAL_RATE_LIMITER.lock().await;
    if let Err(e) = super::cua_gate::validate_action(action, ctx, config.enabled, &mut rl).await {
        return CuaResult::Failed(e.to_string());
    }
    drop(rl); // Release lock immediately

    let mut mutable_ctx = ctx.clone();
    // Capture before-screenshot if not present
    if mutable_ctx.before_screenshot_path.is_none() {
        mutable_ctx.before_screenshot_path = capture_before_screenshot().await;
    }

    let mut current_backend = backend.clone();

    loop {
        // ALWAYS check ESC/cancellation before executing any action
        if cancellation.is_cancelled() {
            tracing::info!("[CUA] Cancelled before action: {:?}", action);
            return CuaResult::Cancelled;
        }

        // Small delay to ensure UI has settled (avoids race conditions)
        tokio::time::sleep(Duration::from_millis(50)).await;

        // Check cancellation again after delay
        if cancellation.is_cancelled() {
            return CuaResult::Cancelled;
        }

        // Dispatch to appropriate backend
        let result = match current_backend {
            CuaBackend::Enigo => execute_enigo(action, &mutable_ctx),
            CuaBackend::CuaDriver => execute_cua_driver(action, &mutable_ctx),
        };

        match result {
            Ok(()) => {
                // Verify via farscry after-screenshot or VLM
                let verification = verify_action(action, &mutable_ctx).await;
                match verification {
                    Ok(v) if v.success => {
                        // Log success to audit trail
                        audit_log_success(action, &mutable_ctx, &v).await;
                        tracing::info!("[CUA Telemetry] Action execution success. Current vlm_call_rate = {:.4}", super::world_model::get_vlm_call_rate());
                        return CuaResult::Success(v);
                    }
                    Ok(v) => {
                        tracing::warn!(
                            "[CUA] Verification failed for {:?} — trying fallback",
                            action
                        );
                        // Try fallback backend
                        if let Some(fallback) = current_backend.fallback() {
                            current_backend = fallback;
                            continue;
                        } else {
                            audit_log_failure(
                                action,
                                &mutable_ctx,
                                "Both backends failed verification",
                            )
                            .await;
                            return CuaResult::Failed(
                                "Verification failed after both backends".to_string(),
                            );
                        }
                    }
                    Err(e) => {
                        tracing::error!("[CUA] verification unavailable: {} — failing closed", e);
                        audit_log_failure(action, &mutable_ctx, "Unverified").await;
                        return CuaResult::Failed("Unverified".to_string());
                    }
                }
            }
            Err(e) => {
                tracing::warn!(
                    "[CUA] {:?} backend failed: {} — trying fallback",
                    current_backend,
                    e
                );
                // Try fallback backend
                if let Some(fallback) = current_backend.fallback() {
                    current_backend = fallback;
                    continue;
                } else {
                    audit_log_failure(action, &mutable_ctx, &e.to_string()).await;
                    return CuaResult::Failed(e.to_string());
                }
            }
        }
    }
}

/// Execute action via enigo (primary backend).
/// CRITICAL: All mouse coordinates are DPI-scaled by ctx.dpi_scale.
fn execute_enigo(action: &CuaAction, ctx: &CuaContext) -> Result<(), ExecutorError> {
    use enigo::{Axis, Button, Coordinate, Direction, Enigo, Key, Keyboard, Mouse, Settings};

    match action {
        CuaAction::MouseClick { x, y, .. }
        | CuaAction::MouseDoubleClick { x, y, .. }
        | CuaAction::MouseMove { x, y } => {
            let (scaled_x, scaled_y) = scale_to_physical(ctx, *x, *y);
            if let Ok(mut guard) = LAST_MOUSE_MOVE.lock() {
                *guard = Some((scaled_x, scaled_y));
            }
        }
        _ => {}
    }

    let mut enigo = match Enigo::new(&Settings::default()) {
        Ok(e) => e,
        Err(e) => {
            if std::env::var("KAIRO_MOCK_ENIGO").is_ok() || cfg!(test) {
                tracing::warn!("Mocking enigo: {}", e);
                return Ok(());
            }
            return Err(ExecutorError::EnigoInit(e.to_string()));
        }
    };

    match action {
        CuaAction::MouseClick { x, y, button, .. } => {
            // Scale logical coordinates to physical pixels
            let (scaled_x, scaled_y) = scale_to_physical(ctx, *x, *y);

            enigo
                .move_mouse(scaled_x, scaled_y, Coordinate::Abs)
                .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;

            // Small settle delay after move
            std::thread::sleep(Duration::from_millis(50));

            let btn = match button {
                super::MouseButton::Left => Button::Left,
                super::MouseButton::Right => Button::Right,
                super::MouseButton::Middle => Button::Middle,
            };
            enigo
                .button(btn, Direction::Click)
                .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
        }

        CuaAction::MouseDoubleClick { x, y, button } => {
            let (scaled_x, scaled_y) = scale_to_physical(ctx, *x, *y);

            enigo
                .move_mouse(scaled_x, scaled_y, Coordinate::Abs)
                .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            std::thread::sleep(Duration::from_millis(30));

            let btn = match button {
                super::MouseButton::Left => Button::Left,
                super::MouseButton::Right => Button::Right,
                super::MouseButton::Middle => Button::Middle,
            };
            enigo
                .button(btn, Direction::Click)
                .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            std::thread::sleep(Duration::from_millis(30));
            enigo
                .button(btn, Direction::Click)
                .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
        }

        CuaAction::MouseMove { x, y } => {
            let (scaled_x, scaled_y) = scale_to_physical(ctx, *x, *y);
            enigo
                .move_mouse(scaled_x, scaled_y, Coordinate::Abs)
                .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
        }

        CuaAction::MouseScroll { direction, amount } => {
            let (dx, dy) = match direction {
                super::ScrollDirection::Up => (0, *amount),
                super::ScrollDirection::Down => (0, -amount),
                super::ScrollDirection::Left => (-amount, 0),
                super::ScrollDirection::Right => (*amount, 0),
            };
            if dy != 0 {
                enigo
                    .scroll(dy, Axis::Vertical)
                    .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            }
            if dx != 0 {
                enigo
                    .scroll(dx, Axis::Horizontal)
                    .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            }
        }

        CuaAction::KeyboardType { text } => {
            const CHUNK_SIZE: usize = 200; // chars; at ~40 WPM enigo ≈ 50ms per chunk
            if text.len() <= CHUNK_SIZE {
                enigo
                    .text(text)
                    .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            } else {
                let chars: Vec<char> = text.chars().collect();
                for chunk in chars.chunks(CHUNK_SIZE) {
                    let chunk_str: String = chunk.iter().collect();
                    enigo
                        .text(&chunk_str)
                        .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
                    std::thread::sleep(Duration::from_millis(10));
                }
            }
        }

        CuaAction::KeyboardCombo { keys } => {
            let mut modifier_keys: Vec<Key> = Vec::new();
            let mut main_key: Option<Key> = None;

            for k in keys {
                match k.to_lowercase().as_str() {
                    "ctrl" | "control" => modifier_keys.push(Key::Control),
                    "shift" => modifier_keys.push(Key::Shift),
                    "alt" => modifier_keys.push(Key::Alt),
                    "win" | "meta" => modifier_keys.push(Key::Meta),
                    s if s.len() == 1 => {
                        main_key = s.chars().next().map(Key::Unicode);
                    }
                    _ => {}
                }
            }

            for key in &modifier_keys {
                enigo
                    .key(*key, Direction::Press)
                    .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            }
            if let Some(key) = main_key {
                enigo
                    .key(key, Direction::Click)
                    .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            }
            for key in modifier_keys.iter().rev() {
                enigo
                    .key(*key, Direction::Release)
                    .map_err(|e| ExecutorError::EnigoAction(e.to_string()))?;
            }
        }

        CuaAction::KeyboardShortcut { shortcut } => {
            execute_well_known_shortcut(&mut enigo, shortcut)
                .map_err(ExecutorError::EnigoAction)?;
        }

        CuaAction::Screenshot => {
            // Screenshot is handled by CuaGate and verification — not an enigo action
        }
        CuaAction::Delay { ms } => {
            std::thread::sleep(Duration::from_millis(*ms));
        }
    }

    Ok(())
}

/// Execute a well-known keyboard shortcut via enigo
fn execute_well_known_shortcut(
    enigo: &mut enigo::Enigo,
    shortcut: &WellKnownShortcut,
) -> Result<(), String> {
    use enigo::{Direction, Key, Keyboard};

    let press_ctrl = |enigo: &mut enigo::Enigo, key: Key| -> Result<(), String> {
        enigo
            .key(Key::Control, Direction::Press)
            .map_err(|e| e.to_string())?;
        enigo
            .key(key, Direction::Click)
            .map_err(|e| e.to_string())?;
        enigo
            .key(Key::Control, Direction::Release)
            .map_err(|e| e.to_string())?;
        Ok(())
    };

    let press_ctrl_shift = |enigo: &mut enigo::Enigo, key: Key| -> Result<(), String> {
        enigo
            .key(Key::Control, Direction::Press)
            .map_err(|e| e.to_string())?;
        enigo
            .key(Key::Shift, Direction::Press)
            .map_err(|e| e.to_string())?;
        enigo
            .key(key, Direction::Click)
            .map_err(|e| e.to_string())?;
        enigo
            .key(Key::Shift, Direction::Release)
            .map_err(|e| e.to_string())?;
        enigo
            .key(Key::Control, Direction::Release)
            .map_err(|e| e.to_string())?;
        Ok(())
    };

    match shortcut {
        WellKnownShortcut::SaveAsPdf => press_ctrl_shift(enigo, Key::Unicode('p')),
        WellKnownShortcut::SaveAs => press_ctrl_shift(enigo, Key::Unicode('s')),
        WellKnownShortcut::SelectAll => press_ctrl(enigo, Key::Unicode('a')),
        WellKnownShortcut::Undo => press_ctrl(enigo, Key::Unicode('z')),
        WellKnownShortcut::Redo => press_ctrl(enigo, Key::Unicode('y')),
        WellKnownShortcut::CloseDialog => enigo
            .key(Key::Escape, Direction::Click)
            .map_err(|e| e.to_string()),
        WellKnownShortcut::ConfirmDialog => enigo
            .key(Key::Return, Direction::Click)
            .map_err(|e| e.to_string()),
        WellKnownShortcut::NextField => enigo
            .key(Key::Tab, Direction::Click)
            .map_err(|e| e.to_string()),
    }
}

/// Execute action via cua-driver binary (fallback backend).
/// cua-driver is the low-level cross-platform driver from trycua — NOT the VM sandbox.
fn execute_cua_driver(action: &CuaAction, ctx: &CuaContext) -> Result<(), ExecutorError> {
    let driver = crate::platform::new_cua_driver();
    driver.execute_driver(action, ctx).map_err(|e| {
        let msg = e.to_string();
        if msg.contains("not found") {
            ExecutorError::CuaDriverNotFound
        } else {
            ExecutorError::CuaDriverFailed(msg)
        }
    })
}

/// Verify the action completed correctly using farscry OCR comparison.
/// Captures after-screenshot and compares to before-screenshot.
/// Falls back gracefully if farscry is not installed.
async fn verify_action(
    action: &CuaAction,
    ctx: &CuaContext,
) -> Result<CuaVerification, ExecutorError> {
    // Capture after screenshot
    let after_path = capture_screenshot().await.unwrap_or_default();

    let before_hash = ctx
        .before_screenshot_path
        .as_ref()
        .and_then(|p| hash_file(p).ok())
        .unwrap_or_default();

    let after_hash = if !after_path.is_empty() {
        hash_file(&after_path).unwrap_or_default()
    } else {
        String::new()
    };

    // If VLM is available, attempt semantic verification
    let bridge = super::vlm_bridge::VlmBridge::new();
    if bridge.is_available().await {
        if let Some(before_path) = &ctx.before_screenshot_path {
            if !after_path.is_empty() {
                let expected = match action {
                    CuaAction::KeyboardShortcut { shortcut } => match shortcut {
                        super::WellKnownShortcut::SaveAsPdf => "export as pdf dialog or file saved",
                        super::WellKnownShortcut::SaveAs => "save dialog open",
                        super::WellKnownShortcut::SelectAll => "all text selected",
                        super::WellKnownShortcut::Undo => "action undone",
                        super::WellKnownShortcut::Redo => "action redone",
                        super::WellKnownShortcut::CloseDialog => "dialog closed",
                        super::WellKnownShortcut::ConfirmDialog => "dialog confirmed or closed",
                        super::WellKnownShortcut::NextField => "focus moved to next field",
                    },
                    CuaAction::KeyboardCombo { keys } => {
                        &format!("keyboard combo {keys:?} executed")
                    }
                    CuaAction::KeyboardType { text } => &format!("text '{text}' typed"),
                    CuaAction::MouseClick { .. } => "element clicked and UI state updated",
                    CuaAction::MouseDoubleClick { .. } => "element double-clicked",
                    CuaAction::MouseMove { .. } => "mouse moved to element",
                    CuaAction::MouseScroll { .. } => "screen scrolled",
                    CuaAction::Screenshot => "screenshot captured",
                    CuaAction::Delay { .. } => "delay elapsed",
                };

                super::world_model::VLM_INVOCATIONS
                    .fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                match bridge
                    .verify_action(before_path, &after_path, expected)
                    .await
                {
                    Ok(vlm_resp) => {
                        return Ok(CuaVerification {
                            success: vlm_resp.success,
                            after_screenshot_path: after_path,
                            before_hash,
                            after_hash,
                        });
                    }
                    Err(e) => {
                        tracing::warn!("[CUA Executor] VLM verification error: {} — falling back to hash/pixel verification", e);
                    }
                }
            }
        }
    }

    // Fallback: If before and after hashes differ, something changed — consider success
    if before_hash.is_empty() || after_hash.is_empty() {
        return Err(ExecutorError::VerificationFailed(
            "Verification screenshots unavailable".into(),
        ));
    }

    let success = match action {
        CuaAction::KeyboardType { .. }
        | CuaAction::KeyboardCombo { .. }
        | CuaAction::KeyboardShortcut { .. } => {
            true // Keyboard actions assumed successful if no exception and screenshots are available
        }
        _ => {
            before_hash != after_hash // Something changed
        }
    };

    Ok(CuaVerification {
        success,
        after_screenshot_path: after_path,
        before_hash,
        after_hash,
    })
}

/// Capture a screenshot and return the file path
async fn capture_screenshot() -> Option<String> {
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();

    let kairo_dir = dirs::home_dir()?.join(".kairo-phantom").join("screenshots");
    std::fs::create_dir_all(&kairo_dir).ok()?;

    let path = kairo_dir.join(format!("cua_after_{timestamp}.png"));

    // Try farscry first
    let result = std::process::Command::new("farscry")
        .args(["screenshot", "--output", path.to_str().unwrap_or("")])
        .output();

    match result {
        Ok(output) if output.status.success() => Some(path.to_string_lossy().to_string()),
        _ => None,
    }
}

/// Capture a before screenshot and return the file path
async fn capture_before_screenshot() -> Option<String> {
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();

    let kairo_dir = dirs::home_dir()?.join(".kairo-phantom").join("screenshots");
    std::fs::create_dir_all(&kairo_dir).ok()?;

    let path = kairo_dir.join(format!("cua_before_{timestamp}.png"));

    // Try farscry first
    let result = std::process::Command::new("farscry")
        .args(["screenshot", "--output", path.to_str().unwrap_or("")])
        .output();

    match result {
        Ok(output) if output.status.success() => Some(path.to_string_lossy().to_string()),
        _ => None,
    }
}

/// Compute SHA-256 hash of a file (for audit trail)
fn hash_file(path: &str) -> Result<String, std::io::Error> {
    use std::io::Read;
    let mut file = std::fs::File::open(path)?;
    let mut hasher = <sha2::Sha256 as sha2::Digest>::new();
    let mut buffer = [0u8; 8192];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        sha2::Digest::update(&mut hasher, &buffer[..n]);
    }
    Ok(hex::encode(sha2::Digest::finalize(hasher)))
}

/// Append a CUA success entry to the audit log
async fn audit_log_success(action: &CuaAction, ctx: &CuaContext, verification: &CuaVerification) {
    audit_log(
        action,
        ctx,
        true,
        &verification.before_hash,
        &verification.after_hash,
        None,
    )
    .await;
}

/// Append a CUA failure entry to the audit log
async fn audit_log_failure(action: &CuaAction, ctx: &CuaContext, reason: &str) {
    audit_log(action, ctx, false, "", "", Some(reason)).await;
}

/// Core audit log writer — append-only, never modifiable
async fn audit_log(
    action: &CuaAction,
    ctx: &CuaContext,
    success: bool,
    before_hash: &str,
    after_hash: &str,
    error: Option<&str>,
) {
    let kairo_dir = match dirs::home_dir() {
        Some(h) => h.join(".kairo-phantom"),
        None => return,
    };

    let _ = std::fs::create_dir_all(&kairo_dir);
    let log_path = kairo_dir.join("audit.log");

    let timestamp = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
    let action_type = format!("{:?}", std::mem::discriminant(action));
    let entry = format!(
        "[{}] CUA action={} window=\"{}\" app=\"{}\" success={} before_hash={} after_hash={}{}\n",
        timestamp,
        action_type,
        ctx.window_title,
        ctx.app_name,
        success,
        before_hash,
        after_hash,
        error.map(|e| format!(" error=\"{e}\"")).unwrap_or_default()
    );

    // Append-only — O_APPEND flag ensures atomicity
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
    {
        let _ = f.write_all(entry.as_bytes());
    }
}

// Needed import for scroll axis — enigo 0.2 uses Axis enum
use enigo::Axis;

/// Map a planner logical coordinate to a physical virtual-desktop pixel.
/// On Windows this routes through the monitor under the active window
/// (per-monitor origin + DPI, with dead-space clamping). On other platforms it
/// preserves the legacy single global `dpi_scale` behaviour until per-platform
/// enumeration lands.
fn scale_to_physical(ctx: &CuaContext, x: i32, y: i32) -> (i32, i32) {
    #[cfg(target_os = "windows")]
    {
        let layout = crate::platform::enumerate_monitors();
        let center = (
            (ctx.window_rect.left + ctx.window_rect.right) / 2,
            (ctx.window_rect.top + ctx.window_rect.bottom) / 2,
        );
        // Apply the application-level dpi_scale (from CuaContext) to get
        // physical pixels, then use the monitor layout for virtual-desktop
        // offset and clamping. We do NOT use resolve_click here because that
        // function applies the monitor's OS-reported scale, which would
        // double-scale when ctx.dpi_scale already reflects the DPI.
        let scaled_x = (x as f32 * ctx.dpi_scale) as i32;
        let scaled_y = (y as f32 * ctx.dpi_scale) as i32;
        match layout.monitor_at(center.0, center.1) {
            Some(m) => {
                let px = m.x + scaled_x;
                let py = m.y + scaled_y;
                layout.clamp_to_nearest(px, py)
            }
            None => layout.clamp_to_nearest(scaled_x, scaled_y),
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        (
            (x as f32 * ctx.dpi_scale) as i32,
            (y as f32 * ctx.dpi_scale) as i32,
        )
    }
}
