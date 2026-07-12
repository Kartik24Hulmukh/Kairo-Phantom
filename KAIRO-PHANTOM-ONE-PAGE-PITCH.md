# Kairo-Phantom — One-Page Pitch

**Version:** 1.2.1 (integrity-corrected) · **Date:** 11 July 2026 · *(No unverified traction. Users = 0, revenue = 0. **Evidence audit in progress** — every public metric must be tied to a reproducible evidence record before external use.)*

---

## The one line

**Kairo-Phantom is building the independent evidence & conformance layer for sovereign desktop agents** — designed to bind human authority, policy, observed computer actions, verified results, and scoped network evidence into a pack another party can verify offline — on desktops and controlled environments where ordinary cloud agents cannot be trusted or used.

> **Prove what the agent did — and where the data did not go.**

*(Drop "is building" / "designed to" only after the real-hardware and dual-witness gates pass.)*

---

## The problem

Some regulated and sovereign environments require local or disconnected operation, while security and assurance teams increasingly need traceable evidence of agent actions. Conventional API logs may be insufficient when they don't bind an action to an accountable principal, the affected artifact, and the resulting state — i.e. they can show "a tool was permitted" but not "what actually changed on the machine, and whether data left the boundary."

## What we do

Kairo runs a local AI agent that operates real desktop applications and is designed to emit an offline-verifiable evidence pack across the whole chain: **human mandate → policy decision → independently-observed desktop action → verified application/file state → scoped network-boundary evidence → tamper-evident receipt.** The existing receipt verifier can check supported signatures and hash chains offline and returns a **sufficiency report** (never a bare "valid") — stating what was observed and what was not. **The full KSEE independent verifier is still in development.**

**Maturity, stated plainly:** the signed audit log and offline receipt checks are Real today. **Independently-observed desktop action and dual-witness network (zero-egress) evidence remain Experimental** until the real-hardware and host-plus-external-witness gates pass. We never present Experimental capabilities as Real.

## What is real today (reproducible)

- **Signed, hash-chained audit log** — Ed25519; tamper → verification FAILS; offline-verifiable with the included verifier (no independent third party has verified yet).
- **Sealed mode** — blocked/detected the current forced-send fixtures within the Kairo runtime (published interface list per test).
- **Prompt-injection fixture suite** — blocked all 25/25 attacks in the current fixture suite, 0/15 false positives. Fail-closed permissions are the primary protection.
- **11 fixture-verified domain adapters**; local test run **997 passed, 6 skipped, 9 failed (environmental)** — quote only with date, commit, exact command, and "local result; skip audit in progress" (do not lead with the raw count externally until the skips are documented from a current run); canary-breaks that turn CI red so "green" can't be faked.
- **Honest labels** — everything unproven is marked Experimental (see CLAIMS.md). We never assert Experimental as Real.

## Why now

- **EU AI Act:** high-risk record-keeping (Article 12) now lands **Dec 2, 2027** (Digital Omnibus) — land-early, harvest-later. *(Verify the Official Journal text before quoting a date.)*
- **US CMMC 2.0:** Phase 2 begins **10 November 2026**, when Level 2 C3PAO requirements begin appearing more systematically in applicable solicitations; required status/assessment type remain contract-dependent during the phased rollout.
- Signed receipts are commoditizing — the moat is outcome evidence + an independent network witness + an open draft profile + assessor adoption, not the signature.

## Why us / what's defensible

- **Outcome evidence, not merely decision evidence:** gateway-only evidence cannot establish downstream desktop state without independent observers.
- **Scoped, independently-witnessed** zero-egress evidence (host sensor + external network witness + canaries + a coverage declaration), not self-attestation.
- A **neutral appraiser**: roadmap adapters will ingest evidence from other agent platforms and normalize it into the KSEE draft profile — turning incumbents into inputs. *(Specific adapters listed in the technical appendix.)*

## The ask / next 90 days

A focused proof sprint to (1) make the desktop causal chain real on pinned hardware, (2) make scoped zero-egress evidence real with an independent witness, (3) get one external party to verify a pack, (4) get one buyer to pay — and to run the Mode A vs Mode B blind test that asks assessors whether outcome evidence changes a deployment decision. Seeking design partners in EU-regulated software + assurance firms, and non-dilutive funding aligned with open trust infrastructure.

**Open source:** github.com/Kartik24Hulmukh/Kairo-Phantom · **Founder:** Kartik Hulmukh (solo)

---

## Technical appendix — roadmap adapters (not for the one-pager face)

The neutral-appraiser roadmap plans **read-only** adapters that normalize evidence from other agent/attestation ecosystems into the KSEE draft profile. Target sources include Microsoft AGT, Attested Intelligence AGA, Asqav / SCITT-style receipt chains, and OpenTelemetry / MCP action traces. Adapters imply **no endorsement** and are gated behind T4B (after the native verifier T4A and after market falsification T2A). The full independent KSEE verifier is future work; today only supported signatures and hash chains are checked offline.
