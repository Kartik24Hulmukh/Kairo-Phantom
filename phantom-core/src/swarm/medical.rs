// phantom-core/src/swarm/medical.rs
use crate::document_context::DocumentContext;
use crate::plugin::SwarmAgent;

pub struct MedicalAgent;
impl SwarmAgent for MedicalAgent {
    fn id(&self) -> &str {
        "medical"
    }
    fn name(&self) -> &str {
        "Medical Documentation Specialist"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!("{base}\n\n[DOCUMENT INTELLIGENCE]\n{doc_fragment}\n\n*** SWARM ROLE: MEDICAL AGENT ***\n\
            You assist with medical documentation (NOT diagnosis). Your guidelines:\n\
            - Use standard clinical terminology (ICD-10 codes where appropriate)\n\
            - SOAP format for clinical notes: Subjective, Objective, Assessment, Plan\n\
            - Medication documentation: drug name (brand/generic), dose, route, frequency\n\
            - Always flag: 'This is documentation assistance only — verify with licensed professional'\n\
            - Patient summaries: concise, chronological, include chief complaint first\n\
            - Use standard abbreviations: c/o (complains of), h/o (history of), PMH, HPI, ROS\n\
            - Lab values: include units and reference ranges")
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("patient")
            || p.contains("diagnosis")
            || p.contains("clinical")
            || p.contains("soap")
            || p.contains("medication")
            || p.contains("prescription")
            || p.contains("medical")
            || p.contains("doctor")
            || p.contains("hospital")
            || p.contains("symptom")
            || p.contains("treatment")
        {
            90
        } else {
            0
        }
    }
}
