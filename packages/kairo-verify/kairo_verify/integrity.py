"""Integrity verification: hash chain, content hashes, Ed25519 signatures,
RFC 6962 Merkle checkpoints. Never trusts stored hashes."""
import json

from .canon import (
    RECEIPT_FIELD_ORDER,
    CHECKPOINT_FIELD_ORDER,
    content_hash,
    merkle_root,
)


def _sig_verifier():
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        def verify(pub_hex, data, sig_hex):
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(
                    bytes.fromhex(sig_hex), data
                )
                return True
            except (InvalidSignature, ValueError):
                return False

        return verify, True
    except ImportError:
        return None, False


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
                raise ValueError(f"{path}:{lineno}: invalid JSON ({e})")
    return records


def verify_receipts(receipts, require_signatures=False):
    violations = []
    verify_sig, sig_available = _sig_verifier()
    if require_signatures and not sig_available:
        violations.append(
            "signatures: --require-signatures set but 'cryptography' is not installed"
        )
    prev_hash, expected_seq = "genesis", 0
    for i, r in enumerate(receipts):
        where = f"receipt[{i}] seq={r.get('seq')}"
        extra = sorted(set(r.keys()) - set(RECEIPT_FIELD_ORDER))
        if extra:
            violations.append(
                f"{where}: unverified extension field(s) {extra} "
                "(not covered by signature)"
            )
        if r.get("prev_hash") != prev_hash:
            violations.append(f"{where}: chain break (prev_hash mismatch)")
        seq = r.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            violations.append(f"{where}: seq is not an integer")
        else:
            if seq != expected_seq:
                violations.append(f"{where}: chain seq gap (expected seq={expected_seq})")
            expected_seq = seq + 1
        if content_hash(r, RECEIPT_FIELD_ORDER) != r.get("self_hash"):
            violations.append(f"{where}: self_hash mismatch (content was modified)")
        if sig_available:
            if not verify_sig(
                r.get("agent_id", ""),
                str(r.get("self_hash", "")).encode("ascii"),
                r.get("signature", ""),
            ):
                violations.append(f"{where}: invalid Ed25519 signature")
        prev_hash = r.get("self_hash", "")
    return violations


def verify_checkpoints(checkpoints, receipts, require_signatures=False):
    violations = []
    verify_sig, sig_available = _sig_verifier()
    if require_signatures and not sig_available:
        violations.append(
            "signatures: --require-signatures set but 'cryptography' is not installed"
        )
    # Leaves: RECOMPUTED canonical content hashes (never trust stored self_hash)
    leaves = [content_hash(r, RECEIPT_FIELD_ORDER).encode("ascii") for r in receipts]
    prev, expected_seq = "genesis", 0
    for i, c in enumerate(checkpoints):
        where = f"checkpoint[{i}] seq={c.get('checkpoint_seq')}"
        if c.get("prev_checkpoint_hash") != prev:
            violations.append(f"{where}: checkpoint chain break")
        extra = sorted(set(c.keys()) - set(CHECKPOINT_FIELD_ORDER))
        if extra:
            violations.append(
                f"{where}: unverified extension field(s) {extra} "
                "(not covered by signature)"
            )
        cseq = c.get("checkpoint_seq")
        if not isinstance(cseq, int) or isinstance(cseq, bool):
            violations.append(f"{where}: checkpoint_seq is not an integer")
        else:
            if cseq != expected_seq:
                violations.append(f"{where}: checkpoint seq gap (expected {expected_seq})")
            expected_seq = cseq + 1
        if content_hash(c, CHECKPOINT_FIELD_ORDER) != c.get("self_hash"):
            violations.append(f"{where}: checkpoint self_hash mismatch")
        if sig_available:
            if not verify_sig(
                c.get("agent_id", ""),
                str(c.get("self_hash", "")).encode("ascii"),
                c.get("signature", ""),
            ):
                violations.append(f"{where}: invalid checkpoint Ed25519 signature")
        tree_size = c.get("tree_size", 0)
        if tree_size > len(leaves):
            violations.append(
                f"{where}: tree_size={tree_size} exceeds receipt count {len(leaves)} "
                "(receipts TRUNCATED after this checkpoint)"
            )
        elif merkle_root(leaves[:tree_size]) != c.get("merkle_root"):
            violations.append(f"{where}: MERKLE root mismatch (recomputed != checkpoint)")
        prev = c.get("self_hash", "")
    return violations
