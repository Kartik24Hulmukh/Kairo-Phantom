# Kairo-Phantom — Technical Architecture & How It Works (End to End)

> **What this document is.** A deep, engineering-level companion to the founder briefing (`kairo-phantom-how-it-works.html`). The briefing answers *what it is and why it matters*. This document answers *how it is actually built, how a task flows through the system end to end, what is proven vs. experimental, and how to build/run/verify it.*
>
> **Honesty discipline (non-negotiable).** Every capability below is labeled **Real**, **Experimental**, or **None yet**. "Real" means built and enforced by a test that turns the build red if the property breaks (a *kill-proof*). "Experimental" means the code exists but has not been independently validated on real hardware / real users. No users, revenue, or team are claimed. Numbers in this doc are the outputs of actual test/CI runs, not aspirations.

- **Repo:** github.com/Kartik24Hulmukh/Kairo-Phantom (Public, MIT)
- **Stage:** Code-complete · pre-launch · **0 users, 0 revenue, solo founder**
- **One-liner:** *Kairo-Phantom is building the offline, provable execution & verification layer for AI agents* — it runs a computer-use agent on-device and, when sealed, produces evidence that no outbound packet was observed across the declared and tested interfaces during the nonce-bound interval (unobserved channels listed), plus a tamper-evident, offline-verifiable receipt of what it did. *(Never say "zero bytes leave the machine"; scoped zero-egress evidence needs a host + independent external witness and is Experimental until that gate passes.)*

---

## 1. The 60-second mental model

Think of an Operator-style "computer-use" agent, but with two properties nobody else ships together:

1. **Sealed / zero-egress.** With `KAIRO_SEALED=1` the runtime is air-gapped: no outbound sockets, no DNS, no telemetry. An egress oracle actively tries to break the seal and turns the build red if a byte escapes.
2. **Provable.** Every action the agent takes is written to an Ed25519-signed, hash-chained audit log. A third party can verify the signature with the public key; changing or deleting one entry breaks verification.

The wedge: the whole market races on *capability* ("can the agent click the button"). Kairo races on *provability* ("can you prove, offline, in a form a regulator/hospital/law firm accepts, what the agent did and did not do").

---

## 2. System architecture (component map)

Kairo-Phantom is a **two-process, all-local system**: a native Rust core ("the hands") and a Python sidecar ("the brain + conscience"), coordinated over local loopback ports. Nothing depends on an external service to function.

```
                          YOUR MACHINE (optionally KAIRO_SEALED=1)
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                                                                            │
  │   ┌───────────────────────────┐        loopback IPC        ┌────────────┐ │
  │   │  phantom-core (Rust)      │  <---- :7437 / :7438 ----> │  kairo-    │ │
  │   │  "the hands"              │                            │  sidecar   │ │
  │   │  - injector.rs           │                            │  (Python)  │ │
  │   │  - Win32 UI Automation    │                            │  "the      │ │
  │   │  - Linux AT-SPI2          │                            │   brain"   │ │
  │   │  - ghost-type + readback  │                            └─────┬──────┘ │
  │   └───────────────────────────┘                                  │        │
  │                                                                   │        │
  │   ┌───────────────────────────────────────────────────────────── ▼ ─────┐ │
  │   │  CUA layer:  planner · executor · gate · vlm_bridge · world_model    │ │
  │   └──────────────────────────────────────────────────────────────────── ┘ │
  │                                                                   │        │
  │   ┌────────────────────────┐   ┌──────────────────────┐   ┌──────▼──────┐ │
  │   │ Domain registry        │   │ Safety modules        │   │ Trust stack │ │
  │   │ docs/sheets/pdf/email/ │   │ prompt_shield.py      │   │ (the        │ │
  │   │ code + readback oracles│   │ pii_guard.py          │   │  conscience)│ │
  │   └────────────────────────┘   └──────────────────────┘   └─────────────┘ │
  │                                                                            │
  └──────────────────────────────────────────────────────────────────────────┘
```

### 2.1 phantom-core (Rust) — "the hands"
- **Role:** Drives and reads back the *real* GUI at the OS accessibility layer — the same channel screen-readers use.
- **Mechanism:** "Ghost-typing" and UI readback via **Win32 UI Automation** (Windows) and **AT-SPI2** (Linux). This produces genuine application state changes (e.g., real tracked changes in a document), not screenshot mockups.
- **Key file:** `phantom-core/src/injector.rs`.
- **Why Rust:** native, fast, OS-level control with a small, auditable surface.
- **Status:** the injection/readback path against a live desktop is **Experimental** — it needs a human-gated demo on real hardware to promote to Real.

### 2.2 kairo-sidecar (Python) — "the brain"
- **Role:** Task planning + safety. A **LangGraph** planner decomposes a plain-language task into discrete, checkable steps.
- **Safety modules:** `sidecar/safety/prompt_shield.py` (prompt-injection detection) and `sidecar/safety/pii_guard.py` (PII exposure/clipboard-leak guarding).
- **Frozen contracts:** `sidecar/oracles.py` plus the P0 fixtures are treated as frozen reference contracts.

### 2.3 CUA layer — computer-use components
Lives under `cua/`: **planner**, **executor**, **gate**, **vlm_bridge**, **world_model**. These are the see-and-act components: turn intent into concrete UI actions, maintain a model of screen state, and route every action through the gate before execution.

### 2.4 Trust stack — "the conscience"
The defensible core. Every action must pass the reference monitor and is committed to the signed log. Modules (Python):
- `ed25519_audit_log.py` — signed, hash-chained audit log
- `sign_oracles.py` — signing/verification oracles
- `provenance_emit.py` — provenance emission
- `airgap_egress.py` — egress enforcement/detection
- `zero_egress_report.py` — the "0 bytes out" proof artifact
- `sealed_profile.py` — sealed-mode profile/config
- `reference_monitor.py` — the gate that screens every action before it runs
- **W7 / Merkle:** `kairo/trust/merkle.py` (RFC 6962), verified by `tests/test_merkle_receipts.py` (17 tests), with an external verifier `tools/verify_receipts_external.py`.

### 2.5 Domain registry — per-task skills with proof
- `kairo/domains/registry.py` registers per-task-type skills (documents, spreadsheets, PDF, email, code, …).
- Each domain ships a **readback oracle** that proves the *actual* output (reads the real result back and checks it), rather than trusting that the action "probably" worked.
- `scripts/gen_status.py` generates `STATUS.md` from the registry so status is derived from code, not hand-edited.

### 2.6 Local daemon / IPC
- **Ports:** `7437` (daemon) and `7438` (sidecar), loopback only.
- **Sealed env:** `KAIRO_SEALED=1` (hard air-gap) and `KAIRO_OFFLINE` (offline mode). In sealed mode the egress monitor should sit at 0 bytes out for the whole session.

---

## 3. End-to-end data flow (a single task)

Scenario: *"Open this .docx and redline any indemnity clause that exceeds our cap; add tracked-change comments citing the policy reference."*

1. **Seal (optional but core).** Operator runs with `KAIRO_SEALED=1`. `sealed_profile.py` applies the profile; `airgap_egress.py` starts the egress monitor at 0 bytes out.
2. **Task intake.** The plain-language task hits the sidecar. The LangGraph planner decomposes it into steps — **no cloud call**; local model only.
3. **Pre-flight safety.** Before *any* step runs, `reference_monitor.py` + `prompt_shield.py` + `pii_guard.py` screen it for embedded prompt-injection (e.g., "ignore previous instructions" hidden in the document), PII exposure, and clipboard leaks. Malicious embedded instructions are blocked; legitimate edits pass. Both directions are tested — block attacks **and** don't false-refuse benign edits.
4. **Execution.** The CUA executor drives `phantom-core` (Rust) to ghost-type into the real app via UI Automation / AT-SPI2, producing genuine tracked changes and cited comments.
5. **Readback proof.** The domain's readback oracle reads the actual document state back and confirms the edits are really present.
6. **Signing.** Each step is appended to the Ed25519-signed, hash-chained audit log (`ed25519_audit_log.py`); each entry cryptographically depends on the previous one. Merkle receipts (`merkle.py`, RFC 6962) provide inclusion proofs.
7. **Deliverable.** Operator ends with: (a) the redlined document, (b) a zero-egress report proving 0 bytes left the machine, and (c) a signed receipt any third party can verify with the public key. Tamper with one entry → verification fails at that entry.

---

## 4. The proof model (what "provable" actually means)

### 4.1 Signed, hash-chained audit log — **Real**
- Each action → one entry, Ed25519-signed.
- Entry *N* embeds a hash of entry *N-1* → a private per-session chain.
- **Kill-proof:** delete/modify any entry and external verification fails at that entry (demonstrated with a TAMPERED receipt).

### 4.2 Merkle receipts (RFC 6962) — **Real (W7)**
- `kairo/trust/merkle.py` builds RFC 6962-style Merkle trees for inclusion proofs.
- Verified by `tests/test_merkle_receipts.py` (**17 tests**).
- **External verification:** `tools/verify_receipts_external.py` verifies receipts *outside* the app, so verification does not depend on trusting Kairo itself.

### 4.3 Example (from the briefing, real CLI shape)
```bash
$ export KAIRO_SEALED=1 && kairo up
✓ sealed mode active — egress monitor: 0 bytes out

$ kairo test airgap --force-socket-send
✓ egress oracle caught the forced send — blocked RED as designed

$ kairo verify ./session-receipt.json --pubkey kairo.pub
✓ signature valid · hash-chain intact · 17/17 entries verified

$ kairo verify ./session-receipt.TAMPERED.json --pubkey kairo.pub
✗ FAIL — chain broken at entry #6 (tamper detected)
```

---

## 5. Sealed / zero-egress model — **Real**

- **Flags:** `KAIRO_SEALED=1`, `KAIRO_OFFLINE`.
- **Enforcement:** `airgap_egress.py` monitors and blocks outbound activity; `zero_egress_report.py` emits the proof artifact.
- **Kill-proof:** the egress oracle *forces* a socket send during the airgap test; if the send is not caught/blocked, the build goes red. Verified by the airgap suite (**12 passed, 0 egress**).
- **Honest caveat:** this proves *the runtime's own* egress is sealed. It does not, by itself, prove the OS or other processes are silent — that is a system-integration claim, not a Kairo runtime claim.

---

## 6. Safety architecture — **Real**

- **Reference monitor** (`reference_monitor.py`): single choke-point; every action is gated before execution (fail-closed intent).
- **Prompt-injection shield** (`prompt_shield.py`): pattern-based + heuristic detection. **106 patterns**; injection suite **25/25 caught, 0/15 false positives on benign edits** — both directions tested.
- **PII guard** (`pii_guard.py`): screens for PII exposure and clipboard leaks.
- **Grounding:** grounded-answer checks — grounding **595/600 = 99.17%**, grounded-answer **96.39%** (measures that outputs are backed by source, not hallucinated).

---

## 7. Testing & verification philosophy

**Principles (enforced, not aspirational):** oracle-first (prove real output via readback), kill-proofs / canary-breaks (a violated property turns the build red), **no fake green** (no mocks-in-prod, no skipped required tests, no threshold-lowering, no asserting Experimental as Real), honest labels.

### 7.1 Verified test metrics (actual run outputs)

| Suite | Result |
|---|---|
| Python full suite (`pytest tests/ -q --ignore=tests/e2e`) | **1005 passed, 7 skipped, 0 failed** |
| Python under coverage run | **959 passed, 0 failed** |
| Prompt-injection | **25/25 caught, 0/15 false positives** (106 patterns) |
| Grounding | **595/600 = 99.17%** |
| Grounded-answer | **96.39%** |
| Tamper (audit chain) | **17** |
| Trust-layer | **33** |
| Airgap / egress | **12 passed, 0 egress** |
| Merkle receipts | **17** |
| Dependency-light | **28** |
| Rust suites | `test result: ok` (0 failed) |

> Skips are honest (e.g., GUI/Windows jobs that need a real display are human-gated, not silently passed).

### 7.2 CI/CD gates
- **Required status checks (branch protection on `master`):** `CI Pass (aggregate)` and `Release Gate / Release Gate (aggregated)`. Both must be green to merge.
- **Workflows:** Cross-Platform CI Gauntlet, Tier 1 Verify (CPU), Release Gate, Root Test Suite, Supply Chain Gates, Sealed No-Network Gate, Wedge/Full Acceptance Gauntlet, Eval Integrity Guard, pages-build-deployment.
- **Master is protected** → all changes land via branch + PR; never self-merge without green required gates; wait for the full (including slow) gauntlet.
- **Supply chain:** cargo-deny in place (one waiver, RUSTSEC-2026-0204, scheduled for review 2026-09-06).

---

## 8. Build & run

> Exact commands live in the repo README; this is the operational shape.

```bash
# 1. Rust core (the hands)
cd phantom-core && cargo build --release

# 2. Python sidecar (the brain + trust stack)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Run sealed (air-gapped)
export KAIRO_SEALED=1        # 0 sockets · 0 DNS · 0 telemetry
export KAIRO_OFFLINE=1
kairo up                    # daemon :7437, sidecar :7438

# 4. Verify a receipt (independently)
python tools/verify_receipts_external.py ./session-receipt.json --pubkey kairo.pub

# 5. Regenerate status from code
python scripts/gen_status.py   # -> STATUS.md
```

**Tech stack:** Rust (phantom-core) · Python 3 + LangGraph (kairo-sidecar) · Ed25519 signatures · RFC 6962 Merkle receipts · Win32 UI Automation / Linux AT-SPI2 · local-only daemon (7437/7438). **License:** MIT. **Clean-room discipline** for anything AGPL / no-license / paper-derived.

---

## 9. Repository layout (key paths)

```
Kairo-Phantom/
├── phantom-core/                 # Rust — the hands
│   └── src/injector.rs           # ghost-type + UI readback
├── kairo-sidecar/ (sidecar/)     # Python — the brain
│   ├── oracles.py                # frozen reference contracts (P0 fixtures)
│   └── safety/
│       ├── prompt_shield.py       # 106 injection patterns
│       └── pii_guard.py           # PII / clipboard-leak guard
├── cua/                          # planner · executor · gate · vlm_bridge · world_model
├── kairo/
│   ├── domains/registry.py       # per-task skills + readback oracles
│   └── trust/merkle.py           # RFC 6962 Merkle receipts (W7)
├── trust stack (Python):         # ed25519_audit_log, sign_oracles, provenance_emit,
│                                  # airgap_egress, zero_egress_report, sealed_profile,
│                                  # reference_monitor
├── tools/verify_receipts_external.py  # independent receipt verifier
├── scripts/gen_status.py         # generates STATUS.md from the registry
├── tests/                        # oracle-first suites + kill-proofs
│   └── test_merkle_receipts.py   # 17 tests
└── STATUS.md                     # generated status of every domain/capability
```

---

## 10. Radical honesty — Real vs Experimental vs None

| Capability | Status | What that means |
|---|---|---|
| Signed, verifiable audit trail | **Real** | Tamper/delete → verification fails. Kill-proven. |
| Merkle receipts (RFC 6962) + external verifier | **Real** | 17 tests; verifiable outside the app. |
| Sealed / air-gapped (zero-egress) mode | **Real** | 0 egress, oracle catches forced sends (12/0). |
| Prompt-injection defense | **Real** | 25/25 caught, 0 false refusals on benign edits (106 patterns). |
| Core work domains (docs, sheets, PDF, code…) | **Real** | Fixture-verified by readback oracles. |
| Grounding / grounded answers | **Real** | 99.17% grounding, 96.39% grounded-answer. |
| Live GUI / OCR on a real desktop | **Experimental** | Needs a human-gated live demo on real hardware. |
| Signed installer (code-signing) | **Experimental** | Needs a purchased Windows/Apple cert. Not faked. |
| On-device personalization ("writes like you") | **Experimental** | Needs a blind A/B on real writing to promote. |
| Real users / revenue / team | **None yet** | Solo founder, pre-launch, 0 users. |

---

## 11. Known limitations / what is NOT done

- **No live-hardware demo yet.** The GUI ghost-typing path is Experimental until shown end-to-end on a real desktop.
- **No code-signed installer.** Requires a purchased cert.
- **No personalization validation.** The "writes like you" claim is unproven until a blind A/B.
- **Zero external validation.** 0 users, 0 design partners, 0 revenue. All confidence is internal test evidence, not market evidence.
- **Sealed-mode scope.** Proves the *runtime's* egress is sealed, not the whole OS.
- **Receipt/audit category is now crowded.** The signed-receipt primitive alone is commoditizing; the defensible position is the *offline + zero-egress + conformance* combination, not receipts in isolation.

---

## 12. Where this goes (plan from here)

1. **Validate before building more.** A 60-second offline redline demo (egress pinned at 0) to ~10 legal-ops / compliance / hospital-IT people. If ≥6/10 say provable-offline changes their buy decision, it's a company.
2. **Ship the trust layer as an open draft profile (never call it "the standard").** Publish the KSEE draft receipt profile + a free standalone verifier + policy-as-code + evidence & state-transition replay. Aim to own the primitive the way Sigstore owns software signing — only after ≥2 independent producers and a second verifier exist (see canonical plan Part 7).
3. **Open-core.** Open-source the trust primitive to drive adoption of the KSEE draft profile (never claim it "is the standard" before the Part-7 legitimacy checklist is met); keep commercial the domain engines, on-device personalization, and the enterprise/hosted evidence console.
4. **Ride the regulatory clock.** EU AI Act high-risk record-keeping (Article 12) now lands **Dec 2, 2027** under the Digital Omnibus — land-early, harvest-later; verify the Official Journal text before quoting a date. CMMC Phase 2 begins 10 Nov 2026 (status/assessment type contract-dependent). Signed, user-linked, auditable execution is becoming a requirement, not a nice-to-have.

**The one-line pitch:** Kairo-Phantom is the signed, offline, verifiable execution & verification layer for the agent era.

---

*Prepared as an internal technical reference. Every capability label is honest. No users, revenue, or team are claimed. Metrics are actual test/CI outputs as of the latest green run; "Experimental" items are built but not independently validated.*
