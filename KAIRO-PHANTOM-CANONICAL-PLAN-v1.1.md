# Kairo-Phantom — Canonical Plan & Roadmap (v1.1, red-teamed)

**Version:** 1.1 · **Date:** 10 July 2026 · **Supersedes:** v1.0 and the 5 input drafts
**What changed in v1.1:** integrated an external technical red-team (`research.md`). ~15 overclaims tightened. The strategy is unchanged; the *claims* are now defensible. See `CHANGELOG-v1.1.md` for the point-by-point diff.
**Stage:** Code-complete · pre-launch · solo founder · **0 users · 0 revenue.**
**Discipline:** Real / Experimental / None yet on every capability. Every number links to a reproducible command; every regulatory claim links to a primary source; every competitor fact must be independently verified before it goes in a deck.

> ⚠️ **Provenance caveat (new in v1.1):** specific competitor facts imported from `research.md` — e.g. AGA patent application **19/433,835 filed 28 Dec 2025**, founder name, product URLs — originate from an uploaded document and are **untrusted until independently verified.** Treat them as leads, not facts. Verify from primary sources (USPTO Patent Center, the vendor's own site) before citing anywhere.

---

## PART 0 — VERDICT ON THE INPUT FILES

Two tiers, unchanged from v1.0:

- **Tier 1 (spine):** `FINAL-PLAN-ROADMAP.md` (strongest overall) + `FINAL-PLAN.md` (strongest GTM). 
- **Tier 2 (tactics only, stale facts):** the 3 Fable5 files — mine for the "wrap don't build" tactic, demo structure, and OTel wrapper; **discard** their dead "Aug 2 2026" deadline and "0 competitors" claim.
- **New input (v1.1):** `research.md` — an external red-team. **Adopted almost in full.** It does not change the strategy; it removes overclaims that would have damaged credibility with a technical assessor.

---

## PART 1 — THE HONEST VERDICT ON THE COMPANY

- **The pieces exist and are commoditizing.** Signed, hash-chained, offline-verifiable receipts are a `pip install`.
- **AGA is architecturally close** — separate governance process, sealed policy, Ed25519 hash-linked receipts, Merkle evidence, portable bundles, an independent offline verifier, patent-pending. This **kills the "only one" story** permanently.
- **But a competitor existing validates the *technical thesis*, not paying demand.** Corrected in v1.1: AGA proves *credible builders see the same gap.* It does **not** prove customers will pay. OPAQUE/Kiteworks are stronger *demand* signals (funding, enterprise distribution); AGA is the strongest *architectural* signal. Customer willingness to pay for Kairo remains **unvalidated** — that is exactly what the 90 days must test.
- **The unclaimed, defensible intersection:** *decision evidence → independently-observed desktop execution → verified application/artifact state → scoped network-boundary evidence → offline-verifiable pack.* This is **outcome evidence**, not merely decision evidence. It is a real product difference — **if made Real.** Today it is **Experimental.**

<callout>
**Verdict (unchanged): Continue — as a 90-day PROOF sprint, not a feature sprint.** Worth it iff within 90 days you can (1) make the desktop causal chain real on pinned hardware; (2) make scoped zero-egress evidence real with an independent network witness; (3) get one external party to verify a pack; (4) get one buyer to pay. If assessors do NOT value the extra desktop + boundary evidence, AGA hasn't just validated the market — it has shown Kairo is building a layer customers don't need. **That is the question the sprint answers.**
</callout>

---

## PART 2 — VALIDATED COMPETITIVE REALITY (corrected)

**"0 competitors" is false.** The correct framing of the nearest rival:

- **Attested Intelligence (AGA)** — nearest architecture. **Corrected:** AGA is **not** simple self-attestation — a *separate governance gateway* (not the subject agent) signs the decision receipts, which is materially stronger than an agent signing its own logs. AGA's public enforcement point is primarily a **gateway / MCP tool-call boundary**. What is **not** publicly demonstrated by AGA: binding that decision to a Win32 UIA / AT-SPI event, an application state transition, a specific artifact revision, an independent readback, or a host-plus-network observation interval. **That gap — decision evidence vs outcome evidence — is Kairo's opening.** #1 threat; run FTO now.
- **OPAQUE** — hardware-attested confidential agents; stronger *commercial* validation. Don't fight them in confidential cloud.
- **Microsoft Agent Governance Toolkit — CORRECTED.** Do **not** say "Microsoft is cloud-only / can't work offline." Microsoft's open-source AGT includes **offline-verifiable receipts.** Do not conflate four different things: (a) MS AGT (OSS, offline receipts), (b) Windows native agent audit, (c) Purview enterprise collection (cloud), (d) cloud-hosted MS agent products. **The real opportunity:** "Microsoft provides governance evidence; Kairo independently appraises desktop outcome + network-boundary evidence across vendors" — not "Microsoft can't reach the enclave."
- **Governance-adjacent:** Kiteworks, DeepInspect, Prefactor, Credo AI, Holistic AI.
- **Receipt commodity layer (adopt, don't fight):** Asqav (post-quantum, IETF draft), CertNode, Signet, AEGIS HIVE, NotaryOS, Agent Receipts, VAP.

<callout>
⚠️ **VERIFY before citing:** Hexr, AgentOS, H33, Apotheon THEMIS (appeared in only one pass) — and now the AGA specifics from `research.md`. Also **corrected:** do NOT claim AGA is "funded" or "US-centric / uninterested in Europe" — there is no verified evidence of AGA's funding, revenue, team size, or geographic intent.
</callout>

**Corrected moat statement:** the crypto is not the moat, and **"rivals have gaps by construction" is too absolute** — wrappers *can* add eBPF/EDR/ETW/WFP/hypervisor/confidential-computing/OS-audit observation. The precise, defensible claim is:

> **"Gateway-only evidence cannot establish downstream desktop state without additional observers."**

Kairo's defensibility therefore comes from **execution speed, assessor adoption, application adapters, conformance vectors, and the failure corpus** — NOT from assumed architectural impossibility.

---

## PART 3 — THE ONE STRATEGIC DECISION: BEACHHEAD (unchanged recommendation)

Plan A (EU-regulated + assurance firms) vs Plan B (US CMMC / defense). **Recommendation stands:** build the evidence model once, **lead outreach with Plan A** (reachable for a solo India-based founder), treat **Plan B as the second track that unlocks with a US co-founder/entity**. **SBIR decision (v1.2): if the company is India-owned and not >=51% owned and controlled by US citizens/permanent residents, SBIR is CLOSED for now** — document it once and remove it from the weekly critical path. Do NOT design the cap table around a grant, and do NOT recruit a nominal US co-founder to manufacture eligibility. Revisit only if the genuine future structure independently meets the rules. Resolve funding eligibility (Gate G0) in Week 1.

**Corrected — do NOT build "one giant multi-regulator compliance profile"** (shallow + legally misleading). Build **one evidence model + separate published mappings:**

```
KSEE core evidence model
├── CMMC / NIST 800-171 mapping
├── DORA mapping
├── EU AI Act (Art. 12/19/26) mapping
├── ISO 42001 mapping
└── Customer policy mapping
```

Never claim "software = compliance." Only: "evidence mapped to control X; an assessor evaluates sufficiency."

---

## PART 4 — CORRECTED REGULATORY REALITY (use exactly this language)

- **EU AI Act:** Digital Omnibus postpones most Annex III high-risk obligations, incl. **Article 12 record-keeping, to Dec 2, 2027**; embedded-product AI to Aug 2028. The **"Aug 2 2026 LIVE"** framing is dead. EU = land-early, harvest-later. **VERIFY** the final Official Journal text before quoting a date.
- **Article 12 is a *provider* design-time obligation**, not deployer paperwork.
- **Penalties:** €35M/7% = *prohibited practices*; high-risk breaches fall in the lower **€15M/3%** tier. Don't quote €35M for Art. 12.
- **CMMC — CORRECTED (do not overclaim the deadline):** *"CMMC Phase 2 begins on 10 November 2026, when Level 2 C3PAO requirements begin appearing more systematically in applicable solicitations. The required status and assessment type remain contract-dependent during the phased rollout."* Do **not** say "all assessments begin Nov 10 / certification required before every award."
- **API-log sufficiency — CORRECTED (not a universal published rule):** *"Conventional API logs may be insufficient when they don't bind actions to an accountable principal, affected artifact, and resulting state."* Do not say "endpoint/API logs are explicitly insufficient."
- **FIPS:** Ed25519 approved under FIPS 186-5; the gap is *module* validation only (wolfCrypt — **VERIFY** CMVP status; needs commercial license). Never say "FIPS validated" while "submitted."

**Permitted:** "Evidence mapped to Article 12/19/26." · "Supports an assessor's evaluation." · "Produces tamper-evident runtime evidence."
**Prohibited:** "EU AI Act certified." · "Regulator approved." · "Guarantees compliance." · "FIPS validated." · "Zero bytes left the entire machine."

---

## PART 5 — FINAL PRODUCT DEFINITION (corrected claims)

<callout>
**Category sentence (corrected to present tense honesty):** Kairo-Phantom **is building** the independent **evidence & conformance layer for sovereign desktop agents** — *designed to* bind human authority, policy, observed computer actions, verified results, and scoped network evidence into a pack another party can verify offline. *(Remove "is building" / "designed to" only after the real-hardware and dual-witness gates pass.)*
**Website headline:** *Prove what the agent did — and where the data did not go.*
</callout>

**Four surfaces:**
- **A. Kairo Verifier — open & free.** Standalone, deterministic, offline. Never outputs a bare `VALID`; outputs a **sufficiency report** (see Part 6). **Corrected:** today it verifies **Kairo native** evidence. Cross-vendor is roadmap: say *"designed to normalize other platforms' evidence into the KSEE draft profile,"* not *"can also verify other platforms."*
- **B. Kairo Sensors — commercial.** Host observers + human approval + external network witness.
- **C. Kairo Assessor Kit — commercial channel.** Nonce-bound conformance challenges; scoped reports.
- **D. KSEE Evidence Profiles — open-core, DRAFT.** **Corrected:** call it the **"KSEE draft evidence profile,"** never "the open standard for sovereign AI execution." A schema + CLI is not a standard (see Part 7 legitimacy checklist).

**"Wrap, don't build":** llama.cpp (MIT) planner, olmOCR (Apache-2.0) readback oracle, Goose/browser-use (MIT) actuation. Never static-link Skyvern/Chunkr (AGPL), claurst (GPL), Semgrep (LGPL). API/IPC/stdio boundary only.

---

## PART 6 — THE MOAT & NET-NEW INVENTIONS (corrected wording + ship order)

1. **Canary-in-the-Receipt** *(days).* **Corrected claim:** a periodic canary proves the control **operated at the tested moments**, not "was armed continuously through every untested interval." Log tested-moment coverage explicitly.
2. **Delegation-Chain Receipts** *(~2 wks).* Human signs scope grant via WebAuthn/FIDO2; out-of-scope actions **fail closed at the UI-action level.** Fail-closed permissions are the *primary* protection (stronger than pattern-based injection detection).
3. **Desktop Causal Continuity Chain / Gap-Proof** *(~2 wks).* Typed graph `MANDATE→POLICY→APPROVAL→REQUEST→OS-OBSERVATION→APP-DELTA→READBACK→ARTIFACT`; missing edges → explicit `EVIDENCE_GAP` nodes. **Corrected framing:** the durable claim is *"gateway-only evidence cannot establish downstream desktop state without these observers,"* not *"competitors can't copy this without a rewrite."*
4. **Host + External Network Witness (Zero-Egress Evidence) — REWRITTEN.** **The most important correction in v1.1.** A TPM is **NOT** a network witness. Correct architecture:
   1. **TPM** — establishes *measured platform state* (boot/PCRs/hw-bound key). **Optional corroboration, not the egress witness.**
   2. **Host sensor** — attributes network behavior to processes/interfaces (eBPF/WFP/ETW).
   3. **External witness** — independently observes traffic across *specified physical paths*.
   4. **Canaries** — prove the observers are active.
   5. **Coverage declaration** — states what was and was NOT observed (Wi-Fi/Bluetooth/cellular/USB-net/2nd NIC/firmware/covert channels).
   **Required claim wording:** *"No outbound packet was observed across the declared and tested interfaces during the nonce-bound interval; all required canaries were detected; unobserved channels are listed."* **Never:** *"the second device / TPM proves no data left the machine."*
5. **Evidence & State-Transition Replay — RENAMED** *(months, north star).* **Corrected:** do NOT promise "deterministic / bit-identical" agent replay. Promise replay of *evidence and state transitions*.

**Verifier output must always be a sufficiency report, never `VALID`:**
```
Receipt integrity:               PASS
Signer provenance:               PASS
Policy binding:                  PASS
Desktop action observation:      PASS
Artifact-state verification:     PASS
Host network observation:        PASS
External witness corroboration:  INCOMPLETE
Wi-Fi interface:                 NOT OBSERVED
Bluetooth:                       DISABLED, NOT ATTESTED
Firmware channels:               OUT OF SCOPE
Overall evidence level:          KSEE-L2
```

**Cross-vendor surfaces (roadmap):** read-only adapters that *normalize* Microsoft AGT / AGA / Asqav-SCITT / OTel-MCP evidence into KSEE — each adapter explains what the source proves and what remains missing; it does **not** imply endorsement.

---

## PART 7 — MAKING KSEE LEGITIMATE (new, per red-team)

A free verifier does **not** create a standard. Before calling KSEE anything beyond "draft," you need: ≥2 independent evidence producers; a 2nd verifier implementation; public positive + negative conformance vectors; a stable versioning/IPR process; an assurance practitioner who uses it; a concrete interop event; standards-community participation. **Assessor co-design, not announce-then-ask:** draft evidence questions → give 3 assessors sample packs → mark sufficient/insufficient/not-relevant → revise → credit reviewers → publish draft → get 2 producers before v1.0.

---

## PART 8 — THE KILLER DEMO (corrected)

Single unedited take, stock Win11, published spec. ~4–5 min:
1. **Seal:** `KAIRO_SEALED=1`; **host + external network witness** at 0 observed egress; TPM quote shown **as platform-state corroboration only**; run canaries → confirm observers active.
2. **Delegate:** human signs scope grant via security key; grant hash enters the chain.
3. **Work + attack:** agent redlines via ghost-typing; hidden injection blocked → enters receipt; 2nd-file attempt **fails closed** (fail-closed permission, not just pattern match).
4. **Assess:** receipt crosses by USB to the assessor's network-less laptop; verifier prints the **sufficiency report** (not `VALID`), incl. observed + NOT-observed channels.
5. **Tamper:** one byte edited → `FAIL: chain broken at entry #6`.
6. **Contrast:** run the verifier against a **gateway-only** bundle (Mode A) → shows what decision evidence can and cannot support.

**Record it working before showing it.**

---

## PART 9 — 90-DAY PROOF SPRINT = THE AGA RESPONSE PLAN

### Days 1–7 — Correct, verify, freeze
- [ ] Resolve **funding eligibility & company structure** (Gate G0): SBIR eligible now, OR SBIR explicitly excluded + a replacement non-dilutive/revenue funding spine chosen.
- [ ] **Claims correction pass:** remove "Injection-safe"; fix "third-party-verifiable" wording; publish **SKIPS.md** (all 7); separate TPM from egress; rename deterministic replay; remove the current cross-vendor-verifier claim. *(This whole pass is loop `T0` — oracle-gated.)*
- [ ] **Competitive verification (loop `T1`):** clone/run AGA's public demo; verify an AGA sample bundle with AGA's own verifier; document exactly what it proves; note any gateway-bypass path — **responsible-disclosure discipline, no unauthorized probing.**
- [ ] **FTO:** retrieve patent 19/433,835 + prosecution record; counsel claim-chart; prior-art search (in-toto, SCITT, RATS, tamper-evident logs, reference monitors, remote attestation, receipt chains, policy gateways); **freeze all public novelty/"patentable" claims until reviewed.**
- [ ] Relicense trust stack MIT → Apache-2.0; profiles CC-BY-4.0.
- [ ] Draft **KSEE core evidence model v0.0.1** + the 5 mappings.
- [ ] Script the killer demo.

### Days 8–30 — Prove the primitive + comparative evidence test
- [ ] **Record the single-take demo on real Win11** (Gate G1).
- [ ] **Comparative evidence test (loop `T2`) — the highest-value experiment:** run one synthetic workflow twice — **Mode A** (gateway receipt only: identity/request/policy/allow-deny/tool-result) vs **Mode B** (Kairo full: + OS action, app pre/post state, independent readback, artifact hash, host + external network observation, known gaps). Give both packs to assessors **blind**; ask: which would you rely on? what decision could it support? what's still insufficient? would extra evidence change deployment approval? **would you pay?**
- [ ] Ship **Invention 2 (Delegation-Chain)**; reach 100 pinned runs.
- [ ] Publish **KSEE draft v0.1** after assessor feedback + the free **native** verifier (reproducible build + checksum + SBOM).
- [ ] File SPC + Z Fellows. (SBIR only if genuinely eligible — otherwise excluded per G0.)

### Days 31–60 — Convert proof to pull
- [ ] Ship **Invention 3 (Continuity/Gap-Proof).**
- [ ] Publish **"Decision evidence vs outcome evidence"** as a technical paper — **not an AGA attack.**
- [ ] Ship read-only **Microsoft AGT adapter**; **AGA adapter** if technically + legally appropriate.
- [ ] Split the benchmark into **BoundaryBench** (network/offline claims) + **EvidenceBench** (completeness/verifiability). **AGA/Microsoft belong in EvidenceBench; local "air-gapped" tools in BoundaryBench.** Don't test AGA for leakage unless a deployment claims air-gap.
- [ ] **10 discovery calls + at least 1 paid/contractually budgeted pilot** (budget owner, price, start date, workflow, decision date). LOIs are a supporting metric, NOT the market-proof bar; 1 external verifier reproduction.
- [ ] Recruit systems-security co-founder candidates.

### Days 61–90 — Category credibility
- [ ] Demonstrate one **KSEE-L3** session with host + external network witnesses on published hardware (Pi witness fallback).
- [ ] Publish comparison methodology + sample synthetic evidence.
- [ ] Obtain a **written assessor statement** on where Kairo's additions are useful.
- [ ] Convert first pilot to a paid contract; **decide whether KSEE conformance has real pull.**

---

## PART 10 — DECISION GATES

| Gate | When | Pass condition | If it fails |
|---|---|---|---|
| G0 — Funding eligibility & structure | Day 7 | SBIR eligible now OR excluded + replacement funding spine chosen (decision note committed) | Private non-dilutive + revenue-first; revisit SBIR only if structure independently qualifies |
| G1 — Demo on real hardware | Day 30 | Single-take Win11; ≥99/100 readback; 100/100 tamper; 100% required canaries; 0 silent gaps | Narrow to ONE deterministic task; stop external work |
| G2 — Assessor signal | Day 60 | ≥1 assessor prefers Mode B and says why; ≥3 reviewing | Re-examine the whole thesis — this is the make/break gate |
| G3 — Market proof | Day 90 | >=1 paid/budgeted pilot + >=1 external verifier repro + >=3 qualified workflows (LOIs supporting only) | Preserve as open infra; sharpen the commercial app |
| G4 — Bus factor | Day 90 | Co-founder OR documented succession + 2 verifier maintainers | Blocking risk in any raise |

---

## PART 11 — STOP-DOING LIST

- Capability/Operator-parity racing; new domains before a paid pilot; personalization.
- New receipt envelopes; post-quantum marketing races.
- "0 competitors," "only one," "injection-safe," "FIPS validated," "zero bytes left the machine," "deterministic replay," "rivals can't copy this," "AGA is funded/US-only," the dead Aug-2026 deadline.
- A single giant "multi-regulator compliance profile."
- Calling KSEE "the standard" before the legitimacy checklist is met.
- One sensational "phone-home" leaderboard (split into BoundaryBench + EvidenceBench).
- Unauthorized probing of competitors; public teardowns without permission + reproducible methodology.
- Grant work beyond 20% of the week.

---

## PART 12 — TOP RISKS & FIXES

| Risk | Fix |
|---|---|
| AGA patent / near-identical architecture | FTO + prior-art now; differentiate on outcome evidence, not "two processes + offline receipts" |
| Desktop path Experimental / flaky | 100-run pinned gate; narrow to one task if it fails |
| "Zero egress" overstated | Host + external witness; publish interface inventory, canary coverage, blind spots; TPM ≠ witness |
| Assessor demand unproven | The Mode A/B blind test (T2) is the whole company thesis — run it early |
| Solo bus factor | Co-founder hunt; assurance channel first; reproducible builds + 2-person custody as features |
| Microsoft/OS | Don't claim "MS can't work offline"; be the cross-vendor appraiser that consumes MS evidence |
| Receipt commoditization | Moat above the signature: outcome evidence + assessor adoption + failure corpus + adapters |
| Regulatory whiplash | Evidence model + separate mappings; never single-deadline messaging |
| Immutable evidence vs privacy law | Encrypt payloads; key deletion/crypto-erasure; minimize data; selective disclosure |
| License ambiguity | Isolate GPL; API/IPC boundary for AGPL; Apache-2.0 core; clean-room records |

---

## PART 13 — THE FOUR THINGS THAT DECIDE EVERYTHING

> **1. Make the desktop causal chain real on hardware.**
> **2. Make scoped zero-egress evidence real with an independent network witness.**
> **3. Make another party verify a pack — with no trust in you.**
> **4. Make one buyer pay.**

And the one sentence the whole sprint exists to validate:

> **Kairo adds independently-observed desktop outcome and scoped network-boundary evidence above the governance receipts AGA and Microsoft already produce — and an assessor prefers it and a buyer pays.**

If that holds, AGA is validation and an interoperability opportunity. If it doesn't, AGA has shown you were building a layer customers don't need — and you'll know honestly, in 90 days, which one it is.

---
---

## v1.2 addendum — corrected execution order (operational red-team, 11 Jul 2026)

The strategy is unchanged. The **order** is corrected to put cheap truth and market falsification *before* expensive hardware/adapter work:

- **Phase 0 — Truth:** T0 (complete CLAIMS + SKIPS; the loop stays RED until the 7 real skips are filled) → T1 (competitor verification + FTO) → freeze public novelty claims.
- **Phase 1 — Desktop outcome:** T3 (100-run pinned desktop path on real hardware) + integrate REAL cryptographic evidence + artifact-state verification → gate **G1**.
- **Phase 2 — Market falsification:** build Mode A vs Mode B evidence packs → T2 blind assessor test → written sufficiency feedback → gate **G2** (make/break). *This comes before TPM and broad adapters.*
- **Phase 3 — Boundary evidence:** T6 (host + external network witness) → publish coverage declaration → BoundaryBench internally.
- **Phase 4 — Interoperability:** T4 (Microsoft/AGA read-only adapters) → second evidence producer → external verifier reproduction.
- **Phase 5 — Profile:** T5 (KSEE assessor co-design) → draft v0.1 only after feedback → never call it a standard.

**Verifier honesty (v1.2):** the loop kit's coverage script was renamed `score_evidence_manifest.py` — it is an *illustrative coverage evaluator*, not a cryptographic verifier. Real receipt verification stays in `tools/verify_receipts_external.py`. The full independent KSEE verifier is future work (Part 7).

*End of canonical plan (v1.1 strategy + v1.2 operational corrections). Founder-only unknowns: funding eligibility (Day 7) and the real-hardware demo (Day 30). Everything else is execution — now run as loops, not one-shot prompts (see `/loop-engineering/`).*
