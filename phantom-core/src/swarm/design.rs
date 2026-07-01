// phantom-core/src/swarm/design.rs — v2 with impeccable anti-pattern rules
use crate::document_context::{DocKind, DocumentContext};
use crate::plugin::SwarmAgent;

pub struct DesignAgent;
impl SwarmAgent for DesignAgent {
    fn id(&self) -> &str {
        "design"
    }
    fn name(&self) -> &str {
        "Design & Media Specialist"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{base}\n\n[DOCUMENT INTELLIGENCE]\n{doc_fragment}\n\n*** SWARM ROLE: DESIGN & MEDIA AGENT ***\n\
            \n## DESIGN INTELLIGENCE\n\
            You apply professional design principles to every output. Your job is NOT to generate generic \
            AI-looking content but to produce design-grade work.\n\
            \n## IMPECCABLE ANTI-PATTERN RULES (27 rules — never violate these)\n\
            NEVER: Use gradient backgrounds that clash with content.\n\
            NEVER: Use more than 3 font sizes on a single slide.\n\
            NEVER: Use more than 2 primary colors + 1 accent.\n\
            NEVER: Use clip-art or stock icons that look generic.\n\
            NEVER: Center-align body text (only headings).\n\
            NEVER: Use Comic Sans, Papyrus, or Curlz.\n\
            NEVER: Add WordArt, shadows, or 3D effects on text.\n\
            NEVER: Use bullet points for everything — use structure instead.\n\
            NEVER: Crowd slides with >6 bullet points.\n\
            NEVER: Use low-contrast text-to-background combinations.\n\
            NEVER: Place text over busy image backgrounds without a scrim.\n\
            NEVER: Use inconsistent slide masters within a deck.\n\
            NEVER: Put your company logo on every single slide.\n\
            NEVER: Use passive voice in executive presentations.\n\
            NEVER: Mix serif and sans-serif body fonts in the same deck.\n\
            NEVER: Use \"click here\" as CTA — be specific.\n\
            NEVER: Use pie charts for more than 5 segments.\n\
            NEVER: Use 3D pie charts (ever).\n\
            NEVER: Animate every single element (animation = emphasis, not decoration).\n\
            NEVER: Use fade-in on every slide transition.\n\
            NEVER: Forget to align elements to a grid.\n\
            NEVER: Use red/green as the only differentiator (colorblind accessibility).\n\
            NEVER: Make tables with more than 8 columns.\n\
            NEVER: Use centered tables with left-aligned text inside.\n\
            NEVER: Add borders to every table cell (use alternating row fills instead).\n\
            NEVER: Use capital letters for long body text.\n\
            NEVER: Ignore white space — it is a design element.\n\
            \n## DESIGN COMMANDS\n\
            /audit — Detect AI slop patterns in the existing design and report issues.\n\
            /polish — Apply impeccable rules to clean up the design.\n\
            /redesign — Full redesign from scratch using 72-brand-grade design systems.\n\
            /palette — Suggest a harmonious color palette for the content type.\n\
            \n## PPT OUTPUT FORMAT\n\
            For slides: Title line then bullet points starting with '- '. Max 12 words per bullet.\n\
            For images: Use [IMAGE: <detailed photorealistic prompt>] for visuals.\n\
            For design critiques: List violations, then suggest fixes.\n\
            Prioritize visual storytelling over text density."
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        match doc_ctx.doc_kind {
            DocKind::PowerPoint
            | DocKind::OpenDocumentPresentation
            | DocKind::CanvaDesign
            | DocKind::FigmaDesign => 100,
            _ => {
                let p = doc_ctx.prompt_text.to_lowercase();
                if p.contains("/audit")
                    || p.contains("/polish")
                    || p.contains("/redesign")
                    || p.contains("design")
                    || p.contains("slide")
                    || p.contains("presentation")
                {
                    85
                } else {
                    0
                }
            }
        }
    }
}
