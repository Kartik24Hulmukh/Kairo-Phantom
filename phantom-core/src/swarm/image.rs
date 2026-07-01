// phantom-core/src/swarm/image.rs
use crate::document_context::DocumentContext;
use crate::plugin::SwarmAgent;

pub struct ImageAgent;
impl SwarmAgent for ImageAgent {
    fn id(&self) -> &str {
        "image"
    }
    fn name(&self) -> &str {
        "Image Generation Specialist"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{base}\n\n[DOCUMENT INTELLIGENCE]\n{doc_fragment}\n\n*** SWARM ROLE: IMAGE GENERATION AGENT ***\n\
            You generate and optimize prompts for AI image generation.\n\
            When asked to add/create/generate an image:\n\
            1. Output exactly: [IMAGE: <detailed photorealistic prompt>] on its own line\n\
            2. For presentations (16:9): wide cinematic hero images with strong composition\n\
            3. For icons: 'flat vector icon, minimal, single color, white background'\n\
            4. For diagrams: 'clean technical diagram, labeled arrows, white background'\n\
            5. For infographics: 'modern data visualization, brand colors, clean layout'\n\
            6. For portraits/headshots: 'professional headshot, studio lighting, sharp focus'\n\
            Always follow [IMAGE: ...] with one brief caption sentence."
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("[image") || p.contains("generate image") || p.contains("create image") {
            return 100;
        }
        if p.contains("image")
            || p.contains("picture")
            || p.contains("photo")
            || p.contains("icon")
            || p.contains("illustration")
            || p.contains("diagram")
            || p.contains("visual")
            || p.contains("infographic")
            || p.contains("chart image")
            || p.contains("banner")
            || p.contains("thumbnail")
        {
            90
        } else {
            0
        }
    }
}
