# Evaluator — scoring rubric + "no fake green" discipline

The evaluator runs after every ACT step. It answers one question: **may this iteration be marked PASS?** It has two layers: hard gates (any fail → automatic FAIL) and a quality rubric (advisory).

## Layer 1 — HARD GATES (any single failure = FAIL, no exceptions)

1. **No forbidden claims.** `check_forbidden_claims.py` returns 0 hits across all public docs.
2. **No fake green.** The change did NOT: lower a threshold, delete/skip a failing assertion, mock a dependency in a prod path, `|| true` / bypass CI, or assert an Experimental capability as Real.
3. **Every number is reproducible.** Any quantitative claim added is backed by a command in the same PR, and any number bound for **external publication** carries the full evidence record (command, commit, OS, versions, lock hash, date, raw-result path, CI URL, exit code — see CLAIMS.md §5). No invented users/revenue/metrics.
4. **Evidence pointer present.** For human/hardware gates, an attestation without an `evidence` hash/id is rejected.
5. **Real ≠ Experimental ≠ None.** Claims match CLAIMS.md buckets exactly.
6. **Provenance.** Any competitor/regulatory fact newly cited has a primary-source link, not a `research.md` reference.

## Layer 2 — QUALITY RUBRIC (score 0–2 each; advisory, informs "iterate again?")

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Correctness | oracle fails | oracle passes, edge cases untested | oracle passes + negative test |
| Honesty of framing | overclaims | neutral | explicitly states limits/gaps |
| Reproducibility | manual only | command exists | command + checksum committed |
| Scope discipline | added new domains/features | on-scope | on-scope + removed dead claims |

A task may be marked `done` only if **all Layer-1 gates pass**. A total rubric score < 5 means "iterate again" even if hard gates pass (unless budget hit).

## Failure feedback contract

When the evaluator returns FAIL it must emit a machine-usable object so the next ACT iteration is informed, not blind:
```json
{
  "verdict": "fail",
  "signature": "forbidden_claim:injection-safe:KAIRO-PHANTOM-ONE-PAGE-PITCH.md",
  "detail": "line 22: 'Injection-safe' is banned; use 'blocked all 25 attacks in the current fixture suite'",
  "suggested_fix": "replace the phrase; fail-closed permissions are the primary protection"
}
```
The `signature` is what anti-thrash compares. Oracles should emit a stable `SIGNATURE: {code, subject, count}` line so the key survives noisy/reordered output; the orchestrator canonicalizes and hashes it, falling back to the normalized first line otherwise. If two consecutive iterations share a signature, the loop halts — the same fix is not working and a human must change the approach or mark it `wont_fix`.

> Note on the coverage scorer: `oracles/score_evidence_manifest.py` is an **illustrative coverage evaluator**, not a cryptographic verifier. A PASS from it means "the self-declared manifest is schema-complete and its hash chain is intact," NOT "the evidence was cryptographically verified." Never let its output be framed as independent verification.
