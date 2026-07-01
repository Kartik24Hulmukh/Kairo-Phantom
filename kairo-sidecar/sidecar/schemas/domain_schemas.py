from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Any, Optional, Union


# --- 1. Code Master ---
class InsertAtLineOp(BaseModel):
    type: Literal["insert_at_line"] = "insert_at_line"
    line: int
    code: str
    language: str


class ReplaceLinesOp(BaseModel):
    type: Literal["replace_lines"] = "replace_lines"
    start_line: int
    end_line: int
    code: str


class AddImportOp(BaseModel):
    type: Literal["add_import"] = "add_import"
    import_statement: str
    insert_at_line: int


class ShowOnlyOp(BaseModel):
    type: Literal["show_only"] = "show_only"
    content: str


CodeOperation = Union[InsertAtLineOp, ReplaceLinesOp, AddImportOp, ShowOnlyOp]


class CodeResponse(BaseModel):
    operations: List[CodeOperation]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


# --- 2. PDF Master ---
class CreateDocxSection(BaseModel):
    heading: Optional[str] = None
    level: Optional[int] = 1
    body: Optional[str] = None
    table: Optional[Dict[str, Any]] = None


class CreateDocxOp(BaseModel):
    type: Literal["create_docx"] = "create_docx"
    sections: List[CreateDocxSection]


class ClipboardTextOp(BaseModel):
    type: Literal["clipboard_text"] = "clipboard_text"
    content: str


class ExcelTableOp(BaseModel):
    type: Literal["excel_table"] = "excel_table"
    headers: List[str]
    rows: List[List[Any]]


PDFOperation = Union[CreateDocxOp, ClipboardTextOp, ExcelTableOp]


class PDFResponse(BaseModel):
    output_type: Literal["docx", "text", "clipboard", "excel_table"]
    operations: List[PDFOperation]
    output_filename: str
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_quality: Literal["high", "medium", "low"] = "high"
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


# --- 3. Browser Master ---
class BrowserSafetyCheck(BaseModel):
    is_password_field: bool = False
    is_payment_field: bool = False
    is_auto_submit: bool = False


class BrowserResponse(BaseModel):
    injection_method: Literal["uia_field", "clipboard", "crdt_yjs", "show_only"]
    content: str
    platform_formatted: bool = True
    is_collaborative_editor: bool = False
    safety_check: BrowserSafetyCheck
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


# --- 4. Terminal Master ---
class TerminalResponse(BaseModel):
    injection_method: Literal["show_only"] = "show_only"
    command: str
    explanation: str
    danger_level: Literal["safe", "caution", "dangerous"] = "safe"
    warning: Optional[str] = None
    alternative: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


# --- 5. Email Master ---
class EmailResponse(BaseModel):
    injection_method: Literal["uia_field", "clipboard"]
    subject: Optional[str] = None
    body: str
    emotional_flag: bool = False
    suggested_revision: Optional[str] = None
    pii_redacted: bool = False
    tone: Literal["formal", "professional", "casual"] = "professional"
    word_count: int
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


# --- 6. Notes Master ---
class NotesResponse(BaseModel):
    injection_method: Literal["file_write", "uia_field", "clipboard"]
    insert_at_line: int
    content: str
    new_tags: List[str] = []
    new_links: List[str] = []
    frontmatter_update: Optional[Dict[str, Any]] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


# --- 7. Design Master ---
class CreateTextOp(BaseModel):
    type: Literal["create_text"] = "create_text"
    parent_frame_id: str
    text: str
    x: float
    y: float
    width: float
    font_size: Optional[float] = None
    font_weight: Literal["regular", "medium", "semibold", "bold"] = "regular"
    color_token: Optional[str] = None
    alignment: Literal["left", "center", "right"] = "left"


class SetTextOp(BaseModel):
    type: Literal["set_text"] = "set_text"
    node_id: str
    text: str


class SetFillsOp(BaseModel):
    type: Literal["set_fills"] = "set_fills"
    node_id: str
    color_hex: str
    opacity: float = 1.0


class DesignShowOnlyOp(BaseModel):
    type: Literal["show_only"] = "show_only"
    design_suggestion: str


DesignOperation = Union[CreateTextOp, SetTextOp, SetFillsOp, DesignShowOnlyOp]


class DesignResponse(BaseModel):
    injection_method: Literal["figma_mcp", "penpot_mcp", "clipboard"]
    operations: List[DesignOperation]
    design_rationale: str
    accessibility_notes: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default="", max_length=200)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


# --- 8. Media Master ---
class MediaResponse(BaseModel):
    injection_method: Literal["clipboard", "uia_field", "script_write", "show_only"]
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="")


# --- 9. Data Master ---
class DataResponse(BaseModel):
    injection_method: Literal["clipboard", "uia_field", "script_write", "show_only"]
    content: str
    language: str = "python"
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="")


# --- 10. Master Orchestrator ---
class OrchestratorResponse(BaseModel):
    domain: Literal[
        "word",
        "excel",
        "powerpoint",
        "code",
        "pdf",
        "browser",
        "terminal",
        "email",
        "notes",
        "design",
        "media",
        "data",
        "unknown",
    ] = "unknown"
    task_type: Literal[
        "insert", "replace", "analyze", "explain", "export", "generate", "rewrite", "fix", "unknown"
    ] = "unknown"
    target: Literal[
        "paragraph",
        "heading",
        "table",
        "cell",
        "formula",
        "shape",
        "slide",
        "selection",
        "document",
        "file",
        "unknown",
    ] = "unknown"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    clarifying_question: Optional[str] = None
    waza_agent: Literal[
        "corporate_strategist",
        "developer",
        "legal_reviewer",
        "medical_scribe",
        "academic_editor",
        "creative_writer",
        "data_analyst",
        "general",
    ] = "general"
    complexity: Literal["simple", "medium", "complex"] = "medium"
    estimated_tokens: int = 500
    requires_web_search: bool = False
    safety_flags: List[str] = []
    reasoning: Optional[str] = None
