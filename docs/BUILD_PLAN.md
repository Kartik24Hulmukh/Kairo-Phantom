# BUILD PLAN — Wedge-First (Trust Leg → Legal Redline → Air-Gap Seal)

> Authored by the Kairo build agent against **Roadmap v2** (`kairo_phantom_v2/KAIRO_PHANTOM_FINAL_ROADMAP.md`)
> and the governing specs (`00_MASTER_OPERATING_PROTOCOL`, `DEFINITION_OF_DONE`, `VERIFICATION_ORACLES`,
> `CLAIM_DISCIPLINE`, `CLEANROOM_IP_PROTOCOL`, `TECH_MANIFEST`, `PDF_DOMAIN_STACK`, `R3_AIRGAP_ENFORCEMENT`).
> Every row is grounded in a real file read in this repo at HEAD `0563e14d`. No claim below asserts
> "Real" unless a named oracle proves it. NO MOCK / NO FAKE GREEN.

## 0. Scope of this plan
Deliver the **Phase 0 v0 WEDGE** per Roadmap G1/G2: a **provably-offline Legal redline** on a real
`.docx`, one OS, local model, emitting a **signed zero-egress report + hash-chained audit-log entry**,
with **injection-in-document treated as data**. Gates that must be green for the wedge to ship:
`13_gauntlet_and_acceptance` (wedge slice) + `no_mock_gate` + `license_gate` + `cleanroom_provenance` +
`sealed_no_network`.

The build order follows the roadmap's own directive: **trust leg first (the un-copyable part), then the
Legal-redline wedge, then the air-gap seal** — NOT the full trinity at once (G2).

---

## 1. GAP TABLE — roadmap requirement → current state → what's needed

Legend for **Current state**: **Real** = has a kill-proof oracle that passes on real fixtures; **Partial**
= real code exists but the v2 oracle/gate is missing or weaker than spec; **Scaffold** = present but not
gate-verified; **Absent** = does not exist.

| # | Roadmap requirement (source) | Current state (evidence) | What's needed |
|---|---|---|---|
| R-01 | **Honest trust gates**; no `\|\| true`/`continue-on-error`/rigged evals; canary-break turns CI red (prompt 01, DoD §1/§3/§4) | **Partial.** `.github/workflows/verify.yml` has a real no-skip static gate, blocking ruff/mypy/clippy, gitleaks, pip-audit, cargo-deny. But there is one `continue-on-error: ${{ matrix.os == 'macos-latest' }}` (verify.yml L422), and no `canary_break.py` honesty proof, no `semgrep_no_mock`. | Add `ci/canary_break.py` (mutate ≥10 behaviours → CI must go red), wire `no_mock_gate` + `semgrep_no_mock`, justify/remove the macOS `continue-on-error`, add `ci/assert_no_skips.py` parity with kit. |
| R-02 | **Deterministic oracle library** `kairo.oracles.*`, each kill-proven, used by ≥1 gauntlet scenario (prompt 02, VERIFICATION_ORACLES) | **Partial.** `kairo-sidecar/sidecar/oracles.py` (437 L) has real `verify_docx`, `verify_xlsx` + `excel_libreoffice_recompute` (real recompute), `verify_pptx`, `verify_pdf`, `NetworkSnifferOracle` (scapy/psutil egress), `verify_screenshot_diff`. Oracles are Ed25519-signed at rest (`oracles.py.sig/.pub`, `sign_oracles.py`). | Add the **missing `docx_tracked_changes_readback`** oracle (see W-2). Confirm each wedge oracle ships a kill-proof fixture. Normalize namespace toward `kairo.oracles.*`. |
| R-03 | **Legal redline engine**: real python-docx tracked changes (`w:ins`/`w:del`) + clause diff; RAG-grounded added clauses; no hallucinated citations (prompt 08a, domain #4) | **Partial.** `legal_redline.py` (822 L): `detect_cuad_clauses`, `generate_redlines_for_clause`, `analyze_contract`, `compare_contracts`, `_apply_rule_based_redline`. Real tracked-changes writer exists in `adeu_bridge.py::_python_docx_tracked_fallback` (emits real `w:ins`/`w:del`, sets `w:trackRevisions`). | Wire redline → tracked-changes writer end-to-end; add `clause_coverage` + `no_hallucinated_citation` oracles; RAG-ground added clauses to a local clause library (turbovec) OR honestly refuse when no library (08a degradation bar). |
| R-04 | **Out-of-band injection defense**: taint labels + capability policy; tainted content can NEVER authorize a privileged action; ~4–5% attack band + adaptive attack reported (prompt 05, oracle `injection_block`) | **Partial.** In-band detection exists: `kairo/security/injection_guard.py::detect_injection` (NFKC, zero-width strip, entropy, base64), `phantom-core/src/prompt_injection_firewall.rs`, `sentinel.rs`, injection corpus fixtures. No evidence of an **out-of-band taint→capability reference monitor** gating privileged actions. | Add a deterministic reference monitor: taint-label perceived content, require explicit capability for privileged actions, deny grant from tainted-only input. Kill-proof: disable monitor → attack authorizes action. |
| R-05 | **Provenance: audit-log first (Ed25519 hash-chained), C2PA fast-follow** (prompt 06, DoD §8, oracle `audit_chain`/`c2pa_verify`) | **Partial.** `kernel/core/audit_log.py` (295 L) is a real hash chain (`prev_signature` covers content) BUT signs with **HMAC-SHA256** (symmetric session key), not **Ed25519** (publicly verifiable). `provenance_emit.py` emits traces. | Add an **Ed25519**-signed audit-log path (keychain key, never in repo) OR document HMAC as session-integrity + add an Ed25519 seal over the session digest. Add `audit_chain` oracle kill-proof (forge entry → chain breaks). C2PA remains fast-follow (G6) — do not claim until a doc-side verifier exists. |
| R-06 | **Air-gap SEALED build**: no network stack linked; `sealed_no_network` static gate; live egress oracle 0/0 (R3, prompt 02 air-gap oracle, oracle `airgap_egress`) | **Absent (seal) / Partial (runtime).** No `kairo-sealed` build profile, no `sealed_no_network.yml`, no sealed-symbol static scan (grep found none). Runtime egress detection exists via `NetworkSnifferOracle`. | Add a `sealed` build profile/marker + `ci/sealed_no_network` static scan for networking symbols in the sealed artifact. Add `ci/airgap_oracle.py` asserting 0 outbound for the redline flow; kill-proof: open a socket → red. |
| R-07 | **Clean-room provenance + license gates green**; every shipped source traces to ADR or BUNDLE dep; no AGPL/GPL/no-license in product (CLEANROOM_IP_PROTOCOL, DoD §11, `cleanroom_provenance.yml` + `license_gate.yml`) | **Partial.** `deny.toml` + cargo-deny license check present; `THIRD_PARTY_LICENSES.md` exists. But no `PROVENANCE:` headers on source, no `cleanroom_provenance` job, and the kit gate targets `src/**` while this repo's code lives in `phantom-core/src`, `kairo-sidecar/sidecar`, `kairo/`, `kernel/`. **PyMuPDF is a preinstalled/available lib — must confirm it is NOT in the shipped PDF path** (TECH_MANIFEST bans AGPL PyMuPDF). | Port `cleanroom_provenance.yml` + `license_gate.yml` with **repo-correct source globs**; add `PROVENANCE:` headers incrementally on wedge files; add `pip-licenses` AGPL/GPL fail-on; confirm PDF path uses Docling/pdfplumber/pypdf(ium)/pikepdf, not PyMuPDF. |
| R-08 | **Claim discipline**: only "reproducible signed zero-egress report + tamper-evident audit log"; label Real vs Experimental (CLAIM_DISCIPLINE, DoD §9/§12) | **Partial.** `STATUS.md` exists with labels; must audit wedge-relevant claims against the exact approved wording. | Verify STATUS.md + UI + any README claim uses approved wording; no "cryptographic proof no bytes ever leave". |
| R-09 | **Wedge gauntlet + acceptance** on real files, offline, signed (prompt 13) | **Partial.** Existing gauntlet workflows (`gui_gauntlet.yml`, `e2e_mock_ai_chaos_gauntlet.yml`, `scenarios.json`). | Add ≥3 legal-redline gauntlet scenarios (clean contract, PDF→Docling→redline, adversarial-hidden-clause) each asserted by a real oracle; wire into the wedge acceptance. |

### Cross-cutting note on CI path mismatch (blocking for R-07)
The kit's `cleanroom_provenance.yml` / `license_gate.yml` assume a single `src/` tree. This repo is
multi-tree (`phantom-core/src`, `kairo-sidecar/sidecar`, `kairo/`, `kernel/`, `mcp-servers/`). The ported
gates MUST use repo-correct globs or they will vacuously pass (a rigged gate — forbidden by prompt 01).

---

## 2. WEDGE-FIRST BUILD SEQUENCE (ordered; each step gated)

Order per Roadmap G2 (trust leg first) and prompt 06 v2 sequencing (audit-log first). Each step lists the
**exact oracle** that must pass, its **Definition-of-Done** anchor, the **CI gate(s)**, and the
**permissive tech** it uses (all confirmed BUNDLE-lane in `TECH_MANIFEST` / verified in
`research/REPO_VERIFICATION_2026-07-03.md`).

### Step 1 — De-rig the trust gates (prompt 01)  → *foundation, everything depends on it*
- **Do:** wire `no_mock_gate` (semgrep) + `assert_no_skips` + `canary_break.py`; remove/justify the macOS
  `continue-on-error`; ensure no `|| true` on any gate.
- **Oracle:** canary-break mutates ≥10 known behaviours → CI red on all 10; restore → green.
- **DoD:** §1 (kill-proven), §3 (no-skip), §4 (no-mock-in-prod).
- **CI gate:** `no_mock_gate`, `semgrep_no_mock`.
- **Tech:** semgrep (LGPL, **TOOL-lane / dev-only**, never shipped), gitleaks (dev-only).

### Step 2 — Deterministic oracle: `docx_tracked_changes_readback` (prompt 02 + 08a)
- **Do:** implement oracle that re-opens output `.docx` with python-docx and asserts (a) every intended
  change present as real `w:ins`/`w:del` revision with author+timestamp, (b) no unintended edits,
  (c) original text recoverable by rejecting changes.
- **Oracle:** `docx_tracked_changes_readback`; **kill-proof:** drop one revision / corrupt a run → fail.
- **DoD:** §1, §5.
- **CI gate:** runs under `no_mock_gate` (real fixture, no mock).
- **Tech:** **python-docx** (BSD-3, BUNDLE); LibreOffice-headless only if recompute needed (dev/runtime engine).

### Step 3 — Out-of-band injection defense reference monitor (prompt 05)
- **Do:** taint-label perceived doc content; deterministic capability policy; privileged action (apply
  redline / write file) requires a capability that tainted-only input cannot grant.
- **Oracle:** `injection_block` — injection corpus (multilingual + ≥1 adaptive) → every privileged action
  from tainted content blocked; **kill-proof:** disable monitor → attacks succeed. Report residual honestly.
- **DoD:** §1, §5, §6.
- **CI gate:** `no_mock_gate`; scenario in wedge gauntlet.
- **Tech:** clean-room from CaMeL/FIDES/Progent **ideas only** (STUDY→REIMPLEMENT, `CLEANROOM_IP_PROTOCOL`).
  Existing `injection_guard.py` (our code) retained as the second, model-assisted layer.

### Step 4 — Audit-log first: hash-chained + Ed25519 seal (prompt 06, audit-log-first)
- **Do:** every file-mutating redline action appends an entry to the hash-chained log; add an **Ed25519**
  signature (local keychain key, never in repo) over the entry/session digest.
- **Oracle:** `audit_chain` — chain continuous, `verify_chain()` true; **kill-proof:** forge an entry →
  chain breaks / signature fails.
- **DoD:** §8 (trust artifacts).
- **CI gate:** `no_mock_gate`; part of wedge acceptance.
- **Tech:** Python `cryptography` / stdlib `hmac`+`hashlib` (already used); Ed25519 via `cryptography`
  (BSD/Apache, BUNDLE). **C2PA deferred** (G6) — no claim until a third-party doc-side verifier exists.

### Step 5 — Anchor perception + CUA verifier — *only the thin slice the wedge needs* (prompts 03/04)
- **Do:** for the offline `.docx` redline, perception = read the document text/structure (no live UI CUA
  needed for the v0 file-in/file-out slice). Universal-Verifier gates the "apply redline" action so a
  receipt is emitted ONLY for a verified action (DoD §8, prompt 06 acceptance).
- **Oracle:** verifier rewards only a correct redline trajectory; **kill-proof:** reward a failed run → fail.
- **DoD:** §1, §5.
- **Tech:** our code (clean-room from Fara/CUWM ideas). Vision legs (supervision/olmocr/OmniParser) NOT
  required for the file-only wedge; deferred to Phase B.

### Step 6 — Legal-redline domain, made Real (prompt 08a)
- **Do:** redline a real contract `.docx` → real tracked changes; added clauses RAG-grounded to a local
  clause library; honest refusal when no library present (never invent terms).
- **Oracles:** `docx_tracked_changes_readback` (Step 2) + `clause_coverage` + `no_hallucinated_citation`;
  **kill-proofs:** remove a required clause → fail; inject a fake citation → fail.
- **DoD:** §1, §5, §6, §7 (honest degradation), §8, §9 (label Real only when practitioner gate passes).
- **CI gate:** `no_mock_gate`, `license_gate`, `cleanroom_provenance`; ≥3 gauntlet scenarios.
- **Tech:** **python-docx** (BSD); **turbovec** (MIT) for local clause RAG; **Docling** (MIT) +
  **pdfplumber** (MIT) + **pypdfium2** (BSD) + **pikepdf** (MPL, unmodified dep) for the PDF→text
  legacy-contract path (`PDF_DOMAIN_STACK`); **NO PyMuPDF** (AGPL, banned).

### Step 7 — Air-gap seal (R3, `sealed_no_network`)
- **Do:** define a `sealed` build/run profile with no network client linked; add static scan for
  networking symbols; run the redline flow under the egress oracle.
- **Oracles:** `airgap_egress` (0 outbound in sealed mode; LAN stays in subnet) + `sealed_binary_scan`;
  **kill-proof:** a build that opens a socket → gate red.
- **DoD:** §8 (air-gap), §12 (claim discipline).
- **CI gate:** `sealed_no_network`.
- **Tech:** our code; `NetworkSnifferOracle` (existing, scapy/psutil) as the runtime egress observer.

### Step 8 — Clean-room provenance + license gates (CLEANROOM_IP_PROTOCOL, R-07)
- **Do:** port `cleanroom_provenance.yml` + `license_gate.yml` with **repo-correct source globs**; add
  `PROVENANCE:` headers to wedge files; confirm no AGPL/GPL/no-license in the shipped wedge path.
- **Oracle/gate:** `cleanroom_provenance` + `license_gate` green; provenance header present on every wedge
  source file; pip/cargo license scan passes.
- **DoD:** §11.
- **Tech:** pip-licenses / cargo-deny / jscpd (all dev-only, TOOL-lane).

### Step 9 — Wedge gauntlet + acceptance (prompt 13, slice)
- **Do:** ≥3 legal-redline scenarios (clean, PDF→Docling→redline, adversarial hidden clause) each asserted
  by a real oracle; run offline; emit signed zero-egress report + audit entry; sign the wedge acceptance.
- **Oracle/EXIT:** wedge gauntlet green, zero skips; canary-break still red on injected breaks; all four
  ship gates green (`no_mock_gate`, `license_gate`, `cleanroom_provenance`, `sealed_no_network`).
- **DoD:** production-ready declaration criteria (wedge scope only).

---

## 3. Permissive-tech confirmation (per step)
All shipped-path libraries are BUNDLE-lane in `specs/TECH_MANIFEST.md` and verified real+permissive in
`research/REPO_VERIFICATION_2026-07-03.md` (verified in-env 2026-07-03; star magnitudes intentionally
ignored):
- **python-docx** — BSD-3 — tracked-changes engine + read-back oracle.
- **turbovec** — MIT (verified 07-03) — on-device clause RAG.
- **Docling** — MIT (IBM, verified 07-03) — PDF structure for legacy contracts.
- **pdfplumber** — MIT (verified 07-03) — deterministic PDF coord/table oracle.
- **pypdf** — BSD-3 / **pypdfium2** — BSD-3 (PDFium) — PDF manipulate/render/extract.
- **pikepdf** — MPL-2.0 — ship as **unmodified dep** only (content edit / redaction).
- **cryptography** — Apache-2.0/BSD — Ed25519 audit seal.
- **DEV/CI-only (never shipped):** semgrep (LGPL), gitleaks, cargo-deny, pip-licenses, jscpd, LibreOffice
  (runtime engine, honest-degradation gated).
- **BANNED (must stay out of shipped path):** PyMuPDF / pymupdf4llm / pdfmux (AGPL), marker (GPL),
  pdf2image/poppler (GPL). Note: PyMuPDF is present in the sandbox toolchain — R-07 must confirm it is not
  imported on any shipped redline/PDF path.

---

## 4. Governing rules honored throughout
- NO MOCK / NO FAKE GREEN — every step writes the oracle first, proves it fails on a break, then implements.
- Additive / minimal-diff — preserve everything already working; never weaken a frozen oracle.
- Clean-room — copy ideas, not code; STUDY→REIMPLEMENT for AGPL/no-license; attribution for BUNDLE deps.
- Local-first / air-gap — default path fully offline; perceived content is TAINTED data, never instructions.
- Claim discipline — "reproducible, signed zero-egress report + tamper-evident audit log"; never
  "cryptographic proof no bytes ever leave"; label domains Real vs Experimental honestly.

## 5. First executable step
**Step 1 (de-rig trust gates)** — it is independently buildable, unblocks every later oracle, and its own
canary-break oracle proves it is honest. Begin here.
