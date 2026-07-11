# T1 — Competitor Verification + FTO + Frozen Novelty Claims

**Date:** 11 July 2026  
**Author:** Kartik Hulmukh (solo founder)  
**Status:** Verification memo complete. FTO/patentability clearance scoped to counsel (licensed-attorney judgment).  
**Method:** Every competitor fact verified from PRIMARY sources (vendor sites, USPTO records, GitHub repos, IETF RFCs). `research-redteam-source.md` treated as UNVERIFIED until confirmed — all facts below carry their primary-source citation.

---

## 1. Attested Intelligence (AGA) — Primary-Source Verification

### 1.1 Company identity

| Fact | Value | Primary source |
|------|-------|----------------|
| Legal entity | Attested Intelligence Holdings LLC | NCCoE submission PDF (attestedintelligence.com/documents/nccoe-ai-agent-identity-attested-intelligence.pdf, dated March 4, 2026) |
| State of formation | Illinois | Illinois File No. 17233815 (cited in same NCCoE PDF) |
| Registered address | 333 W Bethalto Dr, Ste C #113, Bethalto, IL 62010 | USPTO Trademark Serial No. 99677085 (TrademarkElite record) |
| Founder | Jack Brennan | attestedintelligence.com/about (fetched 2026-07-11) |
| Trademark | "ATTESTED INTELLIGENCE" — Serial 99677085, filed March 2, 2026 | USPTO via TrademarkElite (trademarkelite.com/trademark/trademark-detail/99677085/ATTESTED-INTELLIGENCE) |
| Trademark status | "Response after non-final action entered" (as of July 1, 2026) | Same |

**Verification note:** The NCCoE PDF confirms the Illinois LLC formation (File No. 17233815) and the USPTO trademark filing. The founder identity (Jack Brennan) is confirmed from the vendor's own About page and the SSRN preprint (doi.org/10.2139/ssrn.6866422, author: Jack Brennan). The research-redteam-source.md claim of "Jack Brennan as founder" is CONFIRMED from primary sources.

**Namesake caution:** Jack Brennan (AGA founder, per SSRN preprint and attestedintelligence.com/about) is a different person from John Brennan, former CIA Director — do not conflate.

### 1.2 Patent application 19/433,835

**Independence classification:** The patent application number, title, filing date, and 3-independent/20-total claim breakdown are **AGA self-disclosure** (their website + their NCCoE RFI submission), NOT independently verifiable until USPTO publication. Under 35 U.S.C. 122(b), non-provisional utility applications publish at 18 months from filing — filed Dec 28, 2025, so publication is expected ~June 2027 unless a non-publication request was made. The USPTO Patent Center (patentscenter.uspto.gov) returned no public record when queried on July 11, 2026, consistent with pre-publication status.

**Independently verifiable NOW (via USPTO public records):**

| Artifact | Value | Independent source |
|----------|-------|--------------------|
| USPTO Trademark | "ATTESTED INTELLIGENCE" — Serial 99677085, filed March 2, 2026 | USPTO TSDR (via TrademarkElite: trademarkelite.com/trademark/trademark-detail/99677085/ATTESTED-INTELLIGENCE) |
| Trademark status | "Response after non-final action entered" (as of July 1, 2026) | Same |
| Trademark applicant address | 333 W Bethalto Dr, Ste C #113, Bethalto, IL 62010 | Same |
| Illinois SOS entity | Attested Intelligence Holdings LLC — File No. 17233815 | Illinois Secretary of State (cited in NCCoE submission PDF, independently checkable via Illinois SOS business search) |

**AGA self-disclosure (NOT independently verifiable until ~June 2027):**

| Fact | Value | Source (AGA self-disclosure) |
|------|-------|------------------------------|
| Application number | USPTO 19/433,835 | attestedintelligence.com/patent (fetched 2026-07-11) |
| Filing date | December 28, 2025 | Same |
| Title | "Systems and Methods for Generating and Enforcing Attested Governance Artifacts" | Same; also attestedintelligence.com/about |
| Status | Patent Pending | Same; also attestedintelligence.com/trust |
| Independent claims | 3 independent claims, 20 total claims | attestedintelligence.com/patent (web search summary) |
| Claim 1 | Runtime Integrity Enforcement: sealed policy artifacts, continuous runtime integrity measurements, automatic enforcement on drift, signed enforcement receipts | Same |
| Claim 2 | Privacy-Preserving Disclosure: claims taxonomy with sensitivity levels, iterative substitution to lower-sensitivity permissible equivalents, signed substitution receipts, chain-linked disclosure audit trail | Same |
| Claim 3 | Continuity Chain System: append-only leaf hashes of structural metadata (no payload), tamper-evident linking, periodic Merkle checkpoints anchored to immutable storage, offline evidence bundle verification | Same |
| Cryptographic primitives | Ed25519, SHA-256, ML-DSA-65, JCS-lineage (RFC 8785 JSON canonicalization) | Same; also npm package description |
| Hardware requirements | No TEEs, ZK proofs, or specialized hardware required; TEE attestation optional as input | Same |

**USPTO Patent Center access note:** The USPTO Patent Center (patentscenter.uspto.gov) requires a registered account for full application status and transaction history. The application number 19/433,835 is confirmed from the vendor's own patent page and multiple cross-references (About, Trust, NIST submission). The USPTO direct lookup returned empty content on July 11, 2026 — consistent with pre-publication status (filed Dec 28, 2025; 18-month publication expected ~June 2027). **The patent status "Pending" and all claim details are AGA self-disclosure; the USPTO docket must be verified by counsel via Patent Center access once the application publishes.**

### 1.3 Architecture (from primary sources)

| Capability | Confirmed from | Details |
|-----------|---------------|---------|
| Two-process key separation | attestedintelligence.com/technology, attestedintelligence.com/about | Gateway holds signing keys; governed agent has no keys. Gateway is the only path to external resources. |
| Sealed policy artifacts | attestedintelligence.com/technology | Policy sealed with Ed25519 signature; post-seal modification breaks signature. |
| Runtime measurement | attestedintelligence.com/technology | Continuous sampling at configurable cadence (100ms–5s); sha256 of exe_image, config_manifest, memory_region_samples. |
| Signed receipts | attestedintelligence.com/technology | Each governance decision recorded as a signed receipt; Ed25519-SHA256-JCS. |
| Merkle receipt chain | attestedintelligence.com/technology, attestedintelligence.com/patent | Append-only hash-linked chain; periodic Merkle checkpoints. |
| Offline verification | attestedintelligence.com/verify, GitHub repo | Browser-based verifier; no AGA imports; client-side only. Six verifier configurations across JS, Go, Python. |
| MCP server | npm @attested-intelligence/aga-mcp-server, GitHub attestedintelligence/aga-mcp-server | TypeScript MCP server over stdio; npx runnable. |
| Cross-stack conformance | GitHub repo, npm | 57 cross-stack conformance cases; 384 automated tests. |
| Reference implementation | GitHub attestedintelligence/aga-mcp-server (v3.0.0, June 8, 2026) | TypeScript 66%, JavaScript 19%, Go 8%, Python 7%. |
| NIST submissions | attestedintelligence.com/diligence | NIST CAISI RFI response (Docket NIST-2025-0035, March 4, 2026); NCCoE concept paper response. |

**What AGA does NOT publicly demonstrate (no public evidence found as of July 2026 — absence of public evidence, not proof of absence):**

- No public demonstration of binding governance decisions to Win32 UI Automation events
- No public demonstration of binding to AT-SPI2 events
- No public demonstration of binding to Word/Excel/LibreOffice state transitions
- No public demonstration of binding to a specific resulting document revision
- No public demonstration of independent document readback
- No public demonstration of host-plus-network observation interval
- No public demonstration of desktop outcome evidence (what actually changed on the machine)

**This is the key competitive distinction.** AGA produces decision evidence at the gateway/tool boundary. Kairo's proposed differentiation is to extend that to independently observed desktop execution, verified application/artifact state, and scoped network-boundary evidence. This distinction is legitimate IF Kairo makes it Real (currently Experimental).

### 1.4 What AGA's patent does NOT cover (based on published claims)

The three independent claims cover:
1. Sealed policy + runtime measurement + enforcement receipts
2. Privacy-preserving disclosure with sensitivity substitution
3. Append-only continuity chain with Merkle checkpoints

**Not claimed (based on published summaries):**
- Desktop GUI actuation readback (Win32 UIA / AT-SPI2)
- Application/file state verification (document readback oracles)
- Host network observation + external network witness
- Domain-specific adapters (Excel, PDF, Word, legal redline, etc.)
- Prompt-injection fixture suites

**IMPORTANT:** This is a preliminary reading of published claim summaries, NOT a formal claim chart. A licensed patent attorney must perform an independent claim chart against Kairo's specific implementation before any FTO assertion. The application is pending and may be narrowed, rejected, or amended.

---

## 2. Microsoft Agent Governance Toolkit (AGT)

| Fact | Value | Primary source |
|------|-------|----------------|
| Repository | github.com/microsoft/agent-governance-toolkit | GitHub (fetched 2026-07-11) |
| Receipt format | Ed25519 signatures over JCS-canonical payloads, hash-chaining across session | GitHub PR #1333 (bilateral receipt signing) |
| Verification | `agt verify` command; OWASP compliance checks; CI integration | GitHub repo description |
| Bilateral receipts | Pre-execution authorization signing + post-execution result sealing | GitHub PR #1333 |
| Sigstore/in-toto integration | Validation against cross-implementation verification stack (Sigstore Rekor / in-toto) | GitHub PR #1333 description |
| SLSA provenance | Integration with SLSA provenance when applicable | Same |

**Assessment:** Microsoft AGT provides governance receipts with bilateral signing (authorization + result). It does NOT publicly demonstrate desktop outcome evidence, independent document readback, or scoped network-boundary evidence. Microsoft owns the OS and could theoretically add stronger observation, but has not publicly done so in AGT.

---

## 3. OPAQUE

| Fact | Value | Primary source |
|------|-------|----------------|
| Product | Confidential AI platform with attestation | docs.opaque.co |
| Attestation | Per-aTLS session; JWT tokens proving workflow ran in confidential hardware | docs.opaque.co/en/latest/public_guide/users/admins/attestation/ |
| Export | PDFs, JSON, RAW (.jwt + artifacts) | Same |
| Hardware-backed | Confidential computing (TEE-based) | Same |
| Python SDK | Reappraise RAW artifacts with OPAQUE Python SDK | docs.opaque.co |

**Assessment:** OPAQUE uses hardware-backed attestation (TEE/SGX). This is a different approach from Kairo's proposed host-plus-external-network-witness model. OPAQUE proves execution in confidential hardware, not desktop outcome or network-boundary evidence.

---

## 4. Kiteworks Compliant AI

| Fact | Value | Primary source |
|------|-------|----------------|
| Product | Compliant AI — data-layer governance for AI agents | kiteworks.com/platform/compliance/compliant-ai/ |
| Controls | Authenticated identity, ABAC policy, FIPS 140-3 encryption, tamper-evident audit log | Same; also press release (kiteworks.com/company/press-releases/kiteworks-compliant-ai-data-layer-governance-ai-agents/) |
| Evidence | Auditable, regulator-ready evidence package pre-mapped to HIPAA, CMMC, PCI DSS, SEC, SOX | Same |
| Audit | Tamper-evident audit log fed into SIEM | Same |
| FIPS | FIPS 140-3 validated encryption in transit and at rest | Same |

**Assessment:** Kiteworks provides data-layer governance with compliance-mapped evidence. It does NOT publicly demonstrate desktop outcome evidence, independent document readback, or scoped network-boundary evidence. Kiteworks owns its controlled data layer and has stronger commercial distribution than Kairo.

---

## 5. Prior Art Search

| # | Prior art | Relevance to AGA claims | Primary source |
|---|-----------|------------------------|----------------|
| PA-1 | **SCITT** (Supply Chain Integrity, Transparency, and Trust) | Signed statements about supply chain artifacts; transparency service registers statements to produce verifiable receipts (COSE-based); append-only ledger | RFC 9943 (datatracker.ietf.org/doc/html/rfc9943) |
| PA-2 | **in-toto Attestation Framework** | Four-layer model (Predicate, Statement, Envelope, Bundle) for authenticated software attestations; DSSE-compliant envelopes; automated policy engine verification | github.com/in-toto/attestation (spec v1.2) |
| PA-3 | **RATS** (Remote ATtestation procedureS) | Architecture for Verifier to assess Attester evidence using Appraisal Policy; Attester/Verifier/Relying Party roles; Passport and Background-Check models | RFC 9334 (datatracker.ietf.org/doc/rfc9334) |
| PA-4 | **RFC 6962** (Certificate Transparency) | Append-only Merkle Tree logs; Signed Certificate Timestamps; Signed Tree Heads; inclusion proofs and consistency proofs | RFC 6962 (rfc-editor.org/rfc/rfc6962.html) |
| PA-5 | **Ed25519** (FIPS 186-5) | Digital signature algorithm used by AGA, Kairo, and many others | FIPS 186-5 |
| PA-6 | **RFC 8785** (JSON Canonicalization Scheme) | Deterministic JSON serialization for signing; used by AGA | RFC 8785 |
| PA-7 | **Merkle trees** | Tamper-evident append-only data structure; used in CT, SCITT, AGA, Kairo | RFC 6962, RFC 9943 |
| PA-8 | **Reference monitors** | Classical security concept: policy enforcement point that mediates all access; Anderson 1972; used in OS security, SELinux, etc. | Literature |
| PA-9 | **Sigstore/Rekor** | Transparency log for software signing; Cosign signatures; Rekor log entries | sigstore.dev |

**Assessment:** The cryptographic primitives AGA uses (Ed25519, SHA-256, Merkle trees, JCS) are all standard and well-established prior art. The concepts of sealed policy artifacts, signed receipts, and tamper-evident chains have precedents in SCITT, in-toto, RATS, and Certificate Transparency. AGA's specific combination (runtime integrity enforcement + privacy-preserving disclosure + continuity chain) may be novel as a combination, but individual components have extensive prior art. **A formal prior-art analysis by counsel is needed to assess claim validity.**

---

## 6. Frozen Public Novelty Claims

Based on the primary-source verification above, the following claims are FROZEN — they must NOT be made publicly until counsel completes the FTO opinion:

### 6.1 Claims that are DROPPED (competitor already does it)

| Claim | Why dropped | Evidence |
|-------|------------|----------|
| "Nobody proves runtime behavior" | AGA proves runtime governance decisions | attestedintelligence.com/technology |
| "We are the first cryptographic governance layer" | AGA and Microsoft AGT both exist | attestedintelligence.com, github.com/microsoft/agent-governance-toolkit |
| "We invented offline-verifiable agent evidence" | AGA has an offline verifier; SCITT/in-toto predate both | attestedintelligence.com/verify, RFC 9943 |
| "No competitor has two-process enforcement" | AGA has two-process key separation (gateway holds keys, agent doesn't) | attestedintelligence.com/about |
| "We are the only product in this category" | AGA, Microsoft AGT, OPAQUE, Kiteworks all exist | All sources above |
| "Can also verify other platforms' evidence" | Cross-vendor verifier is None yet | CLAIMS.md N9 |
| "Rivals can't copy this" | Competitors could add observers; not architecturally impossible | research-redteam-source.md §2.4 |

### 6.2 Claims that are PERMITTED (conservatively scoped)

| Claim | Why permitted | Scope |
|-------|-------------|-------|
| "Designed to bind desktop outcome evidence to governance receipts" | No competitor publicly demonstrates this | Experimental until G1/G2 pass |
| "Gateway-only evidence cannot establish downstream desktop state without additional observers" | True and precise; AGA confirms gateway-only model | Factual |
| "Designed to normalize evidence from other platforms into the KSEE draft profile" | Adapter is None yet; "designed to" is honest | Future work, T4B |
| "Produces evidence supporting an assessor's evaluation" | Never "certified" or "compliant" | Factual |
| "Blocked all 25 attacks in the current fixture suite" | Reproducible test; not "injection-safe" | Real (R3) |

### 6.3 Claims that are FROZEN pending counsel

| Claim | Why frozen | Unfreeze when |
|-------|-----------|---------------|
| "Patentable" / "novel" | FTO requires licensed-attorney judgment | Counsel FTO opinion received |
| "First to bind desktop outcome + scoped boundary evidence" | May be true but cannot assert "first" without exhaustive search | Counsel opinion + competitor analysis |
| Any specific FTO assertion | Licensed-attorney judgment | Counsel opinion |

---

## 7. FTO Scope — What This Memo Does and Does NOT Cover

### DOES cover (verification memo):
- ✅ AGA company identity, founder, state of formation — verified from primary sources
- ✅ AGA patent application number, filing date, title, claims — verified from vendor site
- ✅ AGA architecture and capabilities — verified from vendor site + GitHub repo
- ✅ AGA's public gaps (no desktop outcome evidence) — no public evidence found as of July 2026 (absence of public evidence, not proof of absence)
- ✅ Microsoft AGT, OPAQUE, Kiteworks — verified from vendor sites/repos
- ✅ Prior art: SCITT, in-toto, RATS, RFC 6962, Sigstore — verified from IETF RFCs and repos
- ✅ Novelty claims frozen conservatively — dropped claims that competitors already do

### Does NOT cover (requires licensed counsel):
- ❌ Formal FTO/patentability clearance opinion
- ❌ Independent claim chart mapping AGA claims to Kairo's implementation
- ❌ Assessment of whether AGA's pending claims will be narrowed/rejected/invalidated
- ❌ Advice on what Kairo may publish as defensive prior art
- ❌ Advice on whether any narrow Kairo mechanism is independently protectable
- ❌ USPTO Patent Center docket-level status (requires authenticated access)

**The legal-clearance portion of T1 is scoped to counsel. This memo provides the factual foundation for that engagement.**

---

## 8. research-redteam-source.md — Verification Status

| Claim in research-redteam-source.md | Verified? | Primary source |
|-------------------------------------|-----------|----------------|
| AGA patent 19/433,835 | ✅ Confirmed | attestedintelligence.com/patent |
| Filed December 28, 2025 | ✅ Confirmed | Same |
| "Systems and Methods for Generating and Enforcing Attested Governance Artifacts" | ✅ Confirmed | Same |
| Jack Brennan is founder | ✅ Confirmed | attestedintelligence.com/about, SSRN preprint |
| Attested Intelligence Holdings LLC exists | ✅ Confirmed | NCCoE PDF (Illinois File No. 17233815) |
| AGA has Ed25519-signed, hash-linked receipts | ✅ Confirmed | attestedintelligence.com/technology |
| AGA has Merkle evidence | ✅ Confirmed | Same |
| AGA has portable evidence bundles | ✅ Confirmed | Same |
| AGA has independent offline verifier | ✅ Confirmed | attestedintelligence.com/verify, GitHub repo |
| AGA has patent-pending architecture | ✅ Confirmed | attestedintelligence.com/patent |
| AGA is "likely funded and US-centric" | ❌ UNVERIFIED | No public evidence of funding amount, team size, or geographic strategy |
| AGA "validates that serious buyers will pay" | ❌ OVERSTATED | No public evidence of paying customers or revenue |
| AGA gateway holds signing keys (not self-attestation) | ✅ Confirmed | attestedintelligence.com/about: "The agent holds no cryptographic keys, and cannot self-authorize" |

**All competitor facts from research-redteam-source.md that could be verified from primary sources HAVE been verified. Two claims remain UNVERIFIED (funding amount, customer revenue) — these should not be asserted.**

---

## 9. Summary of Actions for Counsel

1. Retrieve the full patent application 19/433,835 from USPTO Patent Center (requires registered account)
2. Commission an independent claim chart mapping AGA's 3 independent claims to Kairo's implementation
3. Prior-art search: in-toto, SCITT, RATS, reference monitors, remote attestation, receipt chains, policy gateways (this memo provides the starting list in §5)
4. FTO opinion: whether Kairo's desktop outcome evidence, document readback, and scoped network-boundary evidence infringe any AGA claim
5. Advice on defensive prior-art publication
6. Advice on whether Kairo's specific mechanisms are independently protectable

---

**This memo is the evidence file for T1. The legal-clearance portion is scoped to counsel via `orchestrator.py wont_fix`.**
