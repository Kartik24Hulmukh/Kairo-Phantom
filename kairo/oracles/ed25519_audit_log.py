# PROVENANCE: original | clean-room Ed25519 signed audit log per prompts/06_c2pa_provenance.md (audit-log first)
"""Ed25519-signed, hash-chained audit log for the Legal-redline pipeline.

Implements the audit-log-first approach from prompts/06_c2pa_provenance.md (fix G6):
ship a **hash-chained, Ed25519-signed audit log** that is verifiable today.
C2PA Content Credentials remain a fast-follow.

Each applied edit AND each flagged/refused clause emits a chain-linked entry:
    {action, doc_hash, edit_summary, ts, prev_hash, signature}

The chain is tamper-evident: each entry's signature covers its content plus the
previous entry's hash. Modifying any entry invalidates the chain from that point
forward. The signature is Ed25519 (asymmetric, publicly verifiable) — anyone with
the public key can verify the log; the private key never leaves the keystore.

CLAIM DISCIPLINE (specs/CLAIM_DISCIPLINE.md):
  - "tamper-evident, hash-chained, Ed25519-signed audit log" — TRUE and verifiable.
  - NOT "cryptographic proof no bytes ever leave" — the audit log proves integrity
    of the log itself, not the absence of covert channels.

Dependency: cryptography (Apache-2.0/BSD-3, BUNDLE lane per specs/TECH_MANIFEST.md).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

log = logging.getLogger("kairo.audit.ed25519")


def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    """SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    """A single Ed25519-signed, chain-linked audit entry.

    Fields:
        entry_id:     Unique identifier (UUID4).
        timestamp:    ISO-8601 UTC timestamp.
        action:       What happened: "edit_applied", "clause_flagged", "run_started", "run_completed".
        doc_hash:     SHA-256 of the source document content.
        edit_summary: Summary of the edit/flag (clause_id, old_text, new_text, citation, etc.).
        prev_hash:    SHA-256 hash of the previous entry's content_bytes (empty for genesis).
        entry_hash:   SHA-256 hash of this entry's content_bytes (for chain linking).
        signature:    Ed25519 signature over content_bytes (hex-encoded).
    """

    entry_id: str
    timestamp: str
    action: str
    doc_hash: str
    edit_summary: dict[str, Any]
    prev_hash: str
    entry_hash: str
    signature: str = ""

    def content_bytes(self) -> bytes:
        """Return the canonical bytes that are signed (excludes signature)."""
        payload = {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "doc_hash": self.doc_hash,
            "edit_summary": self.edit_summary,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Ed25519AuditLog:
    """Tamper-evident, Ed25519-signed, hash-chained audit log.

    Usage:
        # Generate a keypair (do this once; store private key in keystore, ship public key)
        private_key, public_key = Ed25519AuditLog.generate_keypair()

        # Create a log with the private key
        audit = Ed25519AuditLog(private_key)
        audit.log_edit(doc_hash="abc...", clause_id="governing_law", ...)
        audit.log_flag(doc_hash="abc...", clause_id="indemnification", ...)

        # Verify with the public key
        assert Ed25519AuditLog.verify_chain(audit.entries, public_key)

    The private key is NEVER committed to the repo. Ship only the public key
    (embedded in the verifier or distributed alongside the product).
    """

    def __init__(self, private_key: ed25519.Ed25519PrivateKey) -> None:
        """Initialize with an Ed25519 private key for signing.

        Args:
            private_key: Ed25519 private key (from keystore/env, never committed).
        """
        self._private_key = private_key
        self._entries: list[AuditEntry] = []
        self._last_hash: str = ""

    @staticmethod
    def generate_keypair() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
        """Generate a new Ed25519 keypair.

        Returns:
            (private_key, public_key) — store private in keystore, ship public.
        """
        private_key = ed25519.Ed25519PrivateKey.generate()
        return private_key, private_key.public_key()

    @staticmethod
    def private_key_to_pem(private_key: ed25519.Ed25519PrivateKey) -> bytes:
        """Serialize a private key to PEM format (for keystore storage)."""
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @staticmethod
    def public_key_to_pem(public_key: ed25519.Ed25519PublicKey) -> bytes:
        """Serialize a public key to PEM format (for shipping/verification)."""
        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @staticmethod
    def load_private_key(pem_bytes: bytes) -> ed25519.Ed25519PrivateKey:
        """Load a private key from PEM bytes."""
        return serialization.load_pem_private_key(pem_bytes, password=None)

    @staticmethod
    def load_public_key(pem_bytes: bytes) -> ed25519.Ed25519PublicKey:
        """Load a public key from PEM bytes."""
        return serialization.load_pem_public_key(pem_bytes)

    def _sign(self, content: bytes) -> str:
        """Sign content with the Ed25519 private key. Returns hex-encoded signature."""
        return self._private_key.sign(content).hex()

    def _make_entry(
        self,
        action: str,
        doc_hash: str,
        edit_summary: dict[str, Any],
    ) -> AuditEntry:
        """Create, sign, and append a new audit entry."""
        entry_id = str(uuid.uuid4())
        timestamp = _now_iso()
        prev_hash = self._last_hash

        # Compute entry_hash over the content (without signature)
        # We need to compute entry_hash BEFORE signing, and it must be included in content_bytes
        # So we compute a preliminary hash, then create the entry with it
        prelim_payload = {
            "entry_id": entry_id,
            "timestamp": timestamp,
            "action": action,
            "doc_hash": doc_hash,
            "edit_summary": edit_summary,
            "prev_hash": prev_hash,
        }
        prelim_bytes = json.dumps(prelim_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        entry_hash = _sha256_hex(prelim_bytes)

        entry = AuditEntry(
            entry_id=entry_id,
            timestamp=timestamp,
            action=action,
            doc_hash=doc_hash,
            edit_summary=edit_summary,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )

        # Sign the full content (including entry_hash)
        signature = self._sign(entry.content_bytes())
        object.__setattr__(entry, "signature", signature)

        self._entries.append(entry)
        self._last_hash = entry_hash
        return entry

    def log_run_started(self, doc_hash: str, playbook_id: str) -> AuditEntry:
        """Log the start of a redline run."""
        return self._make_entry(
            action="run_started",
            doc_hash=doc_hash,
            edit_summary={"playbook_id": playbook_id},
        )

    def log_edit(
        self,
        doc_hash: str,
        clause_id: str,
        clause_label: str,
        old_text: str,
        new_text: str,
        citation: str,
        rationale: str,
    ) -> AuditEntry:
        """Log an applied edit (tracked change)."""
        return self._make_entry(
            action="edit_applied",
            doc_hash=doc_hash,
            edit_summary={
                "clause_id": clause_id,
                "clause_label": clause_label,
                "old_text": old_text,
                "new_text": new_text,
                "citation": citation,
                "rationale": rationale,
            },
        )

    def log_flag(
        self,
        doc_hash: str,
        clause_id: str,
        clause_label: str,
        reason: str,
    ) -> AuditEntry:
        """Log a flagged/refused clause (not found in contract)."""
        return self._make_entry(
            action="clause_flagged",
            doc_hash=doc_hash,
            edit_summary={
                "clause_id": clause_id,
                "clause_label": clause_label,
                "reason": reason,
            },
        )

    def log_run_completed(
        self,
        doc_hash: str,
        total_edits: int,
        total_flagged: int,
        injection_detected: bool,
    ) -> AuditEntry:
        """Log the completion of a redline run."""
        return self._make_entry(
            action="run_completed",
            doc_hash=doc_hash,
            edit_summary={
                "total_edits": total_edits,
                "total_flagged": total_flagged,
                "injection_detected": injection_detected,
            },
        )

    @property
    def entries(self) -> list[AuditEntry]:
        """Return all log entries (read-only copy)."""
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def to_json(self) -> str:
        """Serialize the entire log to JSON."""
        return json.dumps(
            {
                "entries": [
                    {
                        "entry_id": e.entry_id,
                        "timestamp": e.timestamp,
                        "action": e.action,
                        "doc_hash": e.doc_hash,
                        "edit_summary": e.edit_summary,
                        "prev_hash": e.prev_hash,
                        "entry_hash": e.entry_hash,
                        "signature": e.signature,
                    }
                    for e in self._entries
                ]
            },
            indent=2,
        )

    @staticmethod
    def entries_from_json(data: str) -> list[AuditEntry]:
        """Deserialize entries from JSON (does not verify)."""
        obj = json.loads(data)
        return [
            AuditEntry(
                entry_id=e["entry_id"],
                timestamp=e["timestamp"],
                action=e["action"],
                doc_hash=e["doc_hash"],
                edit_summary=e["edit_summary"],
                prev_hash=e["prev_hash"],
                entry_hash=e["entry_hash"],
                signature=e["signature"],
            )
            for e in obj["entries"]
        ]

    @staticmethod
    def verify_entry(entry: AuditEntry, public_key: ed25519.Ed25519PublicKey) -> bool:
        """Verify a single entry's Ed25519 signature against the public key."""
        try:
            public_key.verify(
                bytes.fromhex(entry.signature),
                entry.content_bytes(),
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    @staticmethod
    def verify_chain(entries: list[AuditEntry], public_key: ed25519.Ed25519PublicKey) -> bool:
        """Verify the entire hash chain: every signature is valid AND every prev_hash links correctly.

        Returns True only if the chain is completely untampered.
        """
        expected_prev_hash = ""
        for entry in entries:
            # Check signature is valid
            if not Ed25519AuditLog.verify_entry(entry, public_key):
                log.warning("Chain broken: invalid Ed25519 signature on entry %s", entry.entry_id)
                return False
            # Check chain linkage
            if entry.prev_hash != expected_prev_hash:
                log.warning("Chain broken: prev_hash mismatch on entry %s", entry.entry_id)
                return False
            # Verify entry_hash is correct
            prelim_payload = {
                "entry_id": entry.entry_id,
                "timestamp": entry.timestamp,
                "action": entry.action,
                "doc_hash": entry.doc_hash,
                "edit_summary": entry.edit_summary,
                "prev_hash": entry.prev_hash,
            }
            prelim_bytes = json.dumps(prelim_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            expected_hash = _sha256_hex(prelim_bytes)
            if entry.entry_hash != expected_hash:
                log.warning("Chain broken: entry_hash mismatch on entry %s", entry.entry_id)
                return False
            expected_prev_hash = entry.entry_hash
        return True
