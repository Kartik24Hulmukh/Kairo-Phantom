// phantom-core/src/persona.rs
use crate::document_context::DocumentContext;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PersonaType {
    General,
    Legal,
    Developer,
    Academic,
    Creative,
    Executive,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Persona {
    pub name: String,
    pub persona_type: PersonaType,
    pub tone_rules: Vec<String>,
    pub formatting_preferences: Vec<String>,
}

impl Persona {
    pub fn default_for_app(app_name: &str) -> Self {
        match app_name.to_lowercase().as_str() {
            "winword.exe" | "word" => Self::legal_professional(),
            "code.exe" | "visual studio code" | "code" => Self::developer(),
            "powerpnt.exe" | "powerpoint" => Self::executive(),
            _ => Self::general(),
        }
    }

    pub fn general() -> Self {
        Self {
            name: "General Assistant".into(),
            persona_type: PersonaType::General,
            tone_rules: vec!["Helpful, clear, and concise.".into()],
            formatting_preferences: vec!["Standard prose or bullet points.".into()],
        }
    }

    pub fn legal_professional() -> Self {
        Self {
            name: "Legal Professional".into(),
            persona_type: PersonaType::Legal,
            tone_rules: vec![
                "Formal, precise, and authoritative.".into(),
                "Use legal terminology where appropriate.".into(),
            ],
            formatting_preferences: vec![
                "Strict adherence to legal document structures.".into(),
                "No contractions.".into(),
            ],
        }
    }

    pub fn developer() -> Self {
        Self {
            name: "Senior Software Engineer".into(),
            persona_type: PersonaType::Developer,
            tone_rules: vec![
                "Technical, direct, and solution-oriented.".into(),
                "Focus on maintainability and best practices.".into(),
            ],
            formatting_preferences: vec![
                "Idiomatic code structures.".into(),
                "Clear documentation comments.".into(),
            ],
        }
    }

    pub fn executive() -> Self {
        Self {
            name: "Strategic Executive".into(),
            persona_type: PersonaType::Executive,
            tone_rules: vec![
                "High-level, strategic, and punchy.".into(),
                "Focus on value and outcomes.".into(),
            ],
            formatting_preferences: vec![
                "Executive summaries.".into(),
                "Action-oriented bullet points.".into(),
            ],
        }
    }

    pub fn build_prompt_fragment(&self) -> String {
        format!(
            "## PERSONA: {}\n- Tone: {}\n- Formatting: {}",
            self.name,
            self.tone_rules.join(" "),
            self.formatting_preferences.join(" ")
        )
    }
}

pub struct PersonaManager {
    personas: HashMap<String, Persona>,
}

impl Default for PersonaManager {
    fn default() -> Self {
        Self::new()
    }
}

impl PersonaManager {
    pub fn new() -> Self {
        Self {
            personas: HashMap::new(),
        }
    }

    pub fn get_persona_for_context(&self, app_name: &str) -> Persona {
        // In the future, this will load from user memory/OpenHuman
        Persona::default_for_app(app_name)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersonaAwareContext {
    pub context: DocumentContext,
    pub persona: Persona,
}

impl PersonaAwareContext {
    pub fn new(context: DocumentContext, persona_manager: &PersonaManager) -> Self {
        let app_name = context.app_name.clone().unwrap_or_default();
        let persona = persona_manager.get_persona_for_context(&app_name);
        Self { context, persona }
    }

    pub fn to_system_prompt(&self) -> String {
        let mut prompt = self.context.to_system_prompt_fragment();
        prompt.push_str("\n\n");
        prompt.push_str(&self.persona.build_prompt_fragment());
        prompt
    }
}
