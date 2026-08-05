"""Demo chain generator: produces real, valid, signed receipts + a checkpoint
with freshly generated Ed25519 keys, so anyone can watch verification work -
and watch it fail after a one-byte tamper."""
import json
import os

from .canon import RECEIPT_FIELD_ORDER, CHECKPOINT_FIELD_ORDER, content_hash, merkle_root

_PLAIN = [
    ("index_document", {"document_id": "doc1"}, "ok"),
    ("extract_chunk", {"document_id": "doc1", "chunk_id": "c7"}, "ok"),
    ("propose_edit", {"chunk_id": "c7"}, "proposed"),
    ("apply_edit", {"chunk_id": "c7"}, "executed"),
    ("observer_readback", {"document_id": "doc1"}, "recorded"),
]

_TYPED = [
    ("authority_grant", {"grant_id": "g1", "scope": "redline",
                         "valid_until": "2099-01-01T00:00:00Z", "delegator": "user"}, "recorded"),
    ("data_boundary_crossing", {"data_category": "pii", "document_id": "doc1",
                                "chunk_id": "c7", "boundary": "local->sidecar"}, "recorded"),
    ("control_invocation", {"control": "grounding_gate"}, "held"),
    ("approval_granted", {"approver": "human", "method": "explicit_click"}, "granted"),
    ("irreversible_action", {"operation": "apply_redline"}, "executed"),
]


def _pub_hex(priv):
    from cryptography.hazmat.primitives import serialization
    return priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def build_demo(n=5, typed=False):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    producer = Ed25519PrivateKey.generate()
    auditor = Ed25519PrivateKey.generate()
    prod_id, aud_id = _pub_hex(producer), _pub_hex(auditor)
    spec = _TYPED if typed else _PLAIN

    receipts, prev = [], "genesis"
    for i in range(n):
        action, context, outcome = spec[i % len(spec)]
        r = {
            "seq": i,
            "timestamp": f"2026-08-05T00:{i:02d}:00Z",
            "agent_id": prod_id,
            "action": action,
            "context": context,
            "outcome": outcome,
            "prev_hash": prev,
            "self_hash": "",
            "signature": "",
            "domain": "demo",
        }
        r["self_hash"] = content_hash(r, RECEIPT_FIELD_ORDER)
        r["signature"] = producer.sign(r["self_hash"].encode("ascii")).hex()
        prev = r["self_hash"]
        receipts.append(r)

    leaves = [content_hash(r, RECEIPT_FIELD_ORDER).encode("ascii") for r in receipts]
    c = {
        "checkpoint_seq": 0,
        "timestamp": "2026-08-05T01:00:00Z",
        "agent_id": aud_id,
        "tree_size": len(receipts),
        "merkle_root": merkle_root(leaves),
        "prev_checkpoint_hash": "genesis",
        "self_hash": "",
        "signature": "",
    }
    c["self_hash"] = content_hash(c, CHECKPOINT_FIELD_ORDER)
    c["signature"] = auditor.sign(c["self_hash"].encode("ascii")).hex()
    return receipts, [c]


def write_demo(outdir, n=5, typed=False):
    receipts, checkpoints = build_demo(n=n, typed=typed)
    os.makedirs(outdir, exist_ok=True)
    rp = os.path.join(outdir, "receipts.jsonl")
    cp = os.path.join(outdir, "checkpoints.jsonl")
    with open(rp, "w", encoding="utf-8") as f:
        for r in receipts:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(cp, "w", encoding="utf-8") as f:
        for c in checkpoints:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return rp, cp
