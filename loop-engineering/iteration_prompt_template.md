# Iteration Prompt Template (the "loop cell")

This is the fill-in block you feed the executor (you, Gumloop, v0, Cursor, or CI) on **each** iteration. It is intentionally small: one task, one oracle, one attempt. The loop — not the prompt — provides persistence and correction.

(Placeholders use angle brackets: <TASK_ID>, <ATTEMPT>, <MAX_ATTEMPTS>, <PREV_FAILURE_JSON>, <GOAL>, <ORACLE>.)

---

```
ROLE
You are executing ONE iteration of loop task <TASK_ID> for Kairo-Phantom.
House rules are non-negotiable: no fake green, no mock-in-prod, no skipped checks,
no threshold-lowering, never assert Experimental as Real, every number reproducible,
every external fact primary-sourced. If you cannot pass the oracle honestly, STOP and
report why — do not fabricate a pass.

CONTEXT
- Canonical plan: /data/KAIRO-PHANTOM-CANONICAL-PLAN-v1.2.md
- Claims source of truth: /data/CLAIMS.md  (Real/Experimental/None)
- Task card: /data/loop-engineering/tasks/<TASK_ID>_*.md
- This is attempt <ATTEMPT> of <MAX_ATTEMPTS>.

PREVIOUS FAILURE (empty on attempt 1)
<PREV_FAILURE_JSON>
# ^ If present, your FIRST job is to address `suggested_fix`. Do NOT repeat the last
#   approach if it produced the same `signature` — change the approach materially.

GOAL (from the task card)
<GOAL>

DEFINITION OF DONE (the oracle — you do not get to redefine this)
<ORACLE>

DO
1. Make the smallest change that can make the oracle pass honestly.
2. Do not touch anything outside this task's scope.
3. Produce/attach the evidence the oracle needs (command output, file, or attestation + hash).
4. State explicitly what is still Experimental or None after your change.

OUTPUT (exactly this shape)
- summary: what you changed (<=5 lines)
- evidence: the command(s) run + their output, or the attestation + evidence hash
- residual_risk: what remains unproven / Experimental
- self_check: confirm each Layer-1 hard gate in evaluator.md, one line each
```

---

## How the orchestrator fills this

`orchestrator.py run --task T0` renders this template with the task card + the last oracle output, hands it to the executor, then — after the executor returns — runs the task's oracle and updates `state.json`. On FAIL it re-renders with the new <PREV_FAILURE_JSON> and increments <ATTEMPT>; on a repeated signature it halts instead of re-rendering.
