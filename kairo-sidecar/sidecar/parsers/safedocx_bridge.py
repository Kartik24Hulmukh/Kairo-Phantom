"""
safe-docx Bridge — Deterministic surgical DOCX editing for Kairo Phantom.
=========================================================================
Provides a headless, deterministic DOCX editing path using the TypeScript
@usejunior/safe-docx MCP server. Used when:
  • Adeu is not installed (no Word, headless CI environment)
  • Deterministic idempotent batch edits are required
  • A "clean copy + tracked copy" pair is needed

Install: npm install -g @usejunior/safe-docx

All public functions follow the Kairo sidecar JSON envelope:
    {"ok": bool, "data": {...}, "error": str | None}
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Any

log = logging.getLogger("kairo-sidecar.safedocx_bridge")


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


def _safedocx_installed() -> bool:
    """True if npx is available (safe-docx is invoked via npx)."""
    return shutil.which("npx") is not None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def safedocx_read_file(file_path: str) -> dict:
    """
    Read a DOCX file and return paragraphs with stable _bk_NNN IDs.
    Uses: npx @usejunior/safe-docx read_file <path> --format toon
    """
    if not _safedocx_installed():
        return _unavailable("npx not found — install Node.js to use safe-docx")

    file_path = str(Path(file_path).resolve())
    if not Path(file_path).exists():
        return _error(f"File not found: {file_path}")

    try:
        result = _npx_call("read_file", {"file_path": file_path, "format": "toon"})
        if result["ok"]:
            log.info("safedocx_read_file OK: %s", file_path)
        return result
    except Exception:
        return _error(traceback.format_exc())


def safedocx_grep(file_path: str, pattern: str) -> dict:
    """
    Find text in a DOCX file and return matching paragraph IDs.
    Uses: @usejunior/safe-docx grep <path> --pattern <pattern>
    """
    if not _safedocx_installed():
        return _unavailable("npx not found")

    file_path = str(Path(file_path).resolve())
    if not Path(file_path).exists():
        return _error(f"File not found: {file_path}")

    try:
        result = _npx_call("grep", {"file_path": file_path, "pattern": pattern})
        return result
    except Exception:
        return _error(traceback.format_exc())


def safedocx_replace_text(
    file_path: str,
    target_paragraph_id: str,
    old_string: str,
    new_string: str,
    instruction: str = "",
    clean_output_path: str | None = None,
    tracked_output_path: str | None = None,
) -> dict:
    """
    Surgically replace text in a specific paragraph, producing both a
    clean copy and a tracked-changes copy.
    """
    if not _safedocx_installed():
        return _unavailable("npx not found")

    file_path = str(Path(file_path).resolve())
    if not Path(file_path).exists():
        return _error(f"File not found: {file_path}")

    base, ext = os.path.splitext(file_path)
    if clean_output_path is None:
        clean_output_path = f"{base}_clean{ext}"
    if tracked_output_path is None:
        tracked_output_path = f"{base}_tracked{ext}"

    try:
        result = _npx_call(
            "replace_text",
            {
                "file_path": file_path,
                "target_paragraph_id": target_paragraph_id,
                "old_string": old_string,
                "new_string": new_string,
                "instruction": instruction or f"Replace '{old_string}' with '{new_string}'",
            },
        )
        if not result["ok"]:
            return result

        # Save both versions
        save_result = _npx_call(
            "save",
            {
                "file_path": file_path,
                "save_to_local_path": clean_output_path,
                "tracked_save_to_local_path": tracked_output_path,
                "save_format": "both",
            },
        )
        if not save_result["ok"]:
            return save_result

        log.info(
            "safedocx_replace_text OK: '%s' → '%s' in paragraph %s",
            old_string,
            new_string,
            target_paragraph_id,
        )
        return {
            "ok": True,
            "data": {
                "paragraph_id": target_paragraph_id,
                "clean_output": clean_output_path,
                "tracked_output": tracked_output_path,
                "backend": "safedocx",
            },
        }
    except Exception:
        return _error(traceback.format_exc())


def safedocx_grep_and_replace(
    file_path: str,
    pattern: str,
    new_text: str,
    instruction: str = "",
    clean_output_path: str | None = None,
    tracked_output_path: str | None = None,
) -> dict:
    """
    Convenience: grep for pattern → get paragraph ID → replace text.
    Returns both clean and tracked output paths.
    """
    if not _safedocx_installed():
        return _unavailable("npx not found — install Node.js to use safe-docx")

    file_path = str(Path(file_path).resolve())
    if not Path(file_path).exists():
        return _error(f"File not found: {file_path}")

    # Step 1: Find paragraph ID
    grep_result = safedocx_grep(file_path, pattern)
    if not grep_result["ok"]:
        return grep_result

    paragraph_id = _extract_paragraph_id(grep_result)
    if not paragraph_id:
        return _error(
            f"Pattern '{pattern}' not found in document. "
            f"Grep output: {json.dumps(grep_result.get('data', ''))[:300]}"
        )

    # Step 2: Replace using stable ID
    return safedocx_replace_text(
        file_path,
        paragraph_id,
        pattern,
        new_text,
        instruction=instruction,
        clean_output_path=clean_output_path,
        tracked_output_path=tracked_output_path,
    )


def safedocx_batch_edits(
    file_path: str,
    edits: list[dict],
    clean_output_path: str | None = None,
    tracked_output_path: str | None = None,
) -> dict:
    """
    Apply a batch of edits sequentially using safe-docx.
    Each edit in `edits` must contain: target_text, new_text, (optional) comment.

    Returns paths of clean and tracked output files.
    """
    if not _safedocx_installed():
        return _unavailable("npx not found")

    file_path = str(Path(file_path).resolve())
    if not Path(file_path).exists():
        return _error(f"File not found: {file_path}")
    if not edits:
        return _error("edits list is empty")

    base, ext = os.path.splitext(file_path)
    # Work on a temp copy so we don't mutate the original mid-batch
    tmp_fd, work_copy = tempfile.mkstemp(suffix=ext)
    os.close(tmp_fd)
    shutil.copy2(file_path, work_copy)

    applied: list[dict] = []
    failed: list[dict] = []

    try:
        for edit in edits:
            pattern = edit.get("target_text", "").strip()
            replacement = edit.get("new_text", "").strip()
            comment = edit.get("comment", "")
            if not pattern or not replacement:
                failed.append({"edit": edit, "reason": "empty target_text or new_text"})
                continue

            result = safedocx_grep_and_replace(
                work_copy,
                pattern,
                replacement,
                instruction=comment,
            )
            if result["ok"]:
                # The next operation works on the already-modified file
                # safe-docx saves in-place when we re-read it
                applied.append(edit)
            else:
                failed.append({"edit": edit, "reason": result.get("error", "unknown")})

        if clean_output_path is None:
            clean_output_path = f"{base}_clean{ext}"
        if tracked_output_path is None:
            tracked_output_path = f"{base}_tracked{ext}"

        # Final save of accumulated changes
        final_save = _npx_call(
            "save",
            {
                "file_path": work_copy,
                "save_to_local_path": clean_output_path,
                "tracked_save_to_local_path": tracked_output_path,
                "save_format": "both",
            },
        )
        if not final_save["ok"]:
            return final_save

        log.info("safedocx_batch_edits: %d applied, %d failed", len(applied), len(failed))
        return {
            "ok": True,
            "data": {
                "applied_count": len(applied),
                "failed_count": len(failed),
                "failed_edits": failed,
                "clean_output": clean_output_path,
                "tracked_output": tracked_output_path,
                "backend": "safedocx",
            },
        }
    except Exception:
        return _error(traceback.format_exc())
    finally:
        try:
            os.unlink(work_copy)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _npx_call(tool_name: str, args: dict[str, Any]) -> dict:
    """
    Call safe-docx as a subprocess via npx.
    Constructs: npx @usejunior/safe-docx <tool_name> --<key> <value> ...
    Returns parsed JSON from stdout.
    """
    cmd = ["npx", "--yes", "@usejunior/safe-docx", tool_name]
    for key, value in args.items():
        cmd.extend([f"--{key}", str(value)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return _error(
                f"safe-docx {tool_name} failed (exit {result.returncode}): "
                f"{result.stderr[:400]}"
            )
        try:
            data = json.loads(result.stdout)
            return {"ok": True, "data": data}
        except json.JSONDecodeError:
            # Return raw stdout as data for non-JSON tools
            return {"ok": True, "data": {"raw": result.stdout}}
    except subprocess.TimeoutExpired:
        return _error(f"safe-docx {tool_name} timed out after 30 s")
    except FileNotFoundError:
        return _unavailable("npx not found in PATH — install Node.js")


def _extract_paragraph_id(grep_result: dict) -> str:
    """Extract the first _bk_NNN paragraph ID from a grep result."""
    data = grep_result.get("data", {})
    # Direct field
    if isinstance(data, dict) and "paragraph_id" in data:
        return data["paragraph_id"]
    # Scan raw output text for _bk_NNN pattern
    raw = json.dumps(data)
    match = re.search(r"(_bk_\d+)", raw)
    return match.group(1) if match else ""


def _error(msg: str) -> dict:
    log.error("SafeDocxBridge error: %s", msg)
    return {"ok": False, "data": None, "error": msg}


def _unavailable(msg: str) -> dict:
    log.warning("SafeDocxBridge unavailable: %s", msg)
    return {"ok": False, "data": None, "error": msg, "unavailable": True}
