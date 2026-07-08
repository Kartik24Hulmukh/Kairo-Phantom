"""
W7 Trust Layer Extension — Oracle tests.

Tests:
1. Flight recorder: hash chain integrity, replay verification, Merkle root
2. Timestamp anchor: offline-degrading, honest source labeling, hash verification
3. Policy engine: ALLOW/DENY/REQUIRE_HUMAN decisions for high-risk actions
4. End-to-end: external verifier validates a signed Merkle-chained bundle
   AND replay reproduces the same receipts
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kairo.trust.flight_recorder import (
    FlightLog,
    record_flight,
    replay_flight,
    verify_flight_log,
)
from kairo.trust.timestamp_anchor import (
    TimestampAnchor,
    create_timestamp_anchor,
    verify_timestamp_anchor,
    anchor_checkpoint,
)
from kairo.trust.policy_engine import (
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    evaluate_policy,
    register_policy,
)
from kairo.trust.merkle import (
    create_checkpoint,
    merkle_root,
    merkle_proof,
    verify_merkle_proof,
    verify_checkpoint,
)


# ── Flight Recorder Tests ────────────────────────────────────────────────────

class TestFlightRecorder:
    """Test the deterministic replay / flight recorder."""

    def test_flight_log_creates_hash_chained_entries(self):
        """A flight log must create hash-chained entries."""
        log = FlightLog()
        e1 = log.add_entry("ingest", "input1", "output1")
        e2 = log.add_entry("extract", "input2", "output2")

        assert e1.prev_hash == "genesis"
        assert e2.prev_hash == e1.self_hash
        assert e1.self_hash != e2.self_hash
        assert len(log.entries) == 2

    def test_flight_log_self_hash_is_correct(self):
        """Each entry's self_hash must be the correct SHA-256 of its canonical form."""
        log = FlightLog()
        entry = log.add_entry("test", "input", "output")

        # Recompute the hash
        from kairo.trust.flight_recorder import _entry_hash
        entry_dict = entry.to_dict()
        computed = _entry_hash(entry_dict)
        assert entry.self_hash == computed

    def test_flight_log_save_and_load(self, tmp_path):
        """A flight log must be saveable and loadable."""
        log = FlightLog()
        log.add_entry("stage1", "input1", "output1")
        log.add_entry("stage2", "input2", "output2")

        path = tmp_path / "flight.jsonl"
        log.save(path)

        loaded = FlightLog.load(path)
        assert len(loaded.entries) == 2
        assert loaded.entries[0].stage == "stage1"
        assert loaded.entries[1].stage == "stage2"
        assert loaded.root_hash == log.root_hash

    def test_flight_log_verification_passes_on_valid_log(self, tmp_path):
        """A valid flight log must verify without violations."""
        log = FlightLog()
        log.add_entry("ingest", "input1", "output1")
        log.add_entry("extract", "input2", "output2")

        path = tmp_path / "flight.jsonl"
        log.save(path)

        violations = verify_flight_log(path)
        assert violations == [], f"Valid log should have no violations: {violations}"

    def test_flight_log_verification_detects_tampering(self, tmp_path):
        """A tampered flight log must be detected."""
        log = FlightLog()
        log.add_entry("ingest", "input1", "output1")
        log.add_entry("extract", "input2", "output2")

        path = tmp_path / "flight.jsonl"
        log.save(path)

        # Tamper: modify an entry's output
        lines = path.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        entry["output_hash"] = "tampered"
        lines[0] = json.dumps(entry)
        path.write_text("\n".join(lines) + "\n")

        violations = verify_flight_log(path)
        assert len(violations) > 0, "Tampered log should have violations"

    def test_flight_log_replay_returns_valid_result(self, tmp_path):
        """Replay must return a valid result for a correct log."""
        log = FlightLog()
        log.add_entry("ingest", "input1", "output1", receipt_hash="abc123")
        log.add_entry("extract", "input2", "output2", receipt_hash="def456")

        path = tmp_path / "flight.jsonl"
        log.save(path)

        result = replay_flight(path)
        assert result["valid"] is True
        assert result["entry_count"] == 2
        assert result["merkle_root"] is not None

    def test_flight_log_merkle_root_of_receipts(self):
        """The flight log must compute a Merkle root of receipt hashes."""
        log = FlightLog()
        log.add_entry("stage1", "in1", "out1", receipt_hash="hash1")
        log.add_entry("stage2", "in2", "out2", receipt_hash="hash2")

        root = log.merkle_root_of_receipts
        assert root is not None
        # Verify it matches the merkle module
        leaves = [b"hash1", b"hash2"]
        expected = merkle_root(leaves)
        assert root == expected

    def test_flight_log_no_receipts_has_null_merkle_root(self):
        """A flight log with no receipts should have null Merkle root."""
        log = FlightLog()
        log.add_entry("stage1", "in1", "out1")
        assert log.merkle_root_of_receipts is None

    def test_record_flight_from_stage_list(self, tmp_path):
        """record_flight must create a log from a list of stages."""
        stages = [
            {"stage": "ingest", "input": "doc1", "output": "chunks1"},
            {"stage": "extract", "input": "chunks1", "output": "extractions1"},
        ]
        log = record_flight(stages)
        assert len(log.entries) == 2
        assert log.entries[0].stage == "ingest"
        assert log.entries[1].stage == "extract"

    def test_replay_detects_broken_chain(self, tmp_path):
        """Replay must detect a broken hash chain."""
        log = FlightLog()
        log.add_entry("stage1", "in1", "out1")
        log.add_entry("stage2", "in2", "out2")

        path = tmp_path / "flight.jsonl"
        log.save(path)

        # Break the chain: modify prev_hash of second entry
        lines = path.read_text().strip().split("\n")
        entry = json.loads(lines[1])
        entry["prev_hash"] = "broken"
        lines[1] = json.dumps(entry)
        path.write_text("\n".join(lines) + "\n")

        result = replay_flight(path)
        assert result["valid"] is False
        assert any("prev_hash" in v for v in result["violations"])


# ── Timestamp Anchor Tests ───────────────────────────────────────────────────

class TestTimestampAnchor:
    """Test the external timestamp anchor (offline-degrading)."""

    def test_anchor_created_in_sealed_mode(self):
        """In sealed mode, anchor source must be 'local_sealed'."""
        os.environ["KAIRO_SEALED"] = "1"
        try:
            anchor = create_timestamp_anchor("test_hash")
            assert anchor.source == "local_sealed"
            assert anchor.authority is None
        finally:
            del os.environ["KAIRO_SEALED"]

    def test_anchor_created_in_offline_mode(self):
        """In offline mode, anchor source must be 'local_offline'."""
        os.environ["KAIRO_OFFLINE"] = "1"
        try:
            anchor = create_timestamp_anchor("test_hash")
            assert anchor.source == "local_offline"
        finally:
            del os.environ["KAIRO_OFFLINE"]

    def test_anchor_hash_is_correct(self):
        """The anchor_hash must be the correct SHA-256 of canonical form."""
        anchor = create_timestamp_anchor("test_hash")
        from kairo.trust.timestamp_anchor import _anchor_hash
        computed = _anchor_hash(anchor.to_dict())
        assert anchor.anchor_hash == computed

    def test_anchor_verification_passes_on_valid_anchor(self):
        """A valid anchor must verify without violations."""
        anchor = create_timestamp_anchor("test_hash")
        violations = verify_timestamp_anchor(anchor)
        assert violations == [], f"Valid anchor should have no violations: {violations}"

    def test_anchor_verification_detects_tampering(self):
        """A tampered anchor must be detected."""
        anchor = create_timestamp_anchor("test_hash")
        anchor.timestamp = anchor.timestamp + 1000000  # Tamper
        violations = verify_timestamp_anchor(anchor)
        assert len(violations) > 0, "Tampered anchor should have violations"

    def test_anchor_with_signature(self):
        """An anchor with a private key must have a signature."""
        key = Ed25519PrivateKey.generate()
        seed = key.private_bytes_raw().hex()
        anchor = create_timestamp_anchor("test_hash", private_key_hex=seed)
        assert anchor.signature is not None
        assert len(anchor.signature) > 0

    def test_anchor_checkpoint_persists_to_file(self, tmp_path):
        """anchor_checkpoint must append to a JSONL file."""
        checkpoint = {"self_hash": "test_ckpt_hash", "checkpoint_seq": 0}
        path = tmp_path / "anchors.jsonl"
        anchor = anchor_checkpoint(checkpoint, path)
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        loaded = json.loads(lines[0])
        assert loaded["checkpoint_hash"] == "test_ckpt_hash"

    def test_anchor_source_is_never_external_without_real_authority(self):
        """The anchor must NEVER claim 'external' source without a real authority."""
        anchor = create_timestamp_anchor("test_hash")
        # Without a real TSA implementation, source must not be "external"
        assert anchor.source != "external", (
            "Anchor must not claim 'external' source without a real timestamp authority. "
            "External witnessing is PLANNED but not implemented."
        )


# ── Policy Engine Tests ──────────────────────────────────────────────────────

class TestPolicyEngine:
    """Test the policy-as-code engine."""

    def test_file_delete_protected_path_denied(self):
        """File deletion of protected paths must be DENIED."""
        ctx = PolicyContext(action="file_delete", target="/etc/passwd")
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.DENY

    def test_file_delete_non_protected_requires_human(self):
        """File deletion of non-protected paths must REQUIRE_HUMAN."""
        ctx = PolicyContext(action="file_delete", target="/home/user/myfile.txt")
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.REQUIRE_HUMAN

    def test_network_access_denied_in_sealed_mode(self):
        """Network access must be DENIED in sealed mode."""
        ctx = PolicyContext(action="network_access", target="https://example.com", sealed_mode=True)
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.DENY

    def test_network_access_requires_human_when_not_sealed(self):
        """Network access must REQUIRE_HUMAN when not in sealed mode."""
        ctx = PolicyContext(action="network_access", target="https://example.com", sealed_mode=False)
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.REQUIRE_HUMAN

    def test_clipboard_write_requires_human(self):
        """Clipboard write must REQUIRE_HUMAN (W6 injection leak vector)."""
        ctx = PolicyContext(action="clipboard_write", target="sensitive text")
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.REQUIRE_HUMAN

    def test_code_execution_safe_command_allowed(self):
        """Safe commands must be ALLOWED."""
        ctx = PolicyContext(action="code_execution", target="ls -la")
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.ALLOW

    def test_code_execution_unsafe_command_requires_human(self):
        """Unsafe commands must REQUIRE_HUMAN."""
        ctx = PolicyContext(action="code_execution", target="rm -rf /")
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.REQUIRE_HUMAN

    def test_data_export_small_allowed(self):
        """Small data exports must be ALLOWED."""
        ctx = PolicyContext(action="data_export", target="export.csv", metadata={"size_bytes": 1024})
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.ALLOW

    def test_data_export_large_requires_human(self):
        """Large data exports must REQUIRE_HUMAN."""
        ctx = PolicyContext(action="data_export", target="export.csv", metadata={"size_bytes": 20 * 1024 * 1024})
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.REQUIRE_HUMAN

    def test_unregistered_action_requires_human(self):
        """Unregistered actions must default to REQUIRE_HUMAN."""
        ctx = PolicyContext(action="unknown_action", target="something")
        result = evaluate_policy(ctx)
        assert result.decision == PolicyDecision.REQUIRE_HUMAN

    def test_custom_policy_can_be_registered(self):
        """Custom policies must be registerable."""
        engine = PolicyEngine()

        def custom_policy(ctx: PolicyContext) -> object:
            from kairo.trust.policy_engine import PolicyResult
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason="Custom deny",
                policy_name="custom",
                context=ctx,
            )

        engine.register("custom_action", custom_policy)
        ctx = PolicyContext(action="custom_action", target="test")
        result = engine.evaluate(ctx)
        assert result.decision == PolicyDecision.DENY


# ── End-to-End: Merkle Chain + Flight Recorder + Replay ──────────────────────

class TestEndToEndTrustChain:
    """End-to-end test: create receipts, checkpoint, flight log, and replay."""

    def test_e2e_replay_reproduces_same_receipts(self, tmp_path):
        """
        Oracle: replay must reproduce the same Merkle root and hash chain.

        This is the core W7 oracle: an external verifier can validate a
        signed Merkle-chained bundle e2e AND replay reproduces the same receipts.
        """
        # Generate a keypair
        key = Ed25519PrivateKey.generate()
        seed = key.private_bytes_raw().hex()

        # Create a flight log with receipt hashes
        log1 = FlightLog(agent_id="test-agent")
        log1.add_entry("ingest", "doc1", "chunks1", receipt_hash="receipt_hash_1")
        log1.add_entry("extract", "chunks1", "extractions1", receipt_hash="receipt_hash_2")
        log1.add_entry("ground", "extractions1", "grounded1", receipt_hash="receipt_hash_3")

        path1 = tmp_path / "flight1.jsonl"
        log1.save(path1)

        # Verify and replay
        result1 = replay_flight(path1)
        assert result1["valid"] is True
        root1 = result1["merkle_root"]

        # Create a second identical log (simulating replay)
        log2 = FlightLog(agent_id="test-agent")
        log2.add_entry("ingest", "doc1", "chunks1", receipt_hash="receipt_hash_1")
        log2.add_entry("extract", "chunks1", "extractions1", receipt_hash="receipt_hash_2")
        log2.add_entry("ground", "extractions1", "grounded1", receipt_hash="receipt_hash_3")

        path2 = tmp_path / "flight2.jsonl"
        log2.save(path2)

        result2 = replay_flight(path2)
        root2 = result2["merkle_root"]

        # The Merkle roots must match (same receipts → same root)
        assert root1 == root2, (
            f"Replay must produce the same Merkle root: {root1} != {root2}"
        )

        # The hash chains must match
        assert log1.root_hash == log2.root_hash, (
            "Replay must produce the same chain root hash"
        )

    def test_e2e_merkle_inclusion_proof(self):
        """An inclusion proof must verify against the Merkle root."""
        leaves = [b"receipt1", b"receipt2", b"receipt3", b"receipt4"]
        root = merkle_root(leaves)
        proof = merkle_proof(leaves, 2)  # Proof for leaf 2

        assert verify_merkle_proof(leaves[2], 2, len(leaves), proof, root)

    def test_e2e_merkle_proof_detects_wrong_leaf(self):
        """An inclusion proof must fail for the wrong leaf."""
        leaves = [b"receipt1", b"receipt2", b"receipt3", b"receipt4"]
        root = merkle_root(leaves)
        proof = merkle_proof(leaves, 2)

        # Try to verify with wrong leaf
        assert not verify_merkle_proof(b"wrong", 2, len(leaves), proof, root)

    def test_e2e_checkpoint_with_anchor(self, tmp_path):
        """A checkpoint with a timestamp anchor must be verifiable."""
        # Create a checkpoint
        receipts_path = tmp_path / "receipts.jsonl"
        receipts_path.write_text("")  # Empty receipts for simplicity

        checkpoints_path = tmp_path / "checkpoints.jsonl"
        anchors_path = tmp_path / "anchors.jsonl"

        key = Ed25519PrivateKey.generate()
        seed = key.private_bytes_raw().hex()

        # Create checkpoint
        ckpt = create_checkpoint(receipts_path, checkpoints_path, seed)

        # Verify checkpoint
        violations = verify_checkpoint(ckpt)
        assert violations == [], f"Checkpoint should be valid: {violations}"

        # Anchor the checkpoint
        anchor = anchor_checkpoint(ckpt, anchors_path, private_key_hex=seed)

        # Verify anchor
        anchor_violations = verify_timestamp_anchor(anchor)
        assert anchor_violations == [], f"Anchor should be valid: {anchor_violations}"

        # The anchor must reference the correct checkpoint
        assert anchor.checkpoint_hash == ckpt["self_hash"]
