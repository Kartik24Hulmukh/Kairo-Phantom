"""
oracle_dispatcher.py — Phase 5 oracle verdict dispatcher.

Maps the `oracle` field of a scenario to the correct Phase 3 oracle function
from `sidecar.oracles` and returns a structured verdict:

    {"verdict": "PASS" | "FAIL", "reason": str}

Supported oracle names
──────────────────────
  verify_docx               → oracles.verify_docx
  verify_pdf                → oracles.verify_pdf
  verify_xlsx               → oracles.verify_xlsx
  verify_pptx               → oracles.verify_pptx
  verify_screenshot_diff    → oracles.verify_screenshot_diff
  network_sniffer           → oracles.NetworkSnifferOracle
  fixture_exists            → built-in: just assert the fixture file exists
  always_pass               → built-in: deterministic PASS (for smoke tests)
  always_fail               → built-in: deterministic FAIL (for negative tests)
"""

from __future__ import annotations

import os
import traceback
from typing import Any, Dict

from sidecar import oracles


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _pass(reason: str = "oracle passed") -> Dict[str, str]:
    return {"verdict": "PASS", "reason": reason}


def _fail(reason: str) -> Dict[str, str]:
    return {"verdict": "FAIL", "reason": reason}


# ─── Built-in stubs ──────────────────────────────────────────────────────────


def _always_pass(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    return _pass("always_pass oracle: deterministic PASS")


def _always_fail(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    return _fail("always_fail oracle: deterministic FAIL (negative test)")


def _fixture_exists(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    """PASS if the scenario fixture file exists inside the sandbox."""
    fixture = scenario.get("fixture", "")
    # The fixture may be a filename relative to sandbox_path
    candidate = os.path.join(sandbox_path, os.path.basename(fixture)) if fixture else sandbox_path
    if os.path.exists(candidate):
        return _pass(f"fixture exists: {candidate}")
    return _fail(f"fixture not found: {candidate}")


# ─── Phase 3 oracle wrappers ─────────────────────────────────────────────────


def _run_verify_docx(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    fixture = scenario.get("fixture", "")
    path = os.path.join(sandbox_path, os.path.basename(fixture))
    expected = scenario.get("oracle_args", {}).get("expected_text_substrings", None)
    try:
        oracles.verify_docx(path, expected_text_substrings=expected)
        return _pass("verify_docx PASS")
    except Exception as exc:
        return _fail(f"verify_docx FAIL: {exc}")


def _run_verify_pdf(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    fixture = scenario.get("fixture", "")
    path = os.path.join(sandbox_path, os.path.basename(fixture))
    expected = scenario.get("oracle_args", {}).get("expected_substrings", None)
    try:
        oracles.verify_pdf(path, expected_substrings=expected)
        return _pass("verify_pdf PASS")
    except Exception as exc:
        return _fail(f"verify_pdf FAIL: {exc}")


def _run_verify_xlsx(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    fixture = scenario.get("fixture", "")
    path = os.path.join(sandbox_path, os.path.basename(fixture))
    args = scenario.get("oracle_args", {})
    try:
        oracles.verify_xlsx(
            path,
            cell_values=args.get("cell_values"),
            cell_formulas=args.get("cell_formulas"),
        )
        return _pass("verify_xlsx PASS")
    except Exception as exc:
        return _fail(f"verify_xlsx FAIL: {exc}")


def _run_verify_pptx(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    fixture = scenario.get("fixture", "")
    path = os.path.join(sandbox_path, os.path.basename(fixture))
    args = scenario.get("oracle_args", {})
    try:
        oracles.verify_pptx(
            path,
            expected_slide_count=args.get("expected_slide_count"),
            expected_text_substrings=args.get("expected_text_substrings"),
        )
        return _pass("verify_pptx PASS")
    except Exception as exc:
        return _fail(f"verify_pptx FAIL: {exc}")


def _run_verify_screenshot_diff(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    args = scenario.get("oracle_args", {})
    path_a = os.path.join(sandbox_path, args.get("image_a", ""))
    path_b = os.path.join(sandbox_path, args.get("image_b", ""))
    max_diff = int(args.get("max_hash_diff", 2))
    try:
        oracles.verify_screenshot_diff(path_a, path_b, max_hash_diff=max_diff)
        return _pass("verify_screenshot_diff PASS")
    except Exception as exc:
        return _fail(f"verify_screenshot_diff FAIL: {exc}")


def _run_network_sniffer(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    """Run a zero-egress check: start sniffer, do nothing (air-gap), stop."""
    sniffer = oracles.NetworkSnifferOracle()
    sniffer.start()
    # No outbound activity expected — immediately stop
    external = sniffer.stop()
    if external:
        return _fail(f"network_sniffer: unexpected egress to {external}")
    return _pass("network_sniffer: no external egress detected")


# ─── Dispatch table ──────────────────────────────────────────────────────────

_DISPATCH = {
    "verify_docx": _run_verify_docx,
    "verify_pdf": _run_verify_pdf,
    "verify_xlsx": _run_verify_xlsx,
    "verify_pptx": _run_verify_pptx,
    "verify_screenshot_diff": _run_verify_screenshot_diff,
    "network_sniffer": _run_network_sniffer,
    "fixture_exists": _fixture_exists,
    "always_pass": _always_pass,
    "always_fail": _always_fail,
}


def dispatch(sandbox_path: str, scenario: Dict[str, Any]) -> Dict[str, str]:
    """
    Route to the correct oracle and return {"verdict": "PASS"|"FAIL", "reason": str}.
    Never raises — all exceptions are wrapped into FAIL verdicts.
    """
    oracle_name = scenario.get("oracle", "always_pass")
    handler = _DISPATCH.get(oracle_name)
    if handler is None:
        return _fail(f"Unknown oracle: '{oracle_name}'. " f"Available: {sorted(_DISPATCH)}")
    try:
        return handler(sandbox_path, scenario)
    except Exception:
        return _fail(f"oracle dispatcher crashed: {traceback.format_exc()}")
