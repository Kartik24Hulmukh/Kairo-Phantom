// phantom-core/src/swarm/mod.rs
pub mod content;
pub mod data;
pub mod design;
pub mod engineer;
pub mod image;
pub mod legal;
pub mod medical;
pub mod metrics;
pub mod reasoning;
pub mod sales;
#[allow(unused_imports)]
use crate::integration::IntegrationManager;
use crate::skills::SkillManager;

use crate::ai::{build_backend, AiBackend};
use crate::config::SwarmConfig;
use crate::context7::Context7;
use crate::document_context::DocumentContext;
use crate::memory::KairoMemory;
use crate::persona::{PersonaAwareContext, PersonaManager};
use crate::plugin::{AgentRegistry, SwarmAgent};
use std::sync::Arc;
use tracing::info;

pub use content::{ContentAgent, StudentTutorAgent};
pub use data::DataAnalystAgent;
pub use design::DesignAgent;
pub use engineer::EngineerAgent;
pub use image::ImageAgent;
pub use legal::LegalPlusAgent;
pub use medical::MedicalAgent;
pub use reasoning::ReasoningAgent;
pub use sales::SalesAgent;

#[derive(Debug, Clone, PartialEq)]
pub enum AgentType {
    DesignAndMedia,
    ReasoningAndLogic,
    ContentAndAllRounder,
    StudentTutor,
    Engineer,
    DataAnalyst,
}

pub struct AgentProfile {
    pub agent_type: AgentType,
    pub system_directive: String,
}

impl AgentProfile {
    pub fn agent_type_id(&self) -> &str {
        match self.agent_type {
            AgentType::DesignAndMedia => "design",
            AgentType::ReasoningAndLogic => "reasoning",
            AgentType::ContentAndAllRounder => "content",
            AgentType::StudentTutor => "student",
            AgentType::Engineer => "engineer",
            AgentType::DataAnalyst => "data",
        }
    }
}

pub struct SwarmOrchestrator {
    pub config: SwarmConfig,
    pub registry: AgentRegistry,
    pub brain: Option<Arc<dyn AiBackend>>,
    pub design_backend: Option<Arc<dyn AiBackend>>,
    pub reasoning_backend: Option<Arc<dyn AiBackend>>,
    pub content_backend: Option<Arc<dyn AiBackend>>,
    pub fallback_agent: Arc<dyn AiBackend>,
    pub persona_manager: PersonaManager,
    pub memory: KairoMemory,
    pub context7: Context7,
    pub optimizer: crate::context_optimizer::ContextOptimizer,
    pub skill_manager: SkillManager,
    pub integration_manager: IntegrationManager,
    pub dashboard: Arc<metrics::PerformanceDashboard>,
}

impl SwarmOrchestrator {
    pub fn new(config: SwarmConfig, fallback_agent: Arc<dyn AiBackend>) -> Self {
        let brain = config.brain.as_ref().and_then(|c| build_backend(c).ok());
        let design_backend = config
            .design_agent
            .as_ref()
            .and_then(|c| build_backend(c).ok());
        let reasoning_backend = config
            .reasoning_agent
            .as_ref()
            .and_then(|c| build_backend(c).ok());
        let content_backend = config
            .content_agent
            .as_ref()
            .and_then(|c| build_backend(c).ok());

        let mut registry = AgentRegistry::new();
        registry.register(Arc::new(DesignAgent));
        registry.register(Arc::new(ReasoningAgent));
        registry.register(Arc::new(ContentAgent));
        registry.register(Arc::new(StudentTutorAgent));
        registry.register(Arc::new(EngineerAgent));
        registry.register(Arc::new(DataAnalystAgent));
        registry.register(Arc::new(ImageAgent));
        registry.register(Arc::new(SalesAgent));
        registry.register(Arc::new(MedicalAgent));
        registry.register(Arc::new(LegalPlusAgent));

        Self {
            config,
            registry,
            brain,
            design_backend,
            reasoning_backend,
            content_backend,
            fallback_agent,
            persona_manager: PersonaManager::new(),
            memory: KairoMemory::new(),
            context7: Context7::new(),
            optimizer: crate::context_optimizer::ContextOptimizer::new(4096),
            skill_manager: SkillManager::new(),
            integration_manager: IntegrationManager::new(),
            dashboard: Arc::new(metrics::PerformanceDashboard::new()),
        }
    }

    pub async fn route(
        &self,
        doc_ctx: &DocumentContext,
        command_mode: &crate::command_protocol::CommandMode,
    ) -> (Arc<dyn AiBackend>, AgentProfile) {
        let start = std::time::Instant::now();
        let (backend, profile) = self.route_internal(doc_ctx, command_mode).await;
        let latency = start.elapsed().as_millis() as u64;

        self.dashboard
            .record_call(profile.agent_type_id(), latency, true);

        (backend, profile)
    }

    async fn route_internal(
        &self,
        doc_ctx: &DocumentContext,
        command_mode: &crate::command_protocol::CommandMode,
    ) -> (Arc<dyn AiBackend>, AgentProfile) {
        let mut selected_agent: Arc<dyn SwarmAgent> = match self.registry.select_best(doc_ctx) {
            Some(agent) => agent,
            None => {
                info!("⚠️  No agents in registry, using raw fallback backend");
                let profile = AgentProfile {
                    agent_type: AgentType::ContentAndAllRounder,
                    system_directive: crate::ai::KAIRO_SYSTEM_PROMPT.to_string(),
                };
                return (self.fallback_agent.clone(), profile);
            }
        };
        let mut agent_id = selected_agent.id().to_string();

        if self.config.enabled && self.brain.is_some() {
            if let Some(brain_llm) = &self.brain {
                let brain_prompt = format!(
                    "You are the Swarm Brain. The user typed: '{}'. Document type: '{}'. \
                    Decide the best specialized agent. Reply ONLY with the agent ID: {}.",
                    doc_ctx.prompt_text,
                    doc_ctx.doc_kind.human_name(),
                    self.registry
                        .list_agents()
                        .iter()
                        .map(|a| a.id())
                        .collect::<Vec<_>>()
                        .join(", ")
                );

                info!("🧠 Brain is thinking...");
                if let Ok(decision) = brain_llm
                    .complete(
                        "You are a router. Reply with exactly one ID.",
                        &brain_prompt,
                    )
                    .await
                {
                    let d = decision.trim().to_lowercase();
                    if let Some(agent) = self.registry.get_agent(&d) {
                        selected_agent = agent;
                        agent_id = d;
                    }
                }
            }
        }

        let agent_score = selected_agent.match_score(doc_ctx);
        info!(
            "🧠 Swarm routed to: {} (score={}) | doc={}",
            agent_id,
            agent_score,
            doc_ctx.doc_kind.human_name()
        );

        // V4: Log agent selection to ~/.kairo-phantom/agent_debug.jsonl
        crate::toast_notification::log_agent_selection(
            &agent_id,
            agent_score,
            doc_ctx.doc_kind.human_name(),
            &doc_ctx.prompt_text,
        );

        let base_directive = selected_agent.build_system_prompt(doc_ctx);
        let app_name = doc_ctx.app_name.clone().unwrap_or_default();
        let memory_fragment = self.optimizer.optimize_memory(&self.memory, &app_name);
        let ground_truth = self.context7.fetch_ground_truth(&doc_ctx.prompt_text).await;
        let ground_truth_fragment = ground_truth
            .map(|gt| format!("\n\n## GROUND TRUTH (Context7)\n{gt}"))
            .unwrap_or_default();

        // Fetch deep app context if an adapter is available
        let mut deep_context_fragment = String::new();
        if let Some(app_id) = &doc_ctx.app_name {
            if let Some(adapter) = self
                .integration_manager
                .get_adapter(&app_id.to_lowercase())
                .await
            {
                if let Ok(ctx) = adapter.get_deep_context().await {
                    deep_context_fragment = format!("\n\n## DEEP APP CONTEXT ({app_id})\n{ctx}");
                }
            }
        }

        let command_hint = command_mode.system_hint();
        let skill_directive = self
            .skill_manager
            .get_skill_directive(command_mode)
            .unwrap_or_default();
        let persona_aware_ctx = PersonaAwareContext::new(doc_ctx.clone(), &self.persona_manager);
        let persona_fragment = persona_aware_ctx.persona.build_prompt_fragment();

        let system_directive = format!(
            "<system>\n{base_directive}\n\n{persona_fragment}\n\n{memory_fragment}\n\n{ground_truth_fragment}\n\n{deep_context_fragment}\n\n{skill_directive}\n\n## COMMAND PROTOCOL\n{command_hint}\n\nCRITICAL: Output ONLY within <output> tags. No conversational preamble.\n</system>"
        );

        let agent_type = match agent_id.as_str() {
            "design" => AgentType::DesignAndMedia,
            "reasoning" => AgentType::ReasoningAndLogic,
            "student" => AgentType::StudentTutor,
            "engineer" => AgentType::Engineer,
            "data" => AgentType::DataAnalyst,
            _ => AgentType::ContentAndAllRounder,
        };

        let profile = AgentProfile {
            agent_type,
            system_directive,
        };

        let backend = match agent_id.as_str() {
            "design" => self
                .design_backend
                .clone()
                .unwrap_or_else(|| self.fallback_agent.clone()),
            "reasoning" => self
                .reasoning_backend
                .clone()
                .unwrap_or_else(|| self.fallback_agent.clone()),
            _ => self
                .content_backend
                .clone()
                .unwrap_or_else(|| self.fallback_agent.clone()),
        };

        (backend, profile)
    }

    pub fn get_backend_and_profile_by_type(
        &self,
        agent_type: &AgentType,
        doc_ctx: &DocumentContext,
    ) -> (Arc<dyn AiBackend>, AgentProfile) {
        let agent_id = match agent_type {
            AgentType::DesignAndMedia => "design",
            AgentType::ReasoningAndLogic => "reasoning",
            AgentType::StudentTutor => "student",
            AgentType::Engineer => "engineer",
            AgentType::DataAnalyst => "data",
            AgentType::ContentAndAllRounder => "content",
        };

        let base_directive = self
            .registry
            .get_agent(agent_id)
            .map(|a| a.build_system_prompt(doc_ctx))
            .unwrap_or_else(|| crate::ai::KAIRO_SYSTEM_PROMPT.to_string());

        let system_directive = format!("<system>\n{base_directive}\n\nCRITICAL: Output ONLY within <output> tags. No conversational preamble.\n</system>");

        let profile = AgentProfile {
            agent_type: agent_type.clone(),
            system_directive,
        };

        let backend = match agent_id {
            "design" => self
                .design_backend
                .clone()
                .unwrap_or_else(|| self.fallback_agent.clone()),
            "reasoning" => self
                .reasoning_backend
                .clone()
                .unwrap_or_else(|| self.fallback_agent.clone()),
            _ => self
                .content_backend
                .clone()
                .unwrap_or_else(|| self.fallback_agent.clone()),
        };

        (backend, profile)
    }

    pub fn get_domain_capability(
        &self,
        domain_id: &str,
    ) -> Option<crate::plugin::DomainCapability> {
        self.registry.get_agent(domain_id).map(|a| a.capability())
    }
}

pub struct TestFallbackBackend;
#[async_trait::async_trait]
impl AiBackend for TestFallbackBackend {
    async fn complete(&self, _system: &str, _prompt: &str) -> anyhow::Result<String> {
        Ok("test response".to_string())
    }
    async fn stream_complete(
        &self,
        _system: &str,
        _prompt: &str,
        _tx: tokio::sync::mpsc::Sender<String>,
    ) -> anyhow::Result<()> {
        Ok(())
    }
}

impl SwarmOrchestrator {
    pub fn new_for_test() -> Self {
        let fallback: Arc<dyn AiBackend> = Arc::new(TestFallbackBackend);
        Self::new(SwarmConfig::default(), fallback)
    }

    pub fn select_agent(&mut self, doc_ctx: &DocumentContext) -> String {
        self.registry
            .select_best(doc_ctx)
            .map(|a| a.id().to_string())
            .unwrap_or_else(|| "content".to_string())
    }
}

// ─── B3: Parallel Swarm Execution ─────────────────────────────────────────────
//
// V6 optimization: instead of routing to ONE agent and waiting,
// fan out to ALL high-scoring agents concurrently via futures::future::join_all.
// The primary agent's result is returned; secondary results are stored as alternatives
// in the GhostBuffer (Alt+1 / Alt+2 UX). ~50% latency reduction for multi-agent tasks.

/// Result from a parallel swarm consultation.
#[derive(Debug)]
pub struct ParallelConsultResult {
    /// Agent ID of the primary winner
    pub primary_agent: String,
    /// Primary agent's response text
    pub primary_response: String,
    /// Secondary agent responses (for ghost overlay Alt+1/Alt+2)
    pub alternatives: Vec<(String, String)>, // (agent_id, response_text)
    /// Total wall-clock time (ms). Parallel = max latency, not sum.
    pub elapsed_ms: u64,
}

impl SwarmOrchestrator {
    /// V6 B3: Fan out to multiple agents in parallel, return the best result.
    ///
    /// Agents are scored against `doc_ctx`. The top-N (default N=2) are selected
    /// and called concurrently via `futures::future::join_all`. The highest-scoring
    /// agent's response is the primary; others become alternatives.
    pub async fn parallel_consult(
        &self,
        doc_ctx: &DocumentContext,
        user_prompt: &str,
        max_agents: usize,
    ) -> ParallelConsultResult {
        let start = std::time::Instant::now();

        // 1. Score all agents — pick top N
        let all_agents = self.registry.list_agents();
        let mut scored: Vec<(u8, Arc<dyn crate::plugin::SwarmAgent>)> = all_agents
            .into_iter()
            .map(|a| {
                let score = a.match_score(doc_ctx);
                (score, a)
            })
            .collect();
        // Sort descending by score
        scored.sort_by_key(|a| std::cmp::Reverse(a.0));
        scored.truncate(max_agents.max(1));

        if scored.is_empty() {
            return ParallelConsultResult {
                primary_agent: "content".to_string(),
                primary_response: String::new(),
                alternatives: Vec::new(),
                elapsed_ms: start.elapsed().as_millis() as u64,
            };
        }

        info!(
            "⚡ B3 ParallelSwarm: consulting {} agents concurrently: [{}]",
            scored.len(),
            scored
                .iter()
                .map(|(s, a)| format!("{}({})", a.id(), s))
                .collect::<Vec<_>>()
                .join(", ")
        );

        // 2. Build (agent_id, system_prompt, backend) tuples
        let tasks: Vec<(String, String, Arc<dyn AiBackend>)> = scored
            .iter()
            .map(|(_, agent)| {
                let agent_id = agent.id().to_string();
                let sys = agent.build_system_prompt(doc_ctx);
                let backend = match agent.id() {
                    "design" => self
                        .design_backend
                        .clone()
                        .unwrap_or_else(|| self.fallback_agent.clone()),
                    "reasoning" => self
                        .reasoning_backend
                        .clone()
                        .unwrap_or_else(|| self.fallback_agent.clone()),
                    _ => self
                        .content_backend
                        .clone()
                        .unwrap_or_else(|| self.fallback_agent.clone()),
                };
                (agent_id, sys, backend)
            })
            .collect();

        // 3. Fire all agents concurrently
        let prompt_clone = user_prompt.to_string();
        let futures: Vec<_> = tasks
            .into_iter()
            .map(|(agent_id, sys_prompt, backend)| {
                let prompt = prompt_clone.clone();
                async move {
                    let result = backend
                        .complete(&sys_prompt, &prompt)
                        .await
                        .unwrap_or_else(|e| format!("[{agent_id} failed: {e}]"));
                    (agent_id, result)
                }
            })
            .collect();

        let results: Vec<(String, String)> = futures::future::join_all(futures).await;

        let elapsed_ms = start.elapsed().as_millis() as u64;
        self.dashboard
            .record_call("parallel_swarm", elapsed_ms, !results.is_empty());

        // 4. Primary = first result (highest-scored agent), rest are alternatives
        let mut iter = results.into_iter();
        let (primary_agent, primary_response) = iter
            .next()
            .unwrap_or_else(|| ("content".to_string(), String::new()));
        let alternatives: Vec<(String, String)> = iter.collect();

        info!(
            "⚡ B3 ParallelSwarm: done in {}ms. Primary='{}' ({} chars), {} alternatives",
            elapsed_ms,
            primary_agent,
            primary_response.len(),
            alternatives.len()
        );

        ParallelConsultResult {
            primary_agent,
            primary_response,
            alternatives,
            elapsed_ms,
        }
    }

    /// V6 B3: Select the best response from parallel results using heuristics.
    ///
    /// Prefers responses that:
    /// 1. Are non-empty
    /// 2. Are not error messages (don't start with `[`)
    /// 3. Have more content than the minimum length threshold
    pub fn select_best_response(results: &[(String, String)], min_len: usize) -> Option<&str> {
        results
            .iter()
            .filter(|(_, r)| !r.is_empty() && !r.starts_with('[') && r.len() >= min_len)
            .map(|(_, r)| r.as_str())
            .next()
    }
}
