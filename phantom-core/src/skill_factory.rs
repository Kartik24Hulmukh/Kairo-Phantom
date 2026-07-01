// phantom-core/src/skill_factory.rs
//
// Milestone 2 — Autonomous Skill Creation (Hermes Agent Pattern)
// Distills successful multi-step task traces into dynamic Waza skills.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Mutex;
use tracing::{error, info};

use crate::ai::AiBackend;
use crate::planning_engine::Plan;

/// Context of a successfully executed multi-step workflow.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowHistory {
    pub prompt: String,
    pub plan: Plan,
    pub output: String,
    pub app_name: String,
    pub doc_kind: String,
    pub timestamp: u64,
}

pub struct SkillFactory {
    last_successful_workflow: Mutex<Option<WorkflowHistory>>,
    ai_backend: std::sync::Arc<dyn AiBackend>,
}

impl SkillFactory {
    pub fn new(ai_backend: std::sync::Arc<dyn AiBackend>) -> Self {
        Self {
            last_successful_workflow: Mutex::new(None),
            ai_backend,
        }
    }

    /// Records a successful workflow run into memory.
    pub fn record_success(
        &self,
        prompt: &str,
        plan: Plan,
        output: &str,
        app_name: &str,
        doc_kind: &str,
    ) {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let history = WorkflowHistory {
            prompt: prompt.to_string(),
            plan,
            output: output.to_string(),
            app_name: app_name.to_string(),
            doc_kind: doc_kind.to_string(),
            timestamp,
        };

        let mut lock = self.last_successful_workflow.lock().unwrap();
        *lock = Some(history);
        info!("🧠 [SkillFactory] Successfully recorded completed task for skill distillation.");
    }

    /// Clears the recorded workflow history.
    pub fn clear(&self) {
        let mut lock = self.last_successful_workflow.lock().unwrap();
        *lock = None;
    }

    /// Returns true if a valid workflow history exists in memory.
    pub fn has_history(&self) -> bool {
        self.last_successful_workflow.lock().unwrap().is_some()
    }

    /// Distills the recorded workflow into a dynamic Waza skill and writes it to disk.
    /// Returns the skill ID on success.
    pub async fn distill_and_save_skill(&self) -> Result<String> {
        let history = {
            let lock = self.last_successful_workflow.lock().unwrap();
            lock.clone()
                .context("No successful workflow trace available to save")?
        };

        info!(
            "🧠 [SkillFactory] Running LLM distillation on task: '{}'",
            history.prompt
        );

        // System prompt instructing the model to generate the skill package files
        let system_prompt = r#"You are the Kairo Skill Distillation Engine.
Your task is to take a user's successful multi-step task execution history (prompt, plan, and final generated output) and distill it into a reusable, structured Waza dynamic skill.

You must output a single JSON object containing two keys:
1. "manifest": A JSON representation matching the manifest.toml fields:
   - "id": A unique URL-safe string containing only lowercase letters, numbers, and hyphens (e.g. "quarterly-report-generator")
   - "name": A clean, human-readable name (e.g. "Quarterly Report Generator")
   - "version": "0.1.0"
   - "description": A short explanation of the skill
   - "author": "Kairo Autonomous Engine"
   - "category": Choose one of: "legal", "medical", "developer", "finance", "general"
   - "requires_kairo": "0.6.0"
   - "tags": ["autonomous", "custom"]
2. "skill_md": The markdown content for SKILL.md containing:
   - YAML frontmatter with "name" and "description" at the very top
   - `# [Skill Title]`
   - `## Overview`
   - `## Activation` showing the trigger (e.g. `// id: <prompt>`)
   - `## System Prompt` containing the persona, tone, and directives refined from the successful workflow.
   - `## Examples` summarizing the input and output from this run.

Output ONLY valid JSON. Do not include markdown codeblocks (e.g. ```json) or any other text."#;

        let user_prompt = format!(
            "Successful Workflow Run:\nUser Prompt: {}\nPlan Steps: {:?}\nGenerated Output: {}\nApp: {}\nDocument Kind: {}",
            history.prompt,
            history.plan.to_overlay_string(),
            history.output,
            history.app_name,
            history.doc_kind
        );

        let response = self
            .ai_backend
            .complete(system_prompt, &user_prompt)
            .await?;

        // Clean JSON formatting if LLM wrapped it
        let cleaned = response
            .trim()
            .trim_start_matches("```json")
            .trim_start_matches("```")
            .trim_end_matches("```")
            .trim();

        #[derive(Deserialize)]
        struct DistillResponse {
            manifest: LlmManifest,
            skill_md: String,
        }

        #[derive(Deserialize, Serialize)]
        struct LlmManifest {
            id: String,
            name: String,
            version: String,
            description: String,
            author: String,
            category: String,
            #[serde(default = "default_skill_md_url")]
            skill_md_url: String,
            requires_kairo: String,
            tags: Vec<String>,
        }

        fn default_skill_md_url() -> String {
            "local".to_string()
        }

        let parsed: DistillResponse = serde_json::from_str(cleaned)
            .context("Failed to parse distilled skill JSON response from LLM")?;

        let skill_id = parsed.manifest.id.clone();
        let home_dir = dirs::home_dir().context("Could not resolve home directory")?;
        let skill_dir = home_dir
            .join(".kairo-phantom")
            .join("skills")
            .join("auto")
            .join(&skill_id);

        std::fs::create_dir_all(&skill_dir).context("Failed to create skill output directory")?;

        // Write manifest.toml
        let manifest_content = toml::to_string_pretty(&parsed.manifest)
            .context("Failed to serialize manifest structure to TOML")?;

        std::fs::write(skill_dir.join("manifest.toml"), &manifest_content)
            .context("Failed to write manifest.toml")?;

        // Write SKILL.md
        std::fs::write(skill_dir.join("SKILL.md"), &parsed.skill_md)
            .context("Failed to write SKILL.md")?;

        info!(
            "✅ [SkillFactory] Distilled and saved dynamic skill '{}' successfully.",
            skill_id
        );
        Ok(skill_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::intent_gate::{DocSpecialist, IntentType};
    use crate::planning_engine::{Plan, PlanStep, StepStatus};
    use std::fs;
    use std::sync::Arc;

    struct MockAiBackend {
        response_content: String,
    }

    #[async_trait::async_trait]
    impl AiBackend for MockAiBackend {
        async fn complete(&self, _system: &str, _user: &str) -> Result<String> {
            Ok(self.response_content.clone())
        }

        async fn stream_complete(
            &self,
            _system: &str,
            _user: &str,
            _tx: tokio::sync::mpsc::Sender<String>,
        ) -> Result<()> {
            Ok(())
        }
    }

    #[tokio::test]
    async fn test_skill_factory_record_clear_has_history() {
        let backend = Arc::new(MockAiBackend {
            response_content: "".to_string(),
        });
        let factory = SkillFactory::new(backend);

        assert!(!factory.has_history());

        let plan = Plan {
            steps: vec![PlanStep {
                index: 1,
                description: "Step 1".to_string(),
                status: StepStatus::Pending,
            }],
            intent_type: IntentType::Generate,
            doc_specialist: DocSpecialist::Word,
        };

        factory.record_success("Write a test", plan, "Response", "Word", "Word Document");

        assert!(factory.has_history());

        factory.clear();
        assert!(!factory.has_history());
    }

    #[tokio::test]
    async fn test_skill_factory_distill_and_save_success() {
        let mock_response = r##"{
  "manifest": {
    "id": "test-autogenerated-skill",
    "name": "Test Autogenerated Skill",
    "version": "0.1.0",
    "description": "A test skill distilled from workflow",
    "author": "Kairo Autonomous Engine",
    "category": "general",
    "requires_kairo": "0.6.0",
    "tags": ["autonomous", "custom"]
  },
  "skill_md": "# Test Autogenerated Skill\n## Overview\nThis is a test skill."
}"##
        .to_string();

        let backend = Arc::new(MockAiBackend {
            response_content: mock_response,
        });
        let factory = SkillFactory::new(backend);

        let plan = Plan {
            steps: vec![PlanStep {
                index: 1,
                description: "Step 1".to_string(),
                status: StepStatus::Pending,
            }],
            intent_type: IntentType::Generate,
            doc_specialist: DocSpecialist::Word,
        };

        factory.record_success(
            "Write a test prompt",
            plan,
            "Successfully written test response",
            "Word",
            "Word Document",
        );

        let skill_id = factory.distill_and_save_skill().await.unwrap();
        assert_eq!(skill_id, "test-autogenerated-skill");

        // Verify the directories and files were created
        let home_dir = dirs::home_dir().expect("Home dir resolved");
        let skill_dir = home_dir
            .join(".kairo-phantom")
            .join("skills")
            .join("auto")
            .join(&skill_id);

        assert!(skill_dir.exists());
        assert!(skill_dir.join("manifest.toml").exists());
        assert!(skill_dir.join("SKILL.md").exists());

        // Check content
        let manifest_content = fs::read_to_string(skill_dir.join("manifest.toml")).unwrap();
        assert!(manifest_content.contains("test-autogenerated-skill"));
        assert!(manifest_content.contains("skill_md_url = \"local\""));

        let skill_md_content = fs::read_to_string(skill_dir.join("SKILL.md")).unwrap();
        assert!(skill_md_content.contains("# Test Autogenerated Skill"));

        // Cleanup
        let _ = fs::remove_dir_all(skill_dir);
    }
}
