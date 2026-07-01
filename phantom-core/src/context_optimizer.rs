// phantom-core/src/context_optimizer.rs
// VibeFlow Token Optimizer — Adaptive Context Management
// Prunes redundant or low-weight context fragments to fit within target LLM windows.
// Integrates concept from icm-graph (context window management).

use crate::memory::KairoMemory;
use tracing::info;

pub struct ContextOptimizer {
    pub max_tokens: usize,
}

impl ContextOptimizer {
    pub fn new(max_tokens: usize) -> Self {
        Self { max_tokens }
    }

    /// Optimizes the prompt by ranking context fragments and pruning lowest-priority ones.
    pub fn optimize_memory(&self, memory: &KairoMemory, app_name: &str) -> String {
        let mut fragments = Vec::new();

        // 1. App-specific bias (Highest priority)
        if let Some(bias) = memory.app_bias.get(app_name) {
            fragments.push((100, format!("- App-specific pattern: {bias}")));
        }

        // 2. High-weight user preferences
        for pref in memory.preferences.iter().filter(|p| p.weight > 0.7) {
            fragments.push((90, format!("- {}: {}", pref.key, pref.value)));
        }

        // 3. User model (Persona info)
        for (k, v) in &memory.user_model.word_preferences {
            fragments.push((80, format!("- Word Pref {k}: {v}")));
        }

        // 4. Low-weight user preferences
        for pref in memory
            .preferences
            .iter()
            .filter(|p| p.weight <= 0.7 && p.weight > 0.3)
        {
            fragments.push((50, format!("- {}: {}", pref.key, pref.value)));
        }

        // 5. Recent interactions (Recency bias)
        let recent_limit = 5;
        for (i, interaction) in memory
            .interactions
            .iter()
            .rev()
            .take(recent_limit)
            .enumerate()
        {
            let weight = 40 - i; // Older = lower weight
            fragments.push((
                weight,
                format!("- Previous {}: {}", interaction.app, interaction.prompt),
            ));
        }

        // Sort by weight descending
        fragments.sort_by_key(|&(w, _)| std::cmp::Reverse(w));

        let mut result = Vec::new();
        let mut current_chars = 0;
        let char_limit = self.max_tokens * 4; // Rough heuristic

        for (_, fragment) in fragments {
            if current_chars + fragment.len() > char_limit {
                info!("✂️  ContextOptimizer pruned low-priority fragment due to token limits.");
                break;
            }
            current_chars += fragment.len();
            result.push(fragment);
        }

        if result.is_empty() {
            return "".to_string();
        }

        format!("## OPTIMIZED CONTEXT (VibeFlow)\n{}", result.join("\n"))
    }
}
