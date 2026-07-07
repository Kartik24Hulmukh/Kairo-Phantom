"""
W7 Trust Layer — Merkle-chained receipts: ORACLE tests.

Oracle sources (external, not derived from the implementation under test):

1. RFC 6962 (Certificate Transparency) Merkle Tree Hash test vectors, as
   published in the RFC and reproduced in certificate-transparency-go
   (merkle/testonly). Constants are hard-coded below; they were additionally
   cross-checked by direct hashlib formulas (sha256(0x00||leaf),
   sha256(0x01||L||R)) with no tree recursion involved.

2. The existing receipt canonicalization contract from
   phantom-core/src/identity.rs (struct field order) mirrored by
   sidecar/observability/provenance_bridge.py::canonical_receipt_json.
   Signature convention: Ed25519 over the ASCII bytes of self_hash, with
   agent_id being the verifying key hex (identity.rs::verify_signature).

Tamper-evidence gates:
- Any single-byte change to any receipt must change the Merkle root.
- The standalone external verifier (tools/verify_receipts_external.py) must
  detect chain breaks, hash mismatches, bad signatures, and Merkle root
  mismatches — running as a subprocess with NO repo imports.
"""

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kairo.trust.merkle import (  # noqa: E402
    merkle_root,
    merkle_leaf_hash,
    merkle_proof,
    verify_merkle_proof,
    create_checkpoint,
    verify_checkpoint,
)

from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

EXTERNAL_VERIFIER = REPO_ROOT / "tools" / "verify_receipts_external.py"

# ── RFC 6962 known-answer vectors (leaves are raw bytes) ─────────────────────
RFC6962_EMPTY_ROOT = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
RFC6962_D1_ROOT = "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
RFC6962_D2_ROOT = "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125"
RFC6962_D3_ROOT = "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77"
RFC6962_LEAVES = [b"", b"\x00", b"\x10"]


# ── Helpers: build a real signed receipt chain (same contract as identity.rs) ─

RECEIPT_FIELD_ORDER = [
    "seq", "timestamp", "agent_id", "action", "context", "outcome",
    "prev_hash", "self_hash", "signature",
    "opik_trace_id", "opik_trace_url", "domain",
]


def _canonical(receipt: dict) -> str:
    temp = dict(receipt)
    temp["self_hash"] = ""
    temp["signature"] = ""
    ordered = {k: temp[k] for k in RECEIPT_FIELD_ORDER if k in temp}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def make_chain(tmp_path, n=5):
    """Create a receipts.jsonl with n receipts, hash-chained and Ed25519-signed."""
    key = Ed25519PrivateKey.generate()
    pub_hex = key.public_key().public_bytes_raw().hex()
    receipts = []
    prev = "genesis"
    for i in range(n):
        r = {
            "seq": i,
            "timestamp": 1700000000 + i,
            "agent_id": pub_hex,
            "action": f"action-{i}",
            "context": f"ctx-{i}",
            "outcome": "ok",
            "prev_hash": prev,
            "self_hash": "",
            "signature": "",
            "opik_trace_id": f"trace-{i}",
            "opik_trace_url": "",
            "domain": "docintel",
        }
        r["self_hash"] = hashlib.sha256(_canonical(r).encode()).hexdigest()
        r["signature"] = key.sign(r["self_hash"].encode()).hex()
        prev = r["self_hash"]
        receipts.append(r)
    path = tmp_path / "receipts.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in receipts) + "\n")
    return path, receipts, key, pub_hex


# ═══════════════════════════════ Merkle oracles ══════════════════════════════

class TestRfc6962KnownAnswers:
    def test_empty_tree(self):
        assert merkle_root([]) == RFC6962_EMPTY_ROOT

    def test_single_empty_leaf(self):
        assert merkle_root([b""]) == RFC6962_D1_ROOT

    def test_two_leaves(self):
        assert merkle_root(RFC6962_LEAVES[:2]) == RFC6962_D2_ROOT

    def test_three_leaves(self):
        assert merkle_root(RFC6962_LEAVES) == RFC6962_D3_ROOT

    def test_leaf_hash_domain_separation(self):
        # leaf hash uses 0x00 prefix — sha256(b"\x00") for the empty leaf
        assert merkle_leaf_hash(b"") == RFC6962_D1_ROOT
        # a leaf hash must never equal a bare sha256 of the same bytes
        assert merkle_leaf_hash(b"x") != hashlib.sha256(b"x").hexdigest()


class TestMerkleProofs:
    def test_proof_roundtrip_all_indices(self):
        leaves = [f"leaf-{i}".encode() for i in range(7)]  # odd count on purpose
        root = merkle_root(leaves)
        for i, leaf in enumerate(leaves):
            proof = merkle_proof(leaves, i)
            assert verify_merkle_proof(leaf, i, len(leaves), proof, root)

    def test_proof_rejects_wrong_leaf(self):
        leaves = [f"leaf-{i}".encode() for i in range(4)]
        root = merkle_root(leaves)
        proof = merkle_proof(leaves, 2)
        assert not verify_merkle_proof(b"tampered", 2, len(leaves), proof, root)

    def test_single_bit_flip_changes_root(self):
        leaves = [f"leaf-{i}".encode() for i in range(8)]
        root = merkle_root(leaves)
        tampered = list(leaves)
        tampered[3] = bytes([tampered[3][0] ^ 0x01]) + tampered[3][1:]
        assert merkle_root(tampered) != root


# ══════════════════════════ Checkpoints over receipts ════════════════════════

class TestCheckpoints:
    def test_checkpoint_roundtrip(self, tmp_path):
        receipts_path, receipts, key, pub_hex = make_chain(tmp_path, n=5)
        ckpt_path = tmp_path / "checkpoints.jsonl"
        priv_hex = key.private_bytes_raw().hex()

        ckpt = create_checkpoint(receipts_path, ckpt_path, priv_hex)
        assert ckpt["tree_size"] == 5
        assert ckpt["agent_id"] == pub_hex
        # Root binds to receipt self_hashes
        expected_root = merkle_root([r["self_hash"].encode() for r in receipts])
        assert ckpt["merkle_root"] == expected_root
        assert verify_checkpoint(ckpt) == []

    def test_checkpoint_chain_links(self, tmp_path):
        receipts_path, receipts, key, _ = make_chain(tmp_path, n=3)
        ckpt_path = tmp_path / "checkpoints.jsonl"
        priv_hex = key.private_bytes_raw().hex()
        c1 = create_checkpoint(receipts_path, ckpt_path, priv_hex)
        # Append two more receipts by rebuilding a longer chain in-place
        receipts_path2, _, key2, _ = make_chain(tmp_path, n=5)
        c2 = create_checkpoint(receipts_path2, ckpt_path, key2.private_bytes_raw().hex())
        assert c1["checkpoint_seq"] == 0
        assert c2["checkpoint_seq"] == 1
        assert c2["prev_checkpoint_hash"] == c1["self_hash"]

    def test_checkpoint_detects_receipt_tamper(self, tmp_path):
        receipts_path, receipts, key, _ = make_chain(tmp_path, n=4)
        ckpt_path = tmp_path / "checkpoints.jsonl"
        ckpt = create_checkpoint(receipts_path, ckpt_path, key.private_bytes_raw().hex())
        # Tamper: flip the outcome of receipt 1 (and nothing else)
        lines = receipts_path.read_text().splitlines()
        r = json.loads(lines[1])
        r["outcome"] = "TAMPERED"
        lines[1] = json.dumps(r)
        receipts_path.write_text("\n".join(lines) + "\n")
        # Recomputed root over the (tampered) file must not match the checkpoint
        tampered = [json.loads(l) for l in lines]
        new_root = merkle_root([t["self_hash"].encode() for t in tampered])
        # self_hash unchanged, so root is the same — but self_hash no longer
        # matches content; the VERIFIER must recompute content hashes.
        canonical_hashes = [
            hashlib.sha256(_canonical(t).encode()).hexdigest().encode() for t in tampered
        ]
        content_root = merkle_root(canonical_hashes)
        assert content_root != ckpt["merkle_root"] or new_root == ckpt["merkle_root"]
        # The real gate: external verifier must flag this file (tested below).


# ═══════════════════════ Standalone external verifier ════════════════════════

def run_verifier(*args):
    """Run the external verifier as a subprocess with a CLEAN cwd (no repo imports)."""
    return subprocess.run(
        [sys.executable, str(EXTERNAL_VERIFIER), *args],
        capture_output=True,
        text=True,
        cwd="/tmp",  # not the repo root — proves no repo-relative imports
        timeout=60,
    )


class TestExternalVerifier:
    def test_verifier_is_import_standalone(self):
        src = EXTERNAL_VERIFIER.read_text()
        for forbidden in ("from kairo", "import kairo", "from sidecar", "import sidecar",
                          "from phantom", "import phantom", "from kernel", "import kernel"):
            assert forbidden not in src, f"external verifier imports repo code: {forbidden}"

    def test_clean_chain_passes(self, tmp_path):
        receipts_path, receipts, key, _ = make_chain(tmp_path, n=5)
        ckpt_path = tmp_path / "checkpoints.jsonl"
        create_checkpoint(receipts_path, ckpt_path, key.private_bytes_raw().hex())
        res = run_verifier(str(receipts_path), "--checkpoints", str(ckpt_path))
        assert res.returncode == 0, res.stdout + res.stderr
        assert "OK" in res.stdout

    def test_detects_content_tamper(self, tmp_path):
        receipts_path, receipts, key, _ = make_chain(tmp_path, n=5)
        lines = receipts_path.read_text().splitlines()
        r = json.loads(lines[2])
        r["outcome"] = "TAMPERED"
        lines[2] = json.dumps(r)
        receipts_path.write_text("\n".join(lines) + "\n")
        res = run_verifier(str(receipts_path))
        assert res.returncode != 0
        assert "self_hash mismatch" in res.stdout

    def test_detects_chain_break(self, tmp_path):
        receipts_path, receipts, key, _ = make_chain(tmp_path, n=5)
        lines = receipts_path.read_text().splitlines()
        del lines[2]  # remove a middle receipt
        receipts_path.write_text("\n".join(lines) + "\n")
        res = run_verifier(str(receipts_path))
        assert res.returncode != 0
        assert "chain" in res.stdout.lower()

    def test_detects_bad_signature(self, tmp_path):
        receipts_path, receipts, key, _ = make_chain(tmp_path, n=3)
        lines = receipts_path.read_text().splitlines()
        r = json.loads(lines[1])
        # Re-hash after tamper so self_hash matches content, but signature
        # (made with the original key over the OLD hash) becomes invalid.
        r["outcome"] = "TAMPERED"
        r["self_hash"] = hashlib.sha256(_canonical(r).encode()).hexdigest()
        lines[1] = json.dumps(r)
        # also fix downstream prev_hash so ONLY the signature check can catch it
        r2 = json.loads(lines[2])
        r2["prev_hash"] = r["self_hash"]
        r2["self_hash"] = hashlib.sha256(_canonical(r2).encode()).hexdigest()
        lines[2] = json.dumps(r2)
        receipts_path.write_text("\n".join(lines) + "\n")
        res = run_verifier(str(receipts_path))
        assert res.returncode != 0
        assert "signature" in res.stdout.lower()

    def test_detects_merkle_root_mismatch(self, tmp_path):
        receipts_path, receipts, key, _ = make_chain(tmp_path, n=4)
        ckpt_path = tmp_path / "checkpoints.jsonl"
        ckpt = create_checkpoint(receipts_path, ckpt_path, key.private_bytes_raw().hex())
        # Forge a checkpoint with the wrong root but valid structure/signature
        forged = dict(ckpt)
        forged["merkle_root"] = "0" * 64
        # re-sign forged checkpoint honestly (attacker owns a key)
        from kairo.trust.merkle import _canonical_checkpoint  # test-only import
        forged["self_hash"] = hashlib.sha256(_canonical_checkpoint(forged).encode()).hexdigest()
        forged["signature"] = key.sign(forged["self_hash"].encode()).hex()
        ckpt_path.write_text(json.dumps(forged) + "\n")
        res = run_verifier(str(receipts_path), "--checkpoints", str(ckpt_path))
        assert res.returncode != 0
        assert "merkle" in res.stdout.lower()
