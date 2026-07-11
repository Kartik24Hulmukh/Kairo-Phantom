# T4 — Native Verifier + Read-Only Adapters

**Gate:** none · **Deps:** T0, T2 (adapters come AFTER market falsification) · **Budget:** 4 iterations (script oracle) · **Oracle:** `score_evidence_manifest.py` (illustrative coverage evaluator — NOT a cryptographic verifier)

## Goal
Ship the free, offline, deterministic verifier that outputs a **sufficiency report (never a bare VALID)**, and begin read-only adapters that *normalize* other platforms' evidence — without implying endorsement.

## Adapter order (research.md Position 3)
1. Kairo native evidence
2. Microsoft AGT receipts
3. AGA sample bundle (if legally appropriate after T1)
4. Asqav / SCITT-compatible statement
5. Generic OpenTelemetry / MCP input

## Definition of done (oracle)
```bash
python3 orchestrator.py run --task T4
# runs score_evidence_manifest.py on schemas/evidence_pack.example.json
```
PASS requires: integrity checked; report labels each dimension PASS/INCOMPLETE/NOT OBSERVED; network channels listed; a KSEE-L level emitted. Extend the oracle with an adapter fixture as each adapter lands.

## Language rule
Say "designed to normalize other platforms' evidence into the KSEE draft profile." Never "can verify other platforms."
