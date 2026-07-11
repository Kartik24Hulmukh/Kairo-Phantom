# Loop Spec — formal definition

## Task states

| State | Meaning |
|---|---|
| `blocked` | One or more dependencies not yet `done` |
| `pending` | Dependencies satisfied; not started |
| `in_progress` | Currently being iterated |
| `awaiting_oracle` | Work produced; oracle not yet run |
| `done` | Oracle returned PASS |
| `halted` | Anti-thrash tripped or budget exhausted — needs a human decision |
| `wont_fix` | Terminal **NON-GREEN**: a human decided not to pursue this (with a written reason + optional evidence). Dependents stay **blocked**. This is **NOT** equivalent to `done`. |

## Transitions

```
blocked ─(deps done)─▶ pending ─(start)─▶ in_progress ─(work done)─▶ awaiting_oracle
awaiting_oracle ─(oracle PASS)─▶ done
awaiting_oracle ─(oracle FAIL, new signature)─▶ in_progress   # iterate with the failure fed back
awaiting_oracle ─(oracle FAIL, repeated signature)─▶ halted     # anti-thrash
in_progress ─(iteration budget hit)─▶ halted
halted ─(human: change approach materially)─▶ in_progress
halted ─(human: give up, --reason [+ --evidence])─▶ wont_fix     # terminal, non-green
any ─(human wont_fix)─▶ wont_fix                              # dependents remain blocked
```

## Stop conditions (a loop ENDS when any is true)

1. **Success:** oracle returns PASS.
2. **Anti-thrash:** the same failure *signature* occurs twice in a row. A signature is derived from the oracle's **structured output** when present — a `SIGNATURE: {code, subject, count}` line, canonicalized (sorted keys) and hashed — and falls back to the normalized first output line for legacy oracles. Using the structured code/subject makes the key stable against noisy, reordered, or timestamped output. Do NOT retry the same fix a third time — escalate to a human decision.
3. **Budget:** `max_iterations` for the task is reached (default 4).
4. **Dependency death:** a prerequisite task is `halted`.

## Anti-thrash (the most important rule)

History shows the failure mode is retrying the same thing. Enforced mechanically:
- Each FAIL records `signature` + `attempt`.
- If `signature[n] == signature[n-1]` → `halted`, with a required human note before it can move again.
- A human unblocks by either (a) changing the approach materially (new `signature` expected) or (b) marking the gate `wont_fix` with a written reason.

## Escalation

When a task `halts`, the orchestrator prints an **escalation block**: task id, last 2 failure signatures, the oracle command, and the specific human decision required. No silent retries.

## Human / hardware / external gates

Some oracles cannot be a script (real-hardware demo, assessor preference, external verifier reproduction, paid pilot). These use **attestation**: a human records `verdict: pass|fail` + a `note` + an `evidence` pointer. **In v1.2 the orchestrator hardens this:**
- The `evidence` pointer must resolve to a **real file** — either a structured JSON pointer `{type, path, sha256, created_at, signer, signature}` (the orchestrator recomputes the pointed file's SHA-256 and **rejects a hash mismatch**), or a direct artifact file (whose hash is recorded). **Arbitrary strings like `--evidence bananas` are rejected**, and if the task declares a required `artifact`, the evidence must point at it.
- An attestation is **rejected** if the task is `blocked`, has **unmet dependencies**, or is **already terminal** (`done`/`wont_fix`) — unless a human passes `--reopen`.
- A script-oracle task cannot be attested; it must be `run`.
- The verified evidence hash is appended to the hash-chained `history`, so an attestation is logged, timestamped, and cannot be silently overwritten.

## Determinism & idempotence

- Running `orchestrator.py status` or `next` **never** mutates state. Only `run`, `attest`, `reset`, `wont_fix`, and the explicit `refresh` persist changes. Effective statuses (e.g. blocked→pending when deps are satisfied) are computed in memory for display and are only written by `refresh` or a mutating command.
- `state.json` is written **atomically** (temp file → fsync → `os.replace`) under a best-effort file lock, and every history event is **hash-chained** (`prev_hash → hash`) so tampering with the ledger is detectable — consistent with the product's own evidence philosophy.
- Running an oracle twice on unchanged inputs must return the same verdict.
- All state changes are appended to `state.json.history` as hash-chained events (audit trail).
