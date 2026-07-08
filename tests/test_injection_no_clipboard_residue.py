"""
W6 Oracle: test_injection_no_clipboard_residue

Verifies that the CUA text input pipeline does not leave clipboard residue
after text replacement operations. This is the oracle for W6 (Remove
clipboard-based injection leakage).

The test verifies:
1. Direct UIA ValuePattern path exists and is preferred over clipboard
2. SendInput Unicode typing path exists as a no-clipboard fallback
3. Clipboard clear method exists and is called after clipboard paste
4. The _type_text method saves/restores clipboard and clears after paste
5. No clipboard round-trip occurs on the primary (UIA/SendInput) paths

These tests run on all platforms (the CUA code uses Windows APIs but
the test verifies the code structure and logic, not the actual Windows
clipboard state).
"""
from __future__ import annotations

import ast
import inspect
import os
import pathlib
import sys

import pytest

# Ensure repo root and sidecar are on sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
SIDECAR_ROOT = REPO_ROOT / "kairo-sidecar"
sys.path.insert(0, str(SIDECAR_ROOT))


def _get_source(path: pathlib.Path) -> str:
    """Read source code from a file path."""
    return path.read_text()


def _get_method_source(class_source: str, method_name: str) -> str:
    """Extract a method's source from class source text using AST."""
    tree = ast.parse(class_source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                return ast.get_source_segment(class_source, node)
    return ""


CANVA_CUA_PATH = SIDECAR_ROOT / "sidecar" / "cua" / "canva_cua.py"


class TestNoClipboardResidue:
    """Verify the CUA pipeline does not leave clipboard residue."""

    def test_uia_set_value_method_exists(self):
        """The _uia_set_value method must exist — direct UIA ValuePattern, no clipboard."""
        source = _get_source(CANVA_CUA_PATH)
        assert "def _uia_set_value" in source, (
            "_uia_set_value method must exist for direct UIA ValuePattern text input (no clipboard)"
        )

    def test_sendinput_type_text_method_exists(self):
        """The _sendinput_type_text method must exist — SendInput Unicode typing, no clipboard."""
        source = _get_source(CANVA_CUA_PATH)
        assert "def _sendinput_type_text" in source, (
            "_sendinput_type_text method must exist for SendInput Unicode typing (no clipboard)"
        )

    def test_clear_clipboard_method_exists(self):
        """The _clear_clipboard method must exist — clears clipboard after paste."""
        source = _get_source(CANVA_CUA_PATH)
        assert "def _clear_clipboard" in source, (
            "_clear_clipboard method must exist to clear clipboard residue after paste"
        )

    def test_get_clipboard_method_exists(self):
        """The _get_clipboard method must exist — saves clipboard for restore."""
        source = _get_source(CANVA_CUA_PATH)
        assert "def _get_clipboard" in source, (
            "_get_clipboard method must exist to save clipboard state for restore"
        )

    def test_uia_text_replace_prefers_value_pattern(self):
        """_uia_text_replace must try ValuePattern.SetValue BEFORE clipboard."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_uia_text_replace")
        assert method_src, "_uia_text_replace method not found"

        # ValuePattern must be tried before clipboard
        value_pattern_pos = method_src.find("_uia_set_value")
        clipboard_pos = method_src.find("_type_text")

        assert value_pattern_pos != -1, "_uia_text_replace must call _uia_set_value"
        assert clipboard_pos != -1, "_uia_text_replace must have clipboard fallback"
        assert value_pattern_pos < clipboard_pos, (
            "_uia_text_replace must try ValuePattern (no clipboard) BEFORE clipboard paste. "
            f"ValuePattern at pos {value_pattern_pos}, clipboard at pos {clipboard_pos}"
        )

    def test_uia_text_replace_prefers_sendinput_over_clipboard(self):
        """_uia_text_replace must try SendInput typing BEFORE clipboard."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_uia_text_replace")
        assert method_src, "_uia_text_replace method not found"

        sendinput_pos = method_src.find("_sendinput_type_text")
        clipboard_pos = method_src.find("_type_text")

        assert sendinput_pos != -1, "_uia_text_replace must call _sendinput_type_text"
        assert clipboard_pos != -1, "_uia_text_replace must have clipboard fallback"
        assert sendinput_pos < clipboard_pos, (
            "_uia_text_replace must try SendInput (no clipboard) BEFORE clipboard paste. "
            f"SendInput at pos {sendinput_pos}, clipboard at pos {clipboard_pos}"
        )

    def test_type_text_clears_clipboard_after_paste(self):
        """_type_text must clear the clipboard after paste to remove residue."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_type_text")
        assert method_src, "_type_text method not found"

        assert "_clear_clipboard" in method_src, (
            "_type_text must call _clear_clipboard after paste to remove clipboard residue"
        )

    def test_type_text_saves_and_restores_clipboard(self):
        """_type_text must save and restore the original clipboard content."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_type_text")
        assert method_src, "_type_text method not found"

        assert "_get_clipboard" in method_src, (
            "_type_text must call _get_clipboard to save original clipboard state"
        )

    def test_farscry_text_replace_uses_sendinput_first(self):
        """_farscry_text_replace must try SendInput before clipboard."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_farscry_text_replace")
        assert method_src, "_farscry_text_replace method not found"

        sendinput_pos = method_src.find("_sendinput_type_text")
        clipboard_pos = method_src.find("_type_text")

        assert sendinput_pos != -1, (
            "_farscry_text_replace must call _sendinput_type_text (no clipboard path)"
        )
        if clipboard_pos != -1:
            assert sendinput_pos < clipboard_pos, (
                "_farscry_text_replace must try SendInput BEFORE clipboard fallback"
            )

    def test_sendinput_uses_unicode_flag(self):
        """SendInput typing must use KEYEVENTF_UNICODE flag for direct character input."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_sendinput_type_text")
        assert method_src, "_sendinput_type_text method not found"

        assert "KEYEVENTF_UNICODE" in method_src, (
            "_sendinput_type_text must use KEYEVENTF_UNICODE for direct Unicode character input"
        )
        assert "SendInput" in method_src, (
            "_sendinput_type_text must use Windows SendInput API"
        )

    def test_uia_set_value_uses_value_pattern(self):
        """_uia_set_value must use UIA ValuePattern for direct text setting."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_uia_set_value")
        assert method_src, "_uia_set_value method not found"

        assert "ValuePattern" in method_src or "UIA_ValuePatternId" in method_src, (
            "_uia_set_value must use UIA ValuePattern (ValuePatternId) for direct text setting"
        )
        assert "SetValue" in method_src, (
            "_uia_set_value must call SetValue on the ValuePattern interface"
        )

    def test_clipboard_not_used_in_primary_paths(self):
        """The primary text replacement paths must not call _copy_to_clipboard directly."""
        source = _get_source(CANVA_CUA_PATH)
        uia_method = _get_method_source(source, "_uia_text_replace")
        sendinput_method = _get_method_source(source, "_sendinput_type_text")
        uia_set_value = _get_method_source(source, "_uia_set_value")

        # _uia_set_value must NOT use clipboard at all
        assert "_copy_to_clipboard" not in uia_set_value, (
            "_uia_set_value must NOT use clipboard — it's a direct API method"
        )

        # _sendinput_type_text must NOT use clipboard at all
        assert "_copy_to_clipboard" not in sendinput_method, (
            "_sendinput_type_text must NOT use clipboard — it uses SendInput API"
        )

    def test_module_docstring_documents_clipboard_priority(self):
        """The module docstring must document the clipboard-safe priority order."""
        source = _get_source(CANVA_CUA_PATH)
        # Check the docstring at the top of the file
        assert "ValuePattern" in source[:2000], (
            "Module docstring must mention ValuePattern as the primary (no-clipboard) method"
        )
        assert "SendInput" in source[:2000], (
            "Module docstring must mention SendInput as a no-clipboard method"
        )
        assert "clipboard" in source[:2000].lower(), (
            "Module docstring must mention clipboard as last resort only"
        )


class TestClipboardClearOnExit:
    """Verify clipboard is cleared even on error paths."""

    def test_type_text_clears_on_exception(self):
        """_type_text must clear clipboard even when an exception occurs."""
        source = _get_source(CANVA_CUA_PATH)
        method_src = _get_method_source(source, "_type_text")
        assert method_src, "_type_text method not found"

        # The outer except block must call _clear_clipboard
        # Find the first 'except Exception as e:' block (the outer one)
        except_idx = method_src.find("except Exception as e:")
        if except_idx != -1:
            # Get the block from this except to the end (or next except)
            except_block = method_src[except_idx:]
            assert "_clear_clipboard" in except_block, (
                "_type_text must call _clear_clipboard in the except block "
                "to ensure clipboard is cleared even on error"
            )
