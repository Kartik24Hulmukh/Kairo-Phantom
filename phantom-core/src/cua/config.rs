//! # CUA Configuration
//!
//! CuaConfig is loaded from ~/.kairo-phantom/config.toml under [cua] section.
//! CUA is DISABLED by default — user must explicitly enable it.

use serde::{Deserialize, Serialize};

/// Configuration for the CUA module.
/// Loaded from the [cua] section of ~/.kairo-phantom/config.toml.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CuaConfig {
    /// Whether CUA is enabled at all. MUST be false by default.
    /// User must explicitly set to true in config.toml.
    #[serde(default)]
    pub enabled: bool,

    /// Maximum CUA actions per minute (hard cap, cannot exceed RATE_LIMIT_HARD_MAX)
    #[serde(default = "default_rate_limit")]
    pub rate_limit_per_minute: u32,

    /// Preferred backend: "enigo" (default) or "cua-driver"
    #[serde(default = "default_backend")]
    pub preferred_backend: String,

    /// Enable farscry verification after each action
    #[serde(default = "default_true")]
    pub verify_with_farscry: bool,

    /// Enable audit logging to ~/.kairo-phantom/audit.log
    #[serde(default = "default_true")]
    pub audit_logging: bool,

    /// Additional window titles to block (merged with hard-coded list)
    #[serde(default)]
    pub additional_blocked_windows: Vec<String>,

    /// DPI override (if 0.0, auto-detected via GetDpiForWindow)
    #[serde(default)]
    pub dpi_override: f32,
}

/// Hard maximum rate limit — cannot be exceeded even if config says higher
const RATE_LIMIT_HARD_MAX: u32 = 30;

fn default_rate_limit() -> u32 {
    10
}

fn default_backend() -> String {
    "enigo".to_string()
}

fn default_true() -> bool {
    true
}

impl Default for CuaConfig {
    fn default() -> Self {
        Self {
            enabled: false, // DISABLED by default
            rate_limit_per_minute: 10,
            preferred_backend: "enigo".to_string(),
            verify_with_farscry: true,
            audit_logging: true,
            additional_blocked_windows: Vec::new(),
            dpi_override: 0.0,
        }
    }
}

impl CuaConfig {
    /// Get the effective rate limit (capped at RATE_LIMIT_HARD_MAX)
    pub fn effective_rate_limit(&self) -> u32 {
        self.rate_limit_per_minute.min(RATE_LIMIT_HARD_MAX)
    }

    /// Load CuaConfig from config.toml (returns default if not found)
    pub fn load() -> Self {
        let config_path = dirs::home_dir()
            .map(|h| h.join(".kairo-phantom").join("config.toml"))
            .unwrap_or_default();

        let mut config = if !config_path.exists() {
            Self::default()
        } else {
            match std::fs::read_to_string(&config_path) {
                Ok(content) => {
                    #[derive(Deserialize)]
                    struct FullConfig {
                        #[serde(default)]
                        cua: CuaConfig,
                    }
                    match toml::from_str::<FullConfig>(&content) {
                        Ok(cfg) => {
                            let mut cua = cfg.cua;
                            // Enforce hard maximum
                            if cua.rate_limit_per_minute > RATE_LIMIT_HARD_MAX {
                                tracing::warn!(
                                    "[CUA] rate_limit_per_minute {} exceeds hard max {}, capping",
                                    cua.rate_limit_per_minute,
                                    RATE_LIMIT_HARD_MAX
                                );
                                cua.rate_limit_per_minute = RATE_LIMIT_HARD_MAX;
                            }
                            cua
                        }
                        Err(e) => {
                            tracing::warn!(
                                "[CUA] Failed to parse config.toml: {} — using defaults",
                                e
                            );
                            Self::default()
                        }
                    }
                }
                Err(_) => Self::default(),
            }
        };

        if std::env::var("KAIRO_MOCK_ENIGO").is_ok() {
            config.enabled = true;
        }
        config
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config_is_disabled() {
        let config = CuaConfig::default();
        assert!(!config.enabled, "CUA must be disabled by default");
    }

    #[test]
    fn test_rate_limit_capped_at_hard_max() {
        let mut config = CuaConfig::default();
        config.rate_limit_per_minute = 100; // Try to exceed hard max
        assert_eq!(config.effective_rate_limit(), 30);
    }

    #[test]
    fn test_rate_limit_normal() {
        let mut config = CuaConfig::default();
        config.rate_limit_per_minute = 10;
        assert_eq!(config.effective_rate_limit(), 10);
    }
}
