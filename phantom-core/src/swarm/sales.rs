// phantom-core/src/swarm/sales.rs
use crate::document_context::DocumentContext;
use crate::plugin::SwarmAgent;

pub struct SalesAgent;
impl SwarmAgent for SalesAgent {
    fn id(&self) -> &str {
        "sales"
    }
    fn name(&self) -> &str {
        "Sales & Marketing Specialist"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{base}\n\n[DOCUMENT INTELLIGENCE]\n{doc_fragment}\n\n*** SWARM ROLE: SALES AGENT ***\n\
            You are a senior sales and marketing copywriter. Your guidelines:\n\
            - Write with conviction and urgency, not desperation\n\
            - Lead with value, not features: 'you get X' not 'we have Y'\n\
            - Use AIDA (Attention, Interest, Desire, Action) for cold outreach\n\
            - Subject lines: under 50 chars, curiosity-driven, no spam triggers\n\
            - CTAs: one clear action, time-boxed if possible ('schedule a 15-min call this week')\n\
            - Social proof: weave in results ('saved $2M', 'cut onboarding by 40%') naturally\n\
            - Remove corporate jargon; replace with plain, powerful English"
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("sales")
            || p.contains("proposal")
            || p.contains("pitch")
            || p.contains("outreach")
            || p.contains("email") && p.contains("cold")
            || p.contains("crm")
            || p.contains("marketing")
            || p.contains("campaign")
            || p.contains("copy")
            || p.contains("cta")
            || p.contains("funnel")
        {
            85
        } else {
            0
        }
    }
}
