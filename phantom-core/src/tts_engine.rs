//! Domain 8: Text-to-Speech Engine
//!
//! Engine priority:
//!   1. sherpa-onnx-offline-tts (Apache 2.0, ~63MB model, best quality)
//!   2. Windows SAPI via PowerShell (built-in)
//!   3. macOS say command
//!   4. Linux espeak-ng
//!
//! Used for: wake word acknowledgment, accessibility mode, reading responses.

use anyhow::{bail, Result};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use tracing::{info, warn};

use crate::config::TtsConfig;

/// Text-to-speech engine with sherpa-onnx as primary and SAPI/say/espeak fallbacks.
pub struct TtsEngine {
    config: TtsConfig,
    speaking: AtomicBool,
    /// Path to sherpa-onnx-offline-tts binary (None if not found)
    sherpa_bin: Option<PathBuf>,
    /// Path to sherpa-onnx model directory
    sherpa_model_dir: Option<PathBuf>,
}

impl TtsEngine {
    /// Create a new TtsEngine with the given configuration.
    pub fn new(config: TtsConfig) -> Self {
        let sherpa_bin = if config.sherpa_enabled {
            Self::find_sherpa_binary()
        } else {
            None
        };

        let sherpa_model_dir = sherpa_bin
            .as_ref()
            .and_then(|_| Self::find_sherpa_model(&config.sherpa_model));

        if let Some(ref bin) = sherpa_bin {
            info!("🔊 TtsEngine: sherpa-onnx found at {:?}", bin);
        } else {
            info!("🔊 TtsEngine: sherpa-onnx not found, using platform TTS fallback");
        }

        info!(
            "🔊 TtsEngine initialized (enabled: {}, sherpa: {})",
            config.enabled,
            sherpa_bin.is_some()
        );

        TtsEngine {
            config,
            speaking: AtomicBool::new(false),
            sherpa_bin,
            sherpa_model_dir,
        }
    }

    /// Check if sherpa-onnx is available with a loaded model.
    pub fn is_sherpa_available(&self) -> bool {
        self.config.sherpa_enabled
            && self
                .sherpa_bin
                .as_ref()
                .map(|p| p.exists())
                .unwrap_or(false)
            && self
                .sherpa_model_dir
                .as_ref()
                .map(|d| d.exists())
                .unwrap_or(false)
    }

    /// Check if TTS is enabled and available on this platform.
    pub fn is_available(&self) -> bool {
        self.config.enabled
            && (self.is_sherpa_available()
                || cfg!(windows)
                || cfg!(target_os = "macos")
                || cfg!(unix))
    }

    /// Check if currently speaking.
    pub fn is_speaking(&self) -> bool {
        self.speaking.load(Ordering::SeqCst)
    }

    /// Speak text aloud using the system TTS engine.
    ///
    /// On Windows: Uses SAPI via PowerShell (most reliable cross-version approach).
    /// On other platforms: Uses `say` (macOS) or `espeak` (Linux).
    pub async fn speak(&self, text: &str) -> Result<()> {
        if !self.config.enabled {
            return Ok(());
        }

        if text.trim().is_empty() {
            return Ok(());
        }

        self.speaking.store(true, Ordering::SeqCst);
        info!(
            "🔊 Speaking: '{}'",
            text.chars().take(60).collect::<String>()
        );

        let result = self.platform_speak(text).await;

        self.speaking.store(false, Ordering::SeqCst);
        result
    }

    /// Speak a short acknowledgment (e.g., "I'm listening" after wake word).
    pub async fn acknowledge(&self, message: &str) -> Result<()> {
        self.speak(message).await
    }

    /// Stop any ongoing speech.
    pub fn stop(&self) {
        self.speaking.store(false, Ordering::SeqCst);
        // Kill any running TTS process
        #[cfg(windows)]
        {
            let _ = std::process::Command::new("taskkill")
                .args(["/F", "/IM", "powershell.exe"])
                .output();
        }
    }

    // ── Private helpers ──────────────────────────────────────────────────────────────

    fn find_sherpa_binary() -> Option<PathBuf> {
        use std::process::Command;

        let exe_name = if cfg!(windows) {
            "sherpa-onnx-offline-tts.exe"
        } else {
            "sherpa-onnx-offline-tts"
        };

        // Check ~/.kairo-phantom/bin/
        if let Some(home) = dirs::home_dir() {
            let kairo_bin = home.join(".kairo-phantom").join("bin").join(exe_name);
            if kairo_bin.exists() {
                return Some(kairo_bin);
            }
        }

        // Check system PATH
        let cmd = if cfg!(windows) { "where" } else { "which" };
        if let Ok(out) = Command::new(cmd).arg("sherpa-onnx-offline-tts").output() {
            if out.status.success() {
                let s = String::from_utf8_lossy(&out.stdout);
                if let Some(line) = s.lines().next() {
                    let p = PathBuf::from(line.trim());
                    if p.exists() {
                        return Some(p);
                    }
                }
            }
        }

        None
    }

    fn find_sherpa_model(model_name: &str) -> Option<PathBuf> {
        let model_dir = dirs::home_dir()?
            .join(".kairo-phantom")
            .join("models")
            .join(model_name);

        if model_dir.join("model.onnx").exists() {
            Some(model_dir)
        } else {
            None
        }
    }

    async fn speak_via_sherpa(&self, text: &str) -> Result<()> {
        let sherpa_bin = self
            .sherpa_bin
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("sherpa-onnx not found"))?;
        let model_dir = self
            .sherpa_model_dir
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("sherpa-onnx model not found"))?;

        let tmp_wav = std::env::temp_dir().join("kairo_tts_output.wav");

        let status = tokio::process::Command::new(sherpa_bin)
            .args([
                &format!("--vits-model={}", model_dir.join("model.onnx").display()),
                &format!("--vits-lexicon={}", model_dir.join("lexicon.txt").display()),
                &format!("--vits-tokens={}", model_dir.join("tokens.txt").display()),
                &format!("--output-filename={}", tmp_wav.display()),
                &format!("--text={text}"),
            ])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .await?;

        if !status.success() {
            bail!("sherpa-onnx-offline-tts failed");
        }

        // Play the generated WAV
        self.play_wav(&tmp_wav).await?;
        let _ = std::fs::remove_file(&tmp_wav);
        Ok(())
    }

    async fn play_wav(&self, wav_path: &Path) -> Result<()> {
        #[cfg(windows)]
        {
            let path_str = wav_path.to_str().unwrap_or("").replace('\\', "/");
            let ps_cmd = format!("(New-Object Media.SoundPlayer '{path_str}').PlaySync()");
            let _ = tokio::process::Command::new("powershell")
                .args(["-NoProfile", "-Command", &ps_cmd])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status()
                .await;
            return Ok(());
        }
        #[cfg(target_os = "macos")]
        {
            let _ = tokio::process::Command::new("afplay")
                .arg(wav_path)
                .status()
                .await;
            return Ok(());
        }
        #[cfg(all(not(windows), not(target_os = "macos")))]
        {
            for player in &["aplay", "paplay"] {
                if tokio::process::Command::new(player)
                    .arg(wav_path)
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .status()
                    .await
                    .map(|s| s.success())
                    .unwrap_or(false)
                {
                    return Ok(());
                }
            }
        }
        #[allow(unreachable_code)]
        Ok(())
    }

    // ── Platform-specific implementations ─────────────────────────────────────

    #[cfg(windows)]
    async fn platform_speak(&self, text: &str) -> Result<()> {
        // Try sherpa-onnx first (best quality)
        if self.is_sherpa_available() {
            match self.speak_via_sherpa(text).await {
                Ok(()) => return Ok(()),
                Err(e) => warn!("⚠️ sherpa-onnx failed: {}. Falling back to SAPI.", e),
            }
        }

        // SAPI fallback
        self.speak_via_sapi(text).await
    }

    #[cfg(windows)]
    async fn speak_via_sapi(&self, text: &str) -> Result<()> {
        // Escape single quotes for PowerShell
        let escaped = text.replace('\'', "''");

        // Use SAPI via PowerShell — works on all Windows versions
        let ps_command = format!(
            "Add-Type -AssemblyName System.Speech; \
             $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; \
             $synth.SelectVoice('{}'); \
             $synth.Speak('{}')",
            self.config.voice_model, escaped
        );

        let status = tokio::process::Command::new("powershell")
            .args(["-NoProfile", "-Command", &ps_command])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .await;

        match status {
            Ok(s) if s.success() => Ok(()),
            _ => {
                // Fallback: try without voice selection
                warn!(
                    "⚠️ SAPI voice '{}' not found, using default",
                    self.config.voice_model
                );
                let fallback_cmd = format!(
                    "Add-Type -AssemblyName System.Speech; \
                     $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; \
                     $synth.Speak('{escaped}')"
                );
                let _ = tokio::process::Command::new("powershell")
                    .args(["-NoProfile", "-Command", &fallback_cmd])
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .status()
                    .await;
                Ok(())
            }
        }
    }

    #[cfg(target_os = "macos")]
    async fn platform_speak(&self, text: &str) -> Result<()> {
        let _ = tokio::process::Command::new("say").arg(text).status().await;
        Ok(())
    }

    #[cfg(all(not(windows), not(target_os = "macos")))]
    async fn platform_speak(&self, text: &str) -> Result<()> {
        let _ = tokio::process::Command::new("espeak")
            .arg(text)
            .status()
            .await;
        Ok(())
    }
}
