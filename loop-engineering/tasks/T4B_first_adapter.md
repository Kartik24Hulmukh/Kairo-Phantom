# T4B — First Read-Only Adapter (real public sample)

**Gate:** none · **Deps:** T4A, T2A · **Oracle:** attestation (signed manifest + adapter report)

## Scope
Exactly ONE read-only adapter that normalizes an external evidence format into the KSEE draft profile — on a REAL public sample, license-checked, with positive and negative fixtures and explicit proved / not-proved / unavailable output. No implied endorsement.

## Adapter order (only after market signal)
1. Microsoft AGT receipts
2. Attested Intelligence AGA sample bundle (only if legally appropriate after T1)
3. Asqav / SCITT-compatible statement
4. Generic OpenTelemetry / MCP action trace

Pick the first one a real buyer or assessor asks for. Do NOT build all four.

## Definition of done (attestation)
```bash
python3 orchestrator.py attest --task T4B --verdict pass \
  --evidence evidence/t4b_adapter.json --note "first read-only adapter"
```
Artifact JSON must have: `sample_source_url`, `sample_license`, `positive_fixtures` (≥1), `negative_fixtures` (≥1), and every fixture `verdict` in {proved, not_proved, unavailable}.

## Language rule
"Designed to normalize other platforms' evidence into the KSEE draft profile." Never "can verify other platforms."
