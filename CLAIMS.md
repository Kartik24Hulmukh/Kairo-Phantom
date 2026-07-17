# Kairo Phantom — Claims Register

**Last updated:** 2026-07-18

## Scope

This register maps every public claim to its reproducible artifact, scope
boundary, and known limitation. Claims that cannot be reproduced are not
made. Claims are scoped to the **legal-v3 mutual-NDA redlining** technical
preview unless explicitly noted.

## What is true (legal-v3 technical preview)

| Claim | Evidence | Scope | Limitation |
|:---|:---|:---|:---|
| Mutual-NDA propose→approve→execute→observe→verify path | `tests/test_legal_v3_e2e.py` (3 tests) | DOCX redlining on sandbox Linux | Synthetic fixture only |
| Exact source/playbook/intent/output binding | SHA-256 digests in proposal + bundle | Legal-v3 transaction | Not a general-purpose binding |
| Independent OOXML readback | `kairo/oracles/docx_tracked_changes.py` | DOCX tracked changes | OOXML format only |
| Separate producer/approver/observer identities | Ed25519 keypairs, observer collision rejected | Legal-v3 transaction | Demo keys, not OS keychain |
| Signed event chain (8 mandatory events) | `verify_bundle` checks sequence + parent + digest + signature | Legal-v3 transaction | Not portable DSSE/in-toto yet |
| Adversarial tamper/deletion/reorder/replay rejection | `tests/test_legal_v3_adversarial.py` (8 tests) | Legal-v3 transaction | Not exhaustive |
| Negative conformance (corrupted bundle rejection) | `tests/test_legal_v3_negative_conformance.py` (13 tests) | verify_bundle | Not exhaustive |
| 100-run synthetic soak | `scripts/legal_v3_soak.py`, `bench/LEGAL_V3_SOAK_REPORT.json` | One mutual-NDA fixture | Not multi-fixture |
| Isolated release staging | `scripts/build_legal_v3_release.py`, `SURFACE_AUDIT.json` | Legal-v3 surface | Does not cover legacy code |
| Surface audit zero findings | `SURFACE_AUDIT.json` | Staged legal-v3 release | Does not audit full repo |
| CLI e2e propose/approve/execute/verify | CLI run with demo fixture | Legal-v3 CLI | Demo keys, local filesystem |
| JSON Schema 2020-12 for evidence artifacts | `schemas/legal_v3/*.json` | Proposal, approval, event, bundle | Not DSSE/in-toto envelopes |

## What is NOT true (forbidden claims)

The following claims are **not made** and must not appear in any legal-v3
artifact:

- "production-ready" — legal-v3 is a technical preview
- "injection-safe" — injection guard exists but is not certified
- "zero sockets" / "whole-machine air gap" — not proven for legal-v3
- "every action signed" — only the 8 mandatory events are signed
- "certified" / "compliant" — no external certification exists
- "100% accurate legal automation" — domain verdict is always `requires_human_review`
- "uncopyable" / "1000x" / "unicorn-guaranteed" — not applicable

## Assurance level

Legal-v3 currently targets **L3 (independently confirmed artifact effect)**
for the DOCX artifact path. This means:

- L0 self-reported: ✅ (producer signs proposal)
- L1 mediator-observed: ✅ (observer signs events)
- L2 enforced: ✅ (policy decision + approval binding)
- L3 independently confirmed artifact: ✅ (OOXML readback by independent observer)
- L4 externally anchored: ❌ (no external security review or legal adjudication)

## Open blockers

See [docs/OPEN_BLOCKERS.md](docs/OPEN_BLOCKERS.md) for the full list.
