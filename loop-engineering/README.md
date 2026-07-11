# Kairo-Phantom — Loop-Engineering Kit

**Version:** 1.2.1 · **Date:** 11 July 2026 · **Owner:** Kartik (solo)

> **v1.2.1 (integrity correction):** the loop no longer accepts a file just because it exists and hashes correctly. Each gate’s evidence is checked for *content* by `validators.py`; human/hardware attestations require an **Ed25519-signed manifest** verified against `schemas/trust_roots.json` (fail-closed); the history chain is verified on every mutating command; and `tools/selftest_loop.py` lets anyone confirm the loop rejects fake green (**7/7**). Run it first: `python3 tools/selftest_loop.py`. See `../CHANGELOG-v1.2.1.md`.

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
| `validators.py` | **(v1.2.1)** per-task content validators (`VALIDATORS` keyed T1/T3/T2A/T2B/T6/T4A/T4B/T5/G0/G3/G4), Ed25519 signature verification, canonical encoding, history-chain verification, freshness/base-commit checks |
| `orchestrator.py` | Runnable driver (v1.2.1 hardened): `status`/`next`/`verify` are read-only; `run`/`attest`/`reset`/`wont_fix`/`refresh` mutate. Requires **signed evidence manifests**; runs the per-task content validator; verifies the history chain on every mutation and refuses on a broken ledger; lock covers load→modify→save; anti-thrash + budget; rejects blocked/unmet-dep/already-done |
| `tools/keygen.py` / `tools/sign_manifest.py` / `tools/selftest_loop.py` | **(v1.2.1)** generate a signer keypair (private key off-repo); build+sign an evidence manifest; run the 7-property integrity self-test |
| `schemas/trust_roots.json` / `schemas/EXAMPLE_evidence_manifest.json` | registered signer public keys (empty = fail closed); manifest template |
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
python3 oracles/check_forbidden_claims.py ../CLAIMS.md ../KAIRO-PHANTOM-ONE-PAGE-PITCH.md ../KAIRO-PHANTOM-CANONICAL-PLAN-v1.2.md
python3 oracles/score_evidence_manifest.py schemas/evidence_pack.example.json   # illustrative coverage report
# 3. For human/hardware gates, record the signed verdict with a REAL evidence file:
python3 tools/sign_manifest.py --target T3 --artifact runs/g1_100run_report.json --signer kartik-founder --key ~/.kairo/kartik-founder.key --out evidence/t3.json
python3 orchestrator.py attest --task T3 --verdict pass --evidence evidence/t3.json --note "100-run report, real Win11"
# 4. If a task genuinely can't/shouldn't be done, mark it terminal non-green (dependents stay blocked):
python3 orchestrator.py wont_fix --task G0 --reason "SBIR closed: India-owned; revenue+private funding spine chosen" --evidence docs/funding_decision.md
# 5. Promote blocked->pending after deps complete (explicit, mutating):
python3 orchestrator.py refresh
```

> **Note:** `T0` intentionally stays **RED** until you paste your 7 real skips into `SKIPS.md`. That red is honest — it is the loop refusing to certify "green" while the skip audit is incomplete.

## The one rule

A loop may **never** be marked green by lowering a threshold, skipping a check, mocking a dependency, or asserting an Experimental capability as Real. If a gate can't pass honestly, it stays red and escalates. That is the point.
