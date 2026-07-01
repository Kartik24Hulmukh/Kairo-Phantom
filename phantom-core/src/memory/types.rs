// phantom-core/src/memory/types.rs
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::info;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UserPreference {
    pub key: String,
    pub value: String,
    pub weight: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Interaction {
    pub app: String,
    pub prompt: String,
    pub response: String,
    pub accepted: bool,
    pub timestamp: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SessionMemory {
    pub active_document: String,
    pub recent_interactions: Vec<Interaction>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SkillMemory {
    pub reusable_patterns: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UserModel {
    pub user_id: String,
    pub word_preferences: HashMap<String, String>,
    pub ppt_preferences: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct KnowledgeGraph {
    pub nodes: Vec<String>,
    pub edges: Vec<(usize, usize, String)>, // (from_idx, to_idx, relationship)
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct KairoMemory {
    pub preferences: Vec<UserPreference>,
    pub interactions: Vec<Interaction>,
    pub app_bias: HashMap<String, String>,
    pub session: SessionMemory,
    pub skill: SkillMemory,
    pub user_model: UserModel,
    pub graph: KnowledgeGraph,
}

impl KairoMemory {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn learn_from_interaction(&mut self, interaction: Interaction) {
        info!("🧠 Memory learning from interaction in {}", interaction.app);

        if interaction.accepted {
            if interaction.response.contains("struct")
                || interaction.response.contains("impl")
                || interaction.response.contains("pub fn")
            {
                self.add_preference("technical_level", "highly technical / code-centric", 0.2);
            } else if interaction.response.contains("strategic")
                || interaction.response.contains("roadmap")
            {
                self.add_preference("technical_level", "executive / strategic", 0.2);
            }

            if interaction.response.contains("!") || interaction.response.contains("exciting") {
                self.add_preference("tone", "energetic / optimistic", 0.1);
            } else if interaction.response.contains("shall")
                || interaction.response.contains("hereby")
            {
                self.add_preference("tone", "formal / legalistic", 0.3);
            }

            if interaction.response.contains("- ") {
                self.add_preference("formatting", "prefers bullet points", 0.1);
            }
            if interaction.response.contains("| --- |") {
                self.add_preference("formatting", "uses markdown tables", 0.2);
            }

            self.graph_update(&interaction.prompt, &interaction.response);
        }

        self.interactions.push(interaction);
    }

    fn graph_update(&mut self, prompt: &str, response: &str) {
        let concepts = self.extract_concepts(prompt, response);
        for concept in concepts {
            if !self.graph.nodes.contains(&concept) {
                self.graph.nodes.push(concept);
            }
        }

        if self.graph.nodes.len() >= 2 {
            let last = self.graph.nodes.len() - 1;
            let prev = last - 1;
            self.graph
                .edges
                .push((prev, last, "related_to".to_string()));
        }
    }

    fn extract_concepts(&self, _prompt: &str, response: &str) -> Vec<String> {
        let mut concepts = Vec::new();
        for word in response.split_whitespace() {
            if word.len() > 3 && word.chars().next().unwrap().is_uppercase() {
                concepts.push(
                    word.trim_matches(|c: char| !c.is_alphanumeric())
                        .to_string(),
                );
            }
        }
        concepts.truncate(5);
        concepts
    }

    pub fn add_preference(&mut self, category: &str, value: &str, boost: f32) {
        let key = category.to_string();
        if let Some(pref) = self
            .preferences
            .iter_mut()
            .find(|p| p.key == key && p.value == value)
        {
            pref.weight += boost;
        } else {
            self.preferences.push(UserPreference {
                key,
                value: value.to_string(),
                weight: boost,
            });
        }
    }

    pub fn build_memory_fragment(&self, app_name: &str) -> String {
        let mut parts = Vec::new();
        parts.push("## USER MEMORY (PERSISTENT)".to_string());

        for pref in self.preferences.iter().filter(|p| p.weight > 0.5) {
            parts.push(format!("- {}: {}", pref.key, pref.value));
        }

        if let Some(bias) = self.app_bias.get(app_name) {
            parts.push(format!("- App-specific pattern: {bias}"));
        }

        parts.push("\n## USER MODEL".to_string());
        for (k, v) in &self.user_model.word_preferences {
            parts.push(format!("- Word Pref {k}: {v}"));
        }
        for (k, v) in &self.user_model.ppt_preferences {
            parts.push(format!("- PPT Pref {k}: {v}"));
        }

        if parts.len() <= 2 {
            return "".into();
        }

        parts.join("\n")
    }

    pub fn build_context_hint(&self, app: &str, task: &str) -> Option<String> {
        let app_lower = app.to_lowercase();
        let mut hints = Vec::new();

        for pref in self.preferences.iter().filter(|p| p.weight > 1.0) {
            hints.push(format!("User {} {}", pref.key, pref.value));
        }

        if app_lower.contains("word") || app_lower.contains("winword") {
            if let Some(tone) = self.user_model.word_preferences.get("tone") {
                hints.push(format!("User prefers {tone} tone in Word documents"));
            }
        } else if app_lower.contains("powerpnt") {
            if let Some(style) = self.user_model.ppt_preferences.get("style") {
                hints.push(format!("User prefers {style} slides in PowerPoint"));
            }
        }

        let task_key = format!("REJECTED:{}:{}", app, &task[..task.len().min(50)]);
        if self.skill.reusable_patterns.contains_key(&task_key) {
            hints.push(
                "NOTE: User previously rejected a similar response. Vary the approach.".to_string(),
            );
        }

        if hints.is_empty() {
            None
        } else {
            Some(format!("## LEARNED USER PREFERENCES\n{}", hints.join("\n")))
        }
    }
}
