# Legal v3 — Implementation Status

**Last updated:** 2026-07-18  
**Status:** technical preview (not production-ready for the full platform)

## What is implemented

- **Mutual-NDA governed transaction** (`kairo/legal_v3/transaction.py`):
  propose → approve → execute → observe → verify lifecycle with exact
  source/playbook/intent/output binding, Ed25519 signed event chain,
  and independent OOXML readback.

- **Observer/oracle modules** (`kairo/oracles/`):
  - `docx_tracked_changes.py` — independent OOXML tracked-changes readback
  - `legal_redline_pipeline.py` — clause extraction + injection scan + redline
  - `ed25519_audit_log.py` — signed audit log helpers
  - `zero_egress_report.py` — egress proof report

- **Injection guard** (`kairo/security/injection_guard.py`):
  PromptShield-style taint scan for playbook clauses.

- **CLI** (`tools/kairo_legal_v3.py`):
  keygen, propose, approve, execute, verify subcommands.

- **Release builder** (`scripts/build_legal_v3_release.py`):
  Isolated staging with RELEASE_MANIFEST.json + SURFACE_AUDIT.json.
  Excludes all twelve legacy domains.

- **Soak test** (`scripts/legal_v3_soak.py`):
  N-iteration propose → verify cycle with JSON report.

- **JSON Schemas** (`schemas/legal_v3/`):
  JSON Schema 2020-12 for proposal, approval, event, bundle.

- **CI workflow** (`.github/workflows/legal-v3-gates.yml`):
  Legal-v3 tests, release build, CLI e2e, soak, claim guard, domain guard.

## Test results

| Suite | Count | Result |
|:---|---:|:---:|
| E2E (`test_legal_v3_e2e.py`) | 3 | PASS |
| Adversarial (`test_legal_v3_adversarial.py`) | 8 | PASS |
| Negative conformance (`test_legal_v3_negative_conformance.py`) | 13 | PASS |
| Synthetic soak (100 runs) | 100 | PASS |
| Surface audit | 0 findings | PASS |
| CLI e2e | 1 | PASS |
| `make build` | — | PASS |

## What is NOT implemented

See [OPEN_BLOCKERS.md](OPEN_BLOCKERS.md) for the full list. Key gaps:

- OS keychain/HSM key custody (demo keys only)
- OS sandboxing for parser/sidecar
- Authenticated OS IPC for legacy daemon
- Signed installers
- External security review
- DSSE/in-toto portable envelopes
- Real customer documents / paid pilot

## Assurance level

L3 (independently confirmed artifact effect) for the DOCX artifact path.
Not L4 (externally anchored) — no external security review or legal
adjudication has been conducted.
