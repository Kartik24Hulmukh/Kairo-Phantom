# Kairo-Phantom — Loop-Engineering Kit

**Version:** 1.2 · **Date:** 11 July 2026 · **Owner:** Kartik (solo)

## What this is (and why it replaces "prompts")

A **prompt** runs once and hopes. A **loop** runs, *checks itself against an oracle*, and only stops when a machine-checkable gate passes or a budget is exhausted. This kit turns the 90-day AGA-response sprint (canonical plan v1.1, Part 9) into a set of **self-correcting loops** that obey the house rule: **no fake green.**

The loop is deliberately **oracle-first**: a task is not "done" because the model said so — it is done because a deterministic check (a script, a test, or a recorded human sign-off with a hash) returns PASS.

## The core loop

```
  ┌─────────┐
  │  PLAN   │  pick next actionable task from state.json (deps satisfied, not blocked)
  └───┬────┘
      ▼
  ┌─────────┐  render iteration_prompt_template.md with the task card
  │  ACT    │  (human, Gumloop, v0, Cursor, or CI runs the actual work)
  └───┬────┘
      ▼
  ┌─────────┐  run the task's oracle (deterministic script / test / signed human verdict)
  │ OBSERVE │
  └───┬────┘
      ▼
  ┌─────────┐  PASS → mark done, unlock dependents
  │EVALUATE │  FAIL → record failure signature; if same signature twice → HALT + escalate (anti-thrash)
  └───┬────┘          else → feed the oracle output back into ACT and iterate
      ▼
   (repeat until all gates pass or per-task iteration budget hit)
```

## Files

| File | Purpose |
|---|---|
| `loop-spec.md` | Formal loop: states, transitions, stop conditions, anti-thrash, escalation |
| `gates.md` | G0–G4 + sub-gates, each with an oracle and a pass condition |
| `evaluator.md` | The scoring rubric + the "no fake green" forbidden-claim discipline |
| `iteration_prompt_template.md` | The fill-in loop cell you feed the executor each iteration |
| `state.json` | Machine-readable ledger: tasks, deps, status, attempts, evidence |
| `orchestrator.py` | Runnable driver (v1.2 hardened): `status`/`next` are read-only; `run`/`attest`/`reset`/`wont_fix`/`refresh` mutate. Enforces anti-thrash (structured signatures) + budget; rejects fake attestations (blocked/unmet-dep/already-done, or non-existent evidence files); verifies evidence file hashes; atomic + hash-chained state writes |
| `oracles/check_forbidden_claims.py` | Scans docs for banned phrases ("injection-safe", "Aug 2 2026", etc.) — real, runnable |
| `oracles/check_claims_consistency.py` | Validates CLAIMS.md / SKIPS.md structure + R-vs-N contradictions (stays RED until the 7 `<fill>` skip rows are completed — by design) |
| `oracles/score_evidence_manifest.py` | **Illustrative** KSEE coverage/sufficiency-report scorer over an evidence-pack JSON — NOT a cryptographic verifier (real receipt verification lives in the product's `tools/verify_receipts_external.py`) |
| `tasks/T0..T6_*.md` | One loop card per workstream (goal, inputs, oracle, stop condition, budget) |
| `schemas/evidence_pack.example.json` | Example KSEE evidence pack the verifier scores |

## Quick start

```bash
cd loop-engineering        # (this folder)
# 1. See the whole board and what's actionable next (READ-ONLY, never mutates):
python3 orchestrator.py status
python3 orchestrator.py next
# 2. Run the deterministic oracles that can run today:
python3 orchestrator.py run --task T0        # claims-correction gate
python3 oracles/check_forbidden_claims.py ../CLAIMS.md ../KAIRO-PHANTOM-ONE-PAGE-PITCH.md ../KAIRO-PHANTOM-CANONICAL-PLAN-v1.1.md
python3 oracles/score_evidence_manifest.py schemas/evidence_pack.example.json   # illustrative coverage report
# 3. For human/hardware gates, record the signed verdict with a REAL evidence file:
python3 orchestrator.py attest --task T3 --verdict pass --evidence runs/g1_100run_report.json --note "100-run report, real Win11"
# 4. If a task genuinely can't/shouldn't be done, mark it terminal non-green (dependents stay blocked):
python3 orchestrator.py wont_fix --task G0 --reason "SBIR closed: India-owned; revenue+private funding spine chosen" --evidence docs/funding_decision.md
# 5. Promote blocked->pending after deps complete (explicit, mutating):
python3 orchestrator.py refresh
```

> **Note:** `T0` intentionally stays **RED** until you paste your 7 real skips into `SKIPS.md`. That red is honest — it is the loop refusing to certify "green" while the skip audit is incomplete.

## The one rule

A loop may **never** be marked green by lowering a threshold, skipping a check, mocking a dependency, or asserting an Experimental capability as Real. If a gate can't pass honestly, it stays red and escalates. That is the point.
