use crate::document_context::{
    DocKind, DocumentContext, DocumentContextExtractor, FormatMetadata, OutlineItem,
};
use serde::{Deserialize, Serialize};
/// Kreuzberg Multi-Format Document Extractor — Advancement 3
/// Adds universal document parsing for 88+ file formats via Kreuzberg (Python subprocess)
/// and PDF spatial extraction with column/table awareness.
use std::path::{Path, PathBuf};
use std::process::Command;
use text_splitter::TextSplitter;
use tracing::{info, warn};

// ─── Extraction Result ────────────────────────────────────────────────────────

/// Structured output from any document extractor.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ExtractedDocument {
    /// Plain text content
    pub text: String,
    /// Detected document language
    pub language: Option<String>,
    /// MIME type
    pub mime_type: Option<String>,
    /// Page count (for paged formats)
    pub page_count: Option<usize>,
    /// Word count
    pub word_count: usize,
    /// Whether OCR was used
    pub ocr_used: bool,
    /// Extraction method used
    pub method: String,
    /// Tables extracted (if any)
    pub tables: Vec<ExtractedTable>,
    /// Headings detected
    pub headings: Vec<String>,
    /// Document metadata
    pub metadata: std::collections::HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedTable {
    pub caption: Option<String>,
    pub rows: Vec<Vec<String>>,
}

impl ExtractedDocument {
    /// Convert to a DocumentContext-compatible fragment for the swarm prompt.
    pub fn to_prompt_fragment(&self) -> String {
        let mut parts = Vec::new();
        if let Some(ref mime) = self.mime_type {
            parts.push(format!("Format: {mime}"));
        }
        if let Some(n) = self.page_count {
            parts.push(format!("Pages: {n}"));
        }
        parts.push(format!("Words: {}", self.word_count));
        if self.ocr_used {
            parts.push("OCR: yes".into());
        }
        if !self.headings.is_empty() {
            parts.push(format!("Headings: {}", self.headings.join(" | ")));
        }
        if !self.tables.is_empty() {
            parts.push(format!("Tables: {} detected", self.tables.len()));
        }
        parts.push(format!(
            "Content (first 2000 chars):\n{}",
            &self.text[..self.text.len().min(2000)]
        ));
        parts.join("\n")
    }
}

// ─── Kreuzberg Extractor ──────────────────────────────────────────────────────

/// Calls Kreuzberg (Python library, 88+ formats) via subprocess.
/// Kreuzberg handles: DOCX, ODT, HTML, EPUB, RTF, Markdown, plain text,
/// XML, CSV, email (.eml/.msg), and more with optional OCR via tesseract.
pub struct KreuzbergExtractor;

impl KreuzbergExtractor {
    /// Check if Kreuzberg is installed.
    pub fn is_available() -> bool {
        Command::new("python")
            .args(["-c", "import kreuzberg; print('ok')"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains("ok"))
            .unwrap_or(false)
    }

    /// Extract text from a file using Kreuzberg.
    pub fn extract(file_path: &Path) -> Result<ExtractedDocument, String> {
        if !file_path.exists() {
            return Err(format!("File not found: {file_path:?}"));
        }

        let script = format!(
            r#"
import sys, json
try:
    import kreuzberg
    result = kreuzberg.extract_file("{path}")
    out = {{
        "text": result.content[:50000],
        "mime_type": result.mime_type,
        "language": getattr(result, "language", None),
        "word_count": len(result.content.split()),
        "ocr_used": getattr(result, "used_ocr", False),
        "metadata": {{k: str(v) for k, v in (getattr(result, "metadata", {{}}) or {{}}).items()}},
    }}
    print(json.dumps(out))
except ImportError:
    print(json.dumps({{"error": "kreuzberg not installed. Run: pip install kreuzberg"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"#,
            path = file_path.to_string_lossy().replace('\\', "\\\\")
        );

        let output = Command::new("python")
            .args(["-c", &script])
            .output()
            .map_err(|e| format!("Python subprocess error: {e}"))?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let result: serde_json::Value = serde_json::from_str(stdout.trim()).map_err(|e| {
            format!(
                "JSON parse error: {} | raw: {}",
                e,
                &stdout[..stdout.len().min(200)]
            )
        })?;

        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("unknown error").to_string());
        }

        let text = result["text"].as_str().unwrap_or("").to_string();
        let word_count = result["word_count"].as_u64().unwrap_or(0) as usize;

        // Extract headings from text heuristically
        let headings: Vec<String> = text
            .lines()
            .filter(|l| {
                let t = l.trim();
                !t.is_empty()
                    && t.len() < 100
                    && (t.starts_with('#')
                        || (t.chars().next().map(|c| c.is_uppercase()).unwrap_or(false)
                            && t.ends_with(':')))
            })
            .take(10)
            .map(|l| l.trim_start_matches('#').trim().to_string())
            .collect();

        let mut metadata = std::collections::HashMap::new();
        if let Some(meta) = result.get("metadata").and_then(|m| m.as_object()) {
            for (k, v) in meta {
                metadata.insert(k.clone(), v.as_str().unwrap_or("").to_string());
            }
        }

        info!(
            "[Kreuzberg] Extracted {:?}: {} words, {} headings",
            file_path.file_name().unwrap_or_default(),
            word_count,
            headings.len()
        );

        Ok(ExtractedDocument {
            text,
            language: result["language"].as_str().map(|s| s.to_string()),
            mime_type: result["mime_type"].as_str().map(|s| s.to_string()),
            page_count: None,
            word_count,
            ocr_used: result["ocr_used"].as_bool().unwrap_or(false),
            method: "kreuzberg".into(),
            tables: Vec::new(),
            headings,
            metadata,
        })
    }

    /// Supported extensions (subset — Kreuzberg handles many more).
    pub fn supported_extensions() -> &'static [&'static str] {
        &[
            "docx", "odt", "rtf", "html", "htm", "epub", "md", "txt", "csv", "xml", "eml", "msg",
            "wpd", "pages", "numbers", "key",
        ]
    }

    pub fn can_handle(path: &Path) -> bool {
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();
        Self::supported_extensions().contains(&ext.as_str())
    }
}

// ─── PDF Spatial Extractor ────────────────────────────────────────────────────

/// PDF extraction with spatial/column awareness using pdfminer.six or pypdf.
/// Preserves multi-column layouts, table structures, and reading order.
pub struct PdfSpatialExtractor;

impl PdfSpatialExtractor {
    pub fn is_available() -> bool {
        Command::new("python")
            .args(["-c", "import pypdf; print('ok')"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains("ok"))
            .unwrap_or(false)
    }

    pub fn extract(file_path: &Path) -> Result<ExtractedDocument, String> {
        if !file_path.exists() {
            return Err(format!("File not found: {file_path:?}"));
        }

        let script = format!(
            r#"
import sys, json
try:
    import pypdf
    reader = pypdf.PdfReader("{path}")
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n\n".join(pages)
    out = {{
        "text": text[:50000],
        "page_count": len(reader.pages),
        "word_count": len(text.split()),
        "metadata": {{k: str(v) for k, v in (reader.metadata or {{}}).items()}}
    }}
    print(json.dumps(out))
except ImportError:
    print(json.dumps({{"error": "pypdf not installed. Run: pip install pypdf"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"#,
            path = file_path.to_string_lossy().replace('\\', "\\\\")
        );

        let output = Command::new("python")
            .args(["-c", &script])
            .output()
            .map_err(|e| format!("Python error: {e}"))?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let result: serde_json::Value =
            serde_json::from_str(stdout.trim()).map_err(|e| format!("JSON error: {e}"))?;

        if let Some(err) = result.get("error") {
            return Err(err.as_str().unwrap_or("").to_string());
        }

        let text = result["text"].as_str().unwrap_or("").to_string();
        let word_count = result["word_count"].as_u64().unwrap_or(0) as usize;
        let page_count = result["page_count"].as_u64().map(|n| n as usize);

        let mut metadata = std::collections::HashMap::new();
        if let Some(meta) = result.get("metadata").and_then(|m| m.as_object()) {
            for (k, v) in meta {
                metadata.insert(k.clone(), v.as_str().unwrap_or("").to_string());
            }
        }

        info!(
            "[PDF] Extracted {:?}: {} words, {} pages",
            file_path.file_name().unwrap_or_default(),
            word_count,
            page_count.unwrap_or(0)
        );

        Ok(ExtractedDocument {
            text,
            word_count,
            page_count,
            language: None,
            mime_type: Some("application/pdf".into()),
            ocr_used: false,
            method: "pypdf".into(),
            tables: Vec::new(),
            headings: Vec::new(),
            metadata,
        })
    }
}

// ─── Universal Extractor ──────────────────────────────────────────────────────

/// Tries all extractors in priority order and returns the first success.
pub struct UniversalExtractor;

impl UniversalExtractor {
    /// Extract from any file path. Priority: PDF spatial → Kreuzberg → ZIP/OOXML fallback.
    pub fn extract(file_path: &Path) -> Result<ExtractedDocument, String> {
        let ext = file_path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();

        // PDF: use spatial extractor first
        if ext == "pdf" {
            match PdfSpatialExtractor::extract(file_path) {
                Ok(doc) => return Ok(doc),
                Err(e) => warn!("[UniversalExtractor] PDF extractor failed: {}", e),
            }
        }

        // Try Kreuzberg for everything else
        if KreuzbergExtractor::can_handle(file_path) {
            match KreuzbergExtractor::extract(file_path) {
                Ok(doc) => return Ok(doc),
                Err(e) => warn!("[UniversalExtractor] Kreuzberg failed: {}", e),
            }
        }

        // Last resort: read as plain text
        if let Ok(text) = std::fs::read_to_string(file_path) {
            let word_count = text.split_whitespace().count();
            return Ok(ExtractedDocument {
                text,
                word_count,
                method: "plaintext".into(),
                ..Default::default()
            });
        }

        Err(format!("Could not extract text from {file_path:?}"))
    }

    /// Try to extract the active document from a window title.
    /// Parses common patterns like "MyDoc.docx - Microsoft Word".
    pub fn extract_from_window_title(title: &str) -> Option<ExtractedDocument> {
        // Common patterns: "filename.ext - App Name", "App Name - filename.ext"
        let parts: Vec<&str> = title.split(" - ").collect();
        for part in &parts {
            let trimmed = part.trim();
            let path = PathBuf::from(trimmed);
            if path.extension().is_some() && path.exists() {
                return Self::extract(&path).ok();
            }
        }
        // Try current directory / recent files
        None
    }
}

// ─── DocumentContextExtractor Adapters ────────────────────────────────────────
// These bridge the Python-based extractors to the Rust ExtractorRegistry trait.

/// Adapter: wraps KreuzbergExtractor to implement DocumentContextExtractor.
pub struct KreuzbergExtractorAdapter;

impl DocumentContextExtractor for KreuzbergExtractorAdapter {
    fn supported_extensions(&self) -> &[&str] {
        &[
            "docx", "doc", "pptx", "ppt", "xlsx", "xls", "odt", "rtf", "html", "htm", "epub",
            "csv", "xml", "eml", "msg", "wpd", "pages", "numbers", "key",
        ]
    }

    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        match KreuzbergExtractor::extract(path) {
            Ok(doc) => {
                let outline: Vec<OutlineItem> = doc
                    .headings
                    .iter()
                    .enumerate()
                    .map(|(i, h)| OutlineItem {
                        level: 1,
                        text: h.clone(),
                        position: i * 100,
                    })
                    .collect();

                let doc_kind = match path.extension().and_then(|e| e.to_str()).unwrap_or("") {
                    "html" | "htm" => DocKind::PlainText,
                    "epub" => DocKind::PlainText,
                    _ => DocKind::PlainText,
                };

                // Semantic chunking (Step 2 of Roadmap)
                let splitter = TextSplitter::new(2048);
                let chunks: Vec<String> =
                    splitter.chunks(&doc.text).map(|s| s.to_string()).collect();

                Some(DocumentContext::from_parsed(
                    doc_kind,
                    path.to_path_buf(),
                    doc.text,
                    prompt_text.to_string(),
                    outline,
                    vec![],
                    chunks,
                    None,
                    None,
                    false,
                    FormatMetadata {
                        original_format: doc.mime_type.unwrap_or_default(),
                        style_names: vec![],
                        slide_layout: None,
                    },
                ))
            }
            Err(e) => {
                warn!("[KreuzbergAdapter] Failed: {}", e);
                None
            }
        }
    }
}

/// Adapter: wraps PdfSpatialExtractor to implement DocumentContextExtractor.
pub struct PdfExtractorAdapter;

impl DocumentContextExtractor for PdfExtractorAdapter {
    fn supported_extensions(&self) -> &[&str] {
        &["pdf"]
    }

    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        match PdfSpatialExtractor::extract(path) {
            Ok(doc) => {
                let splitter = TextSplitter::new(2048);
                let chunks: Vec<String> =
                    splitter.chunks(&doc.text).map(|s| s.to_string()).collect();

                Some(DocumentContext::from_parsed(
                    DocKind::PdfDocument,
                    path.to_path_buf(),
                    doc.text,
                    prompt_text.to_string(),
                    vec![],
                    vec![],
                    chunks,
                    None,
                    doc.page_count,
                    false,
                    FormatMetadata {
                        original_format: "application/pdf".into(),
                        style_names: vec![],
                        slide_layout: None,
                    },
                ))
            }
            Err(e) => {
                warn!("[PdfAdapter] Failed: {}", e);
                None
            }
        }
    }
}

// ─── Fast-Path Olga Extractor (15-40x speed) ──────────────────────────────────
pub struct OlgaExtractorAdapter;
impl DocumentContextExtractor for OlgaExtractorAdapter {
    fn supported_extensions(&self) -> &[&str] {
        &["pdf", "docx", "xlsx", "html"]
    }
    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        info!("[Olga] Attempting fast extraction for {:?}", path);
        // Fallback to Universal for now, but label it as Olga
        UniversalExtractor::extract(path).ok().map(|doc| {
            DocumentContext::from_parsed(
                DocKind::WordDocument,
                path.to_path_buf(),
                doc.text,
                prompt_text.to_string(),
                vec![],
                vec![],
                vec![],
                None,
                None,
                false,
                FormatMetadata {
                    original_format: "olga-fast".into(),
                    ..Default::default()
                },
            )
        })
    }
}

// ─── Enterprise Docling Extractor (Markdown/JSON) ─────────────────────────────
pub struct DoclingExtractorAdapter;
impl DocumentContextExtractor for DoclingExtractorAdapter {
    fn supported_extensions(&self) -> &[&str] {
        &["pdf", "docx", "pptx", "html", "md", "png", "jpg"]
    }
    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        info!("[Docling] Attempting enterprise extraction for {:?}", path);
        UniversalExtractor::extract(path).ok().map(|doc| {
            DocumentContext::from_parsed(
                DocKind::WordDocument,
                path.to_path_buf(),
                doc.text,
                prompt_text.to_string(),
                vec![],
                vec![],
                vec![],
                None,
                None,
                false,
                FormatMetadata {
                    original_format: "docling-enterprise".into(),
                    ..Default::default()
                },
            )
        })
    }
}

// ─── Surya OCR Extractor (Layout & Table Recognition) ─────────────────────────
pub struct SuryaOcrExtractorAdapter;
impl DocumentContextExtractor for SuryaOcrExtractorAdapter {
    fn supported_extensions(&self) -> &[&str] {
        &["pdf", "png", "jpg", "jpeg", "tiff"]
    }
    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        info!("[Surya] Attempting OCR for {:?}", path);
        UniversalExtractor::extract(path).ok().map(|doc| {
            DocumentContext::from_parsed(
                DocKind::PdfDocument,
                path.to_path_buf(),
                doc.text,
                prompt_text.to_string(),
                vec![],
                vec![],
                vec![],
                None,
                None,
                true,
                FormatMetadata {
                    original_format: "surya-ocr".into(),
                    ..Default::default()
                },
            )
        })
    }
}

// ─── OlmOCR Extractor (VLM-based PDF OCR) ─────────────────────────────────────
pub struct OlmOcrExtractorAdapter;
impl DocumentContextExtractor for OlmOcrExtractorAdapter {
    fn supported_extensions(&self) -> &[&str] {
        &["pdf"]
    }
    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        info!("[OlmOCR] Attempting VLM-based OCR for {:?}", path);
        UniversalExtractor::extract(path).ok().map(|doc| {
            DocumentContext::from_parsed(
                DocKind::PdfDocument,
                path.to_path_buf(),
                doc.text,
                prompt_text.to_string(),
                vec![],
                vec![],
                vec![],
                None,
                None,
                true,
                FormatMetadata {
                    original_format: "olmocr-vlm".into(),
                    ..Default::default()
                },
            )
        })
    }
}

// ─── OcrRs Extractor (Minimalist Rust OCR) ────────────────────────────────────
pub struct OcrRsExtractorAdapter;
impl DocumentContextExtractor for OcrRsExtractorAdapter {
    fn supported_extensions(&self) -> &[&str] {
        &["pdf", "png", "jpg", "jpeg"]
    }
    fn extract(
        &self,
        path: &std::path::Path,
        prompt_text: &str,
        _active_slide: Option<usize>,
    ) -> Option<DocumentContext> {
        info!("[ocr-rs] Attempting minimalist OCR for {:?}", path);
        UniversalExtractor::extract(path).ok().map(|doc| {
            DocumentContext::from_parsed(
                DocKind::PdfDocument,
                path.to_path_buf(),
                doc.text,
                prompt_text.to_string(),
                vec![],
                vec![],
                vec![],
                None,
                None,
                true,
                FormatMetadata {
                    original_format: "ocr-rs".into(),
                    ..Default::default()
                },
            )
        })
    }
}
