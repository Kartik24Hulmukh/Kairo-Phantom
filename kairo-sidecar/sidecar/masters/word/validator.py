"""
sidecar/masters/word/validator.py
===================================
Validation layer for Word document operations.

Validates styles (fuzzy match), paragraph indices (clamping),
and compound operations before they are applied to the document.
"""

from __future__ import annotations

import difflib
import logging
from typing import List, Tuple

log = logging.getLogger("kairo-sidecar.word.validator")


class WordOperationValidator:
    """
    Validates Word document operations against the live document state.

    All validate_* methods follow the convention:
        (corrected_value, was_corrected: bool)

    The umbrella validate_and_correct() method runs all checks and returns a
    tuple of (corrected_operation_dict, list_of_human_readable_corrections).
    """

    # ── Style fuzzy matching ───────────────────────────────────────────────────

    def validate_style(
        self,
        requested_style: str,
        available_styles: List[str],
    ) -> Tuple[str, bool]:
        """
        Fuzzy-match *requested_style* against *available_styles*.

        Uses difflib.get_close_matches with cutoff=0.6.  Falls back to the
        first style whose name contains the requested name (case-insensitive),
        then to "Normal" as the final default.

        Parameters
        ----------
        requested_style : str
            The style name produced by the LLM.
        available_styles : List[str]
            Paragraph style names that actually exist in this document.

        Returns
        -------
        (matched_style, was_corrected)
        """
        if not requested_style:
            return ("Normal", True)

        # Exact match — fast path
        if requested_style in available_styles:
            return (requested_style, False)

        # Fuzzy match via difflib
        matches = difflib.get_close_matches(
            requested_style,
            available_styles,
            n=1,
            cutoff=0.6,
        )
        if matches:
            return (matches[0], True)

        # Case-insensitive substring match
        lower_req = requested_style.lower()
        for style in available_styles:
            if lower_req in style.lower() or style.lower() in lower_req:
                return (style, True)

        # Normalised alias fallback
        normalised = requested_style.replace(" ", "").replace("_", "").replace("-", "").lower()
        aliases = {
            "heading1": "Heading 1",
            "heading2": "Heading 2",
            "heading3": "Heading 3",
            "heading4": "Heading 4",
            "listbullet": "List Bullet",
            "listnumber": "List Number",
            "normal": "Normal",
            "bodytext": "Body Text",
            "quote": "Quote",
        }
        if normalised in aliases:
            candidate = aliases[normalised]
            if candidate in available_styles:
                return (candidate, True)
            # Return the alias even if not in doc — writer will handle gracefully
            return (candidate, True)

        # Give up — return "Normal" as ultimate fallback
        log.warning(
            f"WordOperationValidator.validate_style: no match found for '{requested_style}'; "
            "falling back to 'Normal'"
        )
        return ("Normal", True)

    # ── Paragraph index clamping ───────────────────────────────────────────────

    def validate_paragraph_index(
        self,
        idx: int,
        doc_length: int,
    ) -> Tuple[int, bool]:
        """
        Clamp *idx* to the valid paragraph range [0, doc_length-1].

        Parameters
        ----------
        idx : int
            Requested paragraph index (possibly out-of-range).
        doc_length : int
            Total number of paragraphs in the document.

        Returns
        -------
        (clamped_idx, was_corrected)
        """
        if doc_length <= 0:
            return (0, idx != 0)

        clamped = max(0, min(idx, doc_length - 1))
        return (clamped, clamped != idx)

    # ── Compound validation ───────────────────────────────────────────────────

    def validate_and_correct(
        self,
        operation: dict,
        doc_context,
    ) -> Tuple[dict, List[str]]:
        """
        Run all applicable validations on *operation* and return the corrected
        operation along with a human-readable list of corrections made.

        Supports operations with keys: type/action, style, paragraph_index,
        after_paragraph_index.

        Parameters
        ----------
        operation : dict
            The operation dict to validate (mutated in-place and returned).
        doc_context
            Either a WordContext (from word_master) or a WordDocumentContext
            (from this package).  Must expose:
              - styles (dict with "paragraph" key) OR styles_used (List[str])
              - total_paragraphs (int) OR len(paragraphs)

        Returns
        -------
        (corrected_operation, corrections_made)
        """
        op = operation.copy()
        corrections: List[str] = []

        # ── Resolve available styles ────────────────────────────────────────
        if hasattr(doc_context, "styles") and isinstance(doc_context.styles, dict):
            available_styles = doc_context.styles.get("paragraph", [])
        elif hasattr(doc_context, "styles_used"):
            available_styles = list(doc_context.styles_used)
        else:
            available_styles = []

        # ── Resolve document length ─────────────────────────────────────────
        if hasattr(doc_context, "total_paragraphs"):
            doc_length = int(doc_context.total_paragraphs)
        elif hasattr(doc_context, "paragraphs"):
            doc_length = len(doc_context.paragraphs)
        else:
            doc_length = 0

        # ── Style validation ────────────────────────────────────────────────
        op_type = op.get("type", op.get("action", ""))
        style_ops = {
            "insert_paragraph",
            "replace_paragraph",
            "append",
            "insert_after_heading",
            "change_style",
        }
        if op_type in style_ops and "style" in op:
            corrected_style, was_corrected = self.validate_style(op["style"], available_styles)
            if was_corrected:
                corrections.append(f"Style '{op['style']}' corrected to '{corrected_style}'")
                op["style"] = corrected_style

        # ── paragraph_index clamping ────────────────────────────────────────
        if "paragraph_index" in op:
            clamped, was_corrected = self.validate_paragraph_index(
                int(op["paragraph_index"]), doc_length
            )
            if was_corrected:
                corrections.append(f"paragraph_index {op['paragraph_index']} clamped to {clamped}")
                op["paragraph_index"] = clamped

        # ── after_paragraph_index clamping ──────────────────────────────────
        if "after_paragraph_index" in op:
            raw_idx = int(op["after_paragraph_index"])
            if raw_idx == -1:
                # -1 means "append at end" — valid, leave unchanged
                pass
            else:
                clamped, was_corrected = self.validate_paragraph_index(raw_idx, doc_length)
                if was_corrected:
                    corrections.append(f"after_paragraph_index {raw_idx} clamped to {clamped}")
                    op["after_paragraph_index"] = clamped

        # ── Text safety (basic empty-text guard) ────────────────────────────
        if op_type in {"insert_paragraph", "replace_paragraph"}:
            text = op.get("text", "")
            runs = op.get("runs", [])
            if not text and not runs:
                corrections.append("Empty text/runs — added placeholder text")
                op["text"] = " "

        return (op, corrections)
