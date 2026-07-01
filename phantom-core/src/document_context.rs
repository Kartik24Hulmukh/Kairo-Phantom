// Kairo Phantom v3.0 — Structured Document Understanding
//
// This module provides the `DocumentContext` type — the canonical context
// object passed through the entire pipeline (Context Engine → Swarm Brain → Agent).
//
// Instead of passing raw text, every Alt+Ctrl+M trigger now produces a rich
// `DocumentContext` containing the document structure: headings, tables,
// slide positions, and tracked-change status.
//
// Design principle: graceful degradation at every layer. If a file cannot
// be opened, parsed, or located, we fall back to plain UIA text. The user
// never notices a failure — they just get slightly less structured context.
//
// NOTE: Uses VibeFlow for AST-aware pruning & kontext-engine for deep
// codebase contextualization to reduce context windows by 70-90%.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// ─── Core Types ───────────────────────────────────────────────────────────────

/// The kind of document the user is currently editing.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum DocKind {
    WordDocument,
    PowerPoint,
    ExcelSpreadsheet,
    OpenDocumentText,
    OpenDocumentPresentation,
    OpenDocumentSpreadsheet,
    PdfDocument,
    Markdown,
    PlainText,
    CodeFile,
    CanvaDesign,
    NotionPage,
    FigmaDesign,
    Terminal,
    /// Yjs CRDT-powered collaborative document (Google Docs, Linear, Tiptap)
    YjsDocument,
    UnknownApp,
}

impl DocKind {
    /// Human-readable label injected into the LLM system prompt.
    pub fn human_name(&self) -> &str {
        match self {
            DocKind::WordDocument => "Microsoft Word document (.docx)",
            DocKind::PowerPoint => "PowerPoint presentation (.pptx)",
            DocKind::ExcelSpreadsheet => "Excel spreadsheet (.xlsx)",
            DocKind::OpenDocumentText => "OpenDocument text (.odt)",
            DocKind::OpenDocumentPresentation => "OpenDocument presentation (.odp)",
            DocKind::OpenDocumentSpreadsheet => "OpenDocument spreadsheet (.ods)",
            DocKind::PdfDocument => "PDF document",
            DocKind::Markdown => "Markdown file",
            DocKind::PlainText => "plain text editor",
            DocKind::CodeFile => "code file",
            DocKind::CanvaDesign => "Canva design",
            DocKind::NotionPage => "Notion page",
            DocKind::FigmaDesign => "Figma design",
            DocKind::Terminal => "terminal / shell",
            DocKind::YjsDocument => "collaborative Yjs document (Google Docs / Linear / Tiptap)",
            DocKind::UnknownApp => "application",
        }
    }
}

/// A heading in a document's outline hierarchy.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutlineItem {
    /// Heading level: 1 = H1, 2 = H2, etc.
    pub level: u8,
    pub text: String,
    /// Character offset in `full_text` where this heading appears.
    pub position: usize,
}

/// A table extracted from the document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TableData {
    pub caption: Option<String>,
    pub headers: Vec<String>,
    pub rows: Vec<Vec<String>>,
    pub position: usize,
}

/// Format-specific metadata for advanced write-back (future phases).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FormatMetadata {
    /// MIME type, e.g. "application/vnd.openxmlformats-officedocument..."
    pub original_format: String,
    /// Named styles used in the document (e.g., "Heading 1", "Normal")
    pub style_names: Vec<String>,
    /// Slide layout name (PowerPoint only)
    pub slide_layout: Option<String>,
}

// ─── DocumentContext ───────────────────────────────────────────────────────────

/// The canonical context object produced for every Alt+Ctrl+M trigger.
/// Flows through: Context Engine → ExtractorRegistry → Swarm Brain → Agent.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentContext {
    pub doc_kind: DocKind,
    pub file_path: Option<PathBuf>,
    /// Full plain-text of the document (for LLM context window).
    pub full_text: String,
    /// User's actual prompt — the last paragraph, what gets erased.
    pub prompt_text: String,
    /// Char count of prompt_text for exact erasure.
    pub prompt_char_count: usize,
    /// Heading hierarchy extracted from the document.
    pub outline: Vec<OutlineItem>,
    /// Tables extracted from the document.
    pub tables: Vec<TableData>,
    /// For presentations: which slide the user is on.
    pub active_slide: Option<usize>,
    /// For presentations: total slide count.
    pub total_slides: Option<usize>,
    /// Whether the document has tracked changes enabled.
    pub format_metadata: FormatMetadata,
    /// Name of the application (e.g. "WINWORD.EXE")
    pub app_name: Option<String>,
    /// Semantic chunks for large document processing
    pub chunks: Vec<String>,
    pub has_tracked_changes: bool,
    /// Syntax-aware code context (only for DocKind::CodeFile)
    pub code_context: Option<crate::code_context::CodeContext>,
}

impl DocumentContext {
    /// Build a minimal context from raw UIA text (no file available).
    /// Preserves existing behavior for Notepad, browsers, terminals, etc.
    pub fn from_raw_text(prompt_text: &str, full_text: &str, doc_kind: DocKind) -> Self {
        let prompt_char_count = prompt_text.chars().count();
        DocumentContext {
            doc_kind,
            file_path: None,
            full_text: full_text.to_string(),
            prompt_text: prompt_text.to_string(),
            prompt_char_count,
            outline: vec![],
            tables: vec![],
            active_slide: None,
            total_slides: None,
            has_tracked_changes: false,
            format_metadata: FormatMetadata::default(),
            app_name: None,
            chunks: vec![],
            code_context: None,
        }
    }

    /// Test helper: Build context from plain text strings, auto-detecting doc kind from app name.
    /// Used by the stress testing gauntlet to avoid requiring real file paths.
    pub fn from_plain_text(app_name: &str, full_text: &str, prompt: &str) -> Self {
        let doc_kind = match app_name.to_lowercase().as_str() {
            n if n.contains("powerpoint") || n.contains("impress") => DocKind::PowerPoint,
            n if n.contains("word") || n.contains("writer") => DocKind::WordDocument,
            n if n.contains("excel") || n.contains("calc") => DocKind::ExcelSpreadsheet,
            n if n.contains("visual studio code") || n.contains("nvim") || n.contains("vim") => {
                DocKind::CodeFile
            }
            n if n.contains("terminal") || n.contains("cmd") || n.contains("powershell") => {
                DocKind::Terminal
            }
            _ => DocKind::UnknownApp,
        };
        let mut ctx = Self::from_raw_text(prompt, full_text, doc_kind);
        ctx.app_name = Some(app_name.to_string());
        ctx
    }

    /// Build a context from a parsed file (DOCX/PPTX/XLSX) with structure.
    #[allow(clippy::too_many_arguments)]
    pub fn from_parsed(
        doc_kind: DocKind,
        file_path: PathBuf,
        full_text: String,
        prompt_text: String,
        outline: Vec<OutlineItem>,
        tables: Vec<TableData>,
        chunks: Vec<String>,
        active_slide: Option<usize>,
        total_slides: Option<usize>,
        has_tracked_changes: bool,
        format_metadata: FormatMetadata,
    ) -> Self {
        let prompt_char_count = prompt_text.chars().count();
        DocumentContext {
            doc_kind,
            file_path: Some(file_path),
            full_text,
            prompt_text,
            prompt_char_count,
            outline,
            tables,
            chunks,
            active_slide,
            total_slides,
            has_tracked_changes,
            format_metadata,
            app_name: None,
            code_context: None,
        }
    }

    pub fn with_code_context(mut self, code_context: crate::code_context::CodeContext) -> Self {
        self.code_context = Some(code_context);
        self
    }

    /// Generate a structured system prompt fragment describing the document.
    /// This is prepended to every agent's system prompt so the LLM knows
    /// exactly what kind of document it is writing into.
    pub fn to_system_prompt_fragment(&self) -> String {
        let mut frag = format!(
            "You are assisting inside a {}. ",
            self.doc_kind.human_name()
        );

        // Add specific formatting constraints based on DocKind (Priority 5 implementation)
        let format_rules = match self.doc_kind {
            DocKind::WordDocument | DocKind::OpenDocumentText => "FORMATTING RULES: Write in professional prose. Use markdown headings (#, ##) ONLY if requested to structure the document, otherwise use standard paragraphs. If continuing a numbered list, maintain strict sequential numbering.",
            DocKind::PowerPoint | DocKind::OpenDocumentPresentation => "FORMATTING RULES: You are writing for a slide deck. Be extremely concise. Use short bullet points. Max 10-15 words per bullet. Avoid dense paragraphs.",
            DocKind::ExcelSpreadsheet | DocKind::OpenDocumentSpreadsheet => "FORMATTING RULES: You are writing for a spreadsheet. Output data in a tabular format, preferably comma-separated or tab-separated. If writing a formula, provide ONLY the formula.",
            DocKind::CanvaDesign | DocKind::FigmaDesign => "FORMATTING RULES: You are writing copy for a visual design. Focus on punchy headlines, short sub-copy, and highly scannable text. Do not use complex markdown.",
            DocKind::NotionPage | DocKind::Markdown => "FORMATTING RULES: You have full Markdown support. Use rich formatting (bold, italics, lists, blockquotes, code blocks) generously to structure the content.",
            DocKind::Terminal => "FORMATTING RULES: Provide ONLY the raw shell command. Do not use markdown code fences (```). Do not include explanations unless explicitly asked.",
            DocKind::CodeFile => "FORMATTING RULES: Provide ONLY valid source code. Do not wrap the code in markdown fences unless you are replacing the entire file context.",
            _ => "FORMATTING RULES: Provide clear, concise plain text.",
        };
        frag.push_str(format_rules);
        frag.push('\n');

        if !self.outline.is_empty() {
            frag.push_str("Document outline:\n");
            for item in &self.outline {
                let indent = "  ".repeat(item.level.saturating_sub(1) as usize);
                frag.push_str(&format!("{}- {}\n", indent, item.text));
            }
        }

        if let (Some(current), Some(total)) = (self.active_slide, self.total_slides) {
            frag.push_str(&format!("Currently on slide {current}/{total}. "));
        }

        if !self.tables.is_empty() {
            frag.push_str(&format!(
                "Document contains {} table(s). ",
                self.tables.len()
            ));
        }

        if self.has_tracked_changes {
            frag.push_str("Document has tracked changes enabled. ");
        }

        if !self.format_metadata.style_names.is_empty() {
            let styles: Vec<&str> = self
                .format_metadata
                .style_names
                .iter()
                .take(5)
                .map(|s| s.as_str())
                .collect();
            frag.push_str(&format!("Document styles in use: {}. ", styles.join(", ")));
        }

        if !self.full_text.is_empty() {
            frag.push_str("\n[DOCUMENT CONTENT]\n");
            let text_len = self.full_text.len();
            if text_len > 3000 {
                frag.push_str(&self.full_text[..1500]);
                frag.push_str("\n... [TRUNCATED] ...\n");
                frag.push_str(&self.full_text[text_len - 1500..]);
            } else {
                frag.push_str(&self.full_text);
            }
            frag.push_str("\n[END CONTENT]\n");
        }

        if let Some(ref cc) = self.code_context {
            frag.push_str("\n[CODE SYNTAX CONTEXT]\n");
            frag.push_str(&format!("Language: {}\n", cc.language));
            if let Some(ref class) = cc.enclosing_class {
                frag.push_str(&format!("Enclosing Symbol/Class/Struct: {class}\n"));
            }
            if let Some(ref func) = cc.enclosing_function {
                frag.push_str(&format!(
                    "Enclosing Function: {} (Lines {}-{})\nSignature: {}\n",
                    func.name, func.start_line, func.end_line, func.signature
                ));
            }
            if !cc.imports.is_empty() {
                frag.push_str("Imports/Use declarations:\n");
                for imp in cc.imports.iter().take(10) {
                    frag.push_str(&format!("  - {imp}\n"));
                }
            }
            if !cc.nearby_symbols.is_empty() {
                frag.push_str("Nearby symbols:\n");
                for sym in cc.nearby_symbols.iter().take(10) {
                    frag.push_str(&format!("  - {sym}\n"));
                }
            }
            frag.push_str(&format!(
                "Current Indentation: '{}' ({} spaces/tabs)\n",
                cc.indentation, cc.cursor_col
            ));
            frag.push_str("\nSurrounding Code (30 lines around cursor):\n");
            frag.push_str(&cc.surrounding_code);
            frag.push_str("\n[END CODE CONTEXT]\n");
        }

        frag.push_str("\nMatch the existing formatting, style, and tone conventions precisely.");
        frag
    }
}

// ─── Extractor Trait ──────────────────────────────────────────────────────────

/// Every format adapter implements this trait.
/// The registry calls `can_handle_extension()` to find the right adapter,
/// then `extract()` to produce a `DocumentContext`.
pub trait DocumentContextExtractor: Send + Sync {
    /// File extensions this extractor handles (lowercase, no dot).
    fn supported_extensions(&self) -> &[&str];

    fn can_handle_extension(&self, ext: &str) -> bool {
        self.supported_extensions()
            .contains(&ext.to_lowercase().as_str())
    }

    /// Extract structured context from the file at `path`.
    /// Returns `None` if extraction fails — caller falls back to `from_raw_text`.
    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        active_slide: Option<usize>,
    ) -> Option<DocumentContext>;
}

// ─── Plain Text Fallback Extractor ────────────────────────────────────────────

/// Handles .txt, .md, and any unrecognized text format by reading the file
/// as plain text. Always succeeds (returns None only if file unreadable).
pub struct PlainTextExtractor;

impl DocumentContextExtractor for PlainTextExtractor {
    fn supported_extensions(&self) -> &[&str] {
        &[
            "txt", "md", "markdown", "rst", "log", "csv", "json", "yaml", "yml", "toml", "ini",
        ]
    }

    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();

        let doc_kind = match ext.as_str() {
            "md" | "markdown" => DocKind::Markdown,
            _ => DocKind::PlainText,
        };

        let full_text = std::fs::read_to_string(path).ok()?;

        Some(DocumentContext::from_raw_text(
            prompt_text,
            &full_text,
            doc_kind,
        ))
    }
}

pub struct CodeFileExtractor;

impl DocumentContextExtractor for CodeFileExtractor {
    fn supported_extensions(&self) -> &[&str] {
        &[
            "rs", "py", "go", "cs", "java", "ts", "tsx", "js", "jsx", "c", "cpp", "h", "hpp", "sh",
            "bat", "ps1",
        ]
    }

    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        let file_path = path.to_string_lossy().to_string();

        let source_code = std::fs::read_to_string(path).ok()?;
        let mut cursor_line = 1;

        let clean_prompt = prompt_text.trim();
        if !clean_prompt.is_empty() {
            for (idx, line) in source_code.lines().enumerate() {
                if line.trim() == clean_prompt {
                    cursor_line = idx + 1;
                    break;
                }
            }
        }

        let code_ctx = crate::code_context::extract_code_context(&file_path, cursor_line).ok()?;

        let mut doc_ctx = DocumentContext::from_raw_text(
            prompt_text,
            &code_ctx.surrounding_code,
            DocKind::CodeFile,
        );
        doc_ctx.file_path = Some(path.to_path_buf());
        doc_ctx = doc_ctx.with_code_context(code_ctx);

        Some(doc_ctx)
    }
}

// ─── Office Document Extractor (native zip/XML parser) ────────────────────────

/// Extracts structured context from DOCX, PPTX, and XLSX files.
///
/// We implement this ourselves by parsing the OOXML format directly —
/// Office Open XML files are ZIP archives containing XML files.
/// This gives us full control without heavyweight dependencies.
///
/// DOCX: word/document.xml → paragraphs, headings, tables
/// PPTX: ppt/slides/slide*.xml → slide text, slide count  
/// XLSX: xl/sharedStrings.xml + xl/worksheets/*.xml → sheet data
pub struct OfficeExtractor;

impl OfficeExtractor {
    /// Parse DOCX: extract headings, text, tables from word/document.xml
    fn extract_docx(&self, path: &std::path::Path, prompt_text: &str) -> Option<DocumentContext> {
        use std::io::Read;

        let file = std::fs::File::open(path).ok()?;
        let mut archive = zip::ZipArchive::new(file).ok()?;

        // Read word/document.xml
        let mut doc_xml = String::new();
        {
            let mut entry = archive.by_name("word/document.xml").ok()?;
            entry.read_to_string(&mut doc_xml).ok()?;
        }

        // Read styles to identify headings
        let mut styles_xml = String::new();
        if let Ok(mut entry) = archive.by_name("word/styles.xml") {
            let _ = entry.read_to_string(&mut styles_xml);
        }

        let full_text = Self::xml_to_plain_text(&doc_xml);
        let outline = Self::extract_docx_outline(&doc_xml);
        let tables = Self::extract_docx_tables(&doc_xml);
        let has_tracked_changes = doc_xml.contains("<w:ins ") || doc_xml.contains("<w:del ");

        // Extract style names from styles.xml
        let style_names = Self::extract_style_names(&styles_xml);

        Some(DocumentContext::from_parsed(
            DocKind::WordDocument,
            path.to_path_buf(),
            full_text,
            prompt_text.to_string(),
            outline,
            tables,
            vec![], // chunks
            None,
            None,
            has_tracked_changes,
            FormatMetadata {
                original_format:
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document".into(),
                style_names,
                slide_layout: None,
            },
        ))
    }

    /// Parse PPTX: extract slide text and count from ppt/slides/
    fn extract_pptx(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        use std::io::Read;

        let file = std::fs::File::open(path).ok()?;
        let mut archive = zip::ZipArchive::new(file).ok()?;

        let mut slide_texts: Vec<(usize, String)> = Vec::new();

        for i in 0..archive.len() {
            let mut entry = archive.by_index(i).ok()?;
            let name = entry.name().to_string();

            if name.starts_with("ppt/slides/slide") && name.ends_with(".xml") {
                // Extract slide number from filename: ppt/slides/slide3.xml → 3
                let slide_num: usize = name
                    .trim_start_matches("ppt/slides/slide")
                    .trim_end_matches(".xml")
                    .parse()
                    .unwrap_or(0);

                let mut xml = String::new();
                entry.read_to_string(&mut xml).ok()?;
                let text = Self::xml_to_plain_text(&xml);
                slide_texts.push((slide_num, text));
            }
        }

        slide_texts.sort_by_key(|(n, _)| *n);
        let total_slides = slide_texts.len();

        let mut full_text = String::new();
        for (num, text) in &slide_texts {
            full_text.push_str(&format!("\n--- Slide {num} ---\n{text}"));
        }

        Some(DocumentContext::from_parsed(
            DocKind::PowerPoint,
            path.to_path_buf(),
            full_text,
            prompt_text.to_string(),
            vec![], // PPT outline derived from slide titles
            vec![],
            vec![], // chunks
            active_slide,
            Some(total_slides),
            false,
            FormatMetadata {
                original_format:
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        .into(),
                style_names: vec![],
                slide_layout: None,
            },
        ))
    }

    /// Parse XLSX: extract sheet names and cell data
    fn extract_xlsx(&self, path: &std::path::Path, prompt_text: &str) -> Option<DocumentContext> {
        use std::io::Read;

        let file = std::fs::File::open(path).ok()?;
        let mut archive = zip::ZipArchive::new(file).ok()?;

        // Read shared strings (cell text content)
        let mut shared_strings: Vec<String> = Vec::new();
        if let Ok(mut entry) = archive.by_name("xl/sharedStrings.xml") {
            let mut xml = String::new();
            let _ = entry.read_to_string(&mut xml);
            shared_strings = Self::extract_shared_strings(&xml);
        }

        // Read workbook for sheet names
        let mut sheet_names: Vec<String> = Vec::new();
        if let Ok(mut entry) = archive.by_name("xl/workbook.xml") {
            let mut xml = String::new();
            let _ = entry.read_to_string(&mut xml);
            sheet_names = Self::extract_sheet_names(&xml);
        }

        let full_text = if sheet_names.is_empty() {
            shared_strings.join(", ")
        } else {
            format!(
                "Sheets: {}\nData: {}",
                sheet_names.join(", "),
                shared_strings.join(", ")
            )
        };

        Some(DocumentContext::from_raw_text(
            prompt_text,
            &full_text,
            DocKind::ExcelSpreadsheet,
        ))
    }

    // ── XML helpers ───────────────────────────────────────────────────────────

    /// Strip XML tags and decode basic entities to get plain text.
    fn xml_to_plain_text(xml: &str) -> String {
        let mut result = String::new();
        let mut in_tag = false;
        let mut last_was_para = false;

        for ch in xml.chars() {
            match ch {
                '<' => {
                    in_tag = true;
                    // Check for paragraph tag to insert newlines
                    if xml[xml.find('<').unwrap_or(0)..].starts_with("</w:p>") && !last_was_para {
                        result.push('\n');
                        last_was_para = true;
                    }
                }
                '>' => {
                    in_tag = false;
                }
                _ if !in_tag => {
                    result.push(ch);
                    last_was_para = false;
                }
                _ => {}
            }
        }

        // Decode basic XML entities
        result
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&apos;", "'")
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
    }

    /// Extract heading outline from DOCX XML using style names.
    fn extract_docx_outline(xml: &str) -> Vec<OutlineItem> {
        let mut outline = Vec::new();
        let mut pos: usize = 0;

        // Find all <w:p> blocks and check for heading styles
        let mut search = xml;
        while let Some(para_start) = search.find("<w:p ").or_else(|| search.find("<w:p>")) {
            let para_end_offset = search[para_start..]
                .find("</w:p>")
                .map(|e| para_start + e + 6);
            let para_end = para_end_offset.unwrap_or(search.len());
            let para_xml = &search[para_start..para_end];

            // Check for heading style: <w:pStyle w:val="Heading1"/> or similar
            if let Some(style_start) = para_xml.find("w:val=\"Heading") {
                let style_str = &para_xml[style_start + 7..];
                if let Some(quote_end) = style_str.find('"') {
                    let style_val = &style_str[..quote_end]; // e.g. "Heading1"
                    let level: u8 = style_val
                        .chars()
                        .last()
                        .and_then(|c| c.to_digit(10))
                        .map(|d| d as u8)
                        .unwrap_or(1);

                    let text = Self::xml_to_plain_text(para_xml);
                    if !text.is_empty() {
                        outline.push(OutlineItem {
                            level,
                            text,
                            position: pos,
                        });
                    }
                }
            }

            pos += para_end;
            if para_end >= search.len() {
                break;
            }
            search = &search[para_end..];
        }

        outline
    }

    /// Extract tables from DOCX XML.
    fn extract_docx_tables(xml: &str) -> Vec<TableData> {
        let mut tables = Vec::new();
        let mut search = xml;
        let mut pos = 0;

        while let Some(tbl_start) = search.find("<w:tbl>").or_else(|| search.find("<w:tbl ")) {
            if let Some(tbl_end_offset) = search[tbl_start..].find("</w:tbl>") {
                let tbl_end = tbl_start + tbl_end_offset + 8;
                let tbl_xml = &search[tbl_start..tbl_end];

                // Extract rows
                let mut rows: Vec<Vec<String>> = Vec::new();
                let mut row_search = tbl_xml;
                while let Some(row_start) = row_search
                    .find("<w:tr ")
                    .or_else(|| row_search.find("<w:tr>"))
                {
                    if let Some(row_end_off) = row_search[row_start..].find("</w:tr>") {
                        let row_end = row_start + row_end_off + 7;
                        let row_xml = &row_search[row_start..row_end];

                        // Extract cells
                        let mut cells = Vec::new();
                        let mut cell_search = row_xml;
                        while let Some(c_start) = cell_search
                            .find("<w:tc>")
                            .or_else(|| cell_search.find("<w:tc "))
                        {
                            if let Some(c_end_off) = cell_search[c_start..].find("</w:tc>") {
                                let c_end = c_start + c_end_off + 7;
                                cells.push(Self::xml_to_plain_text(&cell_search[c_start..c_end]));
                                cell_search = &cell_search[c_end..];
                            } else {
                                break;
                            }
                        }
                        if !cells.is_empty() {
                            rows.push(cells);
                        }
                        row_search = &row_search[row_end..];
                    } else {
                        break;
                    }
                }

                if !rows.is_empty() {
                    let headers = rows.first().cloned().unwrap_or_default();
                    let data_rows = rows.into_iter().skip(1).collect();
                    tables.push(TableData {
                        caption: None,
                        headers,
                        rows: data_rows,
                        position: pos,
                    });
                }

                pos += tbl_end;
                search = &search[tbl_end..];
            } else {
                break;
            }
        }
        tables
    }

    /// Extract named styles from word/styles.xml
    fn extract_style_names(styles_xml: &str) -> Vec<String> {
        let mut names = Vec::new();
        let mut search = styles_xml;
        while let Some(name_start) = search.find("<w:name w:val=\"") {
            let after = &search[name_start + 15..];
            if let Some(quote_end) = after.find('"') {
                let name = &after[..quote_end];
                if !name.is_empty() && names.len() < 20 {
                    names.push(name.to_string());
                }
            }
            search = &search[name_start + 15..];
        }
        names
    }

    /// Extract shared string values from xl/sharedStrings.xml
    fn extract_shared_strings(xml: &str) -> Vec<String> {
        let mut strings = Vec::new();
        let mut search = xml;
        while let Some(si_start) = search.find("<si>") {
            if let Some(si_end) = search[si_start..].find("</si>") {
                let si_xml = &search[si_start..si_start + si_end + 5];
                let text = Self::xml_to_plain_text(si_xml);
                if !text.is_empty() {
                    strings.push(text);
                }
                search = &search[si_start + si_end + 5..];
            } else {
                break;
            }
        }
        strings
    }

    /// Extract sheet names from xl/workbook.xml
    fn extract_sheet_names(xml: &str) -> Vec<String> {
        let mut names = Vec::new();
        let mut search = xml;
        while let Some(sheet_start) = search.find("name=\"") {
            let after = &search[sheet_start + 6..];
            if let Some(quote_end) = after.find('"') {
                names.push(after[..quote_end].to_string());
            }
            search = &search[sheet_start + 6..];
        }
        names
    }
}

impl DocumentContextExtractor for OfficeExtractor {
    fn supported_extensions(&self) -> &[&str] {
        &["docx", "doc", "pptx", "ppt", "xlsx", "xls"]
    }

    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();

        match ext.as_str() {
            "docx" | "doc" => self.extract_docx(path, prompt_text),
            "pptx" | "ppt" => self.extract_pptx(path, prompt_text, active_slide),
            "xlsx" | "xls" => self.extract_xlsx(path, prompt_text),
            _ => None,
        }
    }
}

// ─── Extractor Registry ───────────────────────────────────────────────────────

/// Plugin-ready registry of document extractors.
/// Extractors are tried in registration order; first match wins.
pub struct ExtractorRegistry {
    extractors: Vec<Box<dyn DocumentContextExtractor>>,
}

impl ExtractorRegistry {
    /// 1. OlgaExtractor (Fast-path for PDF/DOCX/XLSX)
    /// 2. DoclingExtractor (Enterprise pipeline for PDF/DOCX/PPTX)
    /// 3. SuryaOcrExtractor (Layout-aware OCR)
    /// 4. OlmOcrExtractor (VLM-based PDF OCR)
    /// 5. OcrRsExtractor (Minimalist offline OCR)
    /// 6. OfficeExtractor (DOCX/PPTX/XLSX — ZIP/OOXML native)
    /// 7. KreuzbergExtractor (88+ formats via Python kreuzberg — Advancement 3)
    /// 8. PdfSpatialExtractor (PDF spatial/column-aware via spdf — Advancement 3)
    /// 9. VectorlessTreeIndex (secondary fast-tree index for long reports)
    /// 10. PlainTextExtractor (txt, md, rst — always last fallback)
    pub fn with_defaults() -> Self {
        let mut r = Self { extractors: vec![] };
        r.register(Box::new(
            crate::extractors::kreuzberg_ext::OlgaExtractorAdapter,
        ));
        r.register(Box::new(
            crate::extractors::kreuzberg_ext::DoclingExtractorAdapter,
        ));
        r.register(Box::new(
            crate::extractors::kreuzberg_ext::SuryaOcrExtractorAdapter,
        ));
        r.register(Box::new(
            crate::extractors::kreuzberg_ext::OlmOcrExtractorAdapter,
        ));
        r.register(Box::new(
            crate::extractors::kreuzberg_ext::OcrRsExtractorAdapter,
        ));
        r.register(Box::new(
            crate::extractors::kreuzberg_ext::PdfExtractorAdapter,
        ));
        r.register(Box::new(
            crate::extractors::kreuzberg_ext::KreuzbergExtractorAdapter,
        ));
        r.register(Box::new(OfficeExtractor));
        r.register(Box::new(CodeFileExtractor));
        r.register(Box::new(PlainTextExtractor));
        r
    }

    /// Register a custom extractor (plugin entry point).
    pub fn register(&mut self, extractor: Box<dyn DocumentContextExtractor>) {
        self.extractors.push(extractor);
    }

    /// Extract context from a file, returning None if no extractor matches.
    pub fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");

        for extractor in &self.extractors {
            if extractor.can_handle_extension(ext) {
                if let result @ Some(_) = extractor.extract(path, prompt_text, active_slide) {
                    return result;
                }
            }
        }
        None
    }
}
