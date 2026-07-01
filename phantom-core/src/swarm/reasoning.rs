// phantom-core/src/swarm/reasoning.rs
use crate::document_context::{DocKind, DocumentContext};
use crate::plugin::SwarmAgent;

pub struct ReasoningAgent;
impl SwarmAgent for ReasoningAgent {
    fn id(&self) -> &str {
        "reasoning"
    }
    fn name(&self) -> &str {
        "Reasoning & Logic Specialist"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!("{base}\n\n[DOCUMENT INTELLIGENCE]\n{doc_fragment}\n\n*** SWARM ROLE: REASONING & LOGIC AGENT ***\nBe precise. Output valid code or terminal commands. No fluff. Include error handling and edge cases.")
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        if matches!(doc_ctx.doc_kind, DocKind::CodeFile | DocKind::Terminal) {
            return 100;
        }
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("code") || p.contains("calculate") || p.contains("debug") {
            80
        } else {
            0
        }
    }
}
