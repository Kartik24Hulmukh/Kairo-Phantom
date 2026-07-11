# Gates — G0–G4 and the task oracles

Every gate below has an **oracle** (how PASS is decided) and a **pass condition** (the bar). Machine oracles are scripts; human/hardware oracles are signed attestations with an evidence pointer. Gates map 1:1 to canonical plan Part 10 (v1.1 strategy + v1.2 corrections).

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
| **T2** Mode A/B comparative evidence test | human attestation (feeds G2) | ≥1 assessor prefers Mode B in writing; blind protocol followed |
| **T3** demo hardening | `runs/g1_100run_report.json` produced + `orchestrator.py attest` | feeds G1 pass condition |
| **T4** verifier + adapters | `oracles/score_evidence_manifest.py` (illustrative COVERAGE report, never bare VALID — NOT a cryptographic verifier) on native + ≥1 adapter fixture | native pack scores; adapter normalizes a sample bundle; output labels observed vs not-observed. Real signature/chain verification stays in `tools/verify_receipts_external.py` |
| **T5** assessor co-design (KSEE draft) | human attestation | 3 assessors marked sample packs; profile revised; draft published with reviewer credit |
| **T6** boundary witness (scoped zero-egress) | `runs/boundarybench_report.json` + attestation | host + external witness agree; interface inventory + canary coverage + blind spots published; TPM logged as corroboration only |

**Rule:** no task is `done` until its oracle returns PASS. "I think it's fine" is not an oracle.
