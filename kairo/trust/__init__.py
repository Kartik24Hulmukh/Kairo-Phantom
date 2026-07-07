"""
kairo.trust — W7 Trust Layer.

Implemented:
- merkle: RFC 6962 Merkle tree over Ed25519 receipt hashes + signed
  checkpoints (see kairo/trust/merkle.py) and the standalone external
  verifier at tools/verify_receipts_external.py.

Planned / NOT yet implemented (do not claim these exist):
- Policy-as-code engine
- Multi-party co-signing of checkpoints
- Deterministic replay
- External transparency log publication (witnessing)
"""
