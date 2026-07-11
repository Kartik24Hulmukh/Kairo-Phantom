# T4A — Native Cryptographic Verifier (positive + negative conformance vectors)

**Gate:** none · **Deps:** T0, T2A · **Oracle:** attestation (signed manifest + conformance report)

## Why this is split from T4B
The v1.2 T4 was named "Native Verifier + Read-Only Adapters" but its only oracle ran `score_evidence_manifest.py` — a self-declared **coverage** scorer that proves none of: canonical serialization, signature validation, signer provenance, nonce freshness, artifact-byte verification, Merkle proofs, or replay rejection. So T4 could go "done" without a working verifier. T4A now demands the real thing; the coverage scorer stays a helper only.

## Definition of done (attestation)
Ship the free, offline, deterministic verifier and produce a conformance report, then attest:
```bash
python3 orchestrator.py attest --task T4A --verdict pass \
  --evidence evidence/t4a_conformance.json --note "native verifier conformance"
```
The artifact JSON must demonstrate ALL of:
- `positive_vectors` (≥1) that all `result: "accept"`
- `negative_vectors` (≥1) that all `result: "reject"` — tampered receipt, bad signature, stale nonce/replay, mutated artifact
- `canonical_encoding`, `signature_check`, `merkle_proof`, `nonce_freshness`, `artifact_byte_hash`, `reproducible_build_sha256` present

The verifier output is a **sufficiency report**, never a bare VALID.

## Language rule
"Checks supported signatures and hash chains offline and reports sufficiency." Never "verifies any evidence."
