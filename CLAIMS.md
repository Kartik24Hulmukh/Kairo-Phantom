# Kairo-Phantom — CLAIMS.md (Real / Experimental / None yet)

**Version:** 1.2 (operationally hardened) · **Date:** 11 July 2026 · **Stage:** code-complete, pre-launch, 0 users, 0 revenue

**The rule:** a capability is **Real** only if backed by a reproducible command whose output anyone can regenerate. **Every public number must be linked to a reproducible command before external publication** (see Section 5 for the required evidence fields). Anything needing real hardware, an external party, a certificate, or an un-happened human judgment is **Experimental** or **None yet.** No "compliant/certified." This file is the single source of truth for what we may say out loud.

**v1.1 changes (from external red-team):** removed "Injection-safe"; R3 renamed to a fixture-suite claim; R8 requires a published interface list; R12 reworded so "verifiable" ≠ "verified"; E2 promotion gate rewritten (TPM ≠ network witness); N8 renamed (no "deterministic/bit-identical"); cross-vendor verifier reworded to "designed to normalize." Skips now documented in `SKIPS.md`.

**v1.2 changes (operational red-team):** R1 changed from "7 documented skips" to "7 skipped; skip audit in progress" (the skip audit is NOT complete until SKIPS.md has 7 real reasons — the consistency oracle stays RED until then, by design); R13 renamed to "11 fixture-verified domain adapters / readback contracts" (forbid "works in 11 real-world domains"); added Section 5 (required evidence fields); the loop kit's coverage script was renamed `score_evidence_manifest.py` and explicitly labeled an illustrative coverage evaluator (NOT a cryptographic verifier).

---

## 1. REAL — reproducible today

| # | Capability | Evidence (reproducible) | Number |
|---|---|---|---|
| R1 | Python test suite | `pytest tests/ -q --ignore=tests/e2e` | 1008 passed / **4 skipped (all environmental; see SKIPS.md)** / 0 failed |
| R2 | Coverage suite | coverage run | 959 passed / 0 failed |
| R3 | **Current prompt-injection fixture suite** *(not "injection-safe")* | injection gauntlet | Blocked all **25/25 attacks in the current fixture suite** · 0/15 false positives · 106 patterns |
| R4 | Grounding accuracy | grounding bench | 595/600 = 99.17% |
| R5 | Grounded-answer rate | grounded-answer bench | 96.39% |
| R6 | Tamper detection (audit chain) | tamper tests | 17/17 |
| R7 | Trust-layer tests | trust-layer suite | 33/33 |
| R8 | Sealed-mode egress (Kairo runtime, tested fixtures) | airgap tests + forced-socket kill-proof | 12/0. **Every published result MUST name: OS, interface, process boundary, duration, protocols, canaries, observer version, excluded paths.** Absent that, say only: "blocked/detected the current forced-send fixtures inside the Kairo runtime." |
| R9 | Merkle receipts (RFC 6962) | `tests/test_merkle_receipts.py` | 17/17 |
| R10 | Dependency-light guarantees | dep-light suite | 28/28 |
| R11 | Rust core | `cargo test` | `test result: ok` |
| R12 | Ed25519 hash-chained audit log | sign + verify + `tools/verify_receipts_external.py` | **Offline-verifiable with the included standalone verifier; no independent third party has yet completed verification.** Tamper → FAIL. |
| R13 | 11 fixture-verified domain adapters / readback contracts | `scripts/gen_status.py` → `STATUS.md` | 11 domain adapters pass their current fixture/readback tests |

**Permitted phrasing:** "produces tamper-evident runtime evidence"; "blocked all 25 attacks in the current fixture suite"; "offline-verifiable audit log"; "eleven domain adapters pass their current fixture/readback tests." **Forbidden:** "works in 11 real-world domains." **Fail-closed permissions are the primary protection — a pattern detector is not a general injection defence.**

---

## 2. EXPERIMENTAL — real code, not yet independently/hardware validated

| # | Capability | Why not Real yet | Gate to promote |
|---|---|---|---|
| E1 | Live desktop GUI actuation + readback on real hardware (Win32 UIA / AT-SPI2) | Not validated by repeated independent runs on stock hardware | 100-run pinned gate on real Win11 (G1) |
| E2 | **Scoped zero-egress evidence** *(not "whole-machine")* | Today's proof covers the Kairo runtime, not the host | **Host observer + separately-administered external network witness + complete interface inventory + required canaries + explicit blind spots.** TPM quote is optional platform-state corroboration, **not** the egress witness. |
| E3 | Personalization / StyleAdapter | No blind A/B on the founder's writing yet | ≥60% blind preference, recorded |
| E4 | Live browser / OCR paths | Not fixture-verified as Real | Readback oracle + fixtures |
| E5 | Desktop causal continuity graph / gap-proof | Plumbing exists; not shipped/validated end-to-end | Continuity chain with explicit EVIDENCE_GAP nodes shipped + tested |

**Never assert an E-item as Real.**

---

## 3. NONE YET — not built / not claimable

| # | Item | Honest status |
|---|---|---|
| N1 | Independent third-party verification of a pack | Nobody external has verified a pack with zero trust in us yet |
| N2 | Paying customers / users / revenue | 0 / 0 / 0 |
| N3 | FIPS module validation | Ed25519 = approved algorithm (FIPS 186-5); the **module** is not validated. Never "FIPS validated." |
| N4 | Installer code-signing | No EV/OV or Apple Developer ID cert |
| N5 | Canary-in-the-Receipt | Planned (ship first). Proves control at **tested moments**, not continuously. |
| N6 | Delegation-Chain Receipts | Planned |
| N7 | Host + external network witness | Planned (this is the egress witness, per E2) |
| N8 | **Evidence & state-transition replay** *(renamed; NOT "deterministic/bit-identical replay")* | Planned (north star) |
| N9 | Cross-vendor verifier / normalizer | Planned. Say **"designed to normalize other platforms' evidence into the KSEE draft profile,"** never "can verify other platforms." |
| N10 | KSEE evidence profile | Draft only. Call it **"KSEE draft evidence profile,"** never "the open standard." |
| N11 | Any "compliance"/"certification" claim | Never. Only: "produces evidence supporting an assessor's evaluation of X." |
| N12 | Assessor demand for the format | Unvalidated — the Mode A/B blind test must establish it |

---

## 4. Hard language rules

- ✅ "Evidence mapped to Article 12/19/26." · "Supports an assessor's evaluation." · "No outbound packet observed across the declared/tested interfaces during this nonce-bound interval; unobserved channels listed."
- ❌ "EU AI Act certified" · "Regulator approved" · "Guarantees compliance" · "FIPS validated" · "Injection-safe" · "Zero bytes left the entire machine" · "0 competitors" · "only one that exists" · "deterministic replay" · "the TPM/second device proves no data left" · "rivals can't copy this."
- ❌ The dead **Aug 2 2026** EU deadline (high-risk / Art. 12 record-keeping is now **Dec 2 2027**; verify OJ text). CMMC: "Phase 2 begins 10 Nov 2026; status/assessment type contract-dependent."
- ❌ Any traction number that isn't 0.
- ⚠️ Competitor facts from `research.md` (AGA patent #, founder, URLs) are **untrusted until independently verified.**

---

## 5. Required evidence fields for every public number

Before any metric in this file is published externally (deck, site, grant, pitch), it must carry a reproducible record with ALL of these fields. If a field is missing, the number is not publication-ready.

- **Exact command** run (copy-pasteable).
- **Commit hash** the command was run at.
- **OS / platform** (e.g. Amazon Linux 2023, Windows 11 23H2).
- **Python / Rust version** (e.g. Python 3.13.x, rustc 1.8x).
- **Dependency lock hash** (e.g. `poetry.lock` / `Cargo.lock` sha256).
- **Date** the run was executed.
- **Raw result path** (committed artifact, e.g. `runs/g1_100run_report.json`).
- **CI URL** (the run that produced it), where applicable.
- **Exit code** of the command.

Until a number has this record, describe it as "local, unverified" — never as an established result.
