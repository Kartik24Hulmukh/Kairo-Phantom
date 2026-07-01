/// Plugin System for Kairo Phantom.
/// Allows community to add specialized app fingerprinters and AI agents.
use crate::context::AppEnvironment;
use crate::document_context::DocumentContext;
use serde::Deserialize;
use std::sync::Arc;

/// Trait for identifying the application environment.
pub trait AppFingerprinter: Send + Sync {
    /// Returns an AppEnvironment if the process/title matches this fingerprinter.
    fn fingerprint(&self, process_name: &str, window_title: &str) -> Option<AppEnvironment>;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum DomainCapability {
    Real,
    PromptOnly,
}

/// Trait for a specialized AI agent in the swarm.
pub trait SwarmAgent: Send + Sync {
    /// The unique identifier for this agent.
    fn id(&self) -> &str;

    /// The human-readable name of the agent.
    fn name(&self) -> &str;

    /// Returns the system prompt for this agent based on document context.
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String;

    /// Returns whether this agent is a good fit for the current context.
    /// Higher score = better fit.
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8;

    /// Returns the capability level of the domain (Real vs PromptOnly).
    fn capability(&self) -> DomainCapability {
        DomainCapability::PromptOnly
    }
}

/// Registry for fingerprinters.
pub struct FingerprinterRegistry {
    fingerprinters: Vec<Box<dyn AppFingerprinter>>,
}

impl Default for FingerprinterRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl FingerprinterRegistry {
    pub fn new() -> Self {
        Self {
            fingerprinters: Vec::new(),
        }
    }

    pub fn register(&mut self, fingerprinter: Box<dyn AppFingerprinter>) {
        self.fingerprinters.push(fingerprinter);
    }

    pub fn identify(&self, process_name: &str, window_title: &str) -> Option<AppEnvironment> {
        for f in &self.fingerprinters {
            if let Some(env) = f.fingerprint(process_name, window_title) {
                return Some(env);
            }
        }
        None
    }
}

/// Registry for swarm agents.
pub struct AgentRegistry {
    agents: Vec<Arc<dyn SwarmAgent>>,
}

impl Default for AgentRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl AgentRegistry {
    pub fn new() -> Self {
        Self { agents: Vec::new() }
    }

    pub fn register(&mut self, agent: Arc<dyn SwarmAgent>) {
        self.agents.push(agent);
    }

    pub fn get_agent(&self, id: &str) -> Option<Arc<dyn SwarmAgent>> {
        self.agents.iter().find(|a| a.id() == id).cloned()
    }

    pub fn list_agents(&self) -> Vec<Arc<dyn SwarmAgent>> {
        self.agents.clone()
    }

    pub fn select_best(&self, doc_ctx: &DocumentContext) -> Option<Arc<dyn SwarmAgent>> {
        self.agents
            .iter()
            .max_by_key(|a| a.match_score(doc_ctx))
            .cloned()
    }

    /// Returns only agents with `Real` (non-PromptOnly) capabilities.
    /// Use this for public-facing capability listings to avoid advertising thin expert domains.
    pub fn public_agents(&self) -> Vec<Arc<dyn SwarmAgent>> {
        self.agents
            .iter()
            .filter(|a| a.capability() == DomainCapability::Real)
            .cloned()
            .collect()
    }

    /// Returns a map of agent id → capability for all registered agents.
    /// PromptOnly agents are included but clearly marked so callers can strip them.
    pub fn capability_map(&self) -> Vec<(String, DomainCapability)> {
        self.agents
            .iter()
            .map(|a| (a.id().to_string(), a.capability()))
            .collect()
    }
}

/// Dynamic fingerprinter loaded from TOML.
#[derive(Deserialize, Clone)]
pub struct DynamicFingerprinter {
    pub process: Option<String>,
    pub title_contains: Option<String>,
    pub env_label: String,
}

impl AppFingerprinter for DynamicFingerprinter {
    fn fingerprint(&self, process_name: &str, window_title: &str) -> Option<AppEnvironment> {
        // Guard: if no criteria specified, never match (avoids silent catch-all)
        if self.process.is_none() && self.title_contains.is_none() {
            return None;
        }

        let mut matches = true;
        if let Some(ref p) = self.process {
            if !process_name.to_lowercase().contains(&p.to_lowercase()) {
                matches = false;
            }
        }
        if let Some(ref t) = self.title_contains {
            if !window_title.to_lowercase().contains(&t.to_lowercase()) {
                matches = false;
            }
        }

        if matches {
            Some(AppEnvironment::Unknown(self.env_label.clone()))
        } else {
            None
        }
    }
}

/// Dynamic agent loaded from TOML.
#[derive(Deserialize, Clone)]
pub struct DynamicAgent {
    pub id: String,
    pub name: String,
    pub system_prompt: String,
    pub match_pattern: Option<String>,
    pub default_score: u8,
}

impl SwarmAgent for DynamicAgent {
    fn id(&self) -> &str {
        &self.id
    }
    fn name(&self) -> &str {
        &self.name
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{}\n\n[DOCUMENT INTELLIGENCE]\n{}\n\n*** ROLE: {} ***\n{}",
            base, doc_fragment, self.name, self.system_prompt
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        if let Some(ref pattern) = self.match_pattern {
            if doc_ctx
                .prompt_text
                .to_lowercase()
                .contains(&pattern.to_lowercase())
            {
                return 90;
            }
        }
        self.default_score
    }
}

/// Plugin TOML structure.
#[derive(Deserialize)]
pub struct PluginConfig {
    pub name: String,
    pub fingerprinters: Option<Vec<DynamicFingerprinter>>,
    pub agents: Option<Vec<DynamicAgent>>,
}
