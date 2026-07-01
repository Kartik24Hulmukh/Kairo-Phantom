// pdf_context.rs — Domain 4: PDF SmartContextCapture
// Structs and async extraction for multi-tier PDF intelligence.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

/// Extraction tier used by the Python sidecar engine.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum ExtractionTier {
    PyMuPdf,
    OpenDataLoader,
    OlmOcr,
    Surya,
    #[default]
    Unknown,
}

impl std::fmt::Display for ExtractionTier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::PyMuPdf => write!(f, "PyMuPDF (Tier 1)"),
            Self::OpenDataLoader => write!(f, "OpenDataLoader (Tier 2)"),
            Self::OlmOcr => write!(f, "olmOCR VLM (Tier 3)"),
            Self::Surya => write!(f, "Surya (Tier 4)"),
            Self::Unknown => write!(f, "Fallback"),
        }
    }
}

/// A single table extracted from a PDF page.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PdfTable {
    pub headers: Vec<String>,
    pub rows: Vec<Vec<String>>,
    pub page: usize,
    #[serde(default)]
    pub caption: Option<String>,
}

/// A heading extracted from PDF structure analysis.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PdfHeading {
    pub text: String,
    pub level: u8,
    pub page: usize,
}

/// An image region found in a PDF page.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PdfImage {
    pub page: usize,
    pub bbox: Vec<f64>, // [x0, y0, x1, y1]
    #[serde(default)]
    pub caption: Option<String>,
}

/// Metadata about the extracted PDF document.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PdfMetadata {
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub author: Option<String>,
    pub pages: usize,
    pub file_path: String,
    #[serde(default)]
    pub extraction_time_ms: f64,
    #[serde(default)]
    pub tier: String,
}

/// Full structured context for a PDF document.
/// This is what the Rust core uses for LLM prompt building and ghost-writing.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PdfDocumentContext {
    pub text: String,
    pub markdown: String,
    pub tables: Vec<PdfTable>,
    pub headings: Vec<PdfHeading>,
    pub images: Vec<PdfImage>,
    pub metadata: PdfMetadata,
    #[serde(default)]
    pub confidence: f64,
    #[serde(default)]
    pub language: String,
    #[serde(default)]
    pub tier_used: ExtractionTier,
}

impl PdfDocumentContext {
    /// Extract PDF content via the multi-tier Python sidecar engine.
    pub async fn extract(file_path: &str) -> Result<Self> {
        let data = crate::sidecar_client::pdf_extract(file_path)
            .await
            .context("Failed to extract PDF via sidecar")?;
        serde_json::from_value(data).context("Failed to parse PDF extraction result")
    }

    /// Build a system prompt fragment for the LLM from extracted PDF context.
    pub fn to_system_prompt_fragment(&self) -> String {
        let mut frag = String::with_capacity(512);

        frag.push_str(&format!(
            "[PDF Document — {} pages, extracted via {} (confidence: {:.0}%)]",
            self.metadata.pages,
            self.tier_used,
            self.confidence * 100.0
        ));
        frag.push('\n');

        if !self.language.is_empty() && self.language != "en" {
            frag.push_str(&format!("Document language: {}\n", self.language));
        }

        if !self.headings.is_empty() {
            frag.push_str("\nDocument outline:\n");
            for h in self.headings.iter().take(20) {
                let indent = "  ".repeat(h.level.saturating_sub(1) as usize);
                frag.push_str(&format!("{}• {} (page {})\n", indent, h.text, h.page));
            }
        }

        if !self.tables.is_empty() {
            frag.push_str(&format!(
                "\nDocument contains {} table(s).\n",
                self.tables.len()
            ));
            for (i, tbl) in self.tables.iter().take(5).enumerate() {
                if !tbl.headers.is_empty() {
                    frag.push_str(&format!(
                        "  Table {}: {} columns ({})\n",
                        i + 1,
                        tbl.headers.len(),
                        tbl.headers.join(", ")
                    ));
                }
            }
        }

        if !self.text.is_empty() {
            let preview: String = self.text.chars().take(500).collect();
            frag.push_str(&format!("\nContent preview:\n{preview}\n"));
        }

        frag
    }

    /// Returns the best available text for LLM consumption (markdown preferred over plain text).
    pub fn best_text(&self) -> &str {
        if !self.markdown.is_empty() {
            &self.markdown
        } else {
            &self.text
        }
    }

    /// Returns true if this PDF has structured tables.
    pub fn has_tables(&self) -> bool {
        !self.tables.is_empty()
    }

    /// Returns true if this is a multi-lingual (non-Latin) document.
    pub fn is_multilingual(&self) -> bool {
        matches!(self.language.as_str(), "zh" | "ja" | "ko" | "ar" | "hi")
    }
}

/// Result of a Kami PDF export operation.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PdfKamiExportResult {
    pub success: bool,
    pub output_path: String,
    pub theme_used: String,
    #[serde(default)]
    pub error: Option<String>,
}
