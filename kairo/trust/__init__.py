"""
kairo.trust — W7 Trust Layer.

Implemented:
- merkle: RFC 6962 Merkle tree over Ed25519 receipt hashes + signed
  checkpoints (see kairo/trust/merkle.py) and the standalone external
  verifier at tools/verify_receipts_external.py.
- flight_recorder: Deterministic replay / flight recorder — records
  hash-chained execution traces that can be replayed and verified.
- timestamp_anchor: External timestamp anchor (offline-degrading) —
  provides timestamp provenance for checkpoints, honestly labeled.
- policy_engine: Policy-as-code engine for high-risk action classes —
  ALLOW/DENY/REQUIRE_HUMAN decisions with built-in policies.

Planned / NOT yet implemented (do not claim these exist):
- External transparency log publication (witnessing via Rekor/in-toto)
- Multi-party co-signing of checkpoints (WebAuthn tap is human-gated)
- Agent identity rotation
"""
