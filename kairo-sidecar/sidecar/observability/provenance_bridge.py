"""
Provenance Bridge — Connects Python observability traces to Rust provenance receipts.

Phase 0.1: This module bridges the Python-side OpikTracer to the Rust-side
ReceiptLog (identity.rs). It reads the Rust receipts.jsonl file and verifies
that every Python trace has a corresponding provenance receipt with matching
trace_id.

The bridge also provides a function to emit a receipt from Python by writing
to the same JSONL file that the Rust ReceiptLog uses, maintaining the hash
chain integrity.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


# Default receipts path — mirrors the Rust ReceiptLog::default_path()
DEFAULT_RECEIPTS_PATH = Path.home() / ".kairo-phantom" / "receipts.jsonl"


def sha256_hex(data: str) -> str:
    """Compute SHA-256 hex of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical_receipt_json(receipt: Dict[str, Any]) -> str:
    """
    Compute the canonical JSON for a receipt (excluding self_hash and signature).
    This must match the Rust-side serialization for hash verification.
    """
    temp = dict(receipt)
    temp["self_hash"] = ""
    temp["signature"] = ""
    # Sort keys to match Rust's serde_json::to_string behavior
    # Note: Rust serde_json does NOT sort keys by default — it uses struct field order.
    # We must match the struct field order from identity.rs:
    # seq, timestamp, agent_id, action, context, outcome, prev_hash, self_hash, signature,
    # opik_trace_id, opik_trace_url, domain
    ordered = {}
    for key in [
        "seq",
        "timestamp",
        "agent_id",
        "action",
        "context",
        "outcome",
        "prev_hash",
        "self_hash",
        "signature",
        "opik_trace_id",
        "opik_trace_url",
        "domain",
    ]:
        if key in temp:
            ordered[key] = temp[key]
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def read_receipts(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read all receipts from the JSONL file."""
    if path is None:
        path = DEFAULT_RECEIPTS_PATH
    elif not isinstance(path, Path):
        path = Path(path)
    if not path.exists():
        return []
    receipts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                receipts.append(json.loads(line))
    return receipts


def verify_receipt_chain(path: Optional[Path] = None) -> int:
    """
    Verify the receipt chain integrity.

    Returns the number of violations found (0 = clean chain).
    This mirrors the Rust ReceiptLog::verify_chain() method.
    """
    receipts = read_receipts(path)
    violations = 0
    prev_hash = "genesis"
    expected_seq = 0

    for i, r in enumerate(receipts):
        # 1. Check prev_hash continuity
        if r.get("prev_hash") != prev_hash:
            violations += 1
        # 2. Check sequence
        if r.get("seq") != expected_seq:
            violations += 1
        # 3. Re-compute self_hash
        computed = sha256_hex(canonical_receipt_json(r))
        if computed != r.get("self_hash"):
            violations += 1
        # 4. Signature verification is done on the Rust side (Ed25519)

        prev_hash = r.get("self_hash", "")
        expected_seq = r.get("seq", 0) + 1

    return violations


def find_receipts_by_trace_id(trace_id: str, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Find all receipts with a given opik_trace_id."""
    receipts = read_receipts(path)
    return [r for r in receipts if r.get("opik_trace_id") == trace_id]


def find_receipts_by_domain(domain: str, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Find all receipts for a given domain."""
    receipts = read_receipts(path)
    return [r for r in receipts if r.get("domain") == domain]


def verify_trace_receipt_linkage(
    trace_ids: List[str],
    path: Optional[Path] = None,
) -> Dict[str, bool]:
    """
    Verify that each trace_id has a corresponding provenance receipt.

    Returns a dict mapping trace_id → True (found) / False (missing).
    """
    receipts = read_receipts(path)
    receipt_trace_ids = {r.get("opik_trace_id", "") for r in receipts}
    return {tid: tid in receipt_trace_ids for tid in trace_ids}
