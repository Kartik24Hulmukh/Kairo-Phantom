"""Obsigna (Agent Receipt Protocol) reader: verifies W3C VC AgentReceipts.

Format source: github.com/agent-receipts/obsigna spec + cross-sdk-tests
(py_vectors.json). Scheme confirmed against their shared test vectors:
- Canonicalization: RFC 8785 (JCS) - recursively sorted keys, compact separators.
- Receipt hash: "sha256:" + sha256hex(canonical JSON of the receipt WITHOUT proof).
- Proof: Ed25519Signature2020; signature covers the canonical JSON bytes of the
  receipt WITHOUT the proof object. proofValue is multibase base64url ('u' prefix).

Scope note (honest): no JSON-LD context resolution is performed (offline, no
network). Structural and chain checks always run; the Ed25519 proof is verified
when the caller supplies the verifying key out-of-band (--key), since receipts
reference keys by DID and offline DID resolution is impossible by design.
"""
import base64
import binascii
import hashlib
import json

REQUIRED_TOP = ("@context", "id", "type", "issuer", "issuanceDate", "credentialSubject", "proof")
REQUIRED_PROOF = ("type", "created", "verificationMethod", "proofPurpose", "proofValue")
OBSIGNA_CONTEXT_MARKER = "agentreceipts.ai"


def canonical_jcs(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def receipt_hash(receipt):
    doc = {k: v for k, v in receipt.items() if k != "proof"}
    return "sha256:" + hashlib.sha256(canonical_jcs(doc).encode("utf-8")).hexdigest()


def is_obsigna(record):
    if not isinstance(record, dict):
        return False
    ctx = record.get("@context")
    return isinstance(ctx, list) and any(OBSIGNA_CONTEXT_MARKER in str(c) for c in ctx)


def _decode_proof_value(proof_value):
    if not isinstance(proof_value, str) or not proof_value.startswith("u"):
        raise ValueError("proofValue is not multibase base64url ('u' prefix missing)")
    body = proof_value[1:]
    return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))


def verify_receipt(receipt, public_key_pem=None):
    violations = []
    for f in REQUIRED_TOP:
        if f not in receipt:
            violations.append(f"missing required field: {f}")
    if violations:
        return violations
    if not is_obsigna(receipt):
        violations.append("@context does not include the agentreceipts.ai context")
    proof = receipt.get("proof")
    if not isinstance(proof, dict):
        return violations + ["proof is not an object"]
    for f in REQUIRED_PROOF:
        if f not in proof:
            violations.append(f"proof missing required field: {f}")
    if violations:
        return violations
    if proof.get("type") != "Ed25519Signature2020":
        return violations + [f"unsupported proof type: {proof.get('type')}"]
    if public_key_pem is None:
        return violations + [
            "signature UNVERIFIED: no verifying key supplied (obsigna receipts "
            "reference keys by DID; offline verification needs --key)"
        ]
    try:
        sig = _decode_proof_value(proof["proofValue"])
    except (ValueError, binascii.Error) as e:
        return violations + [f"proofValue decode failed: {e}"]
    doc = {k: v for k, v in receipt.items() if k != "proof"}
    msg = canonical_jcs(doc).encode("utf-8")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        key_bytes = public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
        pub = load_pem_public_key(key_bytes)
        pub.verify(sig, msg)
    except InvalidSignature:
        violations.append("invalid Ed25519 proof signature")
    except Exception as e:
        violations.append(f"key load/verify error: {type(e).__name__}: {e}")
    return violations


def verify_chain(receipts, public_key_pem=None):
    violations = []
    prev_hash, expected_seq = None, 1
    for i, r in enumerate(receipts):
        where = f"receipt[{i}] id={str(r.get('id', '?'))[:32]}"
        violations += [f"{where}: {v}" for v in verify_receipt(r, public_key_pem)]
        chain = (r.get("credentialSubject") or {}).get("chain")
        if not isinstance(chain, dict):
            violations.append(f"{where}: credentialSubject.chain missing")
            prev_hash = receipt_hash(r)
            continue
        seq = chain.get("sequence")
        if not isinstance(seq, int) or isinstance(seq, bool):
            violations.append(f"{where}: chain.sequence is not an integer")
        else:
            if seq != expected_seq:
                violations.append(f"{where}: chain sequence gap (expected {expected_seq})")
            expected_seq = seq + 1
        prev = chain.get("previous_receipt_hash")
        if prev != prev_hash:
            violations.append(
                f"{where}: chain link mismatch (previous_receipt_hash does not match prior receipt)"
            )
        prev_hash = receipt_hash(r)
    return violations
