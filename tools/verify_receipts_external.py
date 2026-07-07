#!/usr/bin/env python3
"""
STANDALONE external verifier for Kairo Phantom Ed25519 receipts + Merkle
checkpoints. W7 Trust Layer.

This script is deliberately SELF-CONTAINED:
- No imports from the Kairo repo (kairo/, sidecar/, phantom-core/, kernel/).
- stdlib only, except `cryptography` (pip install cryptography) which is
  required solely for Ed25519 signature verification. All hash-chain and
  Merkle checks run without it (signatures are then reported as SKIPPED,
  and --require-signatures makes that a failure).

What it verifies, given a receipts.jsonl (and optionally checkpoints.jsonl):
  1. Linear hash chain: prev_hash continuity from "genesis", seq monotonicity.
  2. Content integrity: recomputes each receipt's canonical self_hash
     (canonicalization contract: fixed field order from identity.rs, compact
     JSON, self_hash/signature emptied).
  3. Ed25519 signatures: signature over the ASCII bytes of self_hash, with
     agent_id as the verifying key (hex).
  4. Merkle checkpoints: recomputes the RFC 6962 root over the receipts'
     RECOMPUTED canonical hashes and compares against each checkpoint whose
     tree_size <= current receipt count; also verifies checkpoint hash-chain
     and signatures.

Exit codes: 0 = all checks passed; 1 = violations found; 2 = usage error.

Usage:
  python verify_receipts_external.py RECEIPTS.jsonl [--checkpoints CKPT.jsonl]
                                     [--require-signatures]
"""

import argparse
import hashlib
import json
import sys

# ── Canonicalization (mirrors phantom-core/src/identity.rs field order) ──────

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


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── RFC 6962 Merkle Tree Hash ────────────────────────────────────────────────

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


def merkle_root(leaves) -> str:
    return _mth(leaves).hex()


# ── Ed25519 (optional dependency) ────────────────────────────────────────────

def make_sig_verifier():
    """Returns (verify_fn, available). verify_fn(pub_hex, data_bytes, sig_hex) -> bool."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        def verify(pub_hex, data, sig_hex):
            try:
                pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
                pub.verify(bytes.fromhex(sig_hex), data)
                return True
            except (InvalidSignature, ValueError):
                return False

        return verify, True
    except ImportError:
        return (lambda *a: False), False


# ── Verification passes ──────────────────────────────────────────────────────

def read_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"ERROR: {path}:{lineno}: invalid JSON ({e})")
    return records


def verify_receipts(receipts, verify_sig, sig_available, require_signatures):
    violations = []
    prev_hash = "genesis"
    expected_seq = 0
    for i, r in enumerate(receipts):
        where = f"receipt[{i}] seq={r.get('seq')}"
        if r.get("prev_hash") != prev_hash:
            violations.append(
                f"{where}: chain break — prev_hash={str(r.get('prev_hash'))[:16]}... "
                f"expected {prev_hash[:16]}..."
            )
        if r.get("seq") != expected_seq:
            violations.append(f"{where}: chain seq gap — expected seq={expected_seq}")
        computed = sha256_hex(canonical(r, RECEIPT_FIELD_ORDER).encode("utf-8"))
        if computed != r.get("self_hash"):
            violations.append(f"{where}: self_hash mismatch (content was modified)")
        if sig_available:
            if not verify_sig(
                r.get("agent_id", ""),
                str(r.get("self_hash", "")).encode("ascii"),
                r.get("signature", ""),
            ):
                violations.append(f"{where}: invalid Ed25519 signature")
        elif require_signatures:
            violations.append(
                f"{where}: signature UNVERIFIED (cryptography not installed) "
                "and --require-signatures set"
            )
        prev_hash = r.get("self_hash", "")
        expected_seq = (r.get("seq") or 0) + 1
    return violations


def verify_checkpoints(checkpoints, receipts, verify_sig, sig_available, require_signatures):
    violations = []
    # Leaves: RECOMPUTED canonical content hashes (never trust stored self_hash)
    leaves = [
        sha256_hex(canonical(r, RECEIPT_FIELD_ORDER).encode("utf-8")).encode("ascii")
        for r in receipts
    ]
    prev_ckpt_hash = "genesis"
    expected_seq = 0
    for i, c in enumerate(checkpoints):
        where = f"checkpoint[{i}] seq={c.get('checkpoint_seq')}"
        if c.get("prev_checkpoint_hash") != prev_ckpt_hash:
            violations.append(f"{where}: checkpoint chain break")
        if c.get("checkpoint_seq") != expected_seq:
            violations.append(f"{where}: checkpoint seq gap")
        computed = sha256_hex(canonical(c, CHECKPOINT_FIELD_ORDER).encode("utf-8"))
        if computed != c.get("self_hash"):
            violations.append(f"{where}: checkpoint self_hash mismatch")
        if sig_available:
            if not verify_sig(
                c.get("agent_id", ""),
                str(c.get("self_hash", "")).encode("ascii"),
                c.get("signature", ""),
            ):
                violations.append(f"{where}: invalid checkpoint Ed25519 signature")
        elif require_signatures:
            violations.append(f"{where}: checkpoint signature UNVERIFIED and --require-signatures set")

        tree_size = c.get("tree_size", 0)
        if tree_size > len(leaves):
            violations.append(
                f"{where}: tree_size={tree_size} exceeds receipt count {len(leaves)} "
                "(receipts were TRUNCATED after this checkpoint)"
            )
        else:
            recomputed_root = merkle_root(leaves[:tree_size])
            if recomputed_root != c.get("merkle_root"):
                violations.append(
                    f"{where}: MERKLE root mismatch — recomputed {recomputed_root[:16]}... "
                    f"!= checkpoint {str(c.get('merkle_root'))[:16]}..."
                )
        prev_ckpt_hash = c.get("self_hash", "")
        expected_seq = (c.get("checkpoint_seq") or 0) + 1
    return violations


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("receipts", help="Path to receipts.jsonl")
    parser.add_argument("--checkpoints", help="Path to checkpoints.jsonl (optional)")
    parser.add_argument(
        "--require-signatures",
        action="store_true",
        help="Fail if signatures cannot be verified (cryptography missing)",
    )
    args = parser.parse_args()

    verify_sig, sig_available = make_sig_verifier()
    if not sig_available:
        print("NOTE: `cryptography` not installed — Ed25519 checks skipped"
              + (" (FATAL: --require-signatures)" if args.require_signatures else ""))

    receipts = read_jsonl(args.receipts)
    print(f"Loaded {len(receipts)} receipt(s) from {args.receipts}")

    violations = verify_receipts(receipts, verify_sig, sig_available, args.require_signatures)

    if args.checkpoints:
        checkpoints = read_jsonl(args.checkpoints)
        print(f"Loaded {len(checkpoints)} checkpoint(s) from {args.checkpoints}")
        violations += verify_checkpoints(
            checkpoints, receipts, verify_sig, sig_available, args.require_signatures
        )

    if violations:
        print(f"\nFAIL — {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)

    checks = ["hash chain", "content hashes"]
    if sig_available:
        checks.append("Ed25519 signatures")
    if args.checkpoints:
        checks.append("Merkle checkpoints")
    print(f"\nOK — all checks passed ({', '.join(checks)})")
    sys.exit(0)


if __name__ == "__main__":
    main()
