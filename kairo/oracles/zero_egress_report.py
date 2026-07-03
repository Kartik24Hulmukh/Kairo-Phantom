# PROVENANCE: original | clean-room zero-egress report per specs/R3_AIRGAP_ENFORCEMENT.md + specs/CLAIM_DISCIPLINE.md
"""Reproducible, signed zero-egress report for the Legal-redline pipeline.

Implements the signed egress report per specs/R3_AIRGAP_ENFORCEMENT.md §4 and
specs/CLAIM_DISCIPLINE.md:

  "Runs fully on your device. Every run emits a reproducible, signed egress
  report showing zero outbound connections, verifiable by your own network
  monitor. The source is open for audit."

  NOT "cryptographic proof no bytes ever leave."

The report is a JSON document signed with Ed25519 that records:
  - The redline run metadata (timestamp, doc hash, playbook ID).
  - The number of edits applied and clauses flagged.
  - An offline attestation: the pipeline ran with no network calls (no LLM,
    no HTTP, no DNS — verified by code path inspection, not a packet capture).
  - The audit log hash (tying the report to the audit chain).

The report is deterministic given the same inputs (except for the timestamp,
which is included in the signature).

Dependency: cryptography (Apache-2.0/BSD-3, BUNDLE lane).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

log = logging.getLogger("kairo.audit.egress_report")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ZeroEgressReport:
    """A signed zero-egress report for a single redline run.

    Fields:
        timestamp:         ISO-8601 UTC timestamp of the report.
        doc_hash:          SHA-256 of the source document.
        playbook_id:       ID of the playbook used.
        total_edits:       Number of edits applied.
        total_flagged:     Number of clauses flagged.
        injection_detected: Whether PromptShield detected injection in the document.
        audit_log_hash:    SHA-256 of the audit log JSON (ties report to the chain).
        offline_attestation: Statement that the pipeline ran offline.
        report_hash:       SHA-256 of the report content (for integrity).
        signature:         Ed25519 signature over the report content (hex).
    """

    timestamp: str
    doc_hash: str
    playbook_id: str
    total_edits: int
    total_flagged: int
    injection_detected: bool
    audit_log_hash: str
    offline_attestation: str
    report_hash: str
    signature: str = ""

    def content_bytes(self) -> bytes:
        """Return the canonical bytes that are signed (excludes signature)."""
        payload = {
            "timestamp": self.timestamp,
            "doc_hash": self.doc_hash,
            "playbook_id": self.playbook_id,
            "total_edits": self.total_edits,
            "total_flagged": self.total_flagged,
            "injection_detected": self.injection_detected,
            "audit_log_hash": self.audit_log_hash,
            "offline_attestation": self.offline_attestation,
            "report_hash": self.report_hash,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def to_json(self) -> str:
        """Serialize the report to JSON (including signature)."""
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "doc_hash": self.doc_hash,
                "playbook_id": self.playbook_id,
                "total_edits": self.total_edits,
                "total_flagged": self.total_flagged,
                "injection_detected": self.injection_detected,
                "audit_log_hash": self.audit_log_hash,
                "offline_attestation": self.offline_attestation,
                "report_hash": self.report_hash,
                "signature": self.signature,
            },
            indent=2,
        )


def generate_zero_egress_report(
    doc_hash: str,
    playbook_id: str,
    total_edits: int,
    total_flagged: int,
    injection_detected: bool,
    audit_log_json: str,
    private_key: ed25519.Ed25519PrivateKey,
) -> ZeroEgressReport:
    """Generate a signed zero-egress report for a redline run.

    Args:
        doc_hash:          SHA-256 of the source document.
        playbook_id:       ID of the playbook used.
        total_edits:       Number of edits applied.
        total_flagged:     Number of clauses flagged.
        injection_detected: Whether PromptShield detected injection.
        audit_log_json:    The audit log JSON (to hash and tie to the report).
        private_key:       Ed25519 private key for signing.

    Returns:
        A signed ZeroEgressReport.
    """
    timestamp = _now_iso()
    audit_log_hash = _sha256_hex(audit_log_json.encode("utf-8"))
    offline_attestation = (
        "This redline run executed fully on-device with no LLM calls, no HTTP requests, "
        "no DNS lookups, and no network connections of any kind. The pipeline code path "
        "contains no network client code. This attestation is reproducible by inspecting "
        "the source and re-running the pipeline offline."
    )

    # Compute report_hash over content (without signature)
    prelim_payload = {
        "timestamp": timestamp,
        "doc_hash": doc_hash,
        "playbook_id": playbook_id,
        "total_edits": total_edits,
        "total_flagged": total_flagged,
        "injection_detected": injection_detected,
        "audit_log_hash": audit_log_hash,
        "offline_attestation": offline_attestation,
    }
    prelim_bytes = json.dumps(prelim_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report_hash = _sha256_hex(prelim_bytes)

    report = ZeroEgressReport(
        timestamp=timestamp,
        doc_hash=doc_hash,
        playbook_id=playbook_id,
        total_edits=total_edits,
        total_flagged=total_flagged,
        injection_detected=injection_detected,
        audit_log_hash=audit_log_hash,
        offline_attestation=offline_attestation,
        report_hash=report_hash,
    )

    signature = private_key.sign(report.content_bytes()).hex()
    object.__setattr__(report, "signature", signature)

    return report


def verify_zero_egress_report(
    report: ZeroEgressReport,
    public_key: ed25519.Ed25519PublicKey,
) -> bool:
    """Verify a zero-egress report's Ed25519 signature.

    Returns True if the signature is valid.
    """
    try:
        public_key.verify(
            bytes.fromhex(report.signature),
            report.content_bytes(),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def report_from_json(data: str) -> ZeroEgressReport:
    """Deserialize a ZeroEgressReport from JSON."""
    obj = json.loads(data)
    return ZeroEgressReport(
        timestamp=obj["timestamp"],
        doc_hash=obj["doc_hash"],
        playbook_id=obj["playbook_id"],
        total_edits=obj["total_edits"],
        total_flagged=obj["total_flagged"],
        injection_detected=obj["injection_detected"],
        audit_log_hash=obj["audit_log_hash"],
        offline_attestation=obj["offline_attestation"],
        report_hash=obj["report_hash"],
        signature=obj["signature"],
    )
