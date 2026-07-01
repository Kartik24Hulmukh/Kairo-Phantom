use crate::document_context::DocumentContext;
use tracing::info;

pub enum MemoryGranularity {
    Session,
    Turn,
    App,
    Global,
}

pub struct MemGasRouter;

impl MemGasRouter {
    /// Adaptive granularity selection based on prompt entropy/specificity.
    pub fn route(doc_ctx: &DocumentContext) -> Vec<String> {
        let mut granularities = Vec::new();

        // 1. App-level (Always included as baseline)
        granularities.push(format!(
            "app:{}",
            doc_ctx.app_name.as_deref().unwrap_or("unknown")
        ));

        // 2. Specific sub-context (Hierarchical)
        if let Some(app_name) = &doc_ctx.app_name {
            match app_name.to_lowercase().as_str() {
                "powerpnt.exe" | "powerpoint" => {
                    // Slide-type granularity
                    granularities.push("context:slide_type".to_string());
                }
                "winword.exe" | "word" => {
                    // Document-section granularity
                    granularities.push("context:section_type".to_string());
                }
                _ => {}
            }
        }

        // 3. Global (Fallback)
        granularities.push("global".to_string());

        info!("🧠 MemGAS: Routed to granularities: {:?}", granularities);
        granularities
    }
}
