pub mod security_auditor;
pub mod tool_gate;

// Enterprise Governance Layer — Phase 4 Production-Grade Feature
// Implements: audit logging, plugin permission manifest, session governance,
// enterprise SSO hooks, and admin-controlled model selection.
// This is what turns Kairo from "cool open-source tool" to "enterprise document AI infrastructure".

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;
use tracing::{info, warn};

// ─── Audit Log Entry ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    /// ISO 8601 timestamp
    pub timestamp: String,
    /// The event type
    pub event: AuditEvent,
    /// Session/user identifier (from SSO or local)
    pub user_id: String,
    /// Application where the action occurred
    pub app_name: String,
    /// Char count of text involved (not the text itself — privacy-first)
    pub char_count: usize,
    /// Which AI agent was used
    pub agent_id: String,
    /// Which model/backend was used
    pub model_used: String,
    /// Whether the user accepted, rejected, or cancelled
    pub outcome: AuditOutcome,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuditEvent {
    GhostSessionStarted,
    GhostSessionAccepted,
    GhostSessionRejected,
    GhostSessionCancelled,
    GhostSessionCompleted,
    GhostSessionBlocked,
    GhostSessionCorrected,
    ImageGenerated,
    McpToolCalled { tool_name: String },
    PluginLoaded { plugin_name: String },
    ConfigChanged,
    StartupCheck,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuditOutcome {
    Success,
    Rejected,
    Cancelled,
    Aborted,
    Blocked,
    Error { message: String },
    Pending,
}

// ─── Audit Logger ─────────────────────────────────────────────────────────────

pub struct AuditLogger {
    /// In-memory ring buffer (last 1000 entries)
    buffer: Mutex<VecDeque<AuditEntry>>,
    /// JSONL log file path
    log_path: Option<PathBuf>,
    /// Whether enterprise audit logging is enabled
    enabled: bool,
    /// Maximum buffer size
    max_buffer: usize,
}

impl AuditLogger {
    pub fn new(enabled: bool, log_path: Option<PathBuf>) -> Self {
        if enabled {
            if let Some(ref path) = log_path {
                if let Some(parent) = path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                info!("📋 Enterprise audit logging enabled → {}", path.display());
            } else {
                info!("📋 Enterprise audit logging enabled (in-memory only)");
            }
        }
        Self {
            buffer: Mutex::new(VecDeque::with_capacity(1000)),
            log_path,
            enabled,
            max_buffer: 1000,
        }
    }

    /// Default: disabled, logs to ~/.kairo-phantom/audit.jsonl if enabled
    pub fn from_env() -> Self {
        let enabled = std::env::var("KAIRO_AUDIT_LOG")
            .map(|v| v == "1" || v.to_lowercase() == "true")
            .unwrap_or(false);

        let log_path = if enabled {
            dirs::home_dir().map(|h| h.join(".kairo-phantom").join("audit.jsonl"))
        } else {
            None
        };

        Self::new(enabled, log_path)
    }

    pub fn log(&self, entry: AuditEntry) {
        if !self.enabled {
            return;
        }

        // Write to JSONL file
        if let Some(ref path) = self.log_path {
            if let Ok(mut file) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
            {
                let line = serde_json::to_string(&entry).unwrap_or_default();
                let _ = writeln!(file, "{line}");
            }
        }

        // Store in ring buffer
        let mut buf = self.buffer.lock().unwrap();
        if buf.len() >= self.max_buffer {
            buf.pop_front();
        }
        buf.push_back(entry);
    }

    /// Build an entry for a ghost session lifecycle event
    pub fn log_ghost_session(
        &self,
        event: AuditEvent,
        outcome: AuditOutcome,
        app_name: &str,
        agent_id: &str,
        model: &str,
        char_count: usize,
    ) {
        let entry = AuditEntry {
            timestamp: chrono_local_now(),
            event,
            user_id: whoami_user(),
            app_name: app_name.to_string(),
            char_count,
            agent_id: agent_id.to_string(),
            model_used: model.to_string(),
            outcome,
        };
        self.log(entry);
    }

    /// Get the last N audit entries
    pub fn recent_entries(&self, n: usize) -> Vec<AuditEntry> {
        let buf = self.buffer.lock().unwrap();
        buf.iter().rev().take(n).cloned().collect()
    }

    /// Get all entries as JSONL string
    pub fn export_jsonl(&self) -> String {
        let buf = self.buffer.lock().unwrap();
        buf.iter()
            .filter_map(|e| serde_json::to_string(e).ok())
            .collect::<Vec<_>>()
            .join("\n")
    }
}

// ─── Plugin Permission Manifest ───────────────────────────────────────────────

/// Declares what capabilities a plugin is allowed to use.
/// Prevents malicious plugins from accessing sensitive APIs.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginPermissionManifest {
    /// Plugin name
    pub name: String,
    /// Plugin version
    pub version: String,
    /// Author/publisher
    pub author: Option<String>,
    /// Declared permissions
    pub permissions: Vec<PluginPermission>,
    /// Whether admin approval is required before loading
    pub requires_approval: bool,
    /// Checksum of the plugin TOML for integrity verification
    pub checksum_sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum PluginPermission {
    /// Can read document text
    ReadDocument,
    /// Can inject text into applications
    WriteDocument,
    /// Can call external HTTP APIs
    NetworkAccess,
    /// Can read/write files on disk
    FileSystem,
    /// Can access clipboard
    Clipboard,
    /// Can spawn subprocesses
    ProcessSpawn,
    /// Can access image generation pipeline
    ImageGeneration,
    /// Can use the Figma bridge
    FigmaAccess,
    /// Can use the PPTX bridge
    PptxAccess,
}

impl PluginPermissionManifest {
    /// Check if a plugin has a specific permission
    pub fn has_permission(&self, perm: &PluginPermission) -> bool {
        self.permissions.contains(perm)
    }

    /// Validate that the manifest is safe (warn on high-risk permissions)
    pub fn validate(&self) {
        let high_risk = [
            PluginPermission::ProcessSpawn,
            PluginPermission::FileSystem,
            PluginPermission::NetworkAccess,
        ];
        for risk in &high_risk {
            if self.has_permission(risk) {
                warn!(
                    "⚠️  Plugin '{}' requests high-risk permission: {:?}",
                    self.name, risk
                );
            }
        }
        info!(
            "✅ Plugin '{}' v{} permissions validated ({} declared)",
            self.name,
            self.version,
            self.permissions.len()
        );
    }
}

// ─── Enterprise Config ────────────────────────────────────────────────────────

/// Enterprise governance configuration (read from config.toml [enterprise] section)
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EnterpriseConfig {
    /// Enable enterprise mode
    #[serde(default)]
    pub enabled: bool,
    /// Organization name (shown in UI)
    pub org_name: Option<String>,
    /// SSO provider URL (for future SSO integration)
    pub sso_provider_url: Option<String>,
    /// Audit logging enabled
    #[serde(default)]
    pub audit_logging: bool,
    /// Restrict to specific model(s) — prevents users from switching to unapproved models
    pub allowed_models: Option<Vec<String>>,
    /// Require admin approval for plugins with NetworkAccess or ProcessSpawn
    #[serde(default)]
    pub strict_plugin_governance: bool,
    /// Private plugin registry URL
    pub plugin_registry_url: Option<String>,
}

impl EnterpriseConfig {
    /// Check if a model is allowed under enterprise policy
    pub fn is_model_allowed(&self, model: &str) -> bool {
        match &self.allowed_models {
            None => true, // No restriction
            Some(allowed) => allowed.iter().any(|m| m == model),
        }
    }

    /// Summary for startup logging
    pub fn summary(&self) -> String {
        if !self.enabled {
            return "Enterprise mode: disabled".into();
        }
        format!(
            "Enterprise mode: ✅ | Org: {} | Audit: {} | Plugin governance: {}",
            self.org_name.as_deref().unwrap_or("N/A"),
            if self.audit_logging { "ON" } else { "OFF" },
            if self.strict_plugin_governance {
                "STRICT"
            } else {
                "permissive"
            },
        )
    }
}

// ─── Session Governance ───────────────────────────────────────────────────────

/// Tracks active ghost sessions for governance/rate-limiting.
pub struct SessionGovernor {
    /// Sessions started in the last window
    recent_starts: Mutex<VecDeque<std::time::Instant>>,
    /// Max sessions per minute (rate limit)
    max_per_minute: usize,
}

impl SessionGovernor {
    pub fn new(max_per_minute: usize) -> Self {
        Self {
            recent_starts: Mutex::new(VecDeque::new()),
            max_per_minute,
        }
    }

    /// Check if a new session can start (rate limiting).
    /// Returns true if allowed, false if rate limited.
    pub fn check_and_record(&self) -> bool {
        let now = std::time::Instant::now();
        let window = std::time::Duration::from_secs(60);

        let mut starts = self.recent_starts.lock().unwrap();
        // Remove entries older than 1 minute
        while let Some(front) = starts.front() {
            if now.duration_since(*front) > window {
                starts.pop_front();
            } else {
                break;
            }
        }

        if starts.len() >= self.max_per_minute {
            warn!(
                "🚫 Session rate limit reached ({}/min). Throttling.",
                self.max_per_minute
            );
            return false;
        }

        starts.push_back(now);
        true
    }
}

// ─── Utility ──────────────────────────────────────────────────────────────────

fn chrono_local_now() -> String {
    // Simple ISO 8601 timestamp using std — no chrono dependency
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    format!("{secs}Z") // Unix epoch as fallback — replace with chrono if needed
}

fn whoami_user() -> String {
    std::env::var("USERNAME")
        .or_else(|_| std::env::var("USER"))
        .unwrap_or_else(|_| "unknown".into())
}
// "?"?"? Deterministic Tool Gate (Gap 4: Governance) "?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?

use std::collections::HashSet;

pub struct ToolGate {
    allowed_paths: HashSet<String>,
    token_cap: usize,
}

impl Default for ToolGate {
    fn default() -> Self {
        Self::new()
    }
}

impl ToolGate {
    pub fn new() -> Self {
        let mut allowed = HashSet::new();
        allowed.insert(
            dirs::home_dir()
                .unwrap()
                .join(".kairo-phantom")
                .to_string_lossy()
                .to_string(),
        );

        Self {
            allowed_paths: allowed,
            token_cap: 5000,
        }
    }

    pub fn validate_file_access(&self, path: &str) -> bool {
        // Enforce: Never write to C:\Windows or /etc
        if path.to_lowercase().starts_with("c:\\windows") || path.starts_with("/etc") {
            tracing::warn!(
                "?? ToolGate: Blocked LLM attempt to access system directory: {}",
                path
            );
            return false;
        }

        // Must be in allowed paths
        let is_allowed = self
            .allowed_paths
            .iter()
            .any(|allowed| path.starts_with(allowed));
        if !is_allowed {
            tracing::warn!("?? ToolGate: Blocked access to unapproved path: {}", path);
        }
        is_allowed
    }

    pub fn validate_token_usage(&self, tokens_requested: usize) -> bool {
        if tokens_requested > self.token_cap {
            tracing::warn!(
                "?? ToolGate: Token cap exceeded ({} > {})",
                tokens_requested,
                self.token_cap
            );
            return false;
        }
        true
    }

    pub fn authorize_tool_call(&self, tool_name: &str, agent_allowlist: &[&str]) -> bool {
        let allowed = agent_allowlist.contains(&tool_name);
        if !allowed {
            tracing::warn!(
                "?? ToolGate: Agent attempted to call unauthorized tool: {}",
                tool_name
            );
        }
        allowed
    }
}
