//! Document-aware prompt builder
//! ================================
//! Builds rich, structured LLM prompts based on parsed document context
//! (from sidecar) and the user's // command. The prompt includes:
//!   - Document structure (headings, active section, surrounding paragraphs)
//!   - Format-specific schema instructions (DocxOperation, ExcelOperation, etc.)
//!   - Operation constraints (no freeform prose, JSON output only)
//!
//! The LLM is forced to output ONLY valid typed operations — never raw prose.

use crate::sidecar_client::{DocFormat, DocxContext, ExcelContext};
use serde_json::Value;

// ─── System prompts per document format ──────────────────────────────────────

const DOCX_SYSTEM: &str = r#"You are Kairo Document Engine. You modify Microsoft Word documents by outputting ONLY valid JSON DocxOperation arrays.

## OUTPUT CONTRACT
You MUST output a JSON array of DocxOperation objects. No preamble. No prose. No markdown. Just valid JSON.
REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].

```typescript
type DocxOperation = {
  action: "insert_after_heading" | "insert_paragraph" | "replace_paragraph" | "append" | "insert_table" | "delete_paragraph";
  heading_text?: string;   // for insert_after_heading: heading to find
  style: string;           // Word style: "Normal" | "Heading1" | "Heading2" | "ListBullet" | "ListNumber" | "Quote"
  content: string | string[]; // text to insert (string or array of strings; use "" or [] for delete_paragraph)
  index?: number;          // for insert_paragraph/replace_paragraph/delete_paragraph: paragraph index
  rows?: string[][];       // for insert_table: [[col1, col2], [val1, val2]]
};
```

## RULES
- Use "ListBullet" style for bullet points, never "- text" in Normal style
- Use "Heading1"/"Heading2" for section titles, never bold Normal
- For summaries: use multiple "append" operations with "ListBullet" style
- Preserve existing content — only generate content for the requested action
- When replying to a user prompt (starts with "//") at index X, you MUST clear or delete that prompt paragraph (e.g. using "replace_paragraph" with content: "" or "delete_paragraph" at index X).
- All string values MUST be on a single line in JSON. Do NOT output raw newlines inside JSON string values; use "\n" or split the content into separate operations.
- CRITICAL: A section consists of a heading and all the body paragraphs that follow it until the next heading. When reordering sections, you MUST reorder BOTH the headings and all their corresponding body paragraphs/content. NEVER leave body paragraphs mismatched under the wrong headings.
- CRITICAL: For reordering sections, swapping text, or restructuring existing paragraphs, you MUST use "replace_paragraph" on the existing indices to swap their content and style. NEVER use "insert_paragraph" or "delete_paragraph" for reordering.
- CRITICAL: When reordering, you MUST output the "replace_paragraph" operations in ascending order of their target "index" (e.g., from index 0 up to the last index), covering every single paragraph of the sections being reordered.
- If you must delete, use "delete_paragraph" (index is relative to the original document).
- NEVER include [MCP:...] or any non-JSON in your output

## EXAMPLE 1
User: "// write a 3-point executive summary after the Introduction"
Output: [
  {"action":"insert_after_heading","heading_text":"Introduction","style":"Heading2","content":"Executive Summary"},
  {"action":"insert_after_heading","heading_text":"Executive Summary","style":"ListBullet","content":["Point one about the topic","Point two with key insight","Point three with recommendation"]}
]

## EXAMPLE 2 (Reordering/Swapping sections)
User: "// Reorder the document to be: Introduction -> Methodology -> Results"
Original Paragraphs:
[Index 0] [Heading1] Results
[Index 1] [Normal] Results body text
[Index 2] [Heading1] Introduction
[Index 3] [Normal] Intro body text
[Index 4] [Heading1] Methodology
[Index 5] [Normal] Method body text

Output: [
  {"action":"replace_paragraph","index":0,"style":"Heading1","content":"Introduction"},
  {"action":"replace_paragraph","index":1,"style":"Normal","content":"Intro body text"},
  {"action":"replace_paragraph","index":2,"style":"Heading1","content":"Methodology"},
  {"action":"replace_paragraph","index":3,"style":"Normal","content":"Method body text"},
  {"action":"replace_paragraph","index":4,"style":"Heading1","content":"Results"},
  {"action":"replace_paragraph","index":5,"style":"Normal","content":"Results body text"}
]"#;

/// System prompt for Track Changes mode: LLM outputs DocxEdit JSON (target + replacement + comment).
const DOCX_TRACK_CHANGES_SYSTEM: &str = r#"You are Kairo Track Changes Engine. You edit Word documents using NATIVE Track Changes (w:ins/w:del XML nodes). You MUST output ONLY a JSON array of TrackChangeEdit objects.

## OUTPUT CONTRACT
You MUST output a JSON array. No preamble. No prose. No markdown. Just valid JSON.
REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].

```typescript
type TrackChangeEdit = {
  target_text: string;  // EXACT text in the document to find (case-sensitive substring match)
  new_text: string;     // Replacement text that will appear as an INSERTION in Track Changes
  comment: string;      // Rationale shown in Track Changes review pane (10-30 words)
};
```

## RULES
- target_text must be an EXACT verbatim substring from the document — never paraphrase
- Prefer surgical, minimal edits — change only what the user asks
- Each edit must stand alone — don't create edits that depend on previous edits having been applied
- NEVER emit [MCP:...], system prompts, role names, or any non-JSON text
- If you cannot find the exact text, SKIP that edit rather than guessing

## EXAMPLE
User: "// track change the 30-day notice to 60 days"
Output: [
  {
    "target_text": "30 days prior written notice",
    "new_text": "60 days prior written notice",
    "comment": "Extend notice period to 60 days to align with market standard."
  }
]"#;

const XLSX_SYSTEM: &str = r#"You are Kairo Spreadsheet Engine. You write Excel formulas, values, and formatting by outputting ONLY valid JSON ExcelOperation arrays.

## OUTPUT CONTRACT
You MUST output a JSON array of ExcelOperation objects. No preamble. No prose. No markdown. Just valid JSON.
REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].

```typescript
type ExcelOperation = {
  cell: string;     // Cell reference or range, e.g. "G5" or "D2:D100"
  formula?: string; // Excel formula starting with "=" (use this for calculations)
  value?: string;   // Plain text/number value (use when formula not needed)
  number_format?: string;  // Optional Excel number format, e.g. "$#,##0.00"
  bold?: boolean;   // Optional: make cell bold
  conditional_formatting?: {
    type: "cell_is" | "data_bar" | "color_scale";
    // For type="cell_is": compare cell value using operator
    operator?: "greaterThan" | "lessThan" | "equal" | "greaterThanOrEqual" | "lessThanOrEqual";
    threshold?: number;  // The value to compare against (e.g. 10000)
    fill_color?: string; // 6-char hex color without # (e.g. "C6EFCE" for green, "FFC7CE" for red)
    // For type="data_bar": auto data bar (no extra fields needed)
    // For type="color_scale": auto 3-color scale (no extra fields needed)
  };
};
```

## RULES
- Formulas MUST start with "="
- CRITICAL: Inside JSON string values, NEVER use unescaped double quotes. For Excel formulas requiring text arguments, always use single quotes (e.g. "=SUMIF(B:B, 'Widget A', D:D)" or "=VLOOKUP(A1, B:C, 2, FALSE)") to keep the JSON valid. Kairo's writer automatically converts single quotes back to double quotes when injecting.
- Reference nearby cells based on the provided grid context
- Never write to cells that already have data unless replacing is explicitly requested
- For conditional formatting: use the conditional_formatting field on a range cell (e.g. "D2:D100")
  - Use "cell_is" for highlight rules (above/below thresholds)
  - Use "data_bar" for data bars
  - Use "color_scale" for color scales
  - Do NOT use IF formulas to simulate conditional formatting
- When answering a prompt starting with "//" in a specific cell (e.g. cell X), you MUST clear that cell by outputting an operation: {"cell":"X","value":""}
- For data analysis, summaries, or text responses, write the analysis text to a nearby empty cell (e.g., cell X + 1 row or column) and output a separate operation to clear the prompt cell.
- NEVER include prose or explanations outside the JSON array — JSON only

## EXAMPLE 1 — Formula
User: "// calculate 5% commission on sales in column C, put result in G5"
Output: [{"cell":"G5","formula":"=C5*0.05","value":""}]

## EXAMPLE 2 — Conditional Formatting
User: "// highlight revenue column D2:D100 green if above 10000, red if below 5000, add data bars to E2:E100"
Output: [
  {"cell":"D2:D100","conditional_formatting":{"type":"cell_is","operator":"greaterThan","threshold":10000,"fill_color":"C6EFCE"}},
  {"cell":"D2:D100","conditional_formatting":{"type":"cell_is","operator":"lessThan","threshold":5000,"fill_color":"FFC7CE"}},
  {"cell":"E2:E100","conditional_formatting":{"type":"data_bar"}}
]

## EXAMPLE 3 — Conversational / Data Analysis
User: "// Analyze this sales data and identify: (1) the best-performing product by revenue, (2) the top region, and (3) write a SUMIF formula to total Widget A revenue."
Output: [
  {"cell":"F1","value":""},
  {"cell":"F2","value":"Analysis: Best Product is Widget A ($28,100). Top Region is North ($23,700). SUMIF formula added in F3."},
  {"cell":"F3","formula":"=SUMIF(B2:B6,B2,D2:D6)"}
]"#;

const PPTX_SYSTEM: &str = r#"You are Kairo Presentation Engine. You edit PowerPoint slides by outputting ONLY valid JSON SlideOperation arrays.

## OUTPUT CONTRACT
You MUST output a JSON array of SlideOperation objects. No preamble. No prose. No markdown. Just valid JSON.
REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].

```typescript
type SlideOperation = {
  slide_index: number;     // Zero-based slide index (ignored for add_new, but must be present — use 0)
  add_new?: boolean;       // true = append a brand new slide; false/omit = update existing slide
  title?: string;          // Slide title — REQUIRED when add_new=true; max 7 words
  bullets: string[];       // Bullet text — MAX 7 WORDS EACH, MAX 5 bullets per slide
  layout_index?: number;   // Layout for new slides: 0=Title Only, 1=Title+Content (default), 5=Blank
  shape_id?: number;       // Shape ID (from slide inventory) — only for update mode
};
```

## RULES
- MAXIMUM 7 words per title — trim mercilessly
- MAXIMUM 7 words per bullet — cut mercilessly, every word must earn its place
- MAXIMUM 5 bullets per slide
- For new presentations: use add_new:true for EVERY slide, including the first
- For existing slide edits: omit add_new (or use false), set correct slide_index
- Never touch slides not in the operation list
- Use active voice. Use concrete nouns. Avoid "very", "really", "that is"
- NEVER include prose or explanations — JSON only

## EXAMPLE — Create 3-slide deck
User: "// create a 3-slide deck on cloud cost optimization"
Output: [
  {"slide_index":0,"add_new":true,"title":"Cloud Cost Optimization","bullets":["Reduce spend by 40%","Eliminate idle resources","Automate rightsizing policies"],"layout_index":0},
  {"slide_index":0,"add_new":true,"title":"Key Cost Drivers","bullets":["Oversized compute instances","Unused storage volumes","Data egress charges","License sprawl"],"layout_index":1},
  {"slide_index":0,"add_new":true,"title":"Action Plan","bullets":["Audit all running workloads","Tag resources by cost center","Set budget alerts","Weekly review cadence"],"layout_index":1}
]

## EXAMPLE — Update existing slide
User: "// rewrite slide 2 to focus on cost savings, 4 bullets"
Output: [{"slide_index":1,"bullets":["Cut infrastructure costs by 40%","Eliminate redundant toolchain overhead","Automate deployment saves 20 hours","ROI positive within 6 months"]}]"#;

// ─── Context formatters ───────────────────────────────────────────────────────

/// Strip Kairo command prefix (// //! /// //?) so the LLM sees only the instruction.
fn strip_prompt_prefix(command: &str) -> &str {
    let s = command.trim();
    // Strip //!, ///, //?, // in order (longest first)
    for prefix in &["//!", "///", "//?", "//"] {
        if let Some(rest) = s.strip_prefix(prefix) {
            return rest.trim();
        }
    }
    s
}

/// Format DOCX context for LLM prompt
pub fn format_docx_context(ctx: &DocxContext, command: &str) -> String {
    let command = strip_prompt_prefix(command);
    let mut parts = vec![];

    // Heading structure
    if !ctx.headings.is_empty() {
        parts.push("## Document Structure".to_string());
        for h in &ctx.headings {
            let indent = "  ".repeat((h.level as usize).saturating_sub(1));
            parts.push(format!("{}{} H{}: {}", indent, "→", h.level, h.text));
        }
    }

    // Format text as a list of paragraphs with indices and styles
    if !ctx.paragraphs.is_empty() {
        parts.push(
            "\n## Document Paragraphs (preview with indices for editing/deleting)".to_string(),
        );
        let mut current_chars = 0;
        for p in &ctx.paragraphs {
            let formatted = format!("[Index {}] [{}] {}\n", p.index, p.style, p.text);
            if current_chars + formatted.chars().count() > 2000 {
                parts.push("...[truncated]".to_string());
                break;
            }
            current_chars += formatted.chars().count();
            parts.push(formatted.trim_end().to_string());
        }
    } else {
        let text_preview = if ctx.full_text.chars().count() > 2000 {
            let cut: String = ctx.full_text.chars().take(2000).collect();
            format!("{cut}...[truncated]")
        } else {
            ctx.full_text.clone()
        };
        parts.push("\n## Document Content (preview)".to_string());
        parts.push(text_preview);
    }

    parts.push(format!("\n## User Command\n{command}"));
    parts.join("\n")
}

/// Format Excel context for LLM prompt
pub fn format_xlsx_context(ctx: &ExcelContext, command: &str) -> String {
    let command = strip_prompt_prefix(command);
    let mut parts = vec![];

    parts.push(format!("## Active Cell: {}", ctx.active_cell));
    parts.push(format!("## Sheet: {}", ctx.sheet_name));

    // Headers
    if !ctx.headers.is_empty() {
        let header_str = ctx
            .headers
            .iter()
            .map(|(col, name)| format!("{col}={name}"))
            .collect::<Vec<_>>()
            .join(", ");
        parts.push(format!("## Column Headers: {header_str}"));
    }

    // Grid (show surrounding cells)
    parts.push("## Surrounding Data (10x10 grid)".to_string());
    for row in &ctx.grid {
        let row_str = row
            .iter()
            .map(|c| {
                if c.is_active {
                    format!("[{}:ACTIVE]", c.r#ref)
                } else if !c.formula.is_empty() {
                    format!("{}:{}", c.r#ref, c.formula)
                } else if !c.value.is_empty() {
                    format!("{}:{}", c.r#ref, c.value)
                } else {
                    format!("{}:empty", c.r#ref)
                }
            })
            .collect::<Vec<_>>()
            .join(" | ");
        parts.push(row_str);
    }

    parts.push(format!("\n## User Command\n{command}"));
    parts.join("\n")
}

/// Format generic document context (for PDF, TXT, MD)
pub fn format_generic_context(data: &Value, command: &str) -> String {
    let command = strip_prompt_prefix(command);
    let full_text = data["full_text"].as_str().unwrap_or("");
    // UTF-8 safe truncation
    let preview = if full_text.chars().count() > 3000 {
        let cut: String = full_text.chars().take(3000).collect();
        format!("{cut}...[truncated]")
    } else {
        full_text.to_string()
    };

    format!("## Document Content\n{preview}\n\n## User Command\n{command}")
}

// ─── Prompt builder ───────────────────────────────────────────────────────────

pub struct DocumentPrompt {
    pub system: String,
    pub user: String,
    pub is_structured: bool, // true = LLM must output JSON operations, false = prose
}

impl DocumentPrompt {
    /// Build a structured prompt for DOCX manipulation.
    pub fn for_docx(
        ctx: &DocxContext,
        command: &str,
        file_path: &str,
        distilled_memories: &str,
    ) -> Self {
        let app_context = format!(
            "=== APP CONTEXT ===\nApplication Name: Microsoft Word\nApplication Type: Word Processor\nFile Path: {file_path}"
        );

        let mut doc_parts = vec![];
        if !ctx.headings.is_empty() {
            doc_parts.push("## Document Structure".to_string());
            for h in &ctx.headings {
                let indent = "  ".repeat((h.level as usize).saturating_sub(1));
                doc_parts.push(format!("{}{} H{}: {}", indent, "→", h.level, h.text));
            }
        }

        if !ctx.paragraphs.is_empty() {
            doc_parts.push(
                "\n## Document Paragraphs (preview with indices for editing/deleting)".to_string(),
            );
            let mut current_chars = 0;
            for p in &ctx.paragraphs {
                let formatted = format!("[Index {}] [{}] {}\n", p.index, p.style, p.text);
                if current_chars + formatted.chars().count() > 2000 {
                    doc_parts.push("...[truncated]".to_string());
                    break;
                }
                current_chars += formatted.chars().count();
                doc_parts.push(formatted.trim_end().to_string());
            }
        } else {
            let text_preview = if ctx.full_text.chars().count() > 2000 {
                let cut: String = ctx.full_text.chars().take(2000).collect();
                format!("{cut}...[truncated]")
            } else {
                ctx.full_text.clone()
            };
            doc_parts.push("\n## Document Content (preview)".to_string());
            doc_parts.push(text_preview);
        }
        let doc_context = format!("=== DOCUMENT CONTEXT ===\n{}", doc_parts.join("\n"));

        let mem_str = if distilled_memories.is_empty() {
            "No writing preferences learned yet. Use professional defaults."
        } else {
            distilled_memories
        };
        let memory_context =
            format!("=== MEMORY CONTEXT ===\nUser Writing Preferences:\n{mem_str}");

        let classification =
            "=== INTENT CLASSIFICATION ===\nIntent Classification: Document Operation Generation";

        let json_reminder = "REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].";

        let user_command = format!("User Instruction: {}\nGenerate the JSON response conforming to the DocxResponse schema. Remember: ONLY the raw JSON output is allowed. No markdown fences.", strip_prompt_prefix(command));

        let user_prompt = format!(
            "{app_context}\n\n{doc_context}\n\n{memory_context}\n\n{classification}\n\n{json_reminder}\n\n{user_command}"
        );

        DocumentPrompt {
            system: DOCX_SYSTEM.to_string(),
            user: user_prompt,
            is_structured: true,
        }
    }

    /// Build a structured prompt for Excel manipulation.
    pub fn for_xlsx(
        ctx: &ExcelContext,
        command: &str,
        file_path: &str,
        distilled_memories: &str,
    ) -> Self {
        let app_context = format!(
            "=== APP CONTEXT ===\nApplication Name: Microsoft Excel\nApplication Type: Spreadsheet\nFile Path: {file_path}"
        );

        let mut doc_parts = vec![];
        doc_parts.push(format!("Active Cell: {}", ctx.active_cell));
        doc_parts.push(format!("Sheet: {}", ctx.sheet_name));

        if !ctx.headers.is_empty() {
            let mut h_keys: Vec<&String> = ctx.headers.keys().collect();
            h_keys.sort();
            let header_str = h_keys
                .iter()
                .map(|col| {
                    format!(
                        "{}={}",
                        col,
                        ctx.headers.get(*col).unwrap_or(&String::new())
                    )
                })
                .collect::<Vec<_>>()
                .join(", ");
            doc_parts.push(format!("Column Headers: {header_str}"));
        }

        doc_parts.push("Surrounding Data (10x10 grid)".to_string());
        for row in &ctx.grid {
            let row_str = row
                .iter()
                .map(|c| {
                    if c.is_active {
                        format!("[{}:ACTIVE]", c.r#ref)
                    } else if !c.formula.is_empty() {
                        format!("{}:{}", c.r#ref, c.formula)
                    } else if !c.value.is_empty() {
                        format!("{}:{}", c.r#ref, c.value)
                    } else {
                        format!("{}:empty", c.r#ref)
                    }
                })
                .collect::<Vec<_>>()
                .join(" | ");
            doc_parts.push(row_str);
        }
        let doc_context = format!("=== DOCUMENT CONTEXT ===\n{}", doc_parts.join("\n"));

        let mem_str = if distilled_memories.is_empty() {
            "No writing preferences learned yet. Use professional defaults."
        } else {
            distilled_memories
        };
        let memory_context =
            format!("=== MEMORY CONTEXT ===\nUser Writing Preferences:\n{mem_str}");

        let classification = "=== INTENT CLASSIFICATION ===\nIntent Classification: Spreadsheet Formula / Data Operation Generation";

        let json_reminder = "REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].";

        let user_command = format!("User Instruction: {}\nGenerate the JSON response conforming to the ExcelResponse schema. Remember: ONLY the raw JSON output is allowed. No markdown fences.", strip_prompt_prefix(command));

        let user_prompt = format!(
            "{app_context}\n\n{doc_context}\n\n{memory_context}\n\n{classification}\n\n{json_reminder}\n\n{user_command}"
        );

        DocumentPrompt {
            system: XLSX_SYSTEM.to_string(),
            user: user_prompt,
            is_structured: true,
        }
    }

    /// Build a structured prompt for PowerPoint manipulation.
    pub fn for_pptx(
        data: &Value,
        command: &str,
        file_path: &str,
        distilled_memories: &str,
    ) -> Self {
        let app_context = format!(
            "=== APP CONTEXT ===\nApplication Name: Microsoft PowerPoint\nApplication Type: Presentation\nFile Path: {file_path}"
        );

        let slide_info = serde_json::to_string_pretty(data).unwrap_or_default();
        let doc_context = format!("=== DOCUMENT CONTEXT ===\nSlide Inventory\n{slide_info}");

        let mem_str = if distilled_memories.is_empty() {
            "No writing preferences learned yet. Use professional defaults."
        } else {
            distilled_memories
        };
        let memory_context =
            format!("=== MEMORY CONTEXT ===\nUser Writing Preferences:\n{mem_str}");

        let classification = "=== INTENT CLASSIFICATION ===\nIntent Classification: Presentation Slide Operation Generation";

        let json_reminder = "REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].";

        let user_command = format!("User Instruction: {}\nGenerate the JSON response conforming to the SlideOperation schema. Remember: ONLY the raw JSON output is allowed. No markdown fences.", strip_prompt_prefix(command));

        let user_prompt = format!(
            "{app_context}\n\n{doc_context}\n\n{memory_context}\n\n{classification}\n\n{json_reminder}\n\n{user_command}"
        );

        DocumentPrompt {
            system: PPTX_SYSTEM.to_string(),
            user: user_prompt,
            is_structured: true,
        }
    }

    /// Build a Track Changes prompt for surgical DOCX editing.
    /// Used with CommandMode::TrackChanges — LLM outputs TrackChangeEdit JSON.
    pub fn for_docx_track_changes(
        ctx: &crate::sidecar_client::DocxContext,
        command: &str,
        file_path: &str,
        distilled_memories: &str,
    ) -> Self {
        let app_context = format!(
            "=== APP CONTEXT ===\nApplication Name: Microsoft Word\nApplication Type: Word Processor (Track Changes Mode)\nFile Path: {file_path}"
        );

        let full_text = if ctx.full_text.chars().count() > 4000 {
            let cut: String = ctx.full_text.chars().take(4000).collect();
            format!("{cut}...[truncated — use target_text from visible text only]")
        } else {
            ctx.full_text.clone()
        };

        let mut doc_parts = vec![];
        if !ctx.headings.is_empty() {
            doc_parts.push("## Document Headings (for navigation reference)".to_string());
            for h in &ctx.headings {
                let indent = "  ".repeat((h.level as usize).saturating_sub(1));
                doc_parts.push(format!("{}→ H{}: {}", indent, h.level, h.text));
            }
        }
        doc_parts
            .push("\n## Full Document Text (find exact substrings for target_text)".to_string());
        doc_parts.push(full_text);
        let doc_context = format!("=== DOCUMENT CONTEXT ===\n{}", doc_parts.join("\n"));

        let mem_str = if distilled_memories.is_empty() {
            "No writing preferences learned yet. Use professional defaults."
        } else {
            distilled_memories
        };
        let memory_context =
            format!("=== MEMORY CONTEXT ===\nUser Writing Preferences:\n{mem_str}");

        let classification = "=== INTENT CLASSIFICATION ===\nIntent Classification: Surgical Document Editing (Track Changes)";

        let json_reminder = "REMINDER: Your entire response must be a single JSON array. First character must be [. Last character must be ].";

        let user_command = format!("User Instruction: {}\nGenerate the JSON response conforming to the TrackChangeEdit schema. Remember: ONLY the raw JSON output is allowed. No markdown fences.", strip_prompt_prefix(command));

        let user_prompt = format!(
            "{app_context}\n\n{doc_context}\n\n{memory_context}\n\n{classification}\n\n{json_reminder}\n\n{user_command}"
        );

        DocumentPrompt {
            system: DOCX_TRACK_CHANGES_SYSTEM.to_string(),
            user: user_prompt,
            is_structured: true,
        }
    }

    /// Build a prose prompt for PDF/TXT/MD (fallback — no structured schema).
    pub fn for_prose(data: &Value, command: &str, format: &DocFormat) -> Self {
        let format_hint = match format {
            DocFormat::Pdf => "The document is a PDF. Write a well-structured analysis or summary.",
            DocFormat::Md => {
                "The document is Markdown. Respond in valid Markdown with proper heading hierarchy."
            }
            DocFormat::Txt => {
                "The document is plain text. Respond in clean plain text, no formatting."
            }
            _ => "Respond clearly and accurately based on the document context.",
        };

        DocumentPrompt {
            system: format!(
                "You are Kairo Document Engine. {format_hint}\n\nRULES:\n- NEVER invent facts not in the document\n- NEVER fabricate statistics or quotes\n- Use hedging language for uncertain specifics"
            ),
            user: format_generic_context(data, command),
            is_structured: false,
        }
    }
}

// ─── Response parser ──────────────────────────────────────────────────────────

/// Parse structured LLM output (JSON operations array) from a potentially
/// messy LLM response that might have some prose around the JSON.
pub fn extract_json_array(response: &str) -> Option<Value> {
    // Clean response: remove [REPLACE] tag if present
    let cleaned_raw = response.trim().trim_start_matches("[REPLACE]").trim();
    // Robustly handle LLM double-escaping backslashes inside JSON strings (e.g. \\" instead of \")
    let cleaned = cleaned_raw.replace("\\\\\"", "\\\"");

    // Try parsing directly first
    if let Ok(v) = serde_json::from_str::<Value>(&cleaned) {
        if v.is_array() {
            return Some(v);
        }
    }

    // Find JSON array in response (LLM might add prose around it)
    if let Some(start) = cleaned.find('[') {
        let slice = &cleaned[start..];
        // Find matching closing bracket
        let mut depth = 0i32;
        let mut end = 0;
        for (i, ch) in slice.char_indices() {
            match ch {
                '[' | '{' => depth += 1,
                ']' | '}' => {
                    depth -= 1;
                    if depth == 0 {
                        end = i + 1;
                        break;
                    }
                }
                _ => {}
            }
        }
        if end > 0 {
            if let Ok(v) = serde_json::from_str::<Value>(&slice[..end]) {
                if v.is_array() {
                    return Some(v);
                }
            }
        }
    }

    None
}

/// Parse DocxOperation array from LLM response.
pub fn parse_docx_operations(response: &str) -> Vec<crate::sidecar_client::DocxOperation> {
    let Some(arr) = extract_json_array(response) else {
        tracing::warn!("⚠️  Could not parse DocxOperation JSON from LLM response");
        return vec![];
    };
    match serde_json::from_value::<Vec<crate::sidecar_client::DocxOperation>>(arr) {
        Ok(ops) => {
            tracing::info!("✅ Parsed {} DocxOperations", ops.len());
            ops
        }
        Err(e) => {
            tracing::warn!("⚠️  DocxOperation parse error: {}", e);
            vec![]
        }
    }
}

/// Parse ExcelOperation array from LLM response.
pub fn parse_excel_operations(response: &str) -> Vec<crate::sidecar_client::ExcelOperation> {
    let Some(arr) = extract_json_array(response) else {
        return vec![];
    };
    match serde_json::from_value::<Vec<crate::sidecar_client::ExcelOperation>>(arr) {
        Ok(ops) => ops,
        Err(e) => {
            tracing::warn!("⚠️  ExcelOperation parse error: {}", e);
            vec![]
        }
    }
}

/// Parse ExcelWriteOp array (Domain 2 — with formatting fields).
pub fn parse_excel_write_ops(response: &str) -> Vec<crate::sidecar_client::ExcelWriteOp> {
    let Some(arr) = extract_json_array(response) else {
        return vec![];
    };
    match serde_json::from_value::<Vec<crate::sidecar_client::ExcelWriteOp>>(arr) {
        Ok(ops) => {
            tracing::info!("✅ Parsed {} ExcelWriteOps", ops.len());
            ops
        }
        Err(e) => {
            tracing::warn!("⚠️  ExcelWriteOp parse error (likely legacy format): {}", e);
            vec![]
        }
    }
}

/// Robustly parse simple arrays, nested arrays, and strings into Vec<String>.
pub fn parse_robust_json_array(val: &serde_json::Value) -> Vec<String> {
    if let Some(arr) = val.as_array() {
        arr.iter()
            .flat_map(|v| {
                if let Some(s) = v.as_str() {
                    vec![s.to_string()]
                } else if let Some(inner_arr) = v.as_array() {
                    inner_arr
                        .iter()
                        .filter_map(|iv| iv.as_str().map(|s| s.to_string()))
                        .collect()
                } else {
                    vec![]
                }
            })
            .collect()
    } else if let Some(s) = val.as_str() {
        vec![s.to_string()]
    } else {
        vec![]
    }
}

/// Parse SlideOperation array from LLM response.
pub fn parse_slide_operations(response: &str) -> Vec<crate::sidecar_client::SlideOperation> {
    let Some(arr) = extract_json_array(response) else {
        return vec![];
    };
    match serde_json::from_value::<Vec<crate::sidecar_client::SlideOperation>>(arr) {
        Ok(ops) => ops,
        Err(e) => {
            tracing::warn!("⚠️  SlideOperation parse error: {}", e);
            vec![]
        }
    }
}

/// Parse TrackChangeEdit array from LLM response into DocxEdit structs.
/// TrackChangeEdit JSON: [{target_text, new_text, comment}, ...]
/// Maps to DocxEdit which the sidecar's adeu_apply_edits endpoint consumes.
pub fn parse_track_change_edits(response: &str) -> Vec<crate::sidecar_client::DocxEdit> {
    let Some(arr) = extract_json_array(response) else {
        tracing::warn!("⚠️  Could not parse TrackChangeEdit JSON from LLM response");
        return vec![];
    };

    // TrackChangeEdit and DocxEdit have identical field names — try direct parse first
    match serde_json::from_value::<Vec<crate::sidecar_client::DocxEdit>>(arr.clone()) {
        Ok(edits) => {
            tracing::info!("✅ Parsed {} TrackChangeEdits", edits.len());
            edits
        }
        Err(_) => {
            // Try manual extraction from array of objects (field names may vary)
            let mut edits = Vec::new();
            if let Some(items) = arr.as_array() {
                for item in items {
                    let target = item
                        .get("target_text")
                        .or_else(|| item.get("find"))
                        .or_else(|| item.get("original"))
                        .and_then(|v| v.as_str())
                        .unwrap_or_default()
                        .to_string();
                    let replacement = item
                        .get("new_text")
                        .or_else(|| item.get("replace"))
                        .or_else(|| item.get("replacement"))
                        .and_then(|v| v.as_str())
                        .unwrap_or_default()
                        .to_string();
                    let comment = item
                        .get("comment")
                        .or_else(|| item.get("rationale"))
                        .or_else(|| item.get("reason"))
                        .and_then(|v| v.as_str())
                        .unwrap_or_default()
                        .to_string();
                    if !target.is_empty() && !replacement.is_empty() {
                        edits.push(crate::sidecar_client::DocxEdit {
                            target_text: target,
                            new_text: replacement,
                            comment,
                        });
                    }
                }
            }
            tracing::info!("✅ Parsed {} TrackChangeEdits (manual)", edits.len());
            edits
        }
    }
}
