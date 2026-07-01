//! Kairo Sidecar Client
//! ====================
//! Communicates with the Python sidecar process (localhost:7438) using
//! newline-delimited JSON over TCP.
//!
//! The sidecar owns all document I/O (DOCX, XLSX, PPTX, PDF).
//! This module is the Rust bridge to those capabilities.

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpStream;
use uuid::Uuid;

const SIDECAR_HOST: &str = "127.0.0.1";
const SIDECAR_PORT: u16 = 7438;

static SIDECAR_AVAILABLE: AtomicBool = AtomicBool::new(false);

// â”€â”€â”€ Protocol types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

#[derive(Debug, Serialize)]
pub struct SidecarRequest {
    pub id: String,
    pub action: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub payload: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
pub struct SidecarResponse {
    pub id: String,
    pub ok: bool,
    #[serde(default)]
    pub data: Option<serde_json::Value>,
    #[serde(default)]
    pub error: Option<String>,
}

// â”€â”€â”€ DocxOperation schema â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/// Typed operations the LLM can request for DOCX files.
/// The LLM is forced to output ONLY valid operations â€” never freeform prose.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DocxOperation {
    /// "insert_after_heading" | "insert_paragraph" | "replace_paragraph" | "append" | "insert_table"
    pub action: String,
    /// For insert_after_heading: the heading text to find
    #[serde(skip_serializing_if = "Option::is_none")]
    pub heading_text: Option<String>,
    /// Word paragraph style: "Normal", "Heading1", "ListBullet", "ListNumber", etc.
    pub style: String,
    /// Text content to insert (string or Vec<String> for multiple paragraphs)
    pub content: serde_json::Value,
    /// For insert_paragraph/replace_paragraph: paragraph index
    #[serde(skip_serializing_if = "Option::is_none")]
    pub index: Option<usize>,
    /// For insert_table: row data [[cell, cell], [cell, cell]]
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rows: Option<Vec<Vec<String>>>,
}

/// Typed operations for XLSX cells.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ExcelOperation {
    /// Cell reference, e.g. "G5"
    pub cell: String,
    /// Formula starting with "=" (takes priority over value)
    #[serde(default)]
    pub formula: String,
    /// Plain value if no formula
    #[serde(default)]
    pub value: String,
}

/// Typed operations for PPTX slides.
/// Supports two modes:
///   • Update existing slide: set `slide_index`, `shape_id?`, `bullets`
///   • Add new slide:         set `add_new: true`, `title`, `bullets`, `layout_index?`
///     `slide_index` is ignored for add_new but must still be present (use 0).
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SlideOperation {
    /// Zero-based slide index (for update) or ignored (for add_new)
    pub slide_index: usize,
    /// If true, append a new slide instead of updating an existing one
    #[serde(default)]
    pub add_new: bool,
    /// Slide title — populated for add_new and for update_title ops
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    /// Shape ID to write bullets into (None = content placeholder, update mode only)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub shape_id: Option<i32>,
    /// Bullet points (max 7 words each, enforced by sidecar validator)
    #[serde(default)]
    pub bullets: Vec<String>,
    /// Layout index for add_new (0=Title Slide, 1=Title+Content [default], 5=Blank)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub layout_index: Option<usize>,
}

// â”€â”€â”€ Document context returned by sidecar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

#[derive(Debug, Deserialize, Default)]
pub struct DocxContext {
    pub full_text: String,
    pub headings: Vec<HeadingEntry>,
    pub paragraphs: Vec<ParagraphEntry>,
    pub paragraph_count: usize,
}

#[derive(Debug, Deserialize, Default, Clone)]
pub struct HeadingEntry {
    pub index: usize,
    pub level: i32,
    pub text: String,
}

#[derive(Debug, Deserialize, Default, Clone)]
pub struct ParagraphEntry {
    pub index: usize,
    pub text: String,
    pub style: String,
    pub is_heading: bool,
}

#[derive(Debug, Deserialize, Default)]
pub struct ExcelContext {
    pub active_cell: String,
    pub sheet_name: String,
    pub grid: Vec<Vec<CellEntry>>,
    pub headers: std::collections::HashMap<String, String>,
    pub named_ranges: Vec<String>,
}

#[derive(Debug, Deserialize, Default, Clone)]
pub struct CellEntry {
    pub r#ref: String,
    pub value: String,
    pub formula: String,
    pub is_active: bool,
}

/// Extended Excel context with workbook blueprint (Domain 2).
#[derive(Debug, Deserialize, Default)]
pub struct ExcelWorkbookBlueprint {
    pub sheets: Vec<ExcelSheetInfo>,
    pub named_ranges: Vec<String>,
    pub total_sheets: usize,
    pub total_named_ranges: usize,
}

#[derive(Debug, Deserialize, Default, Clone)]
pub struct ExcelSheetInfo {
    pub name: String,
    pub max_row: usize,
    pub max_col: usize,
    pub has_tables: bool,
}

/// Formula validation result from Forge (Domain 2).
#[derive(Debug, Deserialize, Default, Clone)]
pub struct ForgeValidationResult {
    pub valid: bool,
    pub corrected: String,
    #[serde(default)]
    pub error: Option<String>,
    #[serde(default)]
    pub fix_applied: Option<String>,
    #[serde(default)]
    pub confidence: f64,
    #[serde(default)]
    pub explanation: String,
}

/// Excel chart creation operation (Domain 2).
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ExcelChartOp {
    pub source_range: String,
    pub chart_type: String, // "bar", "line", "pie", "column", "scatter"
    pub title: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_sheet: Option<String>,
}

/// PivotTable creation operation (Domain 2).
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ExcelPivotOp {
    pub source_range: String,
    pub rows: Vec<String>,
    pub columns: Vec<String>,
    pub values: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_sheet: Option<String>,
}

/// Conditional formatting config for ExcelWriteOp.
#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct ConditionalFormatConfig {
    /// "cell_is" | "data_bar" | "color_scale"
    #[serde(rename = "type", default)]
    pub format_type: String,
    /// "greaterThan" | "lessThan" | "equal" | "greaterThanOrEqual" | "lessThanOrEqual"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operator: Option<String>,
    /// Threshold value for cell_is comparisons
    #[serde(skip_serializing_if = "Option::is_none")]
    pub threshold: Option<f64>,
    /// 6-char hex color without # (e.g. "C6EFCE" for green)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fill_color: Option<String>,
}

/// Extended ExcelOperation with formatting support (Domain 2).
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ExcelWriteOp {
    pub cell: String,
    #[serde(default)]
    pub formula: String,
    #[serde(default)]
    pub value: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub number_format: Option<String>, // e.g. "0.00%", "#,##0.00"
    #[serde(default)]
    pub bold: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub conditional_formatting: Option<ConditionalFormatConfig>,
}

// â”€â”€â”€ Core client function â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/// Send one request to the sidecar and get the response.
/// Returns Err if the sidecar is down or returns an error response.
async fn call_sidecar(req: SidecarRequest) -> Result<serde_json::Value> {
    let json_line = serde_json::to_string(&req)? + "\n";
    let mut response_line = String::new();

    #[cfg(windows)]
    {
        use tokio::net::windows::named_pipe::ClientOptions;
        let mut client = ClientOptions::new()
            .open(r"\\.\pipe\kairo_sidecar")
            .context("Sidecar Named Pipe not reachable")?;

        client.write_all(json_line.as_bytes()).await?;
        let mut buf_reader = BufReader::new(client);
        buf_reader.read_line(&mut response_line).await?;
    }

    #[cfg(not(windows))]
    {
        let stream = TcpStream::connect((SIDECAR_HOST, SIDECAR_PORT))
            .await
            .context("Sidecar TCP socket not reachable")?;
        let (reader, mut writer) = stream.into_split();
        let mut buf_reader = BufReader::new(reader);
        writer.write_all(json_line.as_bytes()).await?;
        buf_reader.read_line(&mut response_line).await?;
    }

    let resp: SidecarResponse =
        serde_json::from_str(response_line.trim()).context("Invalid JSON from sidecar")?;

    if !resp.ok {
        let err_msg = resp
            .error
            .clone()
            .or_else(|| {
                resp.data
                    .as_ref()
                    .and_then(|d| d.get("error"))
                    .and_then(|e| e.as_str())
                    .map(|s| s.to_string())
            })
            .unwrap_or_else(|| "unknown error".to_string());
        if err_msg.starts_with("Domain ") {
            crate::toast_notification::show_error_toast(&err_msg);
        }
        bail!("Sidecar error: {err_msg}");
    }

    Ok(resp.data.unwrap_or(serde_json::Value::Null))
}

// â”€â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/// Check if the sidecar is reachable. Updates SIDECAR_AVAILABLE flag.
pub async fn ping() -> bool {
    let req = SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "ping".to_string(),
        path: None,
        payload: None,
    };
    let ok = call_sidecar(req).await.is_ok();
    SIDECAR_AVAILABLE.store(ok, Ordering::Relaxed);
    ok
}

/// Returns true if the sidecar was reachable at last ping.
pub fn is_available() -> bool {
    SIDECAR_AVAILABLE.load(Ordering::Relaxed)
}

/// Query the sidecar's health status and domain availability.
pub async fn self_check() -> Result<serde_json::Value> {
    let req = SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "self_check".to_string(),
        path: None,
        payload: None,
    };
    call_sidecar(req).await
}

/// Extract full structured context from a document file.
/// Returns the full_text + structure (headings, paragraphs, grid, etc.)
pub async fn extract_context(path: &str, active_cell: Option<&str>) -> Result<serde_json::Value> {
    let mut payload = serde_json::json!({});
    if let Some(cell) = active_cell {
        payload["active_cell"] = serde_json::Value::String(cell.to_string());
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "extract_context".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Read a DOCX file and return structured context.
pub async fn read_docx(path: &str) -> Result<DocxContext> {
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "read_docx".to_string(),
        path: Some(path.to_string()),
        payload: None,
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse DOCX context from sidecar")
}

/// Apply DocxOperation list to a .docx file.
pub async fn write_docx(path: &str, operations: Vec<DocxOperation>) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "operations": serde_json::to_value(&operations)?
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "write_docx".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Read an Excel file with context around the active cell.
pub async fn read_xlsx(path: &str, active_cell: Option<&str>) -> Result<ExcelContext> {
    let mut payload = serde_json::json!({});
    if let Some(cell) = active_cell {
        payload["active_cell"] = serde_json::Value::String(cell.to_string());
    }
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "read_xlsx".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse Excel context")
}

/// Apply ExcelOperation list to a .xlsx file.
pub async fn write_xlsx(path: &str, operations: Vec<ExcelOperation>) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "operations": serde_json::to_value(&operations)?
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "write_xlsx".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Get workbook blueprint: sheets, named ranges, tables summary.
pub async fn get_workbook_blueprint(path: &str) -> Result<ExcelWorkbookBlueprint> {
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "get_workbook_blueprint".to_string(),
        path: Some(path.to_string()),
        payload: None,
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse workbook blueprint")
}

/// Validate an Excel formula via Forge (deterministic).
pub async fn validate_formula(
    formula: &str,
    context: Option<&serde_json::Value>,
) -> Result<ForgeValidationResult> {
    let payload = serde_json::json!({
        "formula": formula,
        "context": context
    });
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "validate_formula".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse formula validation result")
}

/// Get plain-language explanation of an Excel formula.
pub async fn explain_formula(formula: &str) -> Result<String> {
    let payload = serde_json::json!({ "formula": formula });
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "explain_formula".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await?;
    Ok(data["explanation"].as_str().unwrap_or("").to_string())
}

/// Write Excel operations with formatting preservation (Domain 2).
pub async fn write_xlsx_formatted(
    path: &str,
    operations: Vec<ExcelWriteOp>,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "operations": serde_json::to_value(&operations)?
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "write_xlsx_formatted".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Create an Excel chart via ExcelMcp (or openpyxl fallback).
pub async fn create_excel_chart(path: &str, op: ExcelChartOp) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "source_range": op.source_range,
        "chart_type": op.chart_type,
        "title": op.title,
        "target_sheet": op.target_sheet
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "excelmcp_create_chart".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Create an Excel PivotTable via ExcelMcp (or summary table fallback).
pub async fn create_excel_pivot(path: &str, op: ExcelPivotOp) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "source_range": op.source_range,
        "rows": op.rows,
        "columns": op.columns,
        "values": op.values,
        "target_sheet": op.target_sheet
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "excelmcp_create_pivot".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Capture full Excel context for SmartContextCapture (Domain 2).
pub async fn get_excel_smart_context(
    path: &str,
    active_cell: Option<&str>,
) -> Result<serde_json::Value> {
    let mut payload = serde_json::json!({});
    if let Some(cell) = active_cell {
        payload["active_cell"] = serde_json::Value::String(cell.to_string());
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "excel_smart_context".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Fill a formula across a range (AutoFill — relative refs adjust).
pub async fn fill_formula(
    path: &str,
    formula: &str,
    fill_range: &str,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "formula": formula,
        "fill_range": fill_range
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "excelmcp_fill_formula".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Read a PPTX file and return slide inventory.

pub async fn read_pptx(path: &str) -> Result<serde_json::Value> {
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "read_pptx".to_string(),
        path: Some(path.to_string()),
        payload: None,
    })
    .await
}

/// Apply SlideOperation list to a .pptx file.
pub async fn write_pptx(path: &str, operations: Vec<SlideOperation>) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "operations": serde_json::to_value(&operations)?
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "write_pptx".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
pub struct PptxContext {
    pub full_text: serde_json::Value,
    pub current_slide: Option<serde_json::Value>,
    pub slide_text: Option<serde_json::Value>,
    pub slide_count: usize,
    pub theme: String,
    pub user_preferences: serde_json::Value,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
pub struct PptxContextResponse {
    pub context: PptxContext,
    pub system_prompt_fragment: String,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
pub struct DeepPresenterResult {
    pub pptx_path: Option<String>,
    pub slide_count: Option<usize>,
    pub output_dir: Option<String>,
    pub generation_time: Option<String>,
}

/// Capture full presentation context for the LLM.
pub async fn pptx_context_capture(
    presentation_id: &str,
    slide_index: Option<usize>,
) -> Result<PptxContextResponse> {
    let mut payload = serde_json::json!({});
    if let Some(idx) = slide_index {
        payload["slide_index"] = serde_json::Value::Number(idx.into());
    }
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "pptx_context_capture".to_string(),
        path: Some(presentation_id.to_string()),
        payload: Some(payload),
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse presentation context response")
}

/// Generate research-grade presentation using DeepPresenter-9B.
pub async fn deeppresenter_generate(
    topic: &str,
    slide_count: usize,
    style: Option<&str>,
    audience: Option<&str>,
    output_dir: Option<&str>,
    outline: Option<&serde_json::Value>,
) -> Result<DeepPresenterResult> {
    let mut payload = serde_json::json!({
        "topic": topic,
        "slide_count": slide_count,
    });
    if let Some(s) = style {
        payload["style"] = serde_json::Value::String(s.to_string());
    }
    if let Some(a) = audience {
        payload["audience"] = serde_json::Value::String(a.to_string());
    }
    if let Some(o) = output_dir {
        payload["output_dir"] = serde_json::Value::String(o.to_string());
    }
    if let Some(out) = outline {
        payload["outline"] = out.clone();
    }
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "deeppresenter_generate".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse DeepPresenter generation response")
}

/// Generate slide image using ComfyUI, gpt-image-2, or Nano Banana backends.
pub async fn slide_image_generate(
    slide_content: Option<&serde_json::Value>,
    slide_contents: Option<&serde_json::Value>,
    backend: Option<&str>,
    style: Option<&str>,
) -> Result<serde_json::Value> {
    let mut payload = serde_json::json!({});
    if let Some(c) = slide_content {
        payload["slide_content"] = c.clone();
    }
    if let Some(cs) = slide_contents {
        payload["slide_contents"] = cs.clone();
    }
    if let Some(b) = backend {
        payload["backend"] = serde_json::Value::String(b.to_string());
    }
    if let Some(s) = style {
        payload["style"] = serde_json::Value::String(s.to_string());
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "slide_image_generate".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}

/// Generate a 256-dimensional Model2Vec embedding vector from Python sidecar.
pub async fn embed_text(text: &str) -> Result<Vec<f32>> {
    let payload = serde_json::json!({ "text": text });
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "embed_text".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await?;
    let vector: Vec<f32> = serde_json::from_value(data.get("vector").cloned().unwrap_or_default())
        .context("Invalid embedding vector format")?;
    Ok(vector)
}

/// Generate a batch of 256-dimensional Model2Vec embedding vectors from Python sidecar.
pub async fn embed_texts(texts: Vec<String>) -> Result<Vec<Vec<f32>>> {
    let payload = serde_json::json!({ "texts": texts });
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "embed_texts".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await?;
    let vectors: Vec<Vec<f32>> =
        serde_json::from_value(data.get("vectors").cloned().unwrap_or_default())
            .context("Invalid embedding vectors format")?;
    Ok(vectors)
}

/// Compile Quarkdown markup to Reveal.js (html) or PDF via Python sidecar.
pub async fn compile_quarkdown(content: &str, format: &str, output_path: &str) -> Result<bool> {
    let payload = serde_json::json!({
        "content": content,
        "format": format,
        "output_path": output_path,
    });
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "compile_quarkdown".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await?;
    let success = data
        .get("success")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    Ok(success)
}

// ─── Domain 1: Word / DOCX Native Track Changes ──────────────────────────────────────────────────

/// A single text edit to apply as a native Track Change in a DOCX file.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DocxEdit {
    /// Exact text to find in the document (case-sensitive).
    pub target_text: String,
    /// Replacement text (shown as inserted in Track Changes).
    pub new_text: String,
    /// Optional comment / rationale shown in the Track Changes pane.
    #[serde(default)]
    pub comment: String,
}

/// Result of reading a DOCX via Adeu (CriticMarkup markdown + paragraph index).
#[derive(Debug, Deserialize, Default)]
pub struct AdeuDocxContext {
    pub full_text: String,
    pub paragraphs: Vec<serde_json::Value>,
    pub format: String,
    pub file_path: String,
}

/// A detected contract clause from CUAD analysis.
#[derive(Debug, Deserialize, Clone)]
pub struct CuadClause {
    pub id: String,
    pub label: String,
    pub risk_level: String,
    pub description: String,
    pub matched_text: String,
    #[serde(default)]
    pub paragraph_index: Option<usize>,
    pub confidence: f64,
}

/// Suggested AI redline for a high-risk clause.
#[derive(Debug, Deserialize, Clone)]
pub struct ClauseRedline {
    pub clause_id: String,
    pub clause_label: String,
    pub original_text: String,
    pub suggested_text: String,
    pub rationale: String,
    pub risk_reduction: String,
}

/// Full contract analysis result.
#[derive(Debug, Deserialize, Default)]
pub struct ContractAnalysisResult {
    pub detected_clauses: Vec<CuadClause>,
    pub risk_summary: serde_json::Value,
    #[serde(default)]
    pub missing_standard_clauses: Vec<String>,
    pub summary_text: String,
    pub action_items: Vec<serde_json::Value>,
    pub suggested_redlines: Vec<ClauseRedline>,
    pub total_clauses_detected: usize,
}

/// Read a DOCX file via Adeu — returns CriticMarkup markdown + paragraph index.
/// Falls back gracefully if Adeu is not installed.
pub async fn adeu_read(path: &str) -> Result<AdeuDocxContext> {
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "adeu_read".to_string(),
        path: Some(path.to_string()),
        payload: None,
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse adeu_read response")
}

/// Apply a list of Track Change edits to a DOCX file via Adeu.
/// Returns the path of the saved redlined file.
pub async fn adeu_apply_edits(
    path: &str,
    edits: Vec<DocxEdit>,
    output_path: Option<&str>,
    author: Option<&str>,
) -> Result<serde_json::Value> {
    let mut payload = serde_json::json!({
        "edits": serde_json::to_value(&edits)?
    });
    if let Some(op) = output_path {
        payload["output_path"] = serde_json::Value::String(op.to_string());
    }
    if let Some(a) = author {
        payload["author"] = serde_json::Value::String(a.to_string());
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "adeu_apply_edits".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Apply batch surgical edits via safe-docx (Node.js headless, no COM required).
/// Produces both a clean copy and a tracked-changes copy.
pub async fn safedocx_edit(
    path: &str,
    edits: Vec<DocxEdit>,
    clean_output_path: Option<&str>,
    tracked_output_path: Option<&str>,
) -> Result<serde_json::Value> {
    let mut payload = serde_json::json!({
        "edits": serde_json::to_value(&edits)?
    });
    if let Some(c) = clean_output_path {
        payload["clean_output_path"] = serde_json::Value::String(c.to_string());
    }
    if let Some(t) = tracked_output_path {
        payload["tracked_output_path"] = serde_json::Value::String(t.to_string());
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "safedocx_edit".to_string(),
        path: Some(path.to_string()),
        payload: Some(payload),
    })
    .await
}

/// Full contract analysis: CUAD clause detection + executive risk summary + AI redlines.
/// Pass `path` to a DOCX file OR `document_text` directly via `text` parameter.
pub async fn analyze_contract(
    path: Option<&str>,
    document_text: Option<&str>,
) -> Result<ContractAnalysisResult> {
    let mut payload = serde_json::json!({});
    if let Some(t) = document_text {
        payload["document_text"] = serde_json::Value::String(t.to_string());
    }
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "analyze_contract".to_string(),
        path: path.map(|p| p.to_string()),
        payload: Some(payload),
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse contract analysis response")
}

/// Lightweight CUAD-only clause detection (no redlines, fast).
pub async fn detect_contract_clauses(
    path: Option<&str>,
    document_text: Option<&str>,
) -> Result<serde_json::Value> {
    let mut payload = serde_json::json!({});
    if let Some(t) = document_text {
        payload["document_text"] = serde_json::Value::String(t.to_string());
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "detect_clauses".to_string(),
        path: path.map(|p| p.to_string()),
        payload: Some(payload),
    })
    .await
}

// ──────────────────────────────────────────────────────────────────────────────────────────────────

/// Determine the file format from extension.
#[derive(Debug, Clone, PartialEq)]
pub enum DocFormat {
    Docx,
    Xlsx,
    Pptx,
    Pdf,
    Txt,
    Md,
    Code(String), // language name
    Unknown,
}

impl DocFormat {
    pub fn from_path(path: &str) -> Self {
        match Path::new(path).extension().and_then(|e| e.to_str()) {
            Some("docx") => DocFormat::Docx,
            Some("xlsx") | Some("xlsm") => DocFormat::Xlsx,
            Some("pptx") => DocFormat::Pptx,
            Some("pdf") => DocFormat::Pdf,
            Some("txt") => DocFormat::Txt,
            Some("md") | Some("markdown") => DocFormat::Md,
            Some(ext)
                if matches!(
                    ext,
                    "rs" | "py" | "js" | "ts" | "cpp" | "c" | "go" | "java" | "cs"
                ) =>
            {
                DocFormat::Code(ext.to_string())
            }
            _ => DocFormat::Unknown,
        }
    }

    pub fn is_sidecar_supported(&self) -> bool {
        matches!(
            self,
            DocFormat::Docx
                | DocFormat::Xlsx
                | DocFormat::Pptx
                | DocFormat::Pdf
                | DocFormat::Txt
                | DocFormat::Md
        )
    }
}

/// Try to resolve the active document path from the window title.
/// Searches: Documents, Desktop, Downloads, OneDrive paths, and Windows recent files (registry MRU).
/// Only returns a path that actually EXISTS on disk — never a guess.
pub fn resolve_document_path(window_title: &str, process_name: &str) -> Option<String> {
    let process_lower = process_name.to_lowercase();
    let home = dirs::home_dir().unwrap_or_default();

    // Extract filename candidate from title: "doc.docx - Microsoft Word" → "doc.docx"
    let fname_raw = window_title.split(" - ").next()?.trim().to_string();
    // Strip read-only / compat mode markers
    let fname = fname_raw
        .trim_end_matches(']')
        .rsplitn(2, '[')
        .last()
        .unwrap_or(&fname_raw)
        .trim()
        .trim_start_matches('●')
        .trim()
        .to_string();

    if fname.is_empty() {
        return None;
    }

    // Determine expected extensions based on process
    let extensions: &[&str] = if process_lower.contains("winword") {
        &["", ".docx", ".doc"]
    } else if process_lower.contains("excel") {
        &["", ".xlsx", ".xlsm", ".xls"]
    } else if process_lower.contains("powerpnt") {
        &["", ".pptx", ".ppt"]
    } else if process_lower.contains("code") && !process_lower.contains("discord") {
        &[""]
    } else {
        &["", ".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".md"]
    };

    // Build candidate directories — ordered by likelihood
    let onedrive = home.join("OneDrive");
    let onedrive_docs = home.join("OneDrive").join("Documents");
    let onedrive_desktop = home.join("OneDrive").join("Desktop");
    // Also check OneDrive - <CompanyName> variants
    let mut search_dirs: Vec<std::path::PathBuf> = vec![
        home.join("Documents"),
        home.join("Desktop"),
        home.join("Downloads"),
        onedrive_docs,
        onedrive_desktop,
        onedrive,
        home.clone(),
        std::env::current_dir().unwrap_or_default(),
    ];

    // Add OneDrive - <Business> folders (e.g. OneDrive - Microsoft)
    if let Ok(entries) = std::fs::read_dir(&home) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.starts_with("OneDrive") && entry.path().is_dir() {
                search_dirs.push(entry.path());
                search_dirs.push(entry.path().join("Documents"));
                search_dirs.push(entry.path().join("Desktop"));
            }
        }
    }

    // Search each dir for fname + each extension
    for dir in &search_dirs {
        for ext in extensions {
            let candidate = if ext.is_empty() || fname.contains('.') {
                dir.join(&fname)
            } else {
                dir.join(format!("{fname}{ext}"))
            };
            if candidate.exists() {
                tracing::info!("📂 Resolved doc path: {:?}", candidate);
                return Some(candidate.to_string_lossy().to_string());
            }
        }
    }

    // Last resort: Windows recent files from registry (MRU)
    #[cfg(windows)]
    {
        if let Some(path) = find_in_recent_files(&fname) {
            return Some(path);
        }
    }

    tracing::debug!(
        "📂 Could not resolve path for '{}' ({})",
        fname,
        process_name
    );
    None
}

/// Search Windows recent files (shell MRU) for a matching filename.
/// Reads HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs
#[cfg(windows)]
fn find_in_recent_files(fname: &str) -> Option<String> {
    use std::path::Path;
    // Try common recent files dirs
    let home = dirs::home_dir().unwrap_or_default();
    let recent = home
        .join("AppData")
        .join("Roaming")
        .join("Microsoft")
        .join("Windows")
        .join("Recent");
    if recent.exists() {
        if let Ok(entries) = std::fs::read_dir(&recent) {
            for entry in entries.flatten() {
                let entry_name = entry.file_name().to_string_lossy().to_string();
                // .lnk files in recent folder named after the document
                let base = Path::new(&entry_name)
                    .file_stem()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_default();
                if base.eq_ignore_ascii_case(fname)
                    || base.eq_ignore_ascii_case(
                        Path::new(fname)
                            .file_stem()
                            .map(|s| s.to_string_lossy().to_string())
                            .unwrap_or_default()
                            .as_str(),
                    )
                {
                    // Read the .lnk target path using shell32 (simplified: parse raw bytes)
                    // The actual file path is embedded at offset 0x4C in the .lnk file
                    if let Ok(bytes) = std::fs::read(entry.path()) {
                        if bytes.len() > 0x4C + 4 {
                            // LNK header check: magic bytes 4C 00 00 00
                            if bytes[..4] == [0x4C, 0x00, 0x00, 0x00] {
                                // Shell link target embedded path (simplified extraction)
                                // Look for a null-terminated ASCII path after offset 0x4C
                                let path_start = 0x4C + 28; // skip header fields
                                if path_start < bytes.len() {
                                    let path_bytes: Vec<u8> = bytes[path_start..]
                                        .iter()
                                        .take_while(|&&b| b != 0)
                                        .cloned()
                                        .collect();
                                    if let Ok(path_str) = String::from_utf8(path_bytes) {
                                        let p = std::path::Path::new(path_str.trim());
                                        if p.exists() {
                                            return Some(path_str.trim().to_string());
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    None
}

// ──────────────────────────────────────────────────────────────────────────────────────────────────

/// Launch the Python sidecar as a background process.
/// Called once at daemon startup. Monitors and auto-restarts on crash.
///
/// Improvements over the original silent-failure launcher:
/// - stderr is captured to `~/.kairo-phantom/sidecar-error.log` for debugging
/// - Tries `python`, `python3`, then `py` (Windows Python Launcher)
/// - Retry-pings every 1s for up to 10 attempts instead of a single 3s wait
/// - Shows a toast notification if the sidecar fails to start
pub async fn launch_sidecar() {
    use std::process::Stdio;
    use tokio::process::Command;

    // Search multiple locations for sidecar/main.py
    let exe = std::env::current_exe().unwrap_or_default();
    let cwd = std::env::current_dir().unwrap_or_default();

    let candidates = vec![
        // Relative to EXE: target/release/ -> ../../kairo-sidecar/sidecar/main.py
        exe.parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .map(|p| p.join("kairo-sidecar").join("sidecar").join("main.py"))
            .unwrap_or_default(),
        // Relative to EXE: target/release/ -> ../../../kairo-sidecar/sidecar/main.py (if in phantom-core/target/release)
        exe.parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .map(|p| p.join("kairo-sidecar").join("sidecar").join("main.py"))
            .unwrap_or_default(),
        // Relative to current working directory
        cwd.join("kairo-sidecar").join("sidecar").join("main.py"),
        // Explicit known location based on project structure
        dirs::home_dir()
            .unwrap_or_default()
            .join("Desktop")
            .join("Memory")
            .join("KairoPhantom")
            .join("kairo-sidecar")
            .join("sidecar")
            .join("main.py"),
    ];

    let sidecar_path = candidates.into_iter().find(|p| p.exists());

    let sidecar_path = match sidecar_path {
        Some(p) => {
            tracing::info!("🐍 Found sidecar at: {:?}", p);
            p
        }
        None => {
            tracing::warn!(
                "⚠️  Sidecar not found in any candidate path — document-native mode disabled"
            );
            tracing::warn!(
                "   To enable: place sidecar.py at <project_root>/kairo-sidecar/sidecar.py"
            );
            return;
        }
    };

    tokio::spawn(async move {
        let mut backoff_secs = 2u64;
        loop {
            let log_dir = dirs::home_dir().unwrap_or_default().join(".kairo-phantom");
            let _ = std::fs::create_dir_all(&log_dir);
            let log_file_path = log_dir.join("sidecar-error.log");

            let py_execs = vec!["python", "python3", "py"];
            let mut started = false;

            for exec in py_execs {
                tracing::info!(
                    "🐍 Attempting to launch Python sidecar using '{}': {:?}",
                    exec,
                    sidecar_path
                );

                let stderr_file = std::fs::File::create(&log_file_path)
                    .map(Stdio::from)
                    .unwrap_or_else(|_| Stdio::null());

                match Command::new(exec)
                    .arg(&sidecar_path)
                    .stdout(Stdio::null())
                    .stderr(stderr_file)
                    .spawn()
                {
                    Ok(mut child) => {
                        // Ping retry loop: ping every 1 second for up to 30 attempts
                        let mut ping_success = false;
                        for i in 1..=30 {
                            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                            if ping().await {
                                tracing::info!(
                                    "✅ Sidecar ready on port {} (attempt {})",
                                    SIDECAR_PORT,
                                    i
                                );
                                ping_success = true;
                                break;
                            }
                        }

                        if ping_success {
                            started = true;
                            backoff_secs = 2;
                            // Wait for child to exit
                            let _ = child.wait().await;
                            tracing::warn!(
                                "⚠️  Sidecar process exited — restarting in {}s",
                                backoff_secs
                            );
                            break; // break the exec loop to run the backoff/retry loop of the main thread
                        } else {
                            tracing::warn!(
                                "⚠️  Sidecar spawned via '{}' but failed to respond to pings",
                                exec
                            );
                            let _ = child.kill().await;
                        }
                    }
                    Err(e) => {
                        tracing::warn!("⚠️  Failed to spawn sidecar with '{}': {}", exec, e);
                    }
                }
            }

            if !started {
                tracing::error!("❌ All Python executables failed to start the sidecar.");
                crate::toast_notification::show_error_toast(
                    "Kairo Sidecar failed to start. Check ~/.kairo-phantom/sidecar-error.log",
                );

                tokio::time::sleep(std::time::Duration::from_secs(backoff_secs)).await;
                backoff_secs = (backoff_secs * 2).min(60);
            }
        }
    });
}

// ─── Domain 4: PDF Extraction & Kami Export ──────────────────────────────────

/// Extract PDF content via the multi-tier Python sidecar engine.
/// Returns structured JSON with text, markdown, tables, headings, and metadata.
pub async fn pdf_extract(file_path: &str) -> Result<serde_json::Value> {
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "pdf_extract".to_string(),
        path: Some(file_path.to_string()),
        payload: None,
    })
    .await
}

/// Export Markdown content to a professionally typeset PDF via any2pdf/reportlab.
/// Returns the path of the generated PDF file.
pub async fn pdf_kami_export(
    content: &str,
    theme: &str,
    title: &str,
    author: &str,
    output_path: &str,
) -> Result<crate::pdf_context::PdfKamiExportResult> {
    let payload = serde_json::json!({
        "content": content,
        "theme": theme,
        "title": title,
        "author": author,
        "output_path": output_path,
    });
    let data = call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "pdf_kami_export".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await?;
    serde_json::from_value(data).context("Failed to parse kami export result")
}

/// Extract a specific table from a PDF page.
pub async fn pdf_extract_table(
    file_path: &str,
    page: usize,
    table_index: usize,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "page": page,
        "table_index": table_index,
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "pdf_extract_table".to_string(),
        path: Some(file_path.to_string()),
        payload: Some(payload),
    })
    .await
}

// ─── Domain 5: Design & Figma — Vector-Native Ghost-Designing ───

/// Create complex frame, text, rectangle, component, or section nodes inside Figma.
pub async fn figma_create(payload: serde_json::Value) -> Result<serde_json::Value> {
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "figma_create".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}

/// Apply visual updates to the active design window.
pub async fn design_ghost_write(
    window_title: &str,
    payload: serde_json::Value,
) -> Result<serde_json::Value> {
    let mut full_payload = payload.clone();
    if let Some(obj) = full_payload.as_object_mut() {
        obj.insert("window_title".to_string(), serde_json::json!(window_title));
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "design_ghost_write".to_string(),
        path: None,
        payload: Some(full_payload),
    })
    .await
}

/// Route prompt requests to ComfyUI (or the high-fidelity offline PIL fallback).
pub async fn generate_design_asset(
    prompt: &str,
    style: &str,
    output_path: Option<&str>,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "prompt": prompt,
        "style": style,
        "output_path": output_path,
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "generate_design_asset".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}

/// Manipulate shape components, flowcharts, or lines on the tldraw whiteboard canvas.
pub async fn tldraw_canvas(
    operation: &str,
    payload: serde_json::Value,
) -> Result<serde_json::Value> {
    let mut full_payload = payload.clone();
    if let Some(obj) = full_payload.as_object_mut() {
        obj.insert("operation".to_string(), serde_json::json!(operation));
    }
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "tldraw_canvas".to_string(),
        path: None,
        payload: Some(full_payload),
    })
    .await
}

/// Transpile Figma design node trees into clean, premium Tailwind CSS / HTML.
pub async fn extract_design_code(root_id: &str) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "root_id": root_id,
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "extract_design_code".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}

// ─── Domain 7: Export & Publishing ────────────────────────────────────────────

/// Universal Kami export dispatcher — sends any `// kami <command>` to the Python sidecar.
///
/// `command`  — the export format string, e.g. `"pdf"`, `"epub"`, `"slides"`, `"podcast"`.
/// `args`     — optional key/value flags (e.g. `{"local": "true"}` for local TTS podcast).
/// `content`  — the full Markdown document text to export.
/// `title`    — document title extracted from the first H1 heading (used in metadata).
///
/// Returns the full `data` JSON from the sidecar response so callers can extract
/// `notification`, `output_path`, or any other format-specific fields.
pub async fn kami_export_sidecar(
    command: &str,
    args: &std::collections::HashMap<String, String>,
    content: &str,
    title: &str,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "command": command,
        "args": args,
        "content": content,
        "metadata": {
            "title": title,
            "author": "Kairo Phantom"
        }
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "kami_export".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}

// ── Domain 8: Multimodal Input — Sidecar Client ─────────────────────────────

/// Post-process a voice transcription through the Python sidecar.
///
/// The sidecar handles: filler word removal, punctuation restoration,
/// natural language command detection ("write me an email" → "// write email"),
/// and quality estimation.
///
/// Returns JSON with `processed_text`, `command`, `is_command`, `confidence`.
pub async fn voice_process_sidecar(
    transcription: &str,
    app_context: &serde_json::Value,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "transcription": transcription,
        "app_context": app_context,
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "voice_process".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}

/// Format a voice transcription as a Kairo prompt.
///
/// If the transcription contains a command ("hey kairo, write an email"),
/// it's converted to the `//` command format. Otherwise, wrapped as ghost-write.
///
/// Returns JSON with `prompt`, `original`, `processed`, `mode`.
pub async fn voice_format_sidecar(transcription: &str, mode: &str) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "transcription": transcription,
        "mode": mode,
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "voice_format".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}

/// Extract structured screen context from a screenshot image.
///
/// The sidecar tries: farscry (VASP) → tesseract OCR → file metadata.
///
/// Returns JSON with `text`, `structured`, `method`, `app_name`, `success`.
pub async fn screen_extract_sidecar(
    image_path: &str,
    app_context: &serde_json::Value,
) -> Result<serde_json::Value> {
    let payload = serde_json::json!({
        "image_path": image_path,
        "app_context": app_context,
    });
    call_sidecar(SidecarRequest {
        id: Uuid::new_v4().to_string(),
        action: "screen_extract".to_string(),
        path: None,
        payload: Some(payload),
    })
    .await
}
