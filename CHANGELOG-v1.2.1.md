# CHANGELOG v1.2.1 — integrity correction (co-founder verdict)

**Date:** 11 July 2026 · **Trigger:** `Co-founder verdict.md` — which proved the v1.2 loop still accepted fake green.

> Verdict finding (verbatim intent): an empty `{}` file named `runs/g1_100run_report.json` was attested and the loop marked T3 done / G1 done — "a hash proves file identity, not truth." And a manually edited history event still let `status` run — "the chain is hash-chained but never validated on load."
>
> Verdict conclusion: *thesis potentially 100× YES; company currently 100× NO; v1.2 improved the odds; ship a short v1.2.1 integrity correction, not another strategic rewrite.* This release is exactly that.

---

## 1. Loop can no longer be tricked into fake green

| # | Verdict problem | v1.2.1 fix | Where |
|---|---|---|---|
| 1 | File existence + hash accepted as "evidence" | Per-task **content validators** — evidence must satisfy a semantic schema, not just exist | `loop-engineering/validators.py` (`VALIDATORS`) |
| 2 | G1 passed from summary numbers | G1 pass/fail is **computed from individual run records** (readback per-run, tamper injected+detected, canaries, gaps, OS, recording checksum) | `validators.py` `validate_T3` |
| 3 | Human attestation was just a note | Attestation now requires an **Ed25519-signed manifest** (`target, base_commit, created_at, env, artifact{path,sha256}, signer, signature`) verified against `schemas/trust_roots.json`, **fail-closed** (no signer registered → nothing passes) | `validators.py` `verify_signature`, `check_manifest_common`; `tools/keygen.py`, `tools/sign_manifest.py` |
| 4 | History hash-chained but never checked | `verify_history_chain()` runs on **every mutating command**; broken chain → refuse to run; new `verify` command audits the ledger | `validators.py`, `orchestrator.py` |
| 5 | Lock only covered save | Lock now covers **load → modify → save**; concurrent mutation is rejected | `orchestrator.py` |
| 6 | No freshness / provenance | Evidence older than `defaults.max_evidence_age_days` (45) is rejected; `base_commit` must match `repo.head_commit` when set; `env` block required | `validators.py` |
| 7 | No way for an outsider to check | `tools/selftest_loop.py` builds a throwaway env and asserts 7 integrity properties (empty `{}` rejected, unsigned rejected, untrusted signer rejected, good evidence accepted, readback 98/100 rejected, tampered history detected, mutation refused on broken chain) — **all 7 pass** | `tools/selftest_loop.py`, `fixtures/README.md` |

**Proof:** `cd loop-engineering && python3 tools/selftest_loop.py` → `ALL INTEGRITY PROPERTIES HOLD — 7/7`.

---

## 2. Roadmap contradictions fixed

- **T2 dependency cycle + "Mode B needs T6" contradiction** → **T2 split**: `T2A` (desktop-outcome value, deps T0+T3, before T6, feeds G2) + `T2B` (boundary value, deps T2A+T6, after T6). Old `T2_comparative_evidence_test.md` removed.
- **T4 could be "done" with only a coverage score** → **T4 split**: `T4A` (native cryptographic verifier: canonical encoding, signature, pinned roots, hash-chain, Merkle, nonce freshness/replay, artifact-byte hash, positive + negative vectors, reproducible build) + `T4B` (first read-only adapter on a real public sample, license-checked, pos+neg fixtures, proved/not-proved/unavailable, no implied endorsement). Old `T4_verifier_adapters.md` removed. `score_evidence_manifest.py` stays a **helper**, never a pass oracle.
- **State graph** now: T0[] · T1[T0] · T3[T0]→G1 · T2A[T0,T3]→G2 · T6[T0,T3] · T2B[T2A,T6] · T4A[T0,T2A] · T4B[T4A,T2A] · T5[T2A]. No cycles.

---

## 3. Honesty corrections (pitch & claims)

- **One-page pitch header:** "Every metric is reproducible" → **"Evidence audit in progress — every public metric must be tied to a reproducible evidence record before external use."**
- Do **not** lead externally with "1005 passed / 7 skipped / 0 failed" without date + commit + exact command + "local result; skip audit in progress."
- **CLAIMS.md:** every descriptive evidence label ("coverage run", "injection gauntlet", "grounding bench", "tamper tests", "trust-layer suite", "dep-light suite") is now marked **audit pending** — it needs the full Section 5 record (exact command + commit + env + raw path) before external use.

---

## 4. Strategy finalized (not rewritten)

- **Canonical plan renamed** `…-v1.1.md` → **`KAIRO-PHANTOM-CANONICAL-PLAN-v1.2.md`** and included in the zip alongside `KAIRO-PHANTOM-ARCHITECTURE.md` (was missing from the v1.2 zip).
- **Stale G4 fixed** in the Part-10 gate table: bus-factor no longer requires "Co-founder" as a Day-90 pass condition for a solo founder — now documented succession + reproducible builds + 2-person key custody; a co-founder is the goal, not manufactured to clear a gate.
- **90 days re-scoped into three milestones** (Days 1–14 truth+workflow+5 interviews; 15–45 desktop proof + T2A/G2; 46–90 buyer proof).
- **Beachhead narrowed** to a concrete hypothesis: local AI contract-redlining; legal-ops user / security-compliance buyer; validated by 5+5+3 interviews scored on 8 axes before broad interop.
- **Grant money allocated & time-boxed** (security review / test HW / legal FTO / external repro / discovery / contingency; release 25% per gate; ≤20% of any week).
- **10x vs 100x section added:** the 100x bet is *adoption of the evidence format + assessor demand + every vendor becomes an input + a compounding failure corpus* — not another agent that signs its own logs.

---

## 5. New / changed files

**New:** `loop-engineering/validators.py`, `loop-engineering/tools/keygen.py`, `loop-engineering/tools/sign_manifest.py`, `loop-engineering/tools/selftest_loop.py`, `loop-engineering/schemas/trust_roots.json`, `loop-engineering/schemas/EXAMPLE_evidence_manifest.json`, `loop-engineering/fixtures/README.md`, `loop-engineering/tasks/T2A_*.md`, `T2B_*.md`, `T4A_*.md`, `T4B_*.md`, `CHANGELOG-v1.2.1.md`, `KAIRO-PHANTOM-ARCHITECTURE.md`.
**Changed:** `loop-engineering/orchestrator.py` (validators, signed manifests, chain verify, load→save lock, `verify` command), `loop-engineering/state.json` (v1.2.1 graph), `CLAIMS.md`, `KAIRO-PHANTOM-ONE-PAGE-PITCH.md`, canonical plan (renamed + addendum), `GUMLOOP-CHAT-PROMPT.md`, loop docs.
**Removed:** `loop-engineering/tasks/T2_comparative_evidence_test.md`, `loop-engineering/tasks/T4_verifier_adapters.md`.

---

## 6. Founder actions still required (the loop stays honest until you do them)

1. **Register your signing key** — `python3 loop-engineering/tools/keygen.py --signer kartik-founder --out <path OFF the repo>`, paste the printed public key into `loop-engineering/schemas/trust_roots.json`. Until then, attestations **fail closed** (by design).
2. **Fill `SKIPS.md`** with the 7 real skip reasons from a current run (`pytest tests/ -q --ignore=tests/e2e -rs`). T0 stays RED until then (by design).
3. Then run the loop: `python3 loop-engineering/orchestrator.py status`.
