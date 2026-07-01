import json
from typing import Any, List


# ---------------------------------------------------------------------------
# PromptBuilder — canonical variable injection order for all domains
# ---------------------------------------------------------------------------


class PromptBuilder:
    """
    Assembles the final LLM prompt by injecting context blocks in a fixed order:

      1. app_name       → sets the domain context (which application is active)
      2. doc_context    → live document state serialised as JSON
      3. mem_context    → top-5 memories from MemMachine (user style preferences)
      4. classification → intent type, domain, confidence
      5. user_prompt    → ALWAYS LAST — never let user text override system context

    This order ensures the LLM reads system context before the user instruction,
    preventing prompt-injection attacks where the user tries to override instructions.
    """

    # ── Sentinel tokens used in template substitution ─────────────────────────
    _BLOCK_SEP = "\n\n"

    def __init__(self, system_rules: str = ""):
        """
        Parameters
        ----------
        system_rules : str
            Domain-specific SYSTEM: block prepended before all context blocks.
        """
        self._system_rules = system_rules

    def build(
        self,
        app_name: str,
        doc_context: Any,
        mem_context: str,
        classification: Any,
        user_prompt: str,
        *,
        output_schema_hint: str = "",
        json_reminder: str = (
            "REMINDER: Your entire response must be a single JSON object. "
            "First character must be {. Last character must be }."
        ),
    ) -> str:
        """
        Assemble the complete prompt string.

        Injection order (FIXED — DO NOT CHANGE):
          1. system_rules
          2. app_name block
          3. doc_context block
          4. mem_context block
          5. classification block
          6. output_schema_hint (optional)
          7. json_reminder
          8. user_prompt  ← ALWAYS LAST

        Returns
        -------
        str
            The fully-assembled prompt ready for the LLM.
        """
        parts: List[str] = []

        # ── 0. System rules (domain-specific instructions) ────────────────────
        if self._system_rules:
            parts.append(self._system_rules)

        # ── 1. app_name ───────────────────────────────────────────────────────
        app_name_str = str(app_name) if app_name else "Unknown Application"
        parts.append(f"=== APP CONTEXT ===\n" f"Application Name: {app_name_str}")

        # ── 2. doc_context ────────────────────────────────────────────────────
        if doc_context is not None:
            if isinstance(doc_context, str):
                doc_json = doc_context
            else:
                try:
                    if hasattr(doc_context, "to_dict"):
                        doc_json = json.dumps(doc_context.to_dict(), indent=2, default=str)
                    elif hasattr(doc_context, "model_dump"):
                        doc_json = json.dumps(doc_context.model_dump(), indent=2, default=str)
                    elif isinstance(doc_context, dict):
                        doc_json = json.dumps(doc_context, indent=2, default=str)
                    else:
                        doc_json = json.dumps(vars(doc_context), indent=2, default=str)
                except Exception:
                    doc_json = str(doc_context)
        else:
            doc_json = "{}"

        parts.append(f"=== DOCUMENT CONTEXT ===\n{doc_json}")

        # ── 3. mem_context ────────────────────────────────────────────────────
        mem_str = (
            mem_context
            if mem_context
            else "No writing preferences learned yet. Use professional defaults."
        )
        parts.append(f"=== MEMORY CONTEXT ===\nUser Writing Preferences:\n{mem_str}")

        # ── 4. classification ─────────────────────────────────────────────────
        if classification is not None:
            if isinstance(classification, str):
                cls_str = classification
            elif isinstance(classification, dict):
                cls_str = json.dumps(classification)
            elif hasattr(classification, "model_dump"):
                cls_str = json.dumps(classification.model_dump())
            elif hasattr(classification, "__dataclass_fields__"):
                import dataclasses

                cls_str = json.dumps(dataclasses.asdict(classification))
            else:
                cls_str = str(classification)
        else:
            cls_str = "unknown"

        parts.append(f"=== INTENT CLASSIFICATION ===\nClassification: {cls_str}")

        # ── 5. output_schema_hint (optional) ─────────────────────────────────
        if output_schema_hint:
            parts.append(output_schema_hint)

        # ── 6. json_reminder ──────────────────────────────────────────────────
        if json_reminder:
            parts.append(json_reminder)

        # ── 7. user_prompt — ALWAYS LAST ─────────────────────────────────────
        # Strip any attempt to include system-context override phrases
        safe_prompt = user_prompt if user_prompt else ""
        parts.append(f"USER INSTRUCTION: {safe_prompt}\nOUTPUT (JSON only):")

        return self._BLOCK_SEP.join(parts)


# Helper wrapper to support both custom objects and dictionaries
class UniversalContextWrapper:
    def __init__(self, obj: Any):
        if obj is None:
            self._obj = {}
        elif isinstance(obj, UniversalContextWrapper):
            self._obj = obj._obj
        else:
            self._obj = obj

    def __getattr__(self, name: str) -> Any:
        if isinstance(self._obj, dict):
            if name in self._obj:
                return self._obj[name]
            return None
        else:
            try:
                return getattr(self._obj, name)
            except AttributeError:
                if hasattr(self._obj, "__dict__") and name in self._obj.__dict__:
                    return self._obj.__dict__[name]
                return None

    def __getitem__(self, key: str) -> Any:
        if isinstance(self._obj, dict):
            return self._obj.get(key)
        else:
            if hasattr(self._obj, key):
                return getattr(self._obj, key)
            if hasattr(self._obj, "__dict__") and key in self._obj.__dict__:
                return self._obj.__dict__[key]
            return None

    def get(self, key: str, default: Any = None) -> Any:
        if isinstance(self._obj, dict):
            return self._obj.get(key, default)
        else:
            if hasattr(self._obj, key):
                val = getattr(self._obj, key)
                return val if val is not None else default
            if hasattr(self._obj, "__dict__") and key in self._obj.__dict__:
                val = self._obj.__dict__[key]
                return val if val is not None else default
            if hasattr(self._obj, "to_dict"):
                try:
                    d = self._obj.to_dict()
                    if isinstance(d, dict) and key in d:
                        return d[key]
                except Exception:
                    pass
            return default

    def __contains__(self, key: str) -> bool:
        if isinstance(self._obj, dict):
            return key in self._obj
        else:
            return hasattr(self._obj, key) or (
                hasattr(self._obj, "__dict__") and key in self._obj.__dict__
            )


# Maintain DictAttrWrapper alias for compatibility
DictAttrWrapper = UniversalContextWrapper


def build_word_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.word_master import WordContext
    from sidecar.masters.word_prompt_builder import build_word_prompt as _build_word

    # Extract file_path from inputs before unwrapping/converting doc_context
    file_path = "Unknown"
    if doc_context is not None:
        if isinstance(doc_context, UniversalContextWrapper):
            file_path = doc_context.get("file_path") or "Unknown"
        elif isinstance(doc_context, dict):
            file_path = doc_context.get("file_path") or "Unknown"
        else:
            file_path = getattr(doc_context, "file_path", None) or "Unknown"

    if isinstance(doc_context, UniversalContextWrapper):
        doc_context = doc_context._obj

    if doc_context is None:
        doc_context = {}

    if isinstance(doc_context, dict):
        styles = doc_context.get("styles", {})
        paragraphs = doc_context.get("paragraphs", [])
        tables = doc_context.get("tables", [])
        theme_fonts = doc_context.get("theme_fonts", {})
        list_sequences = doc_context.get("list_sequences", [])
        document_purpose = doc_context.get("document_purpose", "business_memo")
        cursor_paragraph_index = doc_context.get("cursor_paragraph_index", 0)
        total_paragraphs = doc_context.get("total_paragraphs", len(paragraphs))

        context_obj = WordContext(
            styles=styles,
            paragraphs=paragraphs,
            tables=tables,
            theme_fonts=theme_fonts,
            list_sequences=list_sequences,
            document_purpose=document_purpose,
            cursor_paragraph_index=cursor_paragraph_index,
            total_paragraphs=total_paragraphs,
        )
    else:
        context_obj = doc_context

    # Extract classification intent
    intent_classification = "Document Operation Generation"
    if classification is not None:
        if isinstance(classification, str):
            intent_classification = classification
        elif isinstance(classification, dict):
            intent_classification = (
                classification.get("task_type")
                or classification.get("intent")
                or classification.get("classification")
                or "Document Operation Generation"
            )
        else:
            intent_classification = (
                getattr(classification, "task_type", None)
                or getattr(classification, "intent", None)
                or getattr(classification, "classification", None)
                or "Document Operation Generation"
            )

    return _build_word(
        user_instruction=user_prompt,
        context=context_obj,
        mem_context=mem_context,
        file_path=file_path,
        app_name="Microsoft Word",
        app_type="Word Processor",
        intent_classification=intent_classification,
    )


def build_excel_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    if isinstance(doc_context, UniversalContextWrapper):
        doc_context = doc_context._obj

    if doc_context is None:
        doc_context = {}

    context = UniversalContextWrapper(doc_context)

    grid_rows = []
    if isinstance(doc_context, dict) and "grid" in doc_context:
        grid_rows = doc_context["grid"]
    else:
        cells = getattr(context, "cells", [])
        if cells:
            row_dict = {}
            for c in cells:
                ref = c.get("address", "A1") if isinstance(c, dict) else getattr(c, "address", "A1")
                row_num = int("".join(ch for ch in ref if ch.isdigit()) or "1")
                val = c.get("value") if isinstance(c, dict) else getattr(c, "value", "")
                formula = c.get("formula") if isinstance(c, dict) else getattr(c, "formula", "")
                active_cell = getattr(context, "active_cell", "A1")
                row_dict.setdefault(row_num, []).append(
                    {
                        "ref": ref,
                        "value": val or "",
                        "formula": formula or "",
                        "is_active": ref == active_cell,
                    }
                )
            for r_num in sorted(row_dict.keys()):
                grid_rows.append(row_dict[r_num])

    memory_str = mem_context or "No writing preferences learned yet. Use professional defaults."
    active_cell = getattr(context, "active_cell", "A1")
    active_sheet = getattr(context, "active_sheet", "Sheet1")
    sheet_names_list = getattr(context, "sheet_names", ["Sheet1"])
    sheet_names = json.dumps(sheet_names_list)
    cell_grid_json = json.dumps(grid_rows, indent=2)

    headers_val = getattr(context, "headers", {})
    if isinstance(headers_val, dict):
        headers = json.dumps(list(headers_val.values()))
    elif isinstance(headers_val, list):
        headers = json.dumps(headers_val)
    else:
        headers = json.dumps([])

    named_ranges_val = getattr(context, "named_ranges", [])
    named_ranges = json.dumps(named_ranges_val)
    locale = getattr(context, "locale", "en") or "en"

    column_types_dict = {}
    cells_list = getattr(context, "cells", [])
    if cells_list:
        for c in cells_list:
            ref = c.get("address", "A1") if isinstance(c, dict) else getattr(c, "address", "A1")
            col_letter = "".join(ch for ch in ref if ch.isalpha())
            val = c.get("value") if isinstance(c, dict) else getattr(c, "value", None)
            if not val:
                continue
            if col_letter not in column_types_dict:
                try:
                    float(val)
                    column_types_dict[col_letter] = "Number"
                except ValueError:
                    column_types_dict[col_letter] = "Text"
        for c in cells_list:
            ref = c.get("address", "A1") if isinstance(c, dict) else getattr(c, "address", "A1")
            col_letter = "".join(ch for ch in ref if ch.isalpha())
            if col_letter not in column_types_dict:
                column_types_dict[col_letter] = "Text"
    column_types = json.dumps(column_types_dict)

    app_context_part = """=== APP CONTEXT ===
Application Name: Microsoft Excel
Application Type: Spreadsheet
File Path: Unknown"""

    doc_context_part = f"""=== DOCUMENT CONTEXT ===
SPREADSHEET CONTEXT (injected):
Active cell: {active_cell} on sheet: {active_sheet}
Available sheets: {sheet_names}
Surrounding cells (15x15 grid centered on active cell):
{cell_grid_json}
Detected headers (row 1): {headers}
Named ranges: {named_ranges}
Column types: {column_types}
Locale: {locale} (en=comma separator, eu=semicolon separator)"""

    memory_part = f"""=== MEMORY CONTEXT ===
User Writing Preferences:
{memory_str}"""

    classification_part = """=== INTENT CLASSIFICATION ===
Intent Classification: Spreadsheet Formula / Data Operation Generation"""

    system_rules = """SYSTEM:
You are the Excel Spreadsheet Master for Kairo Phantom. You have deep expertise in Excel formulas,
financial modeling, data analysis, and spreadsheet best practices.

CONSTRAINTS:
- Output ONLY valid JSON matching ExcelResponse schema. No prose. No explanation. No code fences.
- NEVER write formulas you cannot verify are syntactically correct
- NEVER modify cells not explicitly targeted in your operations
- NEVER auto-calculate or evaluate formulas — write them exactly as strings starting with =
- Inside JSON string values, NEVER use unescaped double quotes. If an Excel formula needs a text argument, always use single quotes (e.g. "=SUMIF(B:B, 'Widget A', D:D)") to keep the JSON valid. Kairo automatically converts single quotes to double quotes when injecting.

FORMULA WRITING RULES:
1. ALL formulas MUST start with =
2. Match the locale: en uses commas =SUM(A1,A2), eu uses semicolons =SUM(A1;A2)
3. Sheet names with spaces MUST be quoted: ='Sheet Name'!A1
4. Always include the 4th argument in VLOOKUP: =VLOOKUP(A1,B:C,2,FALSE)
5. Use absolute references ($) for lookup ranges: =VLOOKUP(A1,$B$1:$C$100,2,FALSE)
6. For SUMIF/COUNTIF: criteria range and sum range must match in size
7. Avoid circular references (referencing active cell)
8. Never hardcode values inside formulas if they can be referenced

OUTPUT SCHEMA:
{
  "operations": [
    {
      "type": "write_formula",
      "cell": "string — e.g. B2",
      "formula": "string — e.g. =SUM(A1:A10)"
    },
    {
      "type": "write_value",
      "cell": "string",
      "value": "string or number"
    },
    {
      "type": "clear_cell",
      "cell": "string"
    }
  ],
  "confidence": 0.0-1.0,
  "reasoning": "one sentence max (not shown to user)",
  "needs_clarification": false,
  "clarification_question": null
}"""

    json_reminder = "REMINDER: Your entire response must be a single JSON object. First character must be {. Last character must be }."

    return f"""{system_rules}

{app_context_part}

{doc_context_part}

{memory_part}

{classification_part}

{json_reminder}
USER INSTRUCTION: {user_prompt}
OUTPUT (JSON only):"""


def build_powerpoint_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import PowerPointMaster

    master = PowerPointMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_code_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import CodeMaster

    master = CodeMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_pdf_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import PDFMaster

    master = PDFMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_browser_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import BrowserMaster

    master = BrowserMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_terminal_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import TerminalMaster

    master = TerminalMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_email_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import EmailMaster

    master = EmailMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_notes_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import NotesMaster

    master = NotesMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_design_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import DesignMaster

    master = DesignMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_media_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import MediaMaster

    master = MediaMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)


def build_data_prompt(
    user_prompt: str, doc_context: Any, mem_context: str, classification: Any = None
) -> str:
    from sidecar.masters.other_masters import DataMaster

    master = DataMaster()
    context = UniversalContextWrapper(doc_context)
    return master.build_prompt(user_prompt, context, mem_context, classification)
