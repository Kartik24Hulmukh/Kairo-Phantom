// phantom-core/src/swarm/engineer.rs
use crate::document_context::{DocKind, DocumentContext};
use crate::plugin::SwarmAgent;

pub struct EngineerAgent;
impl SwarmAgent for EngineerAgent {
    fn id(&self) -> &str {
        "engineer"
    }
    fn name(&self) -> &str {
        "Engineer & Developer Specialist"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{base}\n\n[DOCUMENT CONTEXT]\n{doc_fragment}\n\n<SWARM_ROLE>\n\
            ROLE: Engineer & Developer Specialist\n\
            OBJECTIVE: Technical documentation, READMEs, commit messages, and API docs.\n\
            CONSTRAINTS: Precise language. Exact types. Real examples. Use markdown headings/fences. Follow Conventional Commits for messages.\n\
            </SWARM_ROLE>\n\n\
            COMMAND: Execute the user request within the defined context. START with [REPLACE] if applicable. OUTPUT ONLY THE CONTENT."
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        if matches!(
            doc_ctx.doc_kind,
            DocKind::CodeFile | DocKind::Markdown | DocKind::Terminal
        ) {
            let p = doc_ctx.prompt_text.to_lowercase();
            if p.contains("readme")
                || p.contains("doc")
                || p.contains("api")
                || p.contains("commit")
                || p.contains("changelog")
            {
                return 95;
            }
            return 70;
        }
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("function")
            || p.contains("implement")
            || p.contains("refactor")
            || p.contains("architecture")
            || p.contains("deploy")
        {
            60
        } else {
            0
        }
    }
}
