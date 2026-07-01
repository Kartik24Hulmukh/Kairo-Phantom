// phantom-core/src/governance/tool_gate.rs
//! Deterministic Tool Gate to prevent LLM bypass of security constraints.

use std::collections::HashSet;
use tracing::warn;

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

    pub fn add_allowed_path(&mut self, path: String) {
        self.allowed_paths.insert(path);
    }

    pub fn validate_file_access(&self, path: &str) -> bool {
        // Enforce: Never write to C:\Windows or /etc
        if path.to_lowercase().starts_with("c:\\windows") || path.starts_with("/etc") {
            warn!(
                "🚨 ToolGate: Blocked LLM attempt to access system directory: {}",
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
            warn!("🚨 ToolGate: Blocked access to unapproved path: {}", path);
            return false;
        }
        true
    }

    pub fn validate_token_usage(&self, tokens_requested: usize) -> bool {
        if tokens_requested > self.token_cap {
            warn!(
                "🚨 ToolGate: Token cap exceeded ({} > {})",
                tokens_requested, self.token_cap
            );
            return false;
        }
        true
    }

    pub fn authorize_tool_call(&self, tool_name: &str, agent_allowlist: &[&str]) -> bool {
        let allowed = agent_allowlist.contains(&tool_name);
        if !allowed {
            warn!(
                "🚨 ToolGate: Agent attempted to call unauthorized tool: {}",
                tool_name
            );
            return false;
        }
        true
    }
}
