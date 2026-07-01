// phantom-core/src/planning_engine.rs
//
// Layer 2 — Planning Engine
// ─────────────────────────────────────────────────────────────────────────────
// Generates a structured 3–7 step execution plan using the non-streaming complete()
// method of the AI backend. If the LLM fails, it gracefully falls back to a heuristic
// plan to guarantee that the system never blocks the user.
//

use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{error, info, warn};

use crate::ai::AiBackend;
use crate::document_context::DocumentContext;
use crate::intent_gate::{DocSpecialist, IntentAnalysis, IntentType};

// ─── Step Status ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum StepStatus {
    Pending,
    Running,
    Complete,
    Failed(String),
}

// ─── Plan Step ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PlanStep {
    pub index: usize,
    pub description: String,
    pub status: StepStatus,
}

// ─── Plan ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Plan {
    pub steps: Vec<PlanStep>,
    pub intent_type: IntentType,
    pub doc_specialist: DocSpecialist,
}

impl Plan {
    /// Formats the plan as a clean checklist for the toast notification or overlay.
    pub fn to_overlay_string(&self) -> String {
        let mut steps_text = Vec::new();
        let mut has_execution_started = false;

        for step in &self.steps {
            match &step.status {
                StepStatus::Pending => {
                    steps_text.push(format!("{}. {}", step.index, step.description));
                }
                StepStatus::Running => {
                    has_execution_started = true;
                    steps_text.push(format!("→ Step {} running", step.index));
                }
                StepStatus::Complete => {
                    has_execution_started = true;
                    steps_text.push(format!("✓ Step {} complete", step.index));
                }
                StepStatus::Failed(e) => {
                    has_execution_started = true;
                    steps_text.push(format!("✗ Step {} failed ({})", step.index, e));
                }
            }
        }

        if has_execution_started {
            steps_text.join(", ")
        } else {
            format!("Kairo is planning: {}", steps_text.join(" → "))
        }
    }

    /// Formats the plan as a comment block to be injected directly into the active document.
    pub fn to_document_string(&self) -> String {
        let mut s = format!(
            "// ─── KAIRO PLAN: {} ({}) ───\n",
            self.intent_type.label().to_uppercase(),
            self.doc_specialist.label().to_uppercase()
        );
        for step in &self.steps {
            s.push_str(&format!(
                "//   [ ] Step {}: {}\n",
                step.index, step.description
            ));
        }
        s.push_str("// [Press Alt+Ctrl+M to execute this plan, Esc to cancel]");
        s
    }
}

// ─── Pending Plan (State) ─────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct PendingPlan {
    pub plan: Plan,
    pub original_prompt: String,
    pub doc_specialist: DocSpecialist,
}

// ─── Planning Engine ──────────────────────────────────────────────────────────

pub struct PlanningEngine;

impl PlanningEngine {
    /// Generates a plan using the AI backend. If it fails, falls back to a heuristic plan.
    pub async fn generate(
        intent: &IntentAnalysis,
        prompt: &str,
        doc_ctx: &DocumentContext,
        backend: &Arc<dyn AiBackend>,
    ) -> Plan {
        let system_prompt = r#"You are the Kairo Planning Engine.
Your job is to break down the user's document-writing instruction into a list of 3 to 7 discrete, actionable execution steps.
Output ONLY a raw JSON array of objects with keys "step" (integer, 1-indexed) and "description" (string).
Do NOT include any markdown code blocks (e.g. ```json). Do NOT include any introductory or concluding text.

Example output:
[
  {"step": 1, "description": "Gather financial data for the Q2 table"},
  {"step": 2, "description": "Formulate Excel formulas for the average and total rows"},
  {"step": 3, "description": "Format numbers to currency and highlight top outliers"}
]
"#;

        let user_prompt = format!(
            "Instruction: {}\nSpecialist: {}\nDocument Type: {}\nDocument character count: {}",
            prompt,
            intent.doc_specialist.label(),
            doc_ctx.doc_kind.human_name(),
            doc_ctx.full_text.len()
        );

        // Run the LLM complete call.
        // We set a hard timeout via tokio::time::timeout just in case the LLM blocks or hangs.
        let result = tokio::time::timeout(
            std::time::Duration::from_millis(3000),
            backend.complete(system_prompt, &user_prompt),
        )
        .await;

        match result {
            Ok(Ok(response)) => {
                if let Some(plan) =
                    Self::parse_json_plan(&response, &intent.intent_type, &intent.doc_specialist)
                {
                    info!(
                        "📋 [PlanningEngine] Successfully parsed LLM plan with {} steps",
                        plan.steps.len()
                    );
                    return plan;
                }
                warn!("⚠️  [PlanningEngine] LLM returned invalid JSON. Falling back to heuristic plan.");
            }
            Ok(Err(e)) => {
                error!("❌ [PlanningEngine] LLM complete() error: {:?}. Falling back to heuristic plan.", e);
            }
            Err(_) => {
                warn!(
                    "⚠️  [PlanningEngine] LLM planning timed out. Falling back to heuristic plan."
                );
            }
        }

        Self::heuristic_plan(&intent.intent_type, &intent.doc_specialist, prompt)
    }

    /// Helper to clean codeblocks and parse JSON from the LLM response.
    fn parse_json_plan(
        response: &str,
        intent_type: &IntentType,
        doc_specialist: &DocSpecialist,
    ) -> Option<Plan> {
        let cleaned = response
            .trim()
            .trim_start_matches("```json")
            .trim_start_matches("```")
            .trim_end_matches("```")
            .trim();

        #[derive(Deserialize)]
        struct LlmStep {
            step: usize,
            description: String,
        }

        let llm_steps: Vec<LlmStep> = serde_json::from_str(cleaned).ok()?;

        if llm_steps.is_empty() {
            return None;
        }

        // Clamp number of steps between 3 and 7
        let steps: Vec<PlanStep> = llm_steps
            .into_iter()
            .take(7) // limit to max 7
            .enumerate()
            .map(|(idx, s)| PlanStep {
                index: idx + 1,
                description: s.description,
                status: StepStatus::Pending,
            })
            .collect();

        // Enforce min 3 steps by padding if necessary
        let mut steps = steps;
        while steps.len() < 3 {
            let next_idx = steps.len() + 1;
            steps.push(PlanStep {
                index: next_idx,
                description: "Format and verify final document output structure".to_string(),
                status: StepStatus::Pending,
            });
        }

        Some(Plan {
            steps,
            intent_type: intent_type.clone(),
            doc_specialist: doc_specialist.clone(),
        })
    }

    /// Pure Rust heuristic planning. Guaranteed < 1ms execution.
    pub fn heuristic_plan(
        intent_type: &IntentType,
        doc_specialist: &DocSpecialist,
        prompt: &str,
    ) -> Plan {
        info!(
            "📋 [PlanningEngine] Building heuristic plan for {:?} - {:?}",
            intent_type, doc_specialist
        );
        let steps = match (intent_type, doc_specialist) {
            (IntentType::Rewrite, DocSpecialist::Word) => vec![
                PlanStep {
                    index: 1,
                    description: "Extract current paragraph style and tone".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 2,
                    description: "Rewrite content to improve flow and readability".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 3,
                    description: "Align vocabulary and formatting with rest of document"
                        .to_string(),
                    status: StepStatus::Pending,
                },
            ],
            (IntentType::Summarise, _) => vec![
                PlanStep {
                    index: 1,
                    description: "Scan active section and extract core themes".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 2,
                    description: "Synthesize key arguments and factual claims".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 3,
                    description: "Format summary into highly readable bullet points".to_string(),
                    status: StepStatus::Pending,
                },
            ],
            (IntentType::Generate, DocSpecialist::Excel) => vec![
                PlanStep {
                    index: 1,
                    description: "Locate active coordinates and active sheet name".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 2,
                    description: "Determine formulas or clean tab-separated data layout"
                        .to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 3,
                    description: "Generate cell contents and verify mathematical syntax"
                        .to_string(),
                    status: StepStatus::Pending,
                },
            ],
            (IntentType::Generate, DocSpecialist::PowerPoint) => vec![
                PlanStep {
                    index: 1,
                    description: "Analyze active slide layout and presentation context".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 2,
                    description: "Draft punchy headlines and concise slide copy".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 3,
                    description: "Structure content to match visual PowerPoint constraints"
                        .to_string(),
                    status: StepStatus::Pending,
                },
            ],
            (IntentType::Explain, _) => vec![
                PlanStep {
                    index: 1,
                    description: "Parse term or code segment to explain".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 2,
                    description: "Formulate simple explanation with illustrative example"
                        .to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 3,
                    description: "Present inline annotation block for visual clarity".to_string(),
                    status: StepStatus::Pending,
                },
            ],
            _ => vec![
                PlanStep {
                    index: 1,
                    description: "Parse prompt syntax and analyze surrounding context".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 2,
                    description: "Formulate layout updates in a virtual overlay".to_string(),
                    status: StepStatus::Pending,
                },
                PlanStep {
                    index: 3,
                    description: "Verify compliance guidelines and inject clean results"
                        .to_string(),
                    status: StepStatus::Pending,
                },
            ],
        };

        Plan {
            steps,
            intent_type: intent_type.clone(),
            doc_specialist: doc_specialist.clone(),
        }
    }
}
