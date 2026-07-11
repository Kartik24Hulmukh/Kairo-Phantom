# CHANGELOG — Canonical Plan v1.0 → v1.1 (red-team integration)

Source of corrections: `research.md` (external technical red-team). Verdict on the red-team: **accepted almost in full.** The strategy did not change; ~15 overclaims were tightened. Below maps every change to its research section, with my adjudication.

| # | Research § | v1.0 said | v1.1 says | My call |
|---|---|---|---|---|
| 1 | 1.1 | "we're the only ones" narrative | Removed permanently; "only one" is banned | ACCEPT |
| 2 | 2.1 | (chat) "AGA proves buyers will pay" | "AGA proves credible builders see the same gap"; demand still unvalidated | ACCEPT |
| 3 | 2.2 | (chat) "AGA signs its own receipts" | A separate governance gateway signs the decision — not self-attestation | ACCEPT |
| 4 | 2.3 | Part 6 #4 + demo: "TPM 2.0 quote" as egress witness | **TPM ≠ network witness.** Egress = host sensor + external witness + canaries + coverage declaration; TPM = optional platform-state corroboration | ACCEPT (most material fix) |
| 5 | 2.4 | "every rival has gaps by construction" / "can't copy without a rewrite" | "gateway-only evidence cannot establish downstream desktop state without additional observers"; wrappers CAN add observers | ACCEPT |
| 6 | 2.5 | "the open conformance standard" | "KSEE draft evidence profile" + legitimacy checklist (Part 7) | ACCEPT |
| 7 | 2.6 | AirGapBench (one suite, implies testing AGA) | Split: **BoundaryBench** (network) + **EvidenceBench** (completeness). Don't test AGA for leakage unless it claims air-gap | ACCEPT |
| 8 | 2.7 | (chat) "AGA likely funded / US-centric" | Removed — unverified | ACCEPT |
| 9 | 3.1 | R12 "third-party-verifiable" | "offline-verifiable with the included verifier; no third party has verified yet" | ACCEPT |
| 10 | 3.2 | R8 "zero egress across tested interfaces" | Same, but every result must publish OS/interface/duration/protocols/canaries/observer/excluded paths | ACCEPT |
| 11 | 3.3 | "Injection-safe" (pitch) / R3 generic | R3 = "current prompt-injection fixture suite"; "Injection-safe" removed; fail-closed is primary | ACCEPT |
| 12 | 3.4 | E2 gate = "dual-witness (2nd device / TPM)" | Host + external network witness + interface inventory + canaries + blind spots; TPM optional | ACCEPT |
| 13 | 3.5 | N8 "Deterministic Replay Receipts" | "Evidence & state-transition replay" (no bit-identical promise) | ACCEPT |
| 14 | 3.6 | "0 unjustified skips" | "1005 passed, 7 documented skips, 0 failed" + new `SKIPS.md` | ACCEPT |
| 15 | 4.1 | one-liner in present tense | "is building … designed to …" until gates pass | ACCEPT |
| 16 | 4.2 | "air-gapped evidence + no connectivity" (universal) | "Some regulated/sovereign environments require local operation…" | ACCEPT |
| 17 | 4.3 | "endpoint/API logs explicitly insufficient" | "may be insufficient when they don't bind principal/artifact/state" | ACCEPT |
| 18 | 4.4 | "assessments begin Nov 10 2026; cert before award" | "CMMC Phase 2 begins 10 Nov 2026; status/assessment type contract-dependent" | ACCEPT |
| 19 | 4.5 / 5 | verifier "can also verify other platforms" | "designed to normalize other platforms' evidence (roadmap adapters)" | ACCEPT |
| 20 | 5 | "Microsoft AGT is cloud (Purview)" | AGT has offline receipts; don't conflate with Purview; opportunity = independent cross-vendor appraisal | ACCEPT |
| 21 | 5 | "one multi-regulator profile" | one evidence model + separate mappings (CMMC/NIST, DORA, EU AI Act, ISO 42001, customer) | ACCEPT |
| 22 | 5 | canary "armed the whole session" | "operated at the tested moments" | ACCEPT |
| 23 | 6–8 | verifier outputs pass/fail | verifier always outputs a **sufficiency report**, never bare VALID | ACCEPT (new) |
| 24 | 8 | — | Added the **Mode A vs Mode B blind assessor test** as the central Days 8–30 experiment | ACCEPT (new) |

## Where I applied my own judgment (not blind agreement)
- **The red-team is untrusted content too.** Its concrete AGA facts (patent 19/433,835, founder, URLs) are now flagged in v1.1 as *verify-before-citing*, not adopted as truth. The red-team's *method* (tighten claims) is safe to adopt because every change reduces what we assert; adopting cautious wording can't create a new overclaim.
- **Net effect:** less impressive on paper, materially more credible in front of a technical assessor — which is the only audience that matters for the next 90 days.
