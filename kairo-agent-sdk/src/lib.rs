pub mod agent_registry;
pub mod agent_router;
pub mod cli;
pub mod sandbox;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AgentManifest {
    pub agent: AgentInfo,
    pub triggers: AgentTriggers,
    pub system_prompt: SystemPrompt,
    pub output: OutputConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AgentInfo {
    pub name: String,
    pub id: String,
    pub author: String,
    pub version: String,
    pub description: String,
    #[serde(default)]
    pub sandboxed: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AgentTriggers {
    pub keywords: Vec<String>,
    pub app_contexts: Vec<String>,
    pub confidence_boost: f32,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SystemPrompt {
    pub template: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct OutputConfig {
    pub preferred_format: String,
    pub max_tokens: u32,
}
