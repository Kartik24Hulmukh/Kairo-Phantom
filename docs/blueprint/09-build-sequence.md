# Section 9: Build Sequence (24-Month Roadmap)

## Executive Summary
This section breaks down the 100x adoption plan into a month-by-month build sequence, assigning engineering priorities + dependencies. The roadmap balances:
- **Short-term:** Kill critical risks (sidecar scaling, encryption, legal liability).
- **Medium-term:** Ship SaaS MVP (public API, cloud infrastructure, enterprise onboarding).
- **Long-term:** Expand into verticals (healthcare, finance, government).

---

## Phase 1: Months 1–3 — Foundation & Risk Mitigation

### Month 1: Crisis Mode (Kill Existential Risks)
**Focus:** Security, legal, scaling. This month is all triage.

#### Week 1
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Hire litigation counsel | CEO | — | 0 | Law firm signed |
| Implement UI affordance (auth notification) | Engineering | — | 3 days | Phantom shows "[🔒 Verifying...]" during ghost typing |
| Encryption-at-rest audit | Security | — | 2 days | Report: which data is unencrypted |
| Secrets management audit | DevOps | — | 1 day | Report: which secrets are in code/Git |

#### Week 2
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Start sidecar refactor (design phase) | Principal Eng | UI affordance ✓ | 3 days | Architecture: stateless sidecar design |
| Implement encryption-at-rest | Security | Audit ✓ | 5 days | AES-256-GCM encryption live in test DB |
| Deploy secrets manager (Vault/KMS) | DevOps | Audit ✓ | 3 days | All secrets moved to Vault. App boots from secrets manager. |
| Legal docs (ToS, DPA, privacy policy) | Legal | — | 5 days | Draft contracts (review by counsel) |

#### Week 3
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Sidecar refactor phase 1 (Go rewrite) | Principal Eng | Design ✓ | 10 days | Stateless sidecar v2 (Go) supports 100 concurrent sessions |
| HSM integration (AWS CloudHSM) | Infrastructure | Secrets ✓ | 5 days | Ed25519 private key stored in HSM. Signing tests pass. |
| Fix data validation (input sanitization audit) | Engineering | — | 3 days | SQL injection / XSS audit complete. Report findings. |
| Pen test engagement (booking) | Security | — | 1 day | Pen test firm booked for Month 2 |

#### Week 4
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Sidecar refactor phase 2 (concurrency testing) | Principal Eng | Sidecar v2 ✓ | 10 days | Load test: 1K concurrent sessions per sidecar pod |
| Fix data validation (implement fixes) | Engineering | Audit ✓ | 5 days | All input validations fixed. Tests pass. |
| Database integrity constraints (FKs, checks) | DBA | — | 3 days | Foreign keys + check constraints enabled. Audit pass. |
| Multi-tenant isolation design | Principal Eng | Sidecar v2 ✓ | 3 days | Design: how to partition phantom-core by tenant_id |

**Month 1 Success Criteria:**
- ✓ UI affordance (auth notification) live.
- ✓ Encryption-at-rest deployed to staging.
- ✓ Secrets in Vault (no hardcoded keys).
- ✓ Stateless sidecar v2 (Go) passes load test (1K concurrent).
- ✓ HSM integration done.
- ✓ Ed25519 keys in HSM, not on disk.
- ✓ Input validation fixed.
- ✓ Pen test firm engaged.
- ✓ Legal docs drafted.

---

### Month 2: SaaS Foundation & Compliance
**Focus:** Multi-tenant orchestration, compliance, API design.

#### Week 1
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Pen test execution | External firm | — | 1 week | Preliminary findings (security report) |
| Multi-tenant orchestration (phantom-core refactor) | Principal Eng | Design ✓ | 10 days | phantom-core partitions by tenant_id. Tests pass. |
| OpenAPI 3.0 spec (API design) | Tech lead | — | 3 days | Complete REST API spec (auth, sessions, webhooks) |
| SOC 2 audit kickoff | Compliance | — | 1 day | Audit firm engaged. Scoping complete. |

#### Week 2
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Fix pen test findings (critical/high) | Security | Pen test ✓ | 5 days | All critical findings fixed. Retested. |
| Sidecar scaling v3 (multi-region load balancing) | Infrastructure | Sidecar v2 ✓ | 7 days | Sidecar deployed to 3 regions. Traffic routed by geography. |
| Audit trail (immutable logs) | Engineering | Integrity ✓ | 5 days | All auth events logged immutably. HMAC-signed. Retention policy enforced. |
| SDK design (Node.js, Python, Go) | Engineer | API spec ✓ | 3 days | SDK architecture docs (interfaces, error handling) |

#### Week 3
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Sidecar refactor phase 3 (failover / HA) | Infrastructure | Multi-region ✓ | 7 days | Sidecar failover <30s. Multi-region HA deployed. |
| Node.js SDK implementation | Engineer | SDK design ✓ | 7 days | `@kairo/phantom-js` package (npm, publishable) |
| Database replication (multi-region) | DBA | — | 5 days | Aurora Global Database / Supabase replication live. All 3 regions synced. |
| Webhook event system (draft) | Engineer | — | 3 days | Webhook payload schema + retry logic designed. |

#### Week 4
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Python SDK implementation | Engineer | SDK design ✓ | 7 days | `kairo-phantom-py` package (PyPI, publishable) |
| Go SDK implementation | Engineer | SDK design ✓ | 7 days | `kairo-phantom-go` module (publishable) |
| Rate limiting + quota system | Engineer | OpenAPI ✓ | 5 days | API rate limiter live. Quota enforcement tested. |
| Monitoring + alerting (Prometheus) | SRE | — | 5 days | Dashboards: latency, error rate, connections, CPU, memory live. |

**Month 2 Success Criteria:**
- ✓ Pen test passed (all critical findings fixed).
- ✓ Multi-tenant phantom-core deployed to staging.
- ✓ Sidecar deployed to 3 regions with HA + failover.
- ✓ All 3 SDKs published (npm, PyPI, go.dev).
- ✓ API rate limiting live.
- ✓ Database replication configured.
- ✓ Audit trail immutable + signed.
- ✓ SOC 2 audit in progress (no blocking findings).

---

### Month 3: SaaS MVP Launch & Load Testing
**Focus:** Production readiness, stress testing, first SaaS customers.

#### Week 1
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Stress test (Scenario 1: Ramp-up) | QA + SRE | Sidecar v3 ✓ | 3 days | Load test report: 10K concurrent, <200ms p99. Pass. |
| Stress test (Scenario 2: Steady state) | QA + SRE | Scenario 1 ✓ | 2 days | 30min at 10K concurrent. Memory stable. Pass. |
| Stress test (Scenario 3: Region failure) | SRE | Scenario 2 ✓ | 2 days | Failover <5s, no data loss. Pass. |
| Terraform IaC (production environment) | DevOps | Monitoring ✓ | 5 days | All infrastructure (VPCs, RDS, load balancers, etc.) in Terraform. |

#### Week 2
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Stress test (Scenario 4: DB failure) | SRE | Scenario 3 ✓ | 2 days | RTO <2min, RPO <1min. Pass. |
| Stress test (Scenario 5: High latency) | QA | Scenario 4 ✓ | 1 day | P99 <1000ms, <0.1% error. Pass. |
| Stress test (Scenario 6: Peak burst) | QA | Scenario 5 ✓ | 1 day | No crash at 15K concurrent. Graceful queue. Pass. |
| CI/CD pipeline hardening (staging + prod) | DevOps | Terraform ✓ | 3 days | Automated tests + security checks before deployment. |

#### Week 3
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| Webhook implementation (delivery + retry) | Engineer | Webhook design ✓ | 3 days | Webhook events delivered. Retries working. |
| First SaaS customers onboarded | Sales | SDK ✓ | 3 days | 3–5 pilot customers active. Collecting feedback. |
| Documentation (API, SDKs, integrations) | Tech Writer | API spec ✓ | 5 days | Complete docs live at docs.phantom.io. |
| Runbooks + playbooks (deployment, incident response) | SRE | CI/CD ✓ | 3 days | Runbooks documented. Team trained. |

#### Week 4
| Task | Owner | Dependency | Effort | Deliverable |
|------|-------|-----------|--------|------------|
| SaaS launch (public beta) | Product | All ✓ | 1 day | SaaS tier live. Free tier available. |
| SOC 2 audit completion (Type II mid-term review) | Compliance | — | 1 day | SOC 2 audit provisioning (full audit in Month 6). |
| Community program launch (50 insiders) | Growth | SaaS ✓ | 2 days | 50 developers on insider program. Monthly stipends started. |
| Press release / launch announcement | PR + Product | SaaS ✓ | 2 days | Press release + social media campaign. Launch blog post live. |

**Month 3 Success Criteria:**
- ✓ All 6 stress tests pass.
- ✓ SaaS MVP live (public beta, free + paid tiers).
- ✓ 3–5 pilot customers active.
- ✓ All SDKs published + documented.
- ✓ Monitoring + alerting live.
- ✓ Terraform IaC complete.
- ✓ CI/CD pipeline automated.
- ✓ Insider program launched (50 developers).
- ✓ $0 → $5K MRR (pilot customers).

---

## Phase 2: Months 4–8 — Enterprise Integration & Scale

### Month 4–5: Okta + Entra Integration
**Focus:** Deep partnerships with identity providers.

| Initiative | Effort | Deliverable |
|-----------|--------|------------|
| **Okta Partnership** | 4 weeks | <li>Okta Session Bridge integration (verified assertion → session).</li><li>Okta Marketplace app listing.</li><li>Co-marketing agreement signed.</li><li>3 pilot customers (Okta + Phantom).</li> |
| **Entra ID Integration** | 4 weeks | <li>Conditional Access integration.</li><li>Azure Marketplace listing.</li><li>Co-marketing agreement signed.</li><li>3 pilot customers (Entra + Phantom).</li> |
| **Customer Success** | Ongoing | <li>Expand pilot customers from 5 → 15.</li><li>MRR: $5K → $20K.</li> |
| **Vertical Playbooks (Draft)** | 2 weeks | <li>Finance: Phantom + Okta + banking APIs (draft).</li><li>Healthcare: Phantom + Okta + EHR integration (draft).</li><li>Government: Phantom + Entra ID + FedRAMP (draft).</li> |

**Month 4–5 Success Criteria:**
- ✓ Okta + Entra integrations live.
- ✓ Both marketplace listings approved.
- ✓ 6 pilot customers (3 per partnership).
- ✓ $15K–$20K MRR.
- ✓ Vertical playbooks drafted.

### Month 6: Compliance & Certification Push
**Focus:** SOC 2 + FedRAMP initial steps.

| Initiative | Effort | Deliverable |
|-----------|--------|------------|
| **SOC 2 Type II (Interim)** | 4 weeks | <li>SOC 2 audit firm: final report + certification issued.</li><li>Marketing: "SOC 2 Certified" badge live on website.</li> |
| **FedRAMP Moderate Pre-Assessment** | 2 weeks | <li>Engage FedRAMP JAB auditor.</li><li>Preliminary security assessment (scoping).</li><li>Government customers begin pre-sale discussions.</li> |
| **Customer Case Studies** | 2 weeks | <li>3 enterprise case studies (finance, healthcare, tech).</li><li>Blog posts + landing pages live.</li> |

**Month 6 Success Criteria:**
- ✓ SOC 2 Type II issued.
- ✓ FedRAMP scoping began.
- ✓ Case studies published.
- ✓ $25K–$35K MRR.

### Month 7–8: Vertical Expansion
**Focus:** Launch finance, healthcare, government playbooks.

| Vertical | Effort | Deliverable |
|----------|--------|------------|
| **Finance (Banking + Payments)** | 3 weeks | <li>Phantom + Okta + eFunds API connector.</li><li>Compliance: PCI-DSS assessment.</li><li>1–2 bank pilots.</li><li>$50K+ ACV contract closed.</li> |
| **Healthcare (HIPAA)** | 3 weeks | <li>Phantom + Okta + Redox EHR bridge.</li><li>Compliance: HIPAA Business Associate Agreement (BAA) signed.</li><li>2–3 hospital systems pilots.</li><li>$25K–$50K ACV contracts.</li> |
| **Government (FedRAMP)** | 3 weeks | <li>Phantom + Entra ID + GovCloud connector.</li><li>Pre-certification review underway.</li><li>1 federal agency pilot.</li><li>$100K+ ACV potential.</li> |
| **SaaS/Tech (Self-Serve)** | 2 weeks | <li>Self-serve tier: $500–$5K/month.</li><li>Automated onboarding (no sales needed).</li><li>15–20 SaaS companies signed.</li><li>$5K–$10K MRR from self-serve.</li> |

**Month 7–8 Success Criteria:**
- ✓ All 4 vertical playbooks live.
- ✓ 8–10 enterprise pilots active.
- ✓ $75K–$100K MRR (sum of verticals).
- ✓ 1–2 major contracts closed ($50K+ ACV).

---

## Phase 3: Months 9–12 — Scale & Market Positioning

### Month 9: Insider Program Expansion
**Focus:** Developer advocacy + viral adoption.

| Initiative | Effort | Deliverable |
|-----------|--------|------------|
| **Insider Stipends** | Ongoing | <li>50 insiders → 100 insiders (add 50 more).</li><li>Monthly stipends: $500–$2K per insider.</li><li>Cost: ~$75K/month.</li> |
| **Content Generation** | Ongoing | <li>20–30 insider-created blog posts, videos, POCs per month.</li><li>Distributed across: Dev.to, Medium, YouTube, GitHub, Product Hunt.</li> |
| **Community Events** | 2 weeks | <li>Monthly community office hours (Zoom + recording).</li><li>Quarterly workshops (prompt engineering, risk scoring, integration patterns).</li> |
| **Bounty Program** | 1 week | <li>Security bounties: $1K–$5K per finding.</li><li>Integration bounties: $500–$2K per community integration.</li> |

**Month 9 Success Criteria:**
- ✓ 100 insiders in program.
- ✓ 20–30 pieces of insider content/month.
- ✓ 1K+ community members in Slack.
- ✓ Viral growth (organic referrals driving 20% of new customers).

### Month 10–11: Market Positioning
**Focus:** Analyst engagement + PR blitz.

| Initiative | Effort | Deliverable |
|-----------|--------|------------|
| **Analyst Engagement** | 3 weeks | <li>Gartner Magic Quadrant research (scoping call).</li><li>Forrester Wave assessment (vendor interview).</li><li>Industry reports + analyst briefings.</li> |
| **Conference Speaking** | 4 weeks | <li>RSA Conference: "Invisible MFA for Enterprise" (accepted).</li><li>Okta World: Joint keynote (partnership).</li><li>AWS re:Invent: Security + Identity talks.</li><li>HIMSS (healthcare): HIPAA-compliant auth talks.</li> |
| **PR Campaign** | 3 weeks | <li>TechCrunch / Forbes article: "Phantom Raises $X Series A".</li><li>Security newsletters: "Top 5 Passwordless Vendors".</li><li>Analyst reports featured (Gartner, Forrester mentions).</li> |
| **Customer Testimonials** | 2 weeks | <li>3–5 video testimonials from enterprise customers.</li><li>Landing pages + case studies updated with social proof.</li> |

**Month 10–11 Success Criteria:**
- ✓ Speaking slots secured at 3+ major conferences.
- ✓ TechCrunch / mainstream press coverage.
- ✓ Analyst scoping underway (Gartner MQ consideration).
- ✓ $150K–$200K MRR.

### Month 12: Milestone Review & Series B Planning
**Focus:** Reflect on 12-month progress. Plan Series B.

| Metric | Target | Actual | Pass/Fail |
|--------|--------|--------|-----------|
| **MRR** | $100K+ | ~$150K–$200K | ✓ PASS |
| **ARR** | $1.2M+ | ~$1.8M–$2.4M | ✓ PASS |
| **Customers** | 100+ | ~120–150 | ✓ PASS |
| **CAC** | <$3K | ~$2K | ✓ PASS |
| **LTV** | >$100K | ~$120K–$180K | ✓ PASS |
| **Churn** | <5%/month | ~2–3%/month | ✓ PASS |
| **NPS** | >50 | ~55–65 | ✓ PASS |

**Series B Planning:**
- Investors to pitch: Sequoia, Lightspeed, Gradient (security/identity focus).
- Valuation: $100M+ ($1.8M ARR × 50–60x multiple).
- Raise: $30M–$50M (18 months of runway).
- Use of funds: (a) 10 engineers (product), (b) 5 engineers (sales engineering), (c) 10% to sales/marketing.

**Month 12 Success Criteria:**
- ✓ $200K MRR ($2.4M ARR) achieved.
- ✓ 150+ customers.
- ✓ Series B term sheet in hand (or close).
- ✓ Market leadership established (analyst recognition, conference talks, press).

---

## Phase 4: Months 13–24 — Horizontal Expansion & Defensibility

### Months 13–18: Phantom Pro (Orchestration Layer)
**Focus:** Generalize Phantom's orchestration engine into platform product.

| Initiative | Effort | Deliverable |
|-----------|--------|------------|
| **Orchestration Engine Extraction** | 6 weeks | <li>Abstract LangGraph orchestration into reusable decision engine.</li><li>Risk scoring + policy evaluation divorced from ghost typing.</li><li>Multi-vendor auth orchestration (Okta → Phantom → Entra ID fallback chains).</li> |
| **Phantom Pro API** | 4 weeks | <li>REST API for custom risk policies.</li><li>Decision engine: "If risk_score > 0.8, require MFA; if > 0.95, block".</li><li>Integrates with Okta, Auth0, ADFS.</li> |
| **Phantom Pro Pricing** | 2 weeks | <li>Tier: $1K–$10K/month per enterprise.</li><li>Based on: API calls + policy complexity.</li> |
| **Initial Customers** | 8 weeks | <li>5–10 enterprise customers onboard to Phantom Pro.</li><li>Revenue: $50K–$100K MRR by Month 18.</li> |

**Months 13–18 Success Criteria:**
- ✓ Orchestration engine extracted + generalized.
- ✓ Phantom Pro live (new product tier).
- ✓ 5–10 Pro customers.
- ✓ $300K–$400K MRR (core + Pro combined).
- ✓ $3.6M–$4.8M ARR.

### Months 19–24: Market Consolidation & Competitive Defense
**Focus:** Lock in market leadership. Prepare for Okta/Microsoft response.

| Initiative | Effort | Deliverable |
|-----------|--------|------------|
| **Exclusive Partnerships** | 4 weeks | <li>Okta: Exclusive invisible MFA provider (contract negotiation).</li><li>Entra ID: Preferred Phantom integration (marketing support).</li><li>Auth0: Joint solution (if Auth0 hasn't built competing product).</li> |
| **Vertical Certifications** | 8 weeks | <li>FedRAMP Moderate certification complete (government).</li><li>HIPAA certification complete (healthcare).</li><li>PCI-DSS assessment complete (finance).</li> |
| **International Expansion** | 12 weeks | <li>GDPR audit completed.</li><li>European sales team hired (2–3 reps).</li><li>APAC partnership (reseller channel).</li> |
| **Series B Follow-On** | Ongoing | <li>Series B capital deployed to hire 20–30 engineers.</li><li>Product roadmap: Phantom Pro expansion, vertical integrations.</li> |

**Months 19–24 Success Criteria:**
- ✓ Exclusive partnership agreements signed (Okta + Entra).
- ✓ FedRAMP Moderate + HIPAA + PCI-DSS certified.
- ✓ European sales team active (10–20 customers).
- ✓ $500K–$750K MRR ($6M–$9M ARR).
- ✓ 300–500 total customers.
- ✓ Series B fundraise complete (Series C planning).

---

## Resource Plan (Annual)

### Team Composition (Month 1)
- **Engineering:** 6 engineers (1 principal, 2 senior, 3 mid).
- **Infrastructure/DevOps:** 2 engineers (1 principal, 1 mid).
- **Product/Design:** 1 product manager, 1 designer (part-time).
- **Security/Compliance:** 1 security engineer, 1 compliance officer (part-time).
- **Sales/Growth:** 1 sales person, 1 content/marketing person.
- **Operations:** 1 CEO, 1 COO (finance + HR).

**Total:** ~15 people.  
**Cost:** ~$2.5M/year (fully loaded).

### Team Composition (Month 12)
- **Engineering:** 12 engineers (expanding).
- **Infrastructure/DevOps:** 4 engineers.
- **Product/Design:** 2 product managers, 2 designers.
- **Security/Compliance:** 2 security engineers, 1 compliance officer.
- **Sales/Growth:** 2 sales people, 3 marketing people.
- **Finance/Admin:** 1 controller, 1 HR person.
- **CEO + COO:** 2.

**Total:** ~32 people.  
**Cost:** ~$5M/year.

### Budget Allocation (Month 1–12)

| Category | Percentage | Amount | Notes |
|----------|-----------|--------|-------|
| **Engineering** | 40% | $1.0M | Core product development (sidecar refactor, APIs, SDKs) |
| **Infrastructure** | 15% | $375K | AWS/cloud, databases, monitoring, tooling |
| **Sales/Marketing** | 20% | $500K | Sales reps, content, conferences, PR |
| **Security/Compliance** | 10% | $250K | Pen tests, audits, certifications (SOC 2, FedRAMP) |
| **General/Admin** | 15% | $375K | Operations, finance, HR, legal |

**Total Budget:** $2.5M (Year 1).

---

## Critical Path (Do or Die)

If any of these are not completed on schedule, the 100x plan is jeopardized:

1. ✓ **Month 1, Week 2:** Sidecar refactor begins (design must be done).
2. ✓ **Month 2, Week 1:** Pen test passed (critical findings fixed).
3. ✓ **Month 2, Week 4:** All 3 SDKs published.
4. ✓ **Month 3, Week 1:** Stress tests pass (all 6 scenarios).
5. ✓ **Month 3, Week 3:** SaaS launch (3–5 pilot customers).
6. ✓ **Month 5, Week 4:** Okta + Entra integrations live.
7. ✓ **Month 6:** SOC 2 Type II certification issued.
8. ✓ **Month 8:** $100K MRR achieved.
9. ✓ **Month 12:** $200K MRR ($2.4M ARR) achieved.
10. ✓ **Month 24:** $500K+ MRR ($6M+ ARR) achieved.

**If milestone #8 (Month 8, $100K MRR) is missed, pivot to consulting-only or seek acquisition.**

---

## Decision Gates (Monthly Reviews)

Every month, review:
- **Revenue:** On track for MRR target?
- **Customer growth:** On track for 100+ customers by Month 12?
- **Churn:** >5%/month churn? (Investigate product issues.)
- **NPS:** <50? (Investigate product fit.)
- **Burn rate:** Runway >12 months?

If any metric is red, hold a "war room" meeting. Options:
- (a) Adjust roadmap (extend timeline, cut features).
- (b) Bring in advisors (identity experts, former Okta/Microsoft execs).
- (c) Raise bridge round (if runway is low).
- (d) Pivot or shut down (if fundamentals are broken).

---

## Conclusion

This 24-month roadmap is ambitious but achievable with disciplined execution. The key is to:
- **Kill critical risks first** (Months 1–2).
- **Ship SaaS MVP fast** (Month 3).
- **Prove product-market fit** (Months 4–8).
- **Expand into verticals** (Months 9–12).
- **Build defensibility** (Months 13–24).

The path to 100x adoption is execution discipline + market timing. Execute this roadmap, and Phantom will reach $6M+ ARR within 24 months.
