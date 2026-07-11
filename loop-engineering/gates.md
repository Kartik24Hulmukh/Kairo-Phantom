# Gates — G0–G4 and the task oracles

Every gate below has an **oracle** (how PASS is decided) and a **pass condition** (the bar). Machine oracles are scripts; human/hardware oracles are **Ed25519-signed evidence manifests** verified against `schemas/trust_roots.json` (fail-closed) whose content is checked by a per-task validator in `validators.py` — not merely a file that exists. Gates map 1:1 to canonical plan Part 10 (v1.2 strategy + v1.2.1 integrity corrections).

> **v1.2.1:** a gate does NOT pass because an evidence file is present and hashes correctly. The matching validator in `validators.py` must accept the file's *content* (e.g. G1 is computed from individual run records, not summary numbers), the manifest must be signed by a registered signer, the evidence must be fresh (≤45 days) and match `base_commit`, and the history chain must be intact. Run `python3 tools/selftest_loop.py` to confirm these properties hold (7/7).

## G0 — Funding eligibility & company structure documented (Day 7)
- **Oracle:** human attestation.
- **Pass:** SBIR eligible **now**, OR SBIR **explicitly excluded** AND a replacement non-dilutive/revenue funding spine selected. Evidence: a one-paragraph decision note committed to the repo. **SBIR is removed from the weekly critical path** — if the company is India-owned and not >=51% US-owned/controlled, record "SBIR closed for now" and move on. **Do NOT design the cap table around a grant or recruit a nominal US co-founder for eligibility.**

## G1 — Desktop causal chain real on hardware (Day 30)
- **Oracle:** human attestation + attached run log + recording checksum.
- **Pass:** single unedited take on **stock Win11**; **≥99/100** readback matches; **100/100** tamper caught; **100%** required canaries detected; **0** silent EVIDENCE_GAPs. Evidence: `runs/g1_100run_report.json` sha256.
- **Fail action:** narrow to ONE deterministic task; freeze all external work.

## G2 — Assessor signal (Day 60) — THE make/break gate
- **Oracle:** human attestation from the **Mode A vs Mode B blind test** (task T2).
- **Pass:** ≥1 assessor prefers **Mode B** (Kairo full evidence) over Mode A (gateway-only) *and states why in writing*; ≥3 assessors actively reviewing. Evidence: signed assessor statement(s) hash.
- **Fail action:** re-examine the entire thesis before spending another quarter.

## G3 — Market proof (Day 90)
- **Oracle:** human attestation + artifact hashes.
- **Pass (ALL of):** (1) **≥1 paid or contractually budgeted pilot** — named budget owner, price, start date, target workflow, decision date; (2) **≥1 external party reproduced a verification** with zero trust; (3) **≥3 qualified workflows**. **LOIs are a supporting metric, NOT the gate** — three nonbinding LOIs can still mean zero willingness to pay. Evidence: pilot contract/PO hash + external repro log + workflow list.

## G4 — Bus factor (Day 90)
- **Oracle:** human attestation.
- **Pass (realistic day-90 bar):** documented recovery/succession process; a **reproducible build completed by one external person**; a **second key custodian or secure key-recovery**; **≥1 external contributor/reviewer**; an **active co-founder pipeline**. "Co-founder onboarded or 2 maintainers" is a **12-month target**, not a day-90 pass/fail — finding the right co-founder should not be forced into 90 days.

---

## Task oracles (the daily loops)

| Task | Oracle (command or attestation) | Pass condition |
|---|---|---|
| **T0** claims correction | `oracles/check_forbidden_claims.py` + `oracles/check_claims_consistency.py` (exit 0) | 0 banned phrases in any public doc; CLAIMS/SKIPS structurally valid; no R-vs-N contradiction; SKIPS.md has no `<fill>` rows |
| **T1** competitive verification + FTO | human attestation | AGA sample bundle verified with AGA's own verifier + documented; patent claim-chart + prior-art memo committed; public novelty claims frozen |
| **T2A** desktop-outcome value test (feeds G2) | signed attestation, `validate_T2A` | blind Mode A/B; ≥3 assessors; ≥1 prefers Mode B **with written reason**; willingness-to-pay recorded |
| **T2B** boundary value test (after T6) | signed attestation, `validate_T2B` | blind Mode B1/B2; ≥3 assessors; ≥1 prefers B2 (boundary) **with written reason** |
| **T3** demo hardening | `runs/g1_100run_report.json` + signed attestation, `validate_T3` | G1 computed from individual run records: ≥100 runs, readback ≥99/100, tamper 100% injected+detected, canaries 100%, 0 gaps, Win11, recording checksum |
| **T4A** native cryptographic verifier | signed attestation, `validate_T4A` | positive vectors all accept; negative vectors (tamper, bad sig, stale nonce/replay, mutated artifact) all reject; canonical encoding + Merkle + artifact-byte hash + reproducible build present; sufficiency report, never bare VALID |
| **T4B** first read-only adapter | signed attestation, `validate_T4B` | one real public sample, license recorded, pos+neg fixtures, every verdict in {proved, not_proved, unavailable}, no implied endorsement |

> `oracles/score_evidence_manifest.py` is an **illustrative COVERAGE report** (never bare VALID, NOT a cryptographic verifier) — it is a helper for T4A, never the pass oracle. Real signature/chain verification is `tools/verify_receipts_external.py`.
| **T5** assessor co-design (KSEE draft) | human attestation | 3 assessors marked sample packs; profile revised; draft published with reviewer credit |
| **T6** boundary witness (scoped zero-egress) | `runs/boundarybench_report.json` + attestation | host + external witness agree; interface inventory + canary coverage + blind spots published; TPM logged as corroboration only |

**Rule:** no task is `done` until its oracle returns PASS. "I think it's fine" is not an oracle.
