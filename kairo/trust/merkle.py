"""
W7 Trust Layer — Merkle chaining over Ed25519 receipts (RFC 6962 tree).

The existing provenance receipts (phantom-core/src/identity.rs ReceiptLog,
mirrored by sidecar/observability/provenance_bridge.py) form a LINEAR hash
chain: prev_hash → self_hash, with an Ed25519 signature over self_hash.

A linear chain proves ordering but makes point verification O(n) and offers
no compact commitment you can hand to a third party. This module adds:

1. RFC 6962 Merkle Tree Hash over the receipts' canonical content hashes
   (leaf = ASCII bytes of the recomputed self_hash; 0x00/0x01 domain
   separation exactly as in Certificate Transparency).
2. Signed CHECKPOINTS: {tree_size, merkle_root, prev_checkpoint_hash, ...}
   Ed25519-signed with the same key/convention as receipts (signature over
   the ASCII bytes of the checkpoint's self_hash). Checkpoints are themselves
   hash-chained, so a verifier can detect both receipt tampering AND
   checkpoint rollback.
3. Inclusion proofs (merkle_proof / verify_merkle_proof) so a single receipt
   can be proven against a published root in O(log n).

Threat model note (honest limits): everything here is signed with the agent's
OWN key. An attacker with full write access to disk AND the private key can
rewrite history. Tamper-evidence against that requires publishing checkpoint
roots to an external witness — that is PLANNED, not implemented. See
kairo/trust/__init__.py.

The standalone external verifier (tools/verify_receipts_external.py)
re-implements all of this with zero repo imports.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "merkle_leaf_hash",
    "merkle_root",
    "merkle_proof",
    "verify_merkle_proof",
    "create_checkpoint",
    "verify_checkpoint",
    "read_checkpoints",
]

# ── RFC 6962 Merkle Tree Hash ────────────────────────────────────────────────

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"


def merkle_leaf_hash(leaf: bytes) -> str:
    """RFC 6962 leaf hash: SHA-256(0x00 || leaf), hex."""
    return hashlib.sha256(_LEAF_PREFIX + leaf).hexdigest()


def _mth(leaves: List[bytes]) -> bytes:
    """RFC 6962 Merkle Tree Hash (raw digest bytes)."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return hashlib.sha256(_LEAF_PREFIX + leaves[0]).digest()
    k = _largest_power_of_two_lt(n)
    left = _mth(leaves[:k])
    right = _mth(leaves[k:])
    return hashlib.sha256(_NODE_PREFIX + left + right).digest()


def _largest_power_of_two_lt(n: int) -> int:
    """Largest power of two strictly less than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root(leaves: List[bytes]) -> str:
    """RFC 6962 Merkle root (hex) over raw leaf byte strings."""
    return _mth(leaves).hex()


def merkle_proof(leaves: List[bytes], index: int) -> List[Tuple[str, str]]:
    """
    Inclusion proof for leaves[index] against merkle_root(leaves).

    Returns a list of (side, sibling_hash_hex) pairs, side in {"L", "R"}:
    "L" means the sibling is on the LEFT of the running hash.
    """
    if not (0 <= index < len(leaves)):
        raise IndexError(f"index {index} out of range for {len(leaves)} leaves")

    def path(lvs: List[bytes], idx: int) -> List[Tuple[str, str]]:
        n = len(lvs)
        if n == 1:
            return []
        k = _largest_power_of_two_lt(n)
        if idx < k:
            return path(lvs[:k], idx) + [("R", _mth(lvs[k:]).hex())]
        return path(lvs[k:], idx - k) + [("L", _mth(lvs[:k]).hex())]

    return path(leaves, index)


def verify_merkle_proof(
    leaf: bytes,
    index: int,
    tree_size: int,
    proof: List[Tuple[str, str]],
    root_hex: str,
) -> bool:
    """Verify an inclusion proof produced by merkle_proof."""
    if not (0 <= index < tree_size):
        return False
    running = hashlib.sha256(_LEAF_PREFIX + leaf).digest()
    for side, sibling_hex in proof:
        sibling = bytes.fromhex(sibling_hex)
        if side == "L":
            running = hashlib.sha256(_NODE_PREFIX + sibling + running).digest()
        elif side == "R":
            running = hashlib.sha256(_NODE_PREFIX + running + sibling).digest()
        else:
            return False
    return running.hex() == root_hex


# ── Checkpoints ──────────────────────────────────────────────────────────────

_CHECKPOINT_FIELD_ORDER = [
    "checkpoint_seq",
    "timestamp",
    "agent_id",
    "tree_size",
    "merkle_root",
    "prev_checkpoint_hash",
    "self_hash",
    "signature",
]


def _canonical_checkpoint(ckpt: Dict[str, Any]) -> str:
    """Canonical JSON for a checkpoint (self_hash/signature emptied), matching
    the receipt canonicalization style (fixed field order, compact JSON)."""
    temp = dict(ckpt)
    temp["self_hash"] = ""
    temp["signature"] = ""
    ordered = {k: temp[k] for k in _CHECKPOINT_FIELD_ORDER if k in temp}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def _receipt_canonical(receipt: Dict[str, Any]) -> str:
    """Receipt canonical JSON — must match provenance_bridge/identity.rs."""
    field_order = [
        "seq", "timestamp", "agent_id", "action", "context", "outcome",
        "prev_hash", "self_hash", "signature",
        "opik_trace_id", "opik_trace_url", "domain",
    ]
    temp = dict(receipt)
    temp["self_hash"] = ""
    temp["signature"] = ""
    ordered = {k: temp[k] for k in field_order if k in temp}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def read_checkpoints(path: Path) -> List[Dict[str, Any]]:
    """Read all checkpoints from a checkpoints.jsonl file."""
    return _read_jsonl(Path(path))


def _receipt_leaves(receipts: List[Dict[str, Any]]) -> List[bytes]:
    """Leaves = ASCII bytes of each receipt's RECOMPUTED canonical hash.

    Recomputing (rather than trusting the stored self_hash) means a receipt
    whose content was edited in place binds a DIFFERENT leaf, so the Merkle
    root catches content tampering even when the attacker forgot (or chose
    not) to update self_hash.
    """
    return [
        hashlib.sha256(_receipt_canonical(r).encode("utf-8")).hexdigest().encode("ascii")
        for r in receipts
    ]


def create_checkpoint(
    receipts_path: Path,
    checkpoints_path: Path,
    private_key_hex: str,
) -> Dict[str, Any]:
    """
    Build a Merkle root over all receipts and append a signed checkpoint.

    private_key_hex: 64-hex-char Ed25519 seed (same format identity.rs stores;
    if a longer keypair hex is provided, the first 64 chars are the seed).
    Returns the checkpoint dict that was appended.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    receipts_path = Path(receipts_path)
    checkpoints_path = Path(checkpoints_path)

    receipts = _read_jsonl(receipts_path)
    root = merkle_root(_receipt_leaves(receipts))

    existing = read_checkpoints(checkpoints_path)
    prev_hash = existing[-1]["self_hash"] if existing else "genesis"
    seq = existing[-1]["checkpoint_seq"] + 1 if existing else 0

    seed = bytes.fromhex(private_key_hex[:64])
    key = Ed25519PrivateKey.from_private_bytes(seed)
    pub_hex = key.public_key().public_bytes_raw().hex()

    ckpt: Dict[str, Any] = {
        "checkpoint_seq": seq,
        "timestamp": int(time.time()),
        "agent_id": pub_hex,
        "tree_size": len(receipts),
        "merkle_root": root,
        "prev_checkpoint_hash": prev_hash,
        "self_hash": "",
        "signature": "",
    }
    ckpt["self_hash"] = hashlib.sha256(_canonical_checkpoint(ckpt).encode()).hexdigest()
    # Same convention as receipts: Ed25519 over the ASCII bytes of self_hash.
    ckpt["signature"] = key.sign(ckpt["self_hash"].encode("ascii")).hex()

    checkpoints_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoints_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(ckpt, ensure_ascii=False) + "\n")
    return ckpt


def verify_checkpoint(ckpt: Dict[str, Any]) -> List[str]:
    """
    Verify a single checkpoint's self_hash and Ed25519 signature.
    Returns a list of violation strings (empty = valid).
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    violations: List[str] = []
    computed = hashlib.sha256(_canonical_checkpoint(ckpt).encode()).hexdigest()
    if computed != ckpt.get("self_hash"):
        violations.append(f"checkpoint seq={ckpt.get('checkpoint_seq')}: self_hash mismatch")
        return violations  # signature is over self_hash; no point continuing
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(ckpt["agent_id"]))
        pub.verify(bytes.fromhex(ckpt["signature"]), ckpt["self_hash"].encode("ascii"))
    except (InvalidSignature, ValueError, KeyError) as e:
        violations.append(
            f"checkpoint seq={ckpt.get('checkpoint_seq')}: invalid signature ({type(e).__name__})"
        )
    return violations
