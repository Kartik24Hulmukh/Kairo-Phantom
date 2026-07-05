# PROVENANCE: original | clean-room Word/docs domain oracles per VERIFICATION_ORACLES.md
"""Word/docs domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``docx_readback`` — after creating/editing a .docx, REOPEN it via
     python-docx and assert paragraphs/headings/styles/lists/table cells
     match the intended spec.  KILL-PROOF: alter text or drop a paragraph/
     table → FAILS.

  2. ``structure_readback`` — heading hierarchy + table dims + paragraph
     count survive round-trip.  KILL-PROOF: drop a section/table → FAILS.

Both oracles are KILL-PROVEN: perturbing the expected structure (dropping a
paragraph, altering text, dropping a table, wrong table dims) causes a hard
failure.

HONEST DEGRADATION:
  If python-docx is not installed, the oracles raise
  ``WordEngineUnavailableError`` — they never present unverified
  results as correct.

All operations are fully offline. No network calls. No LLM. No cloud.

Dependencies (all permissive — MIT):
  - python-docx (MIT) — .docx create/edit/read
"""

from __future__ import annotations

from typing import Any

from kairo.domains.word.engine import read_document


# ---------------------------------------------------------------------------
# Oracle 1: docx_readback
# ---------------------------------------------------------------------------


def docx_readback(
    file_path: str,
    expected_paragraphs: list[dict[str, Any]],
    expected_tables: list[dict[str, Any]] | None = None,
) -> bool:
    """Oracle: reopen .docx → assert paragraphs/headings/styles/lists/table cells match spec.

    KILL-PROOF: alter text, drop a paragraph, or change a table cell → FAILS.

    Args:
        file_path: Path to the saved .docx file.
        expected_paragraphs: List of dicts with keys:
            'text' (str) — exact text to match,
            'style' (str) — expected style name (optional),
            'heading_level' (int) — expected heading level (optional),
            'list_type' (str) — expected list type (optional),
            'runs' (list[dict]) — expected runs with text/bold/italic (optional).
        expected_tables: Optional list of dicts with keys:
            'rows' (int), 'cols' (int), 'cells' (list[list[str]]).

    Returns:
        True if the reopened document matches the spec exactly.

    Raises:
        AssertionError: If any field doesn't match.
        WordEngineUnavailableError: If python-docx is not installed.
    """
    doc_info = read_document(file_path)

    # Check paragraph count
    if doc_info.paragraph_count != len(expected_paragraphs):
        raise AssertionError(
            f"docx_readback FAILED: paragraph count mismatch.\n"
            f"  Expected: {len(expected_paragraphs)}\n"
            f"  Got:      {doc_info.paragraph_count}"
        )

    # Check each paragraph
    for i, expected in enumerate(expected_paragraphs):
        actual = doc_info.paragraphs[i]

        # Check text
        exp_text = expected.get("text", "")
        if actual.text != exp_text:
            raise AssertionError(
                f"docx_readback FAILED: paragraph {i} text mismatch.\n"
                f"  Expected: {exp_text!r}\n"
                f"  Got:      {actual.text!r}"
            )

        # Check style (if specified)
        if "style" in expected:
            if actual.style != expected["style"]:
                raise AssertionError(
                    f"docx_readback FAILED: paragraph {i} style mismatch.\n"
                    f"  Expected: {expected['style']}\n"
                    f"  Got:      {actual.style}"
                )

        # Check heading level (if specified)
        if "heading_level" in expected:
            if actual.heading_level != expected["heading_level"]:
                raise AssertionError(
                    f"docx_readback FAILED: paragraph {i} heading level mismatch.\n"
                    f"  Expected: {expected['heading_level']}\n"
                    f"  Got:      {actual.heading_level}"
                )

        # Check list type (if specified)
        if "list_type" in expected:
            if actual.list_type != expected["list_type"]:
                raise AssertionError(
                    f"docx_readback FAILED: paragraph {i} list type mismatch.\n"
                    f"  Expected: {expected['list_type']}\n"
                    f"  Got:      {actual.list_type}"
                )

        # Check runs (if specified)
        if "runs" in expected:
            exp_runs = expected["runs"]
            if len(actual.runs) != len(exp_runs):
                raise AssertionError(
                    f"docx_readback FAILED: paragraph {i} run count mismatch.\n"
                    f"  Expected: {len(exp_runs)}\n"
                    f"  Got:      {len(actual.runs)}"
                )
            for j, exp_run in enumerate(exp_runs):
                act_run = actual.runs[j]
                if act_run.text != exp_run.get("text", ""):
                    raise AssertionError(
                        f"docx_readback FAILED: paragraph {i} run {j} text mismatch.\n"
                        f"  Expected: {exp_run.get('text', '')!r}\n"
                        f"  Got:      {act_run.text!r}"
                    )
                if exp_run.get("bold") and not act_run.bold:
                    raise AssertionError(
                        f"docx_readback FAILED: paragraph {i} run {j} "
                        f"expected bold but got not bold."
                    )
                if exp_run.get("italic") and not act_run.italic:
                    raise AssertionError(
                        f"docx_readback FAILED: paragraph {i} run {j} "
                        f"expected italic but got not italic."
                    )

    # Check tables (if specified)
    if expected_tables is not None:
        if doc_info.table_count != len(expected_tables):
            raise AssertionError(
                f"docx_readback FAILED: table count mismatch.\n"
                f"  Expected: {len(expected_tables)}\n"
                f"  Got:      {doc_info.table_count}"
            )

        for i, expected_tbl in enumerate(expected_tables):
            actual_tbl = doc_info.tables[i]

            exp_rows = expected_tbl.get("rows", 0)
            exp_cols = expected_tbl.get("cols", 0)
            if actual_tbl.rows != exp_rows or actual_tbl.cols != exp_cols:
                raise AssertionError(
                    f"docx_readback FAILED: table {i} dims mismatch.\n"
                    f"  Expected: {exp_rows}x{exp_cols}\n"
                    f"  Got:      {actual_tbl.rows}x{actual_tbl.cols}"
                )

            exp_cells = expected_tbl.get("cells", [])
            if exp_cells:
                for r_idx, exp_row in enumerate(exp_cells):
                    for c_idx, exp_cell in enumerate(exp_row):
                        act_cell = actual_tbl.cells[r_idx][c_idx]
                        if act_cell != exp_cell:
                            raise AssertionError(
                                f"docx_readback FAILED: table {i} cell "
                                f"({r_idx},{c_idx}) mismatch.\n"
                                f"  Expected: {exp_cell!r}\n"
                                f"  Got:      {act_cell!r}"
                            )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: structure_readback
# ---------------------------------------------------------------------------


def structure_readback(
    file_path: str,
    expected_paragraph_count: int,
    expected_table_count: int = 0,
    expected_heading_levels: list[int] | None = None,
    expected_table_dims: list[tuple[int, int]] | None = None,
) -> bool:
    """Oracle: heading hierarchy + table dims + paragraph count survive round-trip.

    KILL-PROOF: drop a section/table or change heading count → FAILS.

    Args:
        file_path: Path to the saved .docx file.
        expected_paragraph_count: Expected number of paragraphs.
        expected_table_count: Expected number of tables.
        expected_heading_levels: Optional list of heading levels in order.
        expected_table_dims: Optional list of (rows, cols) tuples per table.

    Returns:
        True if the structure matches expectations.

    Raises:
        AssertionError: If any structural element doesn't match.
        WordEngineUnavailableError: If python-docx is not installed.
    """
    doc_info = read_document(file_path)

    # Check paragraph count
    if doc_info.paragraph_count != expected_paragraph_count:
        raise AssertionError(
            f"structure_readback FAILED: paragraph count mismatch.\n"
            f"  Expected: {expected_paragraph_count}\n"
            f"  Got:      {doc_info.paragraph_count}"
        )

    # Check table count
    if doc_info.table_count != expected_table_count:
        raise AssertionError(
            f"structure_readback FAILED: table count mismatch.\n"
            f"  Expected: {expected_table_count}\n"
            f"  Got:      {doc_info.table_count}"
        )

    # Check heading levels (if specified)
    if expected_heading_levels is not None:
        actual_headings = [
            p.heading_level for p in doc_info.paragraphs if p.heading_level > 0 or p.style == "Title"
        ]
        if len(actual_headings) != len(expected_heading_levels):
            raise AssertionError(
                f"structure_readback FAILED: heading count mismatch.\n"
                f"  Expected: {len(expected_heading_levels)} headings: {expected_heading_levels}\n"
                f"  Got:      {len(actual_headings)} headings: {actual_headings}"
            )
        for i, (actual_lvl, expected_lvl) in enumerate(zip(actual_headings, expected_heading_levels)):
            if actual_lvl != expected_lvl:
                raise AssertionError(
                    f"structure_readback FAILED: heading {i} level mismatch.\n"
                    f"  Expected: {expected_lvl}\n"
                    f"  Got:      {actual_lvl}"
                )

    # Check table dims (if specified)
    if expected_table_dims is not None:
        if len(doc_info.tables) != len(expected_table_dims):
            raise AssertionError(
                f"structure_readback FAILED: table count for dims check mismatch.\n"
                f"  Expected: {len(expected_table_dims)}\n"
                f"  Got:      {len(doc_info.tables)}"
            )
        for i, (exp_rows, exp_cols) in enumerate(expected_table_dims):
            actual = doc_info.tables[i]
            if actual.rows != exp_rows or actual.cols != exp_cols:
                raise AssertionError(
                    f"structure_readback FAILED: table {i} dims mismatch.\n"
                    f"  Expected: {exp_rows}x{exp_cols}\n"
                    f"  Got:      {actual.rows}x{actual.cols}"
                )

    return True
