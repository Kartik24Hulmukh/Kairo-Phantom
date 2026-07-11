# T0 — Claims Correction Pass

**Gate:** none (unblocks everything) · **Deps:** none · **Budget:** 4 iterations · **Oracle:** script (automatic)

## Goal
Make every public document pass the forbidden-claims scan and the CLAIMS/SKIPS consistency check. This is the foundation — no outreach, demo, or grant goes out until T0 is green.

## Inputs
- `/data/CLAIMS.md`, `/data/KAIRO-PHANTOM-ONE-PAGE-PITCH.md`, `/data/KAIRO-PHANTOM-CANONICAL-PLAN-v1.2.md`, `/data/SKIPS.md`
- research.md sections 3.1–3.6, 4.1–4.5

## Definition of done (oracle)
```bash
python3 orchestrator.py run --task T0
# runs: oracles/check_forbidden_claims.py on all 4 docs  (exit 0)
#  then: oracles/check_claims_consistency.py CLAIMS.md SKIPS.md (exit 0)
```
PASS requires: 0 banned phrases; all three claim buckets present; no third-party-verifiable trap; SKIPS.md has 7 rows and no `<fill>`.

## Work items
- [ ] Remove "Injection-safe" → fixture-suite wording (done in v1.1 pitch).
- [ ] Fill SKIPS.md with the 7 real skip reasons from `pytest -rs`.
- [ ] Confirm no "deterministic replay", "verify other platforms", "Aug 2 2026", "FIPS validated".

## Residual risk
The scanner is heuristic; a novel overclaim it doesn't know about can still slip through. Add new phrases to `BANNED` whenever the red-team finds one.
