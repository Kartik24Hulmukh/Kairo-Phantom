# R4 — REGULATED GTM: what regulated buyers need BEYOND the proof

> Risk: hospitals/law firms buy from companies with process, support, and indemnification — not
> a solo OSS binary, however clever. The tech clears the technical gate; it does not clear
> procurement. This is a non-engineering moat you must build deliberately.

## The two-audience funnel (fix G9) — sequence, don't merge
1. **Prosumer/dev (viral, week 1):** offline redline + live zero-egress report → r/LocalLLaMA,
   HN, MCP registry. This builds distribution and the demand proof — NOT revenue.
2. **Regulated (revenue, weeks 4+):** inbound from the viral demo → design partners → paid.
   The viral crowd is the top of funnel; regulated buyers convert from watching it.

## What regulated procurement actually requires (build this in parallel with the tech)
| Requirement | Minimum viable version for a small team |
|---|---|
| **Verifiable-offline proof** | sealed build + signed egress report (R3) — your unfair advantage |
| **Audit trail** | hash-chained signed audit log (prompt 06) — export for compliance |
| **Data-handling story** | one-page: "all processing local; user owns data + adapters; nothing egresses" |
| **Security posture** | SBOM (from license_gate), threat model, out-of-band injection defense (prompt 05), pen-test (VulnClaw) |
| **Vulnerability process** | a SECURITY.md, disclosure address, patch cadence |
| **Support + SLA** | design-partner-grade support first; formal SLA when you have staff |
| **Legal** | LLC, EULA, DPA template, liability/indemnification stance (get counsel) |
| **Certifications (later)** | SOC 2 Type I → II as you grow; HIPAA BAA only if you ever touch PHI (you're deferring Medical — good) |

## The realistic path
- **Don't chase enterprise procurement as a solo dev.** Land **2–3 design partners** (a boutique
  law firm, a compliance-heavy SMB) on a lightweight pilot agreement. Their logo + a case study
  ("we run AI on client contracts our cloud policy forbids") is the wedge into bigger buyers.
- Price on **provable privacy + audit**, not per-seat AI — that's what they can't get elsewhere.
- The certifications come *after* revenue proves the wedge; don't front-load SOC 2.

## The R4 kill-test (week 1, ~1 day, ~$0) — the single most important experiment
Record a 60-sec offline-redline + zero-egress demo. Send to **10 beachhead buyers** (legal-ops,
hospital IT, compliance). Ask: *"Does 'provably offline' change your answer vs a normal local tool?"*
- **≥6/10 yes → provable-offline is a purchase trigger; build the regulated wedge.**
- ≤3/10 → reposition to prosumer-offline (drop regulated framing); different, smaller business.
- 4–5 → build, but validate willingness-to-pay (a signed pilot LOI) before writing the full operator.

> This test gates everything. More engineering cannot fix a "no" here. Run it in week 1.
