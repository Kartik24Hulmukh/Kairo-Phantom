// phantom-core/src/interrupts.rs

use enigo::{Enigo, KeyboardControllable, Key};
use std::time::Duration;
use tokio::sync::watch;
use tokio::time::sleep;
use tokio_util::sync::CancellationToken;
use tauri::{AppHandle, Manager};
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InjectionState {
    Idle,
    Capturing,
    Streaming,
    Paused,
    Interrupted,
}

pub struct InterruptController {
    cancel_token: CancellationToken,
    state_tx: watch::Sender<InjectionState>,
    state_rx: watch::Receiver<InjectionState>,
}

impl InterruptController {
    pub fn new() -> Self {
        let (state_tx, state_rx) = watch::channel(InjectionState::Idle);
        Self {
            cancel_token: CancellationToken::new(),
            state_tx,
            state_rx,
        }
    }

    /// Triggers on ESC key. Immediately stops all injection loops.
    pub fn handle_esc(&self) {
        self.cancel_token.cancel();
        let _ = self.state_tx.send(InjectionState::Interrupted);
    }

    /// Triggers on CTRL+/
    pub fn handle_ctrl_slash(&self, app_handle: &AppHandle) {
        let _ = self.state_tx.send(InjectionState::Paused);
        
        // Open correction window
        if let Some(window) = app_handle.get_webview_window("correction") {
            window.show().unwrap();
            window.set_focus().unwrap();
        } else {
            tauri::WebviewWindowBuilder::new(
                app_handle,
                "correction",
                tauri::WebviewUrl::App("correction.html".into())
            )
            .title("Correction")
            .inner_size(400.0, 60.0)
            .decorations(false)
            .always_on_top(true)
            .center()
            .build()
            .unwrap();
        }
    }

    pub fn resume_streaming(&self) {
        let _ = self.state_tx.send(InjectionState::Streaming);
    }

    pub fn get_token(&self) -> CancellationToken {
        self.cancel_token.clone()
    }

    pub fn subscribe(&self) -> watch::Receiver<InjectionState> {
        self.state_rx.clone()
    }
}

/// Helper function to perform word-by-word accept mode (Shift+Enter)
pub async fn word_by_word_inject(
    words: Vec<String>, 
    mut cancel_token: CancellationToken,
    mut next_word_rx: tokio::sync::mpsc::Receiver<bool> // true = accept, false = delete
) {
    let mut enigo = Enigo::new();
    
    for word in words {
        if cancel_token.is_cancelled() {
            break;
        }
        
        enigo.key_sequence(&format!("{} ", word));
        
        // Wait 80ms gap or wait for explicit action
        tokio::select! {
            _ = sleep(Duration::from_millis(80)) => {
                // proceed automatically if no key intercepted
            }
            Some(action) = next_word_rx.recv() => {
                if !action {
                    // Backspace pressed: delete the word we just injected
                    for _ in 0..word.len() + 1 {
                        enigo.key_click(Key::Backspace);
                    }
                    continue; // Skip the delay
                }
            }
            _ = cancel_token.cancelled() => {
                break;
            }
        }
    }
}

#[tauri::command]
pub fn submit_correction(app: tauri::AppHandle, correction: String) {
    // In real usage: Appends correction to Context and resumes stream
    // Hide the correction window
    if let Some(window) = app.get_webview_window("correction") {
        window.hide().unwrap();
    }
    
    // We would trigger resume_streaming() here using state passed via Tauri
    println!("Received correction: {}", correction);
}
