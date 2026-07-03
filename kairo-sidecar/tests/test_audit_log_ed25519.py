"""Kill-proof tests for the Ed25519 audit log, zero-egress report, and audit_log_integrity oracle.

Tests:
  1. Audit log: positive chain verification (sign + verify).
  2. Zero-egress report: positive signature verification.
  3. End-to-end: pipeline emits audit log + report, both verify.
  4. Kill-proofs for audit_log_integrity oracle:
     a. Tampered entry content → fail.
     b. Broken chain link → fail.
     c. Forged signature (wrong key) → fail.
     d. Wrong public key → fail.
  5. Kill-proofs for zero-egress report:
     a. Tampered report → fail.
     b. Wrong key → fail.
  6. Existing redline tests still pass with audit log wired in.

All tests run fully offline. No mocks. Ed25519 keys are generated in-test.
"""

from __future__ import annotations

import json
import os

import pytest

from kairo.oracles.ed25519_audit_log import AuditEntry, Ed25519AuditLog
from kairo.oracles.zero_egress_report import (
    ZeroEgressReport,
    generate_zero_egress_report,
    verify_zero_egress_report,
    report_from_json,
)
from kairo.oracles.audit_log_integrity import verify_audit_log_integrity
from kairo.oracles.legal_redline_pipeline import redline_contract
from kairo.oracles.docx_tracked_changes import verify_docx_tracked_changes
from kairo.oracles.clause_coverage import verify_clause_coverage
from kairo.oracles.no_hallucinated_citation import verify_no_hallucinated_citation

# --- Fixture paths ---
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURE_DIR = os.path.join(_REPO_ROOT, "fixtures", "legal_redline")
_CONTRACT = os.path.join(_FIXTURE_DIR, "sample_contract.docx")
_PLAYBOOK = os.path.join(_FIXTURE_DIR, "playbook.json")
_GROUND_TRUTH = os.path.join(_FIXTURE_DIR, "ground_truth.json")

AUTHOR = "Kairo Legal"


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for each test."""
    private_key, public_key = Ed25519AuditLog.generate_keypair()
    return private_key, public_key


@pytest.fixture
def playbook_data():
    with open(_PLAYBOOK, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def ground_truth():
    with open(_GROUND_TRUTH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def redline_with_audit(tmp_path, keypair):
    """Run the pipeline with audit logging enabled."""
    private_key, public_key = keypair
    out = os.path.join(str(tmp_path), "redlined.docx")
    result = redline_contract(_CONTRACT, _PLAYBOOK, out, author=AUTHOR, private_key=private_key)
    assert result.ok, f"Pipeline failed: {result.error}"
    return result, public_key


# ======================== AUDIT LOG: POSITIVE ========================


def test_audit_log_chain_verifies(keypair):
    """A freshly generated audit log chain verifies against the public key."""
    private_key, public_key = keypair
    audit = Ed25519AuditLog(private_key)
    audit.log_run_started(doc_hash="abc123", playbook_id="test_pb")
    audit.log_edit(
        doc_hash="abc123",
        clause_id="governing_law",
        clause_label="Governing Law",
        old_text="Delaware",
        new_text="New York",
        citation="Firm Standard GL-001",
        rationale="Client is NY-based",
    )
    audit.log_flag(
        doc_hash="abc123",
        clause_id="indemnification",
        clause_label="Indemnification",
        reason="Not found in contract",
    )
    audit.log_run_completed(
        doc_hash="abc123",
        total_edits=1,
        total_flagged=1,
        injection_detected=False,
    )
    assert len(audit.entries) == 4
    assert Ed25519AuditLog.verify_chain(audit.entries, public_key) is True


def test_audit_log_integrity_oracle_positive(keypair):
    """The audit_log_integrity oracle passes on a valid chain."""
    private_key, public_key = keypair
    audit = Ed25519AuditLog(private_key)
    audit.log_edit(
        doc_hash="abc",
        clause_id="test",
        clause_label="Test",
        old_text="old",
        new_text="new",
        citation="cite",
        rationale="reason",
    )
    assert verify_audit_log_integrity(audit.entries, public_key) is True


# ======================== ZERO-EGRESS REPORT: POSITIVE ========================


def test_zero_egress_report_verifies(keypair):
    """A signed zero-egress report verifies against the public key."""
    private_key, public_key = keypair
    report = generate_zero_egress_report(
        doc_hash="abc123",
        playbook_id="test_pb",
        total_edits=5,
        total_flagged=1,
        injection_detected=False,
        audit_log_json='{"entries": []}',
        private_key=private_key,
    )
    assert verify_zero_egress_report(report, public_key) is True
    assert "no network connections" in report.offline_attestation
    assert report.total_edits == 5
    assert report.total_flagged == 1


def test_zero_egress_report_roundtrip(keypair):
    """Report survives JSON serialization roundtrip with valid signature."""
    private_key, public_key = keypair
    report = generate_zero_egress_report(
        doc_hash="abc",
        playbook_id="pb1",
        total_edits=3,
        total_flagged=0,
        injection_detected=True,
        audit_log_json='{"entries": []}',
        private_key=private_key,
    )
    json_str = report.to_json()
    restored = report_from_json(json_str)
    assert verify_zero_egress_report(restored, public_key) is True


# ======================== END-TO-END WITH AUDIT ========================


def test_pipeline_emits_audit_log(redline_with_audit):
    """The pipeline produces a non-empty audit log JSON when private_key is provided."""
    result, _ = redline_with_audit
    assert result.audit_log_json
    assert result.egress_report_json
    assert result.doc_hash


def test_pipeline_audit_log_verifies(redline_with_audit):
    """The pipeline's audit log chain verifies against the public key."""
    result, public_key = redline_with_audit
    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    assert verify_audit_log_integrity(entries, public_key) is True


def test_pipeline_egress_report_verifies(redline_with_audit):
    """The pipeline's zero-egress report verifies against the public key."""
    result, public_key = redline_with_audit
    report = report_from_json(result.egress_report_json)
    assert verify_zero_egress_report(report, public_key) is True


def test_pipeline_audit_log_has_expected_entries(redline_with_audit, ground_truth):
    """The audit log contains run_started + N edits + M flags + run_completed."""
    result, _ = redline_with_audit
    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    actions = [e.action for e in entries]
    assert "run_started" in actions
    assert "run_completed" in actions
    edit_count = actions.count("edit_applied")
    flag_count = actions.count("clause_flagged")
    assert edit_count == len(ground_truth["expected_edits"])
    assert flag_count >= 1  # indemnification_missing


def test_pipeline_without_key_has_no_audit(tmp_path):
    """Without a private key, the pipeline does not emit audit log or report."""
    out = os.path.join(str(tmp_path), "redlined.docx")
    result = redline_contract(_CONTRACT, _PLAYBOOK, out, author=AUTHOR)
    assert result.ok
    assert result.audit_log_json == ""
    assert result.egress_report_json == ""


# ======================== KILL-PROOFS: audit_log_integrity ========================


def test_killproof_tampered_entry_content(redline_with_audit):
    """Kill-proof: tampering an entry's edit_summary makes verification fail."""
    result, public_key = redline_with_audit
    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    # Tamper with an edit entry's content
    for i, e in enumerate(entries):
        if e.action == "edit_applied":
            tampered_summary = dict(e.edit_summary)
            tampered_summary["new_text"] = "TAMPERED TEXT"
            entries[i] = AuditEntry(
                entry_id=e.entry_id,
                timestamp=e.timestamp,
                action=e.action,
                doc_hash=e.doc_hash,
                edit_summary=tampered_summary,
                prev_hash=e.prev_hash,
                entry_hash=e.entry_hash,
                signature=e.signature,
            )
            break
    with pytest.raises(AssertionError, match="chain verification failed"):
        verify_audit_log_integrity(entries, public_key)


def test_killproof_broken_chain_link(redline_with_audit):
    """Kill-proof: swapping a prev_hash breaks the chain."""
    result, public_key = redline_with_audit
    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    # Break the chain by setting a wrong prev_hash on the second entry
    if len(entries) >= 2:
        e = entries[1]
        entries[1] = AuditEntry(
            entry_id=e.entry_id,
            timestamp=e.timestamp,
            action=e.action,
            doc_hash=e.doc_hash,
            edit_summary=e.edit_summary,
            prev_hash="WRONG_HASH_VALUE",
            entry_hash=e.entry_hash,
            signature=e.signature,
        )
    with pytest.raises(AssertionError, match="chain verification failed"):
        verify_audit_log_integrity(entries, public_key)


def test_killproof_forged_signature(redline_with_audit):
    """Kill-proof: using a different keypair's public key fails verification."""
    result, _ = redline_with_audit
    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    # Generate a completely different keypair
    _, wrong_public_key = Ed25519AuditLog.generate_keypair()
    with pytest.raises(AssertionError, match="chain verification failed"):
        verify_audit_log_integrity(entries, wrong_public_key)


def test_killproof_tampered_signature(redline_with_audit):
    """Kill-proof: modifying the signature bytes makes verification fail."""
    result, public_key = redline_with_audit
    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    # Tamper with the first entry's signature
    e = entries[0]
    entries[0] = AuditEntry(
        entry_id=e.entry_id,
        timestamp=e.timestamp,
        action=e.action,
        doc_hash=e.doc_hash,
        edit_summary=e.edit_summary,
        prev_hash=e.prev_hash,
        entry_hash=e.entry_hash,
        signature="00" * 64,  # fake signature
    )
    with pytest.raises(AssertionError, match="chain verification failed"):
        verify_audit_log_integrity(entries, public_key)


def test_killproof_empty_entries(keypair):
    """Kill-proof: an empty entries list fails the oracle."""
    _, public_key = keypair
    with pytest.raises(AssertionError, match="entries list is empty"):
        verify_audit_log_integrity([], public_key)


# ======================== KILL-PROOFS: zero-egress report ========================


def test_killproof_tampered_report(keypair):
    """Kill-proof: tampering the report content makes signature verification fail."""
    private_key, public_key = keypair
    report = generate_zero_egress_report(
        doc_hash="abc",
        playbook_id="pb1",
        total_edits=5,
        total_flagged=1,
        injection_detected=False,
        audit_log_json='{"entries": []}',
        private_key=private_key,
    )
    # Tamper with total_edits
    tampered = ZeroEgressReport(
        timestamp=report.timestamp,
        doc_hash=report.doc_hash,
        playbook_id=report.playbook_id,
        total_edits=999,  # tampered
        total_flagged=report.total_flagged,
        injection_detected=report.injection_detected,
        audit_log_hash=report.audit_log_hash,
        offline_attestation=report.offline_attestation,
        report_hash=report.report_hash,
        signature=report.signature,
    )
    assert verify_zero_egress_report(tampered, public_key) is False


def test_killproof_report_wrong_key(keypair):
    """Kill-proof: verifying with the wrong public key fails."""
    private_key, _ = keypair
    _, wrong_public_key = Ed25519AuditLog.generate_keypair()
    report = generate_zero_egress_report(
        doc_hash="abc",
        playbook_id="pb1",
        total_edits=5,
        total_flagged=1,
        injection_detected=False,
        audit_log_json='{"entries": []}',
        private_key=private_key,
    )
    assert verify_zero_egress_report(report, wrong_public_key) is False


# ======================== EXISTING REDLINE TESTS STILL PASS WITH AUDIT ========================


def test_tracked_changes_readback_with_audit(redline_with_audit, ground_truth):
    """The tracked-changes oracle still passes when audit logging is enabled."""
    result, _ = redline_with_audit
    expected_changes = [
        {"old": e["old_text"], "new": e["new_text"]} for e in ground_truth["expected_edits"]
    ]
    assert (
        verify_docx_tracked_changes(
            result.output_path,
            expected_changes,
            require_author=True,
            require_date=True,
            original_text=ground_truth["expected_original_text"],
        )
        is True
    )


def test_clause_coverage_with_audit(redline_with_audit, playbook_data):
    """The clause_coverage oracle still passes with audit logging."""
    result, _ = redline_with_audit
    assert verify_clause_coverage(result, playbook_data["clauses"]) is True


def test_no_hallucinated_citation_with_audit(redline_with_audit, playbook_data):
    """The no_hallucinated_citation oracle still passes with audit logging."""
    result, _ = redline_with_audit
    assert verify_no_hallucinated_citation(result, playbook_data["clauses"]) is True
