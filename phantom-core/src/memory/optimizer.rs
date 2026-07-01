use std::sync::Mutex;
use tracing::{info, warn};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub enum SemanticZone {
    Success,
    Failure,
    Preference,
}

#[derive(Debug, Clone)]
pub struct MemoryPolicy {
    pub name: String,
    pub threshold: f64,
    pub sample_size: usize,
    pub score: f64,
}

pub struct MemoryOptimizer {
    policies: Mutex<Vec<MemoryPolicy>>,
    active_policy_index: Mutex<usize>,
}

impl Default for MemoryOptimizer {
    fn default() -> Self {
        Self::new()
    }
}

impl MemoryOptimizer {
    pub fn new() -> Self {
        let policies = vec![
            MemoryPolicy {
                name: "Conservative".into(),
                threshold: 0.85,
                sample_size: 10,
                score: 0.0,
            },
            MemoryPolicy {
                name: "Balanced".into(),
                threshold: 0.70,
                sample_size: 7,
                score: 0.0,
            },
            MemoryPolicy {
                name: "Aggressive".into(),
                threshold: 0.50,
                sample_size: 3,
                score: 0.0,
            },
        ];
        Self {
            policies: Mutex::new(policies),
            active_policy_index: Mutex::new(1), // Default to Balanced
        }
    }

    /// Records the outcome of a memory application to evaluate the active policy.
    pub fn record_outcome(&self, accepted: bool) {
        let mut policies = self.policies.lock().unwrap();
        let idx = *self.active_policy_index.lock().unwrap();
        let policy = &mut policies[idx];

        // Simple rolling score update
        let weight = 0.1;
        let outcome_score = if accepted { 1.0 } else { 0.0 };
        policy.score = (policy.score * (1.0 - weight)) + (outcome_score * weight);
    }

    /// Runs a policy optimization cycle, potentially switching to a better policy.
    pub fn optimize(&self) {
        let policies = self.policies.lock().unwrap();
        let mut active_idx = self.active_policy_index.lock().unwrap();

        info!("🧠 MemoryOptimizer: Evaluating policies...");

        let mut best_idx = *active_idx;
        let mut best_score = policies[best_idx].score;

        for (i, p) in policies.iter().enumerate() {
            info!("  - Policy '{}': score={:.4}", p.name, p.score);
            if p.score > best_score + 0.05 {
                // 5% improvement threshold to switch
                best_idx = i;
                best_score = p.score;
            }
        }

        if best_idx != *active_idx {
            warn!(
                "🧠 MemoryOptimizer: SWITCHING policy from '{}' to '{}'",
                policies[*active_idx].name, policies[best_idx].name
            );
            *active_idx = best_idx;
        }
    }

    pub fn active_policy(&self) -> MemoryPolicy {
        let policies = self.policies.lock().unwrap();
        let idx = *self.active_policy_index.lock().unwrap();
        policies[idx].clone()
    }

    /// Per-session heartbeat called by the benchmark and live pipeline.
    /// Triggers a policy re-evaluation after every session so the optimizer
    /// can switch to a better retrieval policy as feedback accumulates.
    pub fn tick(&self) {
        self.optimize();
    }

    /// Upgrade 5: Context-Aware Prompt Distillation.
    /// Distills relevant memory fragments into a concise hint for the LLM.
    pub fn distill_context(&self, app: &str, task: &str, memories: &[String]) -> String {
        let mut distilled = Vec::new();
        let policy = self.active_policy();

        // Only include memories if they meet the policy threshold
        for mem in memories {
            // Simple heuristic for score: if it contains app name or task keywords, it's more relevant
            let mut score = 0.5;
            if mem.to_lowercase().contains(&app.to_lowercase()) {
                score += 0.3;
            }
            if mem.to_lowercase().contains(&task.to_lowercase()) {
                score += 0.2;
            }

            if score >= policy.threshold {
                // Distill: Extract just the key insights (Mock logic: first 2 lines)
                let insights: Vec<&str> = mem.lines().take(3).collect();
                distilled.push(insights.join("\n"));
            }
        }

        distilled.join("\n\n")
    }

    /// PRIME Pattern: Distills trajectories into structured experiences.
    pub fn distill_trajectory(&self, zone: SemanticZone, episode: &str) -> String {
        let label = match zone {
            SemanticZone::Success => "🌟 SUCCESS STRATEGY",
            SemanticZone::Failure => "⚠️ FAILURE PATTERN",
            SemanticZone::Preference => "👤 USER PREFERENCE",
        };

        format!("{label}:\n{episode}")
    }
}
