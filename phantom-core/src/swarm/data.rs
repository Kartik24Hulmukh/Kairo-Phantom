// phantom-core/src/swarm/data.rs
use crate::document_context::{DocKind, DocumentContext};
use crate::plugin::SwarmAgent;

pub struct DataAnalystAgent;
impl SwarmAgent for DataAnalystAgent {
    fn id(&self) -> &str {
        "data"
    }
    fn name(&self) -> &str {
        "Data & Spreadsheet Analyst"
    }
    fn build_system_prompt(&self, doc_ctx: &DocumentContext) -> String {
        let base = crate::ai::KAIRO_SYSTEM_PROMPT;
        let doc_fragment = doc_ctx.to_system_prompt_fragment();
        format!(
            "{base}\n\n[DOCUMENT CONTEXT]\n{doc_fragment}\n\n<SWARM_ROLE>\n\
            ROLE: Data & Spreadsheet Analyst\n\
            OBJECTIVE: Excel formulas, pivot tables, and data summaries.\n\
            CONSTRAINTS: Correct formula syntax (=VLOOKUP, etc.). Explain patterns clearly. Use bullet points for summaries. Describe best chart types.\n\
            CRITICAL: If asked to create a PivotTable, you MUST output a single JSON array containing one object with: \"source_range\" (e.g. \"Sheet1!A1:E20\"), \"rows\" (list of column names), \"columns\" (list of column names), \"values\" (list of column names), and optionally \"target_sheet\" (string name of the new sheet to create the pivot table on, e.g. \"PivotTable\"). Do NOT output any freeform text or code block formatting around the JSON, just output the JSON array directly like: [[{{\"source_range\": \"Sheet1!A1:D20\", \"rows\": [[ \"Category\" ]], \"columns\": [[]], \"values\": [[ \"Sales\" ]], \"target_sheet\": \"PivotTable\"}}]].\n\
            If asked to create a Chart, you MUST output a single JSON array containing one object with: \"source_range\" (e.g. \"Sheet1!A1:B10\"), \"chart_type\" (one of \"bar\", \"line\", \"pie\", \"column\", \"scatter\"), \"title\" (chart title), and optionally \"target_sheet\". Do NOT output any freeform text, just output the JSON array directly.\n\
            </SWARM_ROLE>\n\n\
            COMMAND: Execute the user request within the defined context. START with [REPLACE] if applicable. OUTPUT ONLY THE CONTENT."
        )
    }
    fn match_score(&self, doc_ctx: &DocumentContext) -> u8 {
        if matches!(
            doc_ctx.doc_kind,
            DocKind::ExcelSpreadsheet | DocKind::OpenDocumentSpreadsheet
        ) {
            return 100;
        }
        let p = doc_ctx.prompt_text.to_lowercase();
        if p.contains("formula")
            || p.contains("excel")
            || p.contains("spreadsheet")
            || p.contains("pivot")
            || p.contains("vlookup")
            || p.contains("chart")
        {
            75
        } else {
            0
        }
    }
}
