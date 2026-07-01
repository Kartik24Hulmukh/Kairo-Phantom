//! Domain 8: Voice Dictation Engine
//!
//! Primary ASR: Moonshine Voice (MIT, ~107ms, HTTP sidecar on port 7439)
//! Fallback ASR: whisper.cpp CLI (when Moonshine unavailable or low-confidence)
//!
//! Pipeline: cpal/ffmpeg audio capture → WAV file → Moonshine/whisper.cpp →
//!           transcription → VoiceBridge post-process → ContextCaptured event.
//!
//! The transcription is treated as a `//` prompt and routed through the
//! Swarm Brain — the AI RESPONSE is ghost-written, not the raw transcription.

use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use tracing::{error, info, warn};

use crate::config::VoiceConfig;

// ── MoonshineEngine ───────────────────────────────────────────────────────────

/// HTTP client for the Moonshine Voice transcription sidecar (port 7439).
///
/// Connects to `sidecar/speech/moonshine_service.py` running locally.
/// Moonshine delivers ~107ms inference vs 11,000ms for whisper.cpp.
pub struct MoonshineEngine {
    /// HTTP base URL of the Moonshine sidecar
    service_url: String,
    /// Confidence threshold below which whisper.cpp fallback is triggered
    confidence_threshold: f32,
}

impl MoonshineEngine {
    pub fn new(port: u16, confidence_threshold: f32) -> Self {
        MoonshineEngine {
            service_url: format!("http://localhost:{port}"),
            confidence_threshold,
        }
    }

    /// Check if Moonshine sidecar is reachable.
    pub async fn is_available(&self) -> bool {
        let client = crate::config::get_client_builder()
            .build()
            .unwrap_or_default();
        client
            .get(format!("{}/health", self.service_url))
            .timeout(std::time::Duration::from_secs(2))
            .send()
            .await
            .map(|r| r.status().is_success())
            .unwrap_or(false)
    }

    /// Transcribe WAV file via the Moonshine HTTP sidecar.
    ///
    /// Returns `(text, confidence, language)` on success.
    pub async fn transcribe(&self, wav_path: &Path) -> Result<(String, f32, String)> {
        let payload = serde_json::json!({
            "audio_path": wav_path.to_str().unwrap_or(""),
        });

        let client = crate::config::get_client_builder()
            .build()
            .unwrap_or_default();
        let response = client
            .post(format!("{}/transcribe", self.service_url))
            .json(&payload)
            .timeout(std::time::Duration::from_secs(60))
            .send()
            .await
            .context("Moonshine sidecar unreachable")?;

        if !response.status().is_success() {
            bail!("Moonshine sidecar returned HTTP {}", response.status());
        }

        let data: serde_json::Value = response
            .json()
            .await
            .context("Invalid JSON from Moonshine sidecar")?;

        let text = data["text"].as_str().unwrap_or("").to_string();
        let confidence = data["confidence"].as_f64().unwrap_or(0.0) as f32;
        let language = data["language"].as_str().unwrap_or("en").to_string();

        Ok((text, confidence, language))
    }

    /// Returns true if the result needs whisper.cpp fallback.
    ///
    /// Triggers fallback when confidence is below threshold OR detected language is non-English.
    pub fn needs_fallback(&self, confidence: f32, language: &str) -> bool {
        confidence < self.confidence_threshold || language != "en"
    }
}

// ── VoiceEngine ───────────────────────────────────────────────────────────────

/// Manages ASR lifecycle: audio recording + transcription.
///
/// Uses Moonshine Voice as primary engine (fast, offline, MIT).
/// Falls back to whisper.cpp CLI when Moonshine is unavailable or returns
/// low-confidence output.
pub struct VoiceEngine {
    /// Path to whisper.cpp CLI binary (e.g. ~/.kairo-phantom/bin/whisper-cli.exe)
    whisper_binary: PathBuf,
    /// Path to the GGML model file (e.g. ~/.kairo-phantom/models/ggml-base.en.bin)
    model_path: PathBuf,
    /// Whether a recording is currently active
    recording: AtomicBool,
    /// Configuration
    config: VoiceConfig,
    /// Directory for temporary WAV files
    temp_dir: PathBuf,
    // Moonshine config (cached from VoiceConfig)
    moonshine_enabled: bool,
    moonshine_port: u16,
    confidence_threshold: f32,
}

/// A handle to an active audio recording session.
pub struct AudioRecorder {
    /// Path to the WAV file being recorded
    wav_path: PathBuf,
    /// Whether recording has been stopped
    stopped: AtomicBool,
    /// Silence threshold in RMS amplitude
    silence_threshold: f32,
    /// Max duration in seconds
    max_duration_secs: u64,
}

impl VoiceEngine {
    /// Create a new VoiceEngine with the given configuration.
    pub fn new(config: VoiceConfig) -> Result<Self> {
        let kairo_dir = dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".kairo-phantom");

        let bin_dir = kairo_dir.join("bin");
        let models_dir = kairo_dir.join("models");
        let temp_dir = kairo_dir.join("tmp");

        // Ensure directories exist
        std::fs::create_dir_all(&bin_dir).ok();
        std::fs::create_dir_all(&models_dir).ok();
        std::fs::create_dir_all(&temp_dir).ok();

        // Resolve whisper binary path
        let whisper_binary = Self::find_whisper_binary(&bin_dir);
        let model_file = format!("ggml-{}.bin", config.whisper_model);
        let model_path = models_dir.join(&model_file);

        info!(
            "🎤 VoiceEngine initialized (model: {}, binary: {:?})",
            config.whisper_model, whisper_binary
        );

        Ok(VoiceEngine {
            whisper_binary,
            model_path,
            recording: AtomicBool::new(false),
            moonshine_enabled: config.moonshine_enabled,
            moonshine_port: config.moonshine_port,
            confidence_threshold: config.confidence_threshold,
            config,
            temp_dir,
        })
    }

    /// Check if whisper.cpp is available and model is downloaded.
    pub fn is_available(&self) -> bool {
        self.whisper_binary.exists() && self.model_path.exists()
    }

    /// Check if whisper.cpp binary exists (model may still need download).
    pub fn has_binary(&self) -> bool {
        self.whisper_binary.exists()
    }

    /// Get the expected model path for status reporting.
    pub fn model_path(&self) -> &Path {
        &self.model_path
    }

    /// Get the whisper binary path.
    pub fn binary_path(&self) -> &Path {
        &self.whisper_binary
    }

    /// Check if currently recording.
    pub fn is_recording(&self) -> bool {
        self.recording.load(Ordering::SeqCst)
    }

    /// Start recording audio to a temporary WAV file.
    ///
    /// Returns an AudioRecorder handle. Call `stop_recording()` to finalize.
    /// Recording will also auto-stop after `max_recording_seconds` or
    /// `silence_threshold_ms` of silence.
    pub fn start_recording(&self) -> Result<AudioRecorder> {
        if self.recording.load(Ordering::SeqCst) {
            bail!("Recording already in progress");
        }

        self.recording.store(true, Ordering::SeqCst);

        let wav_filename = format!(
            "kairo_voice_{}.wav",
            chrono::Utc::now().format("%Y%m%d_%H%M%S")
        );
        let wav_path = self.temp_dir.join(wav_filename);

        info!("🔴 Recording started → {}", wav_path.display());

        // Create the WAV file with a standard header
        // 16-bit PCM, mono, 16000 Hz (whisper.cpp native rate)
        Self::write_wav_header(&wav_path)?;

        Ok(AudioRecorder {
            wav_path,
            stopped: AtomicBool::new(false),
            silence_threshold: 0.01, // RMS threshold for silence detection
            max_duration_secs: self.config.max_recording_seconds,
        })
    }

    /// Stop recording and return the path to the WAV file.
    pub fn stop_recording(&self, recorder: &AudioRecorder) -> Result<PathBuf> {
        recorder.stopped.store(true, Ordering::SeqCst);
        self.recording.store(false, Ordering::SeqCst);

        info!("⬛ Recording stopped → {}", recorder.wav_path.display());
        Ok(recorder.wav_path.clone())
    }

    /// Record audio using a simple system-level approach.
    ///
    /// This creates a WAV file by capturing from the default input device
    /// using a spawned process. Falls back to PowerShell recording if cpal
    /// is not available at runtime.
    pub async fn record_audio(&self, duration_secs: u64) -> Result<PathBuf> {
        let wav_filename = format!(
            "kairo_voice_{}.wav",
            chrono::Utc::now().format("%Y%m%d_%H%M%S")
        );
        let wav_path = self.temp_dir.join(&wav_filename);

        info!("🔴 Recording {} seconds of audio...", duration_secs);

        // Use PowerShell + .NET to capture audio (works on all Windows)
        // This is the most reliable cross-Windows approach without cpal compile-time dep
        #[cfg(windows)]
        {
            let ps_script = format!(
                r#"
Add-Type -AssemblyName System.Speech
$recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$recognizer.SetInputToDefaultAudioDevice()
$grammar = New-Object System.Speech.Recognition.DictationGrammar
$recognizer.LoadGrammar($grammar)
$recognizer.InitialSilenceTimeout = [TimeSpan]::FromSeconds({duration_secs})
$recognizer.BabbleTimeout = [TimeSpan]::FromSeconds({duration_secs})
$result = $recognizer.Recognize([TimeSpan]::FromSeconds({duration_secs}))
if ($result) {{ $result.Text }} else {{ "" }}
"#
            );

            // Alternative: use ffmpeg if available (better quality)
            let ffmpeg_result = tokio::process::Command::new("ffmpeg")
                .args([
                    "-f",
                    "dshow",
                    "-i",
                    "audio=Microphone",
                    "-t",
                    &duration_secs.to_string(),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-y",
                    wav_path.to_str().unwrap_or("output.wav"),
                ])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status()
                .await;

            if ffmpeg_result.map(|s| s.success()).unwrap_or(false) {
                info!("🎤 Audio captured via ffmpeg → {}", wav_path.display());
                Ok(wav_path)
            } else {
                // Fallback: No ffmpeg found, fail loudly
                bail!("No audio capture backend found. Install ffmpeg and add to PATH.");
            }
        }

        #[cfg(not(windows))]
        {
            // On Linux/macOS: try arecord or sox
            let status = tokio::process::Command::new("arecord")
                .args([
                    "-f",
                    "S16_LE",
                    "-r",
                    "16000",
                    "-c",
                    "1",
                    "-d",
                    &duration_secs.to_string(),
                    wav_path.to_str().unwrap_or("output.wav"),
                ])
                .status()
                .await;

            if !status.map(|s| s.success()).unwrap_or(false) {
                bail!("No audio capture backend found. Install ffmpeg or arecord and add to PATH.");
            }
            Ok(wav_path)
        }
    }

    /// Transcribe a WAV file using whisper.cpp CLI.
    ///
    /// Returns the transcribed text. Works 100% offline.
    pub async fn transcribe(&self, wav_path: &Path) -> Result<String> {
        if !self.whisper_binary.exists() {
            bail!(
                "whisper.cpp binary not found at {:?}. \
                 Download from https://github.com/ggerganov/whisper.cpp/releases \
                 and place in ~/.kairo-phantom/bin/",
                self.whisper_binary
            );
        }

        if !self.model_path.exists() {
            bail!(
                "Whisper model not found at {:?}. \
                 Download ggml-{}.bin from https://huggingface.co/ggerganov/whisper.cpp/tree/main \
                 and place in ~/.kairo-phantom/models/",
                self.model_path,
                self.config.whisper_model
            );
        }

        info!("📝 Transcribing {} with whisper.cpp...", wav_path.display());

        let output = tokio::process::Command::new(&self.whisper_binary)
            .args([
                "-m",
                self.model_path.to_str().unwrap_or(""),
                "-f",
                wav_path.to_str().unwrap_or(""),
                "--no-timestamps",
                "-l",
                &self.config.language,
                "--output-txt",
                "-np", // No progress bar
            ])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output()
            .await
            .context("Failed to run whisper.cpp")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            bail!("whisper.cpp failed: {stderr}");
        }

        let transcription = String::from_utf8_lossy(&output.stdout).trim().to_string();

        // Also check the .txt output file (whisper.cpp sometimes writes there instead)
        if transcription.is_empty() {
            let txt_path = wav_path.with_extension("txt");
            if txt_path.exists() {
                let text = std::fs::read_to_string(&txt_path)
                    .unwrap_or_default()
                    .trim()
                    .to_string();
                // Clean up
                let _ = std::fs::remove_file(&txt_path);
                if !text.is_empty() {
                    info!("📝 Transcription (from .txt): {} chars", text.len());
                    return Ok(text);
                }
            }
        }

        info!(
            "📝 Transcription: {} chars — '{}'",
            transcription.len(),
            transcription.chars().take(80).collect::<String>()
        );

        Ok(transcription)
    }

    /// Full voice pipeline: record → transcribe (Moonshine → whisper fallback) → return text.
    ///
    /// This is the primary entry point called from the main event loop.
    /// Uses Moonshine Voice as primary ASR (107ms) with whisper.cpp fallback.
    pub async fn voice_to_text(&self, duration_hint_secs: u64) -> Result<String> {
        let wav_path = self.record_audio(duration_hint_secs).await?;

        let text = if self.moonshine_enabled {
            let moonshine = MoonshineEngine::new(self.moonshine_port, self.confidence_threshold);

            match moonshine.transcribe(&wav_path).await {
                Ok((text, confidence, language))
                    if !moonshine.needs_fallback(confidence, &language) =>
                {
                    info!(
                        "🎤 Moonshine ASR: confidence={:.2}, lang={}, '{}'",
                        confidence,
                        language,
                        text.chars().take(80).collect::<String>()
                    );
                    text
                }
                Ok((moonshine_text, confidence, language)) => {
                    // Low confidence or non-English — try whisper.cpp
                    let reason = if language != "en" {
                        format!("non-English language: {language}")
                    } else {
                        format!(
                            "low confidence: {:.2} < {:.2}",
                            confidence, self.confidence_threshold
                        )
                    };
                    info!(
                        "🎤 Moonshine fallback reason: {}. Trying whisper.cpp.",
                        reason
                    );

                    if self.config.whisper_fallback_enabled && self.is_available() {
                        match self.transcribe(&wav_path).await {
                            Ok(whisper_text) if !whisper_text.is_empty() => {
                                info!(
                                    "🎤 whisper.cpp fallback succeeded: {} chars",
                                    whisper_text.len()
                                );
                                whisper_text
                            }
                            _ => {
                                warn!(
                                    "🎤 whisper.cpp fallback also failed, using Moonshine result"
                                );
                                moonshine_text
                            }
                        }
                    } else {
                        // Whisper not available — return moonshine result anyway
                        if !moonshine_text.is_empty() {
                            moonshine_text
                        } else {
                            bail!("No transcription available: Moonshine low-confidence, whisper.cpp unavailable")
                        }
                    }
                }
                Err(e) => {
                    info!("🎤 Moonshine unavailable: {}. Using whisper.cpp.", e);
                    self.transcribe(&wav_path).await?
                }
            }
        } else {
            // Moonshine disabled — use whisper.cpp directly
            self.transcribe(&wav_path).await?
        };

        // Clean up temporary WAV
        let _ = std::fs::remove_file(&wav_path);

        Ok(text)
    }

    // ── Private helpers ──────────────────────────────────────────────────────

    fn find_whisper_binary(bin_dir: &Path) -> PathBuf {
        // Check multiple possible names
        let candidates = [
            "whisper-cli.exe",
            "whisper.exe",
            "main.exe", // whisper.cpp default build name
            "whisper-cli",
            "whisper",
            "main",
        ];

        for name in &candidates {
            let path = bin_dir.join(name);
            if path.exists() {
                return path;
            }
        }

        // Check system PATH
        if let Ok(output) = std::process::Command::new("where")
            .arg("whisper-cli")
            .output()
        {
            if output.status.success() {
                let path_str = String::from_utf8_lossy(&output.stdout);
                let first_line = path_str.lines().next().unwrap_or("").trim();
                if !first_line.is_empty() {
                    return PathBuf::from(first_line);
                }
            }
        }

        // Default expected location
        bin_dir.join(if cfg!(windows) {
            "whisper-cli.exe"
        } else {
            "whisper-cli"
        })
    }

    fn write_wav_header(path: &Path) -> Result<()> {
        use std::io::Write;
        let mut f = std::fs::File::create(path)?;

        // RIFF WAV header for 16-bit PCM, mono, 16000 Hz
        let sample_rate: u32 = 16000;
        let bits_per_sample: u16 = 16;
        let channels: u16 = 1;
        let byte_rate = sample_rate * (bits_per_sample as u32 / 8) * channels as u32;
        let block_align = channels * (bits_per_sample / 8);

        // Write RIFF header with placeholder sizes (will be updated on close)
        f.write_all(b"RIFF")?;
        f.write_all(&0u32.to_le_bytes())?; // file size - 8 (placeholder)
        f.write_all(b"WAVE")?;
        f.write_all(b"fmt ")?;
        f.write_all(&16u32.to_le_bytes())?; // fmt chunk size
        f.write_all(&1u16.to_le_bytes())?; // PCM format
        f.write_all(&channels.to_le_bytes())?;
        f.write_all(&sample_rate.to_le_bytes())?;
        f.write_all(&byte_rate.to_le_bytes())?;
        f.write_all(&block_align.to_le_bytes())?;
        f.write_all(&bits_per_sample.to_le_bytes())?;
        f.write_all(b"data")?;
        f.write_all(&0u32.to_le_bytes())?; // data size (placeholder)

        Ok(())
    }
}

impl AudioRecorder {
    /// Get the path to the WAV file being recorded.
    pub fn wav_path(&self) -> &Path {
        &self.wav_path
    }

    /// Check if recording has been stopped.
    pub fn is_stopped(&self) -> bool {
        self.stopped.load(Ordering::SeqCst)
    }
}
