# CHANGELOG — v1.1 → v1.2 (operational hardening)

**Date:** 11 July 2026 · **Basis:** `Kairo_phantom_v1.1_final_updates.md` (operational red-team). Verdict was **8/10 strategic APPROVE, 5/10 operational REJECT-until-fixed**. Every operational fix below is now applied. **Strategy is unchanged; only correctness, honesty, and execution order changed.**

> Rule of this release: nothing here invents traction or capability. Users = 0, revenue = 0. The changes make the kit *harder to fake green*, not greener.

---

## 1. orchestrator.py — integrity hardening (updates §4)

| Fix | §4 item | What changed |
|---|---|---|
| **4.1** Reject bad attestations | 4.1 | `attest` now REJECTS a task that is `blocked`, has **unmet deps**, or is **already terminal** (`done`/`wont_fix`) unless a human passes `--reopen`. A script-oracle task cannot be attested. *(Proven: `attest --task T3` → "REJECTED: T3 is blocked; unmet deps ['T0']".)* |
| **4.2** Real, hash-verified evidence | 4.2 | Evidence must resolve to a **real file** — a structured JSON pointer `{type,path,sha256,created_at,signer,signature}` (hash recomputed and **mismatch rejected**) or a direct artifact (hashed). **Arbitrary strings rejected.** If a task declares a required `artifact`, evidence must point at it. Verified hash appended to history. *(Proven: `bananas`→reject, wrong-hash pointer→reject, correct file/pointer→accept.)* |
| **4.3** Read-only status/next | 4.3 | `status` and `next` **never** save. Only `run`/`attest`/`reset`/`wont_fix`/`refresh` persist. Effective statuses computed in memory. *(Proven: state.json md5 unchanged after `status`.)* |
| **4.4** `wont_fix` terminal state | 4.4 | New terminal **NON-GREEN** state + `wont_fix --task <id> --reason <r> [--evidence <f>]`. Dependents stay **blocked**; it is NOT equal to `done`. |
| **4.5** Atomic + hash-chained writes | 4.5 | `state.json` written atomically (temp → fsync → `os.replace`) under a file lock; every history event is hash-chained (`prev_hash → hash`). |
| **4.6** Structured anti-thrash signature | 4.6 | Signature now derived from an oracle's `SIGNATURE: {code,subject,count}` line (canonicalized + hashed), falling back to the normalized first line. Stable against noisy/reordered output. |

## 2. CLAIMS.md (updates §2, §6, §7)

- **R1**: "7 documented skips" → **"7 skipped; skip audit in progress"** (audit is NOT complete until SKIPS.md has 7 real reasons).
- **R13**: "11 Real capability domains" → **"11 fixture-verified domain adapters / readback contracts."** Permitted: "eleven domain adapters pass their current fixture/readback tests." **Forbidden: "works in 11 real-world domains."**
- **Global rule**: "Every number links to a reproducible command" → **"Every public number must be linked to a reproducible command before external publication."**
- **New Section 5**: required evidence fields for every public number (exact command, commit, OS, Python/Rust version, lock hash, date, raw-result path, CI URL, exit code).

## 3. gates.md + state.json (updates §5, §8)

- **G0** "SBIR citizenship fork" → **"Funding eligibility & company structure documented."** Pass = SBIR eligible now OR SBIR explicitly excluded + replacement funding spine selected. **SBIR removed from the weekly critical path.**
- **G3** now requires **≥1 paid / contractually-budgeted pilot** (budget owner, price, start, workflow, decision date) **+ 1 external verification reproduction + 3 qualified workflows**. **LOIs are a supporting metric, not the gate.**
- **G4** (day-90) softened to a realistic bar: documented recovery/succession + reproducible build by 1 external person + second key custodian/recovery + ≥1 external contributor/reviewer + active co-founder pipeline. "Co-founder onboarded or 2 maintainers" moved to a **12-month target**.

## 4. Verifier rename + honesty (updates §3)

- `verify_evidence_pack.py` → **`score_evidence_manifest.py`** with a header disclaimer: *"Illustrative schema/coverage evaluator. It does not cryptographically verify evidence or establish that claimed observations occurred."*
- Report now prints **"DECLARED COVERAGE LEVEL … (self-declared)"** instead of a bare "OVERALL EVIDENCE LEVEL: KSEE-L2", with an explicit self-declared/NOT-verified banner.
- Updated references in `state.json` (T4 oracle), `gates.md`, `README.md`, `tasks/T4`, `evaluator.md`. Real receipt verification stays separate in the product's `tools/verify_receipts_external.py`.

## 5. loop-spec.md (updates §4)

- Fixed the "status never mutates" description to match the hardened code; documented that only mutating commands persist.
- Added the `wont_fix` terminal state, its transitions, atomic/hash-chained write note, hardened attestation rules, and the structured-signature note.

## 6. Canonical plan (updates §1, §10)

- SBIR de-emphasized: if India-owned and not ≥51% US-owned/controlled, **"SBIR closed for now"** — do NOT design the cap table around a grant or recruit a nominal US co-founder.
- Added the **corrected execution order** (Phase 0 truth → Phase 1 desktop outcome → Phase 2 **market falsification** → Phase 3 boundary → Phase 4 interop → Phase 5 profile), putting cheap truth and market falsification *before* expensive TPM/adapter work. State.json deps updated to match (T2 no longer depends on T4; T4 depends on T2).

## 7. One-page pitch (updates §7)

- "where the cloud is forbidden" → **"on desktops and controlled environments where ordinary cloud agents cannot be trusted or used."**
- Added a plain maturity paragraph: **desktop observation and dual-witness network evidence remain Experimental.**
- "checks the pack with zero trust in us" → **"the existing receipt verifier can check supported signatures and chains offline; the full KSEE independent verifier is still in development."**
- Reduced acronym density: moved the adapter list (Microsoft AGT / AGA / Asqav / SCITT / OTel / MCP) to a **technical appendix**; the one-pager now says "roadmap adapters will ingest evidence from other agent platforms."

## 8. New files

- `CHANGELOG-v1.2.md` (this file).
- `GUMLOOP-SYSTEM-PROMPT.md` — forces GLM 5.2 into ultracode mode.
- `GUMLOOP-CHAT-PROMPT.md` — the message to send with this zip to start Phase 0.

---

## What did NOT change (on purpose)

- **SKIPS.md still has 7 `<fill>` rows.** The `check_claims_consistency.py` oracle is **EXPECTED to stay RED** until Kartik pastes 7 real skip reasons. This red is honest, not a bug — it is the loop refusing to certify green while the skip audit is incomplete.
- The strategy, the KSEE model, the Real/Experimental/None discipline, and the anti-fake-green house rules are unchanged.
