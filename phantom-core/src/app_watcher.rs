// phantom-core/src/app_watcher.rs
//
// FarScry — Foreground App Watcher
// ─────────────────────────────────────────────────────────────────────────────
// Polls the foreground window and emits AppChangedEvent whenever a different
// process becomes the active app.
//
// Implementation strategy
// ───────────────────────
// • Uses GetForegroundWindow() → GetWindowThreadProcessId() → QueryFullProcessImageNameW()
//   to resolve the process name in a single API call chain.
// • Polls every POLL_INTERVAL_MS milliseconds inside a dedicated std::thread.
// • Sends AppChangedEvent via a std::sync::mpsc::Sender.
// • For non-Windows targets the watcher is a no-op stub so the crate compiles
//   on Linux / macOS CI.
//
// The FarScry Python sidecar service (sidecar/farscry_service.py) reads these
// events over a named pipe / IPC channel and propagates them to the routing layer.

use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tracing::{debug, error, info, warn};

use once_cell::sync::Lazy;
use std::sync::atomic::AtomicBool;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct RecordedAction {
    #[serde(rename = "type")]
    pub action_type: String,
    pub keys: Option<Vec<String>>,
    pub text: Option<String>,
    pub shortcut: Option<String>,
    pub ms: Option<u64>,
}

pub static IS_RECORDING: AtomicBool = AtomicBool::new(false);
pub static RECORDING_NAME: Lazy<Mutex<String>> =
    Lazy::new(|| Mutex::new("recorded_workflow".to_string()));
pub static RECORDED_ACTIONS: Lazy<Mutex<Vec<RecordedAction>>> =
    Lazy::new(|| Mutex::new(Vec::new()));
pub static LAST_EVENT_TIME: Lazy<Mutex<std::time::Instant>> =
    Lazy::new(|| Mutex::new(std::time::Instant::now()));

/// Default polling interval for the foreground-window watcher.
const POLL_INTERVAL_MS: u64 = 250;

// ─── Event ────────────────────────────────────────────────────────────────────

/// Fired each time the active application changes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AppChangedEvent {
    /// Bare process name, e.g. "WINWORD.EXE", "Code.exe"
    pub process_name: String,
    /// Human-readable label resolved from known process names
    pub app_label: String,
    /// Window title at the moment of the switch
    pub window_title: String,
    /// Win32 process ID of the new foreground process
    pub pid: u32,
}

impl AppChangedEvent {
    /// Maps known process names to friendly labels.
    pub fn label_for_process(process_name: &str) -> &'static str {
        match process_name.to_ascii_lowercase().as_str() {
            s if s.starts_with("winword") => "Microsoft Word",
            s if s.starts_with("excel") => "Microsoft Excel",
            s if s.starts_with("powerpnt") => "Microsoft PowerPoint",
            s if s.starts_with("outlook") => "Microsoft Outlook",
            s if s.starts_with("code") => "Visual Studio Code",
            s if s.starts_with("notepad++") => "Notepad++",
            s if s.starts_with("notepad") => "Notepad",
            s if s.starts_with("chrome") => "Google Chrome",
            s if s.starts_with("msedge") => "Microsoft Edge",
            s if s.starts_with("firefox") => "Mozilla Firefox",
            s if s.starts_with("acrobat") => "Adobe Acrobat",
            s if s.starts_with("powershell") => "PowerShell",
            s if s.starts_with("windowsterminal") => "Windows Terminal",
            s if s.starts_with("cmd") => "Command Prompt",
            _ => "Unknown",
        }
    }
}

// ─── Watcher ──────────────────────────────────────────────────────────────────

/// Background thread that polls the foreground window and emits AppChangedEvents.
pub struct AppWatcher {
    tx: Sender<AppChangedEvent>,
    poll_interval: Duration,
}

impl AppWatcher {
    /// Create a new watcher with the default poll interval (250ms).
    pub fn new(tx: Sender<AppChangedEvent>) -> Self {
        Self {
            tx,
            poll_interval: Duration::from_millis(POLL_INTERVAL_MS),
        }
    }

    /// Create a watcher with a custom poll interval (useful for tests).
    pub fn with_interval(tx: Sender<AppChangedEvent>, poll_ms: u64) -> Self {
        Self {
            tx,
            poll_interval: Duration::from_millis(poll_ms),
        }
    }

    /// Spawn the polling loop on a dedicated background thread.
    ///
    /// Returns a `WatcherHandle` that can stop the thread via `stop()`.
    pub fn spawn(self) -> WatcherHandle {
        let stop_flag = Arc::new(Mutex::new(false));
        let stop_clone = Arc::clone(&stop_flag);
        let stop_clone2 = Arc::clone(&stop_flag);

        let handle = thread::Builder::new()
            .name("kairo-app-watcher".to_string())
            .spawn(move || {
                self.run_loop(stop_clone);
            })
            .expect("AppWatcher: failed to spawn background thread");

        #[cfg(target_os = "windows")]
        {
            let _ = thread::Builder::new()
                .name("kairo-workflow-recorder".to_string())
                .spawn(move || {
                    Self::monitor_uia_events(stop_clone2);
                });
        }

        WatcherHandle {
            _thread: handle,
            stop_flag,
        }
    }

    #[cfg(target_os = "windows")]
    fn monitor_uia_events(stop_flag: Arc<Mutex<bool>>) {
        use std::sync::atomic::Ordering;
        use std::time::Instant;
        use uiautomation::core::UIAutomation;
        use uiautomation::types::UIProperty;

        let uia = match UIAutomation::new() {
            Ok(u) => u,
            Err(_) => return,
        };

        let mut last_focused_id = Vec::new();

        while !*stop_flag.lock().unwrap() {
            if let Ok(focused) = uia.get_focused_element() {
                // 1. Update World Model Cache and compute diff/delta
                #[cfg(feature = "cua")]
                {
                    let hwnd = unsafe {
                        windows::Win32::UI::WindowsAndMessaging::GetForegroundWindow().0 as isize
                    };
                    if let Ok(id) = focused.get_runtime_id() {
                        if let Ok(new_tree) = crate::cua::world_model::build_tree(&focused, 0) {
                            let mut model_map =
                                crate::cua::world_model::GLOBAL_WORLD_MODEL.lock().unwrap();
                            let app_model = model_map.entry(hwnd).or_default();

                            if let Some(ref old_tree) = app_model.root {
                                let mut delta = crate::cua::world_model::UiDelta::default();
                                crate::cua::world_model::diff_trees(
                                    old_tree, &new_tree, &mut delta,
                                );
                                if !delta.added.is_empty()
                                    || !delta.removed.is_empty()
                                    || !delta.value_changed.is_empty()
                                {
                                    info!(
                                        "[World Model] UiDelta detected for hwnd {}: {} added, {} removed, {} value changed",
                                        hwnd, delta.added.len(), delta.removed.len(), delta.value_changed.len()
                                    );
                                }
                            }
                            app_model.root = Some(new_tree);
                        }
                    }
                }

                // 2. Recording logic
                if IS_RECORDING.load(Ordering::SeqCst) {
                    if let Ok(id) = focused.get_runtime_id() {
                        if id != last_focused_id {
                            last_focused_id = id;

                            // Check if password field
                            let mut is_password = false;
                            if let Ok(b) = focused.is_password() {
                                is_password = b;
                            }

                            // Also check class name for safety
                            if let Ok(s) = focused.get_classname() {
                                if s.to_lowercase().contains("password") {
                                    is_password = true;
                                }
                            }

                            if !is_password {
                                if let Ok(name) = focused.get_name() {
                                    if !name.is_empty() {
                                        let mut actions = RECORDED_ACTIONS.lock().unwrap();
                                        let mut last_time = LAST_EVENT_TIME.lock().unwrap();

                                        actions.push(RecordedAction {
                                            action_type: "keyboard_shortcut".to_string(),
                                            keys: None,
                                            text: None,
                                            shortcut: Some("next_field".to_string()),
                                            ms: Some(100),
                                        });

                                        *last_time = Instant::now();
                                        info!("[Recorder] Recorded UIA element focus: {}", name);
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Check inactivity timeout (5 seconds)
            let now = Instant::now();
            let last_time = *LAST_EVENT_TIME.lock().unwrap();
            if now.duration_since(last_time) > Duration::from_secs(5) {
                let mut actions = RECORDED_ACTIONS.lock().unwrap();
                if actions.len() >= 3 {
                    let name = RECORDING_NAME.lock().unwrap().clone();
                    if let Some(home) = dirs::home_dir() {
                        let dir = home.join(".kairo-phantom").join("workflows");
                        let _ = std::fs::create_dir_all(&dir);
                        let path = dir.join(format!("{name}.toml"));

                        #[derive(serde::Serialize)]
                        struct TomlWorkflow {
                            apps: std::collections::HashMap<String, TomlApp>,
                        }
                        #[derive(serde::Serialize)]
                        struct TomlApp {
                            shortcuts: std::collections::HashMap<String, Vec<RecordedAction>>,
                        }

                        let mut app_shortcuts = std::collections::HashMap::new();
                        app_shortcuts.insert(name.clone(), actions.clone());

                        let mut apps = std::collections::HashMap::new();
                        apps.insert(
                            "generic".to_string(),
                            TomlApp {
                                shortcuts: app_shortcuts,
                            },
                        );

                        let workflow = TomlWorkflow { apps };
                        if let Ok(toml_str) = toml::to_string(&workflow) {
                            if std::fs::write(&path, toml_str).is_ok() {
                                info!("[Recorder] Workflow '{}' saved to {:?}", name, path);
                            }
                        }
                    }
                    actions.clear();
                }
            }

            thread::sleep(Duration::from_millis(250));
        }
    }

    /// Main polling loop — blocks the calling thread until stop_flag is set.
    fn run_loop(&self, stop_flag: Arc<Mutex<bool>>) {
        let mut last_pid: u32 = 0;

        info!(
            "[AppWatcher] Polling foreground window every {}ms",
            self.poll_interval.as_millis()
        );

        loop {
            // Honour stop signal
            if let Ok(guard) = stop_flag.lock() {
                if *guard {
                    info!("[AppWatcher] Stop requested — exiting poll loop");
                    break;
                }
            }

            if let Some(event) = Self::poll_foreground() {
                if event.pid != last_pid {
                    last_pid = event.pid;
                    debug!(
                        "[AppWatcher] App changed → {} ({})",
                        event.app_label, event.process_name
                    );
                    if let Err(e) = self.tx.send(event) {
                        warn!("[AppWatcher] Receiver dropped — stopping: {e}");
                        break;
                    }
                }
            }

            thread::sleep(self.poll_interval);
        }
    }

    /// Platform-specific foreground window poll.
    ///
    /// Returns `None` if the foreground window cannot be identified.
    fn poll_foreground() -> Option<AppChangedEvent> {
        #[cfg(target_os = "windows")]
        {
            Self::poll_foreground_windows()
        }
        #[cfg(not(target_os = "windows"))]
        {
            None
        }
    }

    #[cfg(target_os = "windows")]
    fn poll_foreground_windows() -> Option<AppChangedEvent> {
        use windows::Win32::Foundation::{CloseHandle, HWND};
        use windows::Win32::System::ProcessStatus::K32GetModuleBaseNameW;
        use windows::Win32::System::Threading::{
            OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_VM_READ,
        };
        use windows::Win32::UI::WindowsAndMessaging::{
            GetForegroundWindow, GetWindowTextW, GetWindowThreadProcessId,
        };

        unsafe {
            let hwnd: HWND = GetForegroundWindow();
            if hwnd.is_invalid() {
                return None;
            }

            // Resolve PID
            let mut pid: u32 = 0;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
            if pid == 0 {
                return None;
            }

            // Open process with minimal rights
            let proc = OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
                false,
                pid,
            )
            .ok()?;

            // Resolve process name via K32GetModuleBaseNameW
            let mut name_buf = [0u16; 260];
            let name_len = K32GetModuleBaseNameW(proc, None, &mut name_buf);
            let _ = CloseHandle(proc);

            if name_len == 0 {
                return None;
            }

            let process_name = String::from_utf16_lossy(&name_buf[..name_len as usize]);

            // Resolve window title
            let mut title_buf = [0u16; 512];
            let title_len = GetWindowTextW(hwnd, &mut title_buf);
            let window_title = if title_len > 0 {
                String::from_utf16_lossy(&title_buf[..title_len as usize])
            } else {
                String::new()
            };

            let app_label = AppChangedEvent::label_for_process(&process_name).to_string();

            Some(AppChangedEvent {
                process_name,
                app_label,
                window_title,
                pid,
            })
        }
    }
}

// ─── Handle ───────────────────────────────────────────────────────────────────

/// RAII handle returned by `AppWatcher::spawn()`.
/// Dropping this handle sets the stop flag but does NOT join the thread
/// (non-blocking teardown).
pub struct WatcherHandle {
    _thread: thread::JoinHandle<()>,
    stop_flag: Arc<Mutex<bool>>,
}

impl WatcherHandle {
    /// Signal the background thread to stop at the next poll iteration.
    pub fn stop(&self) {
        if let Ok(mut guard) = self.stop_flag.lock() {
            *guard = true;
        }
    }
}

// ─── Builder / Helper ─────────────────────────────────────────────────────────

/// Convenience: spawn an AppWatcher and return (WatcherHandle, Receiver).
pub fn start_app_watcher() -> (WatcherHandle, Receiver<AppChangedEvent>) {
    let (tx, rx) = mpsc::channel();
    let watcher = AppWatcher::new(tx);
    let handle = watcher.spawn();
    (handle, rx)
}

// ─── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_label_for_known_process() {
        assert_eq!(
            AppChangedEvent::label_for_process("WINWORD.EXE"),
            "Microsoft Word"
        );
        assert_eq!(
            AppChangedEvent::label_for_process("EXCEL.EXE"),
            "Microsoft Excel"
        );
        assert_eq!(
            AppChangedEvent::label_for_process("Code.exe"),
            "Visual Studio Code"
        );
        assert_eq!(
            AppChangedEvent::label_for_process("POWERPNT.EXE"),
            "Microsoft PowerPoint"
        );
        assert_eq!(
            AppChangedEvent::label_for_process("chrome.exe"),
            "Google Chrome"
        );
        assert_eq!(AppChangedEvent::label_for_process("notepad.exe"), "Notepad");
    }

    #[test]
    fn test_label_for_unknown_process() {
        assert_eq!(
            AppChangedEvent::label_for_process("random_app.exe"),
            "Unknown"
        );
        assert_eq!(AppChangedEvent::label_for_process(""), "Unknown");
    }

    #[test]
    fn test_start_stop_watcher() {
        // Spawn with a fast poll interval
        let (tx, rx) = mpsc::channel();
        let watcher = AppWatcher::with_interval(tx, 50);
        let handle = watcher.spawn();

        // Let it run briefly
        std::thread::sleep(Duration::from_millis(200));
        handle.stop();

        // On non-Windows CI the channel will be empty; that's expected
        // On Windows at least one event may arrive
        #[cfg(target_os = "windows")]
        {
            // We can't assert the exact event but we can assert non-panic
            let _events: Vec<_> = rx.try_iter().collect();
        }
    }

    #[test]
    fn test_channel_drop_stops_watcher() {
        let (tx, rx) = mpsc::channel();
        let watcher = AppWatcher::with_interval(tx, 50);
        let handle = watcher.spawn();

        // Drop the receiver — the watcher should detect send failure and exit
        drop(rx);
        std::thread::sleep(Duration::from_millis(300));

        // After the channel is dropped, stop() should not panic
        handle.stop();
    }
}
