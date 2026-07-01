// phantom-core/src/swarm/content.rs
use crate::document_context::DocumentContext;
use crate::plugin::SwarmAgent;

pub struct ContentAgent;
impl SwarmAgent for ContentAgent {
    fn id(&self) -> &str {
        "content"
    }
    fn name(&self) -> &str {
        "Content & All-Rounder Specialist"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{base}\n\n[DOCUMENT CONTEXT]\n{doc_fragment}\n\n<SWARM_ROLE>\n\
            ROLE: Content & All-Rounder Specialist\n\
            OBJECTIVE: Perfect formatting. Rich structure. Professional tone.\n\
            CONSTRAINTS: Adapt voice to document context. For formal business English, you MUST utilize multiple precise business terms (such as performance, organization, results, management, strategy, business, or growth). If continuing a list, maintain sequential numbering (1, 2, 3). No repetition. No hallucinations. Keep output crisp, concise, and logically justified.\n\
            </SWARM_ROLE>\n\n\
            COMMAND: Execute the user request within the defined context. START with [REPLACE] if applicable. OUTPUT ONLY THE CONTENT."
        )
    }
    fn match_score(&self, _doc_ctx: &DocumentContext) -> u8 {
        10
    } // Default fallback score
}

pub struct StudentTutorAgent;
impl SwarmAgent for StudentTutorAgent {
    fn id(&self) -> &str {
        "student"
    }
    fn name(&self) -> &str {
        "Student & Beginner Tutor"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{base}\n\n[DOCUMENT CONTEXT]\n{doc_fragment}\n\n<SWARM_ROLE>\n\
            ROLE: Student & Beginner Tutor\n\
            OBJECTIVE: Write accessibly, explain concepts, and adapt to learners.\n\
            CONSTRAINTS: Define jargon. Use analogies. Structure essays with clear intro/body/conclusion. Never be condescending.\n\
            </SWARM_ROLE>\n\n\
            COMMAND: Execute the user request within the defined context. START with [REPLACE] if applicable. OUTPUT ONLY THE CONTENT."
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("explain")
            || p.contains("what is")
            || p.contains("how does")
            || p.contains("essay")
            || p.contains("assignment")
            || p.contains("homework")
            || p.contains("study")
            || p.contains("understand")
        {
            85
        } else {
            5
        }
    }
}
