//! Domain 8: Wake Word Detection
//!
//! Engine priority:
//!   1. horchd CLI subprocess (MIT/Apache-2.0, rustpotter-based, <1% CPU)
//!   2. openwakeword Python service (Apache 2.0, port 7440)
//!   3. whisper.cpp polling fallback (existing, higher CPU)
//!
//! When detected, sends PhantomEvent::VoicePressed to the event loop.

use anyhow::Result;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::sync::mpsc::Sender;
use tracing::{info, warn};

use crate::config::WakeWordConfig;
use crate::PhantomEvent;

/// Engine used for wake word detection.
#[derive(Debug, Clone, PartialEq)]
enum WakeEngine {
    /// horchd CLI subprocess (rustpotter-based, best quality)
    Horchd(PathBuf),
    /// openwakeword Python service (HTTP on port 7440)
    OpenWakeWord,
    /// whisper.cpp polling fallback
    WhisperPolling,
}

/// Wake word detection daemon.
///
/// Runs in the background, continuously listening for the configured
/// wake phrase. When detected, sends a VoicePressed event.
pub struct WakeWordDaemon {
    config: WakeWordConfig,
    active: Arc<AtomicBool>,
    /// Detected engine to use
    engine: WakeEngine,
}

impl WakeWordDaemon {
    /// Create a new WakeWordDaemon (does not start listening).
    pub fn new(config: WakeWordConfig) -> Self {
        let engine = Self::detect_engine();
        info!(
            "👂 WakeWordDaemon initialized (phrase: '{}', enabled: {}, engine: {:?})",
            config.phrase, config.enabled, engine
        );

        WakeWordDaemon {
            config,
            active: Arc::new(AtomicBool::new(false)),
            engine,
        }
    }

    /// Detect the best available wake word engine.
    fn detect_engine() -> WakeEngine {
        // 1. Check for horchd (rustpotter CLI wrapper)
        let horchd_candidates = [dirs::home_dir()
            .unwrap_or_default()
            .join(".kairo-phantom")
            .join("bin")
            .join(if cfg!(windows) {
                "horchd.exe"
            } else {
                "horchd"
            })];

        for candidate in &horchd_candidates {
            if candidate.exists() {
                info!("👂 Using horchd engine at {:?}", candidate);
                return WakeEngine::Horchd(candidate.clone());
            }
        }

        // Check PATH for horchd
        let which_cmd = if cfg!(windows) { "where" } else { "which" };
        if let Ok(out) = std::process::Command::new(which_cmd).arg("horchd").output() {
            if out.status.success() {
                let path_str = String::from_utf8_lossy(&out.stdout);
                if let Some(line) = path_str.lines().next() {
                    let p = PathBuf::from(line.trim());
                    if p.exists() {
                        info!("👂 Using horchd from PATH: {:?}", p);
                        return WakeEngine::Horchd(p);
                    }
                }
            }
        }

        // 2. Check for openwakeword Python service
        // Quick non-async check (synchronous port probe)
        if let Ok(stream) = std::net::TcpStream::connect_timeout(
            &"127.0.0.1:7440".parse().unwrap(),
            std::time::Duration::from_millis(200),
        ) {
            drop(stream);
            info!("👂 Using openwakeword service on port 7440");
            return WakeEngine::OpenWakeWord;
        }

        // 3. Fall back to whisper.cpp polling
        info!("👂 No neural wake word engine found — falling back to whisper.cpp polling");
        WakeEngine::WhisperPolling
    }

    /// Check if the daemon is enabled.
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    /// Check if the daemon is currently running.
    pub fn is_active(&self) -> bool {
        self.active.load(Ordering::SeqCst)
    }

    /// Start the wake word detection loop.
    ///
    /// Engine selection (in priority order):
    /// 1. horchd subprocess (rustpotter-based, <1% CPU)
    /// 2. openwakeword service (Python, port 7440)
    /// 3. whisper.cpp polling (existing, higher CPU)
    pub async fn start(&self, tx: Sender<PhantomEvent>) -> Result<()> {
        if !self.config.enabled {
            info!("👂 Wake word detection disabled in config");
            return Ok(());
        }

        let active = Arc::clone(&self.active);
        let phrase = self.config.phrase.to_lowercase();
        let sensitivity = self.config.sensitivity;
        let engine = self.engine.clone();

        active.store(true, Ordering::SeqCst);
        info!(
            "👂 Wake word detection started (engine: {:?}) — listening for '{}'",
            engine, phrase
        );

        let active_clone = active.clone();

        match engine {
            WakeEngine::Horchd(horchd_path) => {
                Self::start_horchd(horchd_path, phrase, sensitivity, active_clone, tx).await;
            }
            WakeEngine::OpenWakeWord => {
                Self::start_openwakeword_poll(phrase, active_clone, tx).await;
            }
            WakeEngine::WhisperPolling => {
                Self::start_whisper_polling(phrase, sensitivity, active_clone, tx).await;
            }
        }

        Ok(())
    }

    /// Start horchd subprocess and parse its stdout for detections.
    async fn start_horchd(
        horchd_path: PathBuf,
        phrase: String,
        sensitivity: f32,
        active: Arc<AtomicBool>,
        tx: Sender<PhantomEvent>,
    ) {
        tokio::spawn(async move {
            info!("👂 horchd subprocess starting...");

            // horchd CLI: listens and prints "wake_word_detected: <confidence>" lines
            let mut child = match tokio::process::Command::new(&horchd_path)
                .args([
                    "--sensitivity",
                    &format!("{sensitivity:.2}"),
                    "--phrase",
                    &phrase,
                ])
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::null())
                .spawn()
            {
                Ok(c) => c,
                Err(e) => {
                    warn!("👂 horchd failed to start: {}. Wake word disabled.", e);
                    return;
                }
            };

            use tokio::io::{AsyncBufReadExt, BufReader};
            let stdout = child.stdout.take().expect("horchd stdout missing");
            let mut lines = BufReader::new(stdout).lines();

            while active.load(Ordering::SeqCst) {
                match lines.next_line().await {
                    Ok(Some(line)) => {
                        let line_lower = line.to_lowercase();
                        if line_lower.contains("detected") || line_lower.contains(&phrase) {
                            info!("👂 horchd: wake word detected! line='{}'", line.trim());
                            let _ = tx.send(PhantomEvent::VoicePressed).await;
                            // Cool-down
                            tokio::time::sleep(std::time::Duration::from_secs(5)).await;
                        }
                    }
                    Ok(None) => break, // EOF
                    Err(e) => {
                        warn!("👂 horchd read error: {}", e);
                        break;
                    }
                }
            }

            let _ = child.kill().await;
            info!("👂 horchd subprocess stopped");
        });
    }

    /// Poll the openwakeword Python service (port 7440) for detection events.
    async fn start_openwakeword_poll(
        phrase: String,
        active: Arc<AtomicBool>,
        tx: Sender<PhantomEvent>,
    ) {
        tokio::spawn(async move {
            let client = crate::config::get_client_builder()
                .build()
                .unwrap_or_default();
            let mut interval = tokio::time::interval(std::time::Duration::from_millis(500));

            while active.load(Ordering::SeqCst) {
                interval.tick().await;

                match client
                    .get("http://localhost:7440/status")
                    .timeout(std::time::Duration::from_millis(400))
                    .send()
                    .await
                {
                    Ok(resp) if resp.status().is_success() => {
                        if let Ok(data) = resp.json::<serde_json::Value>().await {
                            let detected = data["detected"].as_bool().unwrap_or(false);
                            if detected {
                                let confidence = data["confidence"].as_f64().unwrap_or(0.0);
                                info!("👂 openwakeword: detected (confidence={:.2})", confidence);
                                let _ = tx.send(PhantomEvent::VoicePressed).await;
                                tokio::time::sleep(std::time::Duration::from_secs(5)).await;
                            }
                        }
                    }
                    _ => {} // Service not responding, keep polling
                }
            }

            info!("👂 openwakeword polling stopped");
        });
    }

    /// Whisper.cpp polling fallback (existing implementation).
    async fn start_whisper_polling(
        phrase: String,
        sensitivity: f32,
        active: Arc<AtomicBool>,
        tx: Sender<PhantomEvent>,
    ) {
        tokio::spawn(async move {
            let kairo_dir = dirs::home_dir()
                .unwrap_or_else(|| std::path::PathBuf::from("."))
                .join(".kairo-phantom");

            // Check if whisper.cpp is available
            let whisper_bin = kairo_dir.join("bin").join(if cfg!(windows) {
                "whisper-cli.exe"
            } else {
                "whisper-cli"
            });
            let model_path = kairo_dir.join("models").join("ggml-base.en.bin");

            if !whisper_bin.exists() || !model_path.exists() {
                warn!("👂 Wake word: whisper.cpp not available, daemon stopping");
                active.store(false, Ordering::SeqCst);
                return;
            }

            let temp_dir = kairo_dir.join("tmp");
            std::fs::create_dir_all(&temp_dir).ok();

            let mut interval = tokio::time::interval(std::time::Duration::from_secs(4));

            while active.load(Ordering::SeqCst) {
                interval.tick().await;

                // Record 3 seconds of audio
                let wav_path = temp_dir.join("wake_word_chunk.wav");

                // Quick record using ffmpeg (3 seconds)
                let record_result = tokio::process::Command::new("ffmpeg")
                    .args([
                        "-f",
                        "dshow",
                        "-i",
                        "audio=Microphone",
                        "-t",
                        "3",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        "-y",
                        wav_path.to_str().unwrap_or("wake.wav"),
                    ])
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .status()
                    .await;

                if !record_result.map(|s| s.success()).unwrap_or(false) {
                    continue; // Skip this cycle
                }

                // Transcribe the chunk
                let transcribe_result = tokio::process::Command::new(&whisper_bin)
                    .args([
                        "-m",
                        model_path.to_str().unwrap_or(""),
                        "-f",
                        wav_path.to_str().unwrap_or(""),
                        "--no-timestamps",
                        "-l",
                        "en",
                        "-np",
                    ])
                    .stdout(std::process::Stdio::piped())
                    .stderr(std::process::Stdio::null())
                    .output()
                    .await;

                if let Ok(output) = transcribe_result {
                    let text = String::from_utf8_lossy(&output.stdout).to_lowercase();

                    // Check for wake phrase with fuzzy matching
                    let detected = text.contains(&phrase)
                        || (sensitivity > 0.7 && Self::fuzzy_match(&text, &phrase));

                    if detected {
                        info!("👂 Wake word detected! Transcription: '{}'", text.trim());
                        let _ = tx.send(PhantomEvent::VoicePressed).await;

                        // Cool-down: wait 5 seconds before listening again
                        tokio::time::sleep(std::time::Duration::from_secs(5)).await;
                    }
                }

                // Cleanup temp file
                let _ = std::fs::remove_file(&wav_path);
            }

            info!("👂 Wake word detection stopped (whisper polling)");
        });
    }

    /// Stop the wake word detection loop.
    pub fn stop(&self) {
        self.active.store(false, Ordering::SeqCst);
        info!("👂 Wake word detection stopped");
    }

    /// Basic fuzzy matching: checks if the phrase words appear near each other.
    fn fuzzy_match(text: &str, phrase: &str) -> bool {
        let phrase_words: Vec<&str> = phrase.split_whitespace().collect();
        if phrase_words.is_empty() {
            return false;
        }

        // Check if all words of the phrase appear in the text
        phrase_words.iter().all(|word| text.contains(word))
    }
}
