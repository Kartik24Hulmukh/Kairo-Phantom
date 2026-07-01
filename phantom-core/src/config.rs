/// Config — loads ~/.kairo-phantom/config.toml
/// Falls back to sensible defaults (Ollama local).
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PhantomConfig {
    /// Hotkey combination to trigger materialization
    #[serde(default = "default_hotkey")]
    pub hotkey: String,

    /// Milliseconds between each typed character (15 = realistic human speed)
    #[serde(default = "default_typing_delay")]
    pub typing_delay_ms: u64,

    /// Legacy single model config (used as fallback if swarm is not configured)
    #[serde(default)]
    pub model: ModelConfig,

    /// Optional cloud fallback when Ollama is unavailable
    #[serde(default)]
    pub fallback: Option<ModelConfig>,

    /// The Multi-Agent Swarm Configuration
    #[serde(default)]
    pub swarm: SwarmConfig,

    /// List of paths to plugin TOML files
    #[serde(default)]
    pub plugins: Vec<String>,

    /// Voice dictation configuration (Domain 8: Multimodal Input)
    #[serde(default)]
    pub voice: VoiceConfig,

    /// Text-to-speech configuration (Domain 8: Multimodal Input)
    #[serde(default)]
    pub tts: TtsConfig,

    /// Wake word detection configuration (Domain 8: Multimodal Input)
    #[serde(default)]
    pub wake_word: WakeWordConfig,

    /// Screen context capture configuration (Domain 8: Multimodal Input)
    #[serde(default)]
    pub screen_context: ScreenContextConfig,

    /// Domain 9: Enterprise Governance & Compliance
    #[serde(default)]
    pub enterprise: EnterpriseConfig,

    /// List of folders to index for Document Graph Memory
    #[serde(default = "default_document_graph_folders")]
    pub document_graph_folders: Vec<String>,

    /// Relevance floor for calibration
    #[serde(default = "default_relevance_floor")]
    pub relevance_floor: f32,

    /// Clarity threshold for calibration
    #[serde(default = "default_clarity_threshold")]
    pub clarity_threshold: f32,
}

/// Domain 9 — Enterprise Governance & Compliance configuration.
/// All sub-sections default to disabled/empty (zero breaking change).
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct EnterpriseConfig {
    /// SSO & Identity (Logto/OIDC JWT validation)
    #[serde(default)]
    pub sso: SsoConfigSection,
    /// SPIFFE agent identity
    #[serde(default)]
    pub spiffe: SpiffeConfigSection,
    /// Audit log settings
    #[serde(default)]
    pub audit: AuditConfig,
    /// Compliance scanning settings
    #[serde(default)]
    pub compliance: ComplianceConfig,
    /// Enable RBAC for Waza agents
    #[serde(default)]
    pub rbac_enabled: bool,
}

/// SSO configuration section (mirrors enterprise::sso::SsoConfig)
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct SsoConfigSection {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub discovery_url: String,
    #[serde(default)]
    pub client_id: String,
    #[serde(default)]
    pub issuer: String,
    #[serde(default)]
    pub audience: String,
    #[serde(default)]
    pub jwt_secret: String,
    #[serde(default = "default_idle_timeout")]
    pub idle_timeout_secs: u64,
}

fn default_idle_timeout() -> u64 {
    3600
}

/// SPIFFE configuration section (mirrors enterprise::spiffe_identity::SpiffeConfig)
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SpiffeConfigSection {
    #[serde(default = "spiffe_enabled_default")]
    pub enabled: bool,
    #[serde(default = "default_trust_domain")]
    pub trust_domain: String,
    #[serde(default = "default_agent_name")]
    pub agent_name: String,
    #[serde(default)]
    pub agent_socket_path: Option<String>,
}

impl Default for SpiffeConfigSection {
    fn default() -> Self {
        Self {
            enabled: spiffe_enabled_default(),
            trust_domain: default_trust_domain(),
            agent_name: default_agent_name(),
            agent_socket_path: None,
        }
    }
}

fn spiffe_enabled_default() -> bool {
    true
}
fn default_trust_domain() -> String {
    "kairo-phantom.io".to_string()
}
fn default_agent_name() -> String {
    "ghost-writer".to_string()
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct AuditConfig {
    /// Path to audit DB (defaults to ~/.kairo-phantom/kairo_audit.db)
    #[serde(default)]
    pub db_path: Option<String>,
    /// HMAC key for hourly chain sealing (base64-encoded 32 bytes)
    #[serde(default)]
    pub hmac_key_b64: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct ComplianceConfig {
    /// Enable pre-injection compliance scanning
    #[serde(default = "compliance_enabled_default")]
    pub enabled: bool,
    /// Block on error-level violations (vs just warning)
    #[serde(default = "block_on_error_default")]
    pub block_on_error: bool,
}

fn compliance_enabled_default() -> bool {
    true
}
fn block_on_error_default() -> bool {
    true
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct SwarmConfig {
    /// Enables the multi-agent LLM routing pipeline.
    #[serde(default)]
    pub enabled: bool,

    /// The Brain: analyzes the context and delegates.
    pub brain: Option<ModelConfig>,

    /// Content & Prose Specialist
    pub content_agent: Option<ModelConfig>,

    /// Reasoning & Code Specialist
    pub reasoning_agent: Option<ModelConfig>,

    /// Design & Layout Specialist
    pub design_agent: Option<ModelConfig>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ModelConfig {
    /// AI provider: "ollama" | "openai" | "anthropic" | "gemini"
    #[serde(default = "default_provider")]
    pub provider: String,

    /// Model name (e.g. "llama3", "gpt-4o-mini", "claude-3-haiku-20240307")
    pub model_name: Option<String>,

    /// API key (not needed for Ollama)
    pub api_key: Option<String>,

    /// Base URL override (for Ollama or self-hosted)
    pub base_url: Option<String>,
}

impl Default for ModelConfig {
    fn default() -> Self {
        ModelConfig {
            provider: default_provider(),
            model_name: Some("qwen2.5-coder:14b".into()),
            api_key: None,
            base_url: Some("http://localhost:11434".into()),
        }
    }
}

fn default_hotkey() -> String {
    "ctrl+space".into()
}
fn default_typing_delay() -> u64 {
    15
}
fn default_provider() -> String {
    "ollama".into()
}

// ── Domain 8: Multimodal Input Configuration ─────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct VoiceConfig {
    /// Enable voice dictation (Alt+V hotkey)
    #[serde(default = "default_true")]
    pub enabled: bool,
    /// Whisper.cpp model name (downloaded to ~/.kairo-phantom/models/)
    #[serde(default = "default_whisper_model")]
    pub whisper_model: String,
    /// Language code for transcription
    #[serde(default = "default_voice_lang")]
    pub language: String,
    /// Milliseconds of silence before auto-stopping recording
    #[serde(default = "default_silence_threshold")]
    pub silence_threshold_ms: u64,
    /// Maximum recording duration in seconds
    #[serde(default = "default_max_recording")]
    pub max_recording_seconds: u64,

    // ── Moonshine Voice (primary ASR engine) ──────────────────────────────
    /// Use Moonshine Voice as primary ASR engine (MIT license, 107ms inference)
    #[serde(default = "default_true")]
    pub moonshine_enabled: bool,
    /// Port of the Moonshine HTTP sidecar service
    #[serde(default = "default_moonshine_port")]
    pub moonshine_port: u16,
    /// Moonshine model: "moonshine/moonshine-base" (26MB) or "moonshine/moonshine-medium" (245MB)
    #[serde(default = "default_moonshine_model")]
    pub moonshine_model: String,
    /// Minimum Moonshine confidence score (0.0–1.0) below which whisper.cpp fallback is used
    #[serde(default = "default_confidence_threshold")]
    pub confidence_threshold: f32,
    /// Use whisper.cpp as fallback when Moonshine fails or returns low confidence
    #[serde(default = "default_true")]
    pub whisper_fallback_enabled: bool,
}

impl Default for VoiceConfig {
    fn default() -> Self {
        VoiceConfig {
            enabled: true,
            whisper_model: default_whisper_model(),
            language: default_voice_lang(),
            silence_threshold_ms: default_silence_threshold(),
            max_recording_seconds: default_max_recording(),
            moonshine_enabled: true,
            moonshine_port: default_moonshine_port(),
            moonshine_model: default_moonshine_model(),
            confidence_threshold: default_confidence_threshold(),
            whisper_fallback_enabled: true,
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TtsConfig {
    /// Enable text-to-speech (disabled by default)
    #[serde(default)]
    pub enabled: bool,
    /// Voice model/name for TTS engine
    #[serde(default = "default_tts_voice")]
    pub voice_model: String,
    /// Whether to automatically speak AI responses aloud
    #[serde(default)]
    pub speak_responses: bool,

    // ── sherpa-onnx TTS ───────────────────────────────────────────────────
    /// Use sherpa-onnx-offline-tts as primary TTS (Apache 2.0, requires model download)
    #[serde(default = "default_true")]
    pub sherpa_enabled: bool,
    /// sherpa-onnx VITS voice model (en_US-amy-medium = ~63MB)
    #[serde(default = "default_sherpa_model")]
    pub sherpa_model: String,
}

impl Default for TtsConfig {
    fn default() -> Self {
        TtsConfig {
            enabled: false,
            voice_model: default_tts_voice(),
            speak_responses: false,
            sherpa_enabled: true,
            sherpa_model: default_sherpa_model(),
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct WakeWordConfig {
    /// Enable wake word detection (disabled by default)
    #[serde(default)]
    pub enabled: bool,
    /// Wake word phrase
    #[serde(default = "default_wake_phrase")]
    pub phrase: String,
    /// Detection sensitivity (0.0 = low, 1.0 = high)
    #[serde(default = "default_sensitivity")]
    pub sensitivity: f32,
}

impl Default for WakeWordConfig {
    fn default() -> Self {
        WakeWordConfig {
            enabled: false,
            phrase: default_wake_phrase(),
            sensitivity: default_sensitivity(),
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ScreenContextConfig {
    /// Enable screen context capture (Alt+Shift+M hotkey)
    #[serde(default = "default_true")]
    pub enabled: bool,
    /// Path to farscry binary (auto-detected from PATH if None)
    #[serde(default)]
    pub farscry_path: Option<String>,
}

impl Default for ScreenContextConfig {
    fn default() -> Self {
        ScreenContextConfig {
            enabled: true,
            farscry_path: None,
        }
    }
}

fn default_true() -> bool {
    true
}
fn default_whisper_model() -> String {
    "base.en".into()
}
fn default_voice_lang() -> String {
    "en".into()
}
fn default_silence_threshold() -> u64 {
    1500
}
fn default_max_recording() -> u64 {
    120
}
fn default_tts_voice() -> String {
    "Microsoft David".into()
}
fn default_wake_phrase() -> String {
    "hey kairo".into()
}
fn default_sensitivity() -> f32 {
    0.5
}
fn default_moonshine_port() -> u16 {
    7439
}
fn default_moonshine_model() -> String {
    "moonshine/moonshine-base".into()
}
fn default_confidence_threshold() -> f32 {
    0.6
}
fn default_sherpa_model() -> String {
    "en_US-amy-medium".into()
}

fn default_document_graph_folders() -> Vec<String> {
    vec![dirs::home_dir()
        .unwrap_or_default()
        .join("Documents")
        .join("Kairo")
        .to_string_lossy()
        .to_string()]
}

fn default_relevance_floor() -> f32 {
    0.05
}
fn default_clarity_threshold() -> f32 {
    0.4
}

impl Default for PhantomConfig {
    fn default() -> Self {
        PhantomConfig {
            hotkey: default_hotkey(),
            typing_delay_ms: default_typing_delay(),
            model: ModelConfig::default(),
            fallback: None,
            swarm: SwarmConfig::default(),
            plugins: Vec::new(),
            voice: VoiceConfig::default(),
            tts: TtsConfig::default(),
            wake_word: WakeWordConfig::default(),
            screen_context: ScreenContextConfig::default(),
            enterprise: EnterpriseConfig::default(),
            document_graph_folders: default_document_graph_folders(),
            relevance_floor: default_relevance_floor(),
            clarity_threshold: default_clarity_threshold(),
        }
    }
}

impl PhantomConfig {
    /// Load config from ~/.kairo-phantom/config.toml or return defaults
    pub fn load_or_default() -> Result<Self> {
        let config_path = Self::config_path();

        if config_path.exists() {
            let content = std::fs::read_to_string(&config_path)?;
            let config: PhantomConfig = toml::from_str(&content)?;
            Ok(config)
        } else {
            // First run — create default config file
            let config = PhantomConfig::default();
            if let Some(parent) = config_path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let toml_str = toml::to_string_pretty(&config)?;
            std::fs::write(&config_path, &toml_str)?;
            tracing::info!("Created default config at: {}", config_path.display());
            Ok(config)
        }
    }

    pub fn config_path() -> PathBuf {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".kairo-phantom")
            .join("config.toml")
    }
}

/// Helper to get a configured reqwest ClientBuilder.
/// If KAIRO_OFFLINE=1 env var is active, all non-local HTTP egress is routed to a dummy proxy.
pub fn get_client_builder() -> reqwest::ClientBuilder {
    let mut builder = reqwest::Client::builder();
    if std::env::var("KAIRO_OFFLINE").unwrap_or_default() == "1" {
        if let Ok(proxy) = reqwest::Proxy::all("http://127.0.0.1:9999") {
            builder = builder
                .proxy(proxy.no_proxy(reqwest::NoProxy::from_string("localhost,127.0.0.1,::1")));
        }
    }
    builder
}
