"""Canonicalization and hashing.

Mirrors the contract documented in tools/verify_receipts_external.py in the
Kairo-Phantom repo (field order from phantom-core/src/identity.rs):
fixed field order, compact JSON, self_hash/signature emptied.
"""
import hashlib
import json

RECEIPT_FIELD_ORDER = [
    "seq", "timestamp", "agent_id", "action", "context", "outcome",
    "prev_hash", "self_hash", "signature",
    "opik_trace_id", "opik_trace_url", "domain",
]

CHECKPOINT_FIELD_ORDER = [
    "checkpoint_seq", "timestamp", "agent_id", "tree_size", "merkle_root",
    "prev_checkpoint_hash", "self_hash", "signature",
]


def canonical(record, field_order):
    temp = dict(record)
    temp["self_hash"] = ""
    temp["signature"] = ""
    ordered = {k: temp[k] for k in field_order if k in temp}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def content_hash(record, field_order):
    return hashlib.sha256(canonical(record, field_order).encode("utf-8")).hexdigest()


def _mth(leaves):
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return hashlib.sha256(b"\x00" + leaves[0]).digest()
    k = 1
    while k * 2 < n:
        k *= 2
    return hashlib.sha256(b"\x01" + _mth(leaves[:k]) + _mth(leaves[k:])).digest()


def merkle_root(leaves):
    return _mth(leaves).hex()
