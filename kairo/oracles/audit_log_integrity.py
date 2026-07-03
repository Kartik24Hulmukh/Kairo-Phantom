# PROVENANCE: original | clean-room oracle `audit_log_integrity` per prompts/06_c2pa_provenance.md
"""Deterministic audit-log-integrity oracle for the Legal-redline wedge.

Implements the ``audit_log_integrity`` oracle required by prompts/06_c2pa_provenance.md
and listed in specs/VERIFICATION_ORACLES.md.

Verifies:
  1. Every entry's Ed25519 signature is valid against the public key.
  2. The hash chain is continuous (each entry's prev_hash matches the previous entry's entry_hash).
  3. Each entry_hash is correctly computed from the entry's content.

Kill-proofs (each must FAIL on the broken input):
  - Tampered entry content → signature verification fails.
  - Broken chain link (swapped prev_hash) → chain verification fails.
  - Forged signature (wrong key) → signature verification fails.
  - Wrong public key → signature verification fails.
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ed25519

from kairo.oracles.ed25519_audit_log import AuditEntry, Ed25519AuditLog


def verify_audit_log_integrity(
    entries: list[AuditEntry],
    public_key: ed25519.Ed25519PublicKey,
) -> bool:
    """Assert the audit log chain is complete and every signature is valid.

    Args:
        entries: The list of AuditEntry objects from the audit log.
        public_key: The Ed25519 public key to verify signatures against.

    Returns:
        True if the entire chain is valid.

    Raises:
        AssertionError if any signature is invalid, the chain is broken,
        or an entry_hash is incorrect.
    """
    if not entries:
        raise AssertionError("audit_log_integrity FAILED: entries list is empty")

    ok = Ed25519AuditLog.verify_chain(entries, public_key)
    if not ok:
        raise AssertionError(
            "audit_log_integrity FAILED: chain verification failed "
            "(invalid signature, broken chain link, or incorrect entry_hash)"
        )
    return True
