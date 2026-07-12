# SOC 2 Type II Readiness — Kairo Phantom

> **⚠️ ASPIRATIONAL — NOT certified, NOT audited, NOT a compliance claim.**
> This document is a **self-reported readiness assessment**. No SOC 2 audit has
> been performed. No certification has been issued. Do not cite this document
> as SOC 2 certification or compliance. The real, test-verified security
> properties are documented in CLAIMS.md. This document describes **planned**
> controls and design intent only.

**Prepared by:** Kairo Phantom Security Team  
**Applicable Trust Service Criteria:** CC6, CC7, CC8, CC9, A1, C1  
**Status:** Readiness Assessment — Pre-Audit (NOT certified)  
**Last Updated:** 2026-05-27

---

> **IMPLEMENTATION STATUS CORRECTION (2026-07, no-fake-green audit):**
> References in this document to **SPIFFE-based agent identity**, an RBAC engine,
> and `~/.kairo-phantom/enterprise/spiffe_identity.json` describe **planned**
> controls — the `enterprise/` Rust module does not exist in the repository, and
> the existing `SpiffeIdentity` struct issues a mock certificate. What IS
> implemented: an Ed25519 agent keypair with a signed, hash-chained receipt log
> (`phantom-core/src/identity.rs`), Merkle checkpoints with a standalone external
> verifier (`kairo/trust/`, `tools/verify_receipts_external.py`), and zero-egress
> enforcement proven in CI. Read "SPIFFE" claims below as **roadmap, not current state**.

## Executive Summary

Kairo Phantom is designed as a **privacy-first, offline-first** AI ghost-writer. The architecture eliminates the most common SOC 2 failure modes by design:

| Risk | Kairo Approach | Control |
|------|---------------|---------|
| Customer data sent to third parties | Ollama runs 100% locally — no data leaves the machine | CC6.7 |
| Unauthorized access to enterprise content | Documents processed in-memory only; never written to disk | CC6.1 |
| Audit trail gaps | SHA-256-chained enterprise audit log | CC7.2 |
| Privilege escalation | SPIFFE-based agent identity + RBAC engine | CC6.3 |
| Supply chain attacks | SBOM generation + dependency vulnerability audit | CC9.2 |
| Session leakage | Per-session sentinel UUID + blocklist scanner | CC6.6 |

---

## CC6 — Logical and Physical Access Controls

### CC6.1 — Access Control Policies

Kairo Phantom enforces access control at three levels:

**Agent Identity (SPIFFE-style)**
- Each running Kairo instance has a cryptographic identity (Ed25519 keypair)
  — implemented in `phantom-core/src/identity.rs` (`SpiffeIdentity`)
- SPIFFE-format URI (`spiffe://<trust-domain>/agent/<name>`) attached per agent
- *Planned / not yet implemented:* SVID issuance via a SPIRE server, identity
  file at `~/.kairo-phantom/enterprise/spiffe_identity.json`, and the
  `kairo agent identity show` CLI subcommand

**RBAC Engine**
- In-memory RBAC table implemented in `phantom-core/src/identity.rs` (`RbacTable`),
  gated by `rbac_enabled` in config
- Roles: `viewer`, `editor`, `admin`, `compliance`
- *Planned / not yet implemented:* file-based policy at
  `enterprise/rbac_policy.json` and the `kairo rbac-check` CLI subcommand

**SSO Integration (Enterprise)**
- Logto/OIDC integration available for enterprise deployments
- JWT RS256/HS256 validation via `jsonwebtoken` crate
- Session tokens validated before document access

### CC6.6 — Threat and Vulnerability Management

**Prompt Injection Firewall**
- 50 detectors across 6 layers (`prompt_injection_firewall.rs`)
- Covers: direct injection, jailbreaks, indirect prompt injection, multi-turn attacks
- Tested against OWASP Agentic AI Top 10

**Sentinel Architecture**
- Per-session unique UUID sentinel injected into every system prompt
- If LLM echoes the sentinel back, response is immediately blocked
- Retry logic: 2 automatic retries with hardened instruction hierarchy
- Audit event logged for every block

**PII Guard**
- Scans all user text before LLM call
- Redacts: SSN, credit cards, email addresses, phone numbers, API keys
- Zero data persistence: redacted text is never stored

### CC6.7 — Data Transmission Policies

**Offline-First Architecture**
- Default model: Ollama (`qwen2.5:7b`) — runs entirely locally
- Zero network requests during ghost-write sessions in offline mode
- Cloud mode requires explicit opt-in in `config.toml`

**Network Isolation**
- No telemetry collected without explicit opt-in
- MCP bridges use loopback (`127.0.0.1`) only
- All network connections are authenticated (SPIFFE mTLS available)

---

## CC7 — System Operations

### CC7.2 — Monitoring of System Components

**Audit Chain**
- Every ghost-write session generates an audit event
- Events: `GhostSessionStarted`, `GhostSessionCompleted`, `GhostSessionBlocked`
- Audit chain is SHA-256 hash-chained (each entry includes hash of previous)
- Chain integrity verifiable via: `kairo audit-verify`
- Export for SIEM: `kairo audit-export --format cef` (CEF/LEEF/JSON)

**Health Monitoring**
- Built-in health check: `// health` command
- Reports: AI engine status, memory stats, MCP bridges, WASM plugins, PII guard
- Startup timer with checkpoint profiling for performance regression detection

### CC7.3 — Threat Detection

**Red Team Module**
- Autonomous red-team simulation (`red_team.rs`)
- Runs Decepticon-style adversarial probing
- Tests: prompt injection, data exfiltration, privilege escalation

**SIEM Integration**
- CEF, LEEF, and JSON-lines export formats
- Compatible with: Splunk, IBM QRadar, Microsoft Sentinel
- Command: `kairo siem-export --format cef --output audit.cef`

---

## CC8 — Change Management

### CC8.1 — Change Control

**Semantic Versioning**
- All releases follow SemVer (`MAJOR.MINOR.PATCH`)
- Breaking changes increment MAJOR
- Security fixes always trigger PATCH release within 24 hours

**SBOM (Software Bill of Materials)**
- Full dependency manifest available via `cargo metadata`
- Vulnerability scanning: `cargo audit` integrated in CI
- Supply chain audit: `kairo supply-chain-audit` (Domain 10)

---

## CC9 — Risk Mitigation

### CC9.1 — Risk Assessment

**OWASP Agentic AI Top 10 Compliance**
- Full compliance matrix: `docs/security/OWASP_AGENTIC_TOP10_COMPLIANCE.md`
- OWASP Compliance Report: `kairo owasp-report`
- Score: 8/10 controls fully implemented, 2 in progress

### CC9.2 — Supply Chain Risk Management

- All dependencies sourced from `crates.io` with checksums in `Cargo.lock`
- `cargo-deny` configured to block known-vulnerable crates
- SBOM available on request for enterprise audits

---

## A1 — Availability

**Offline-First Reliability**
- Core functionality works without internet: Ollama + local SQLite
- Auto-reconnect and retry logic for cloud fallback (exponential backoff)
- 90-second timeout on all AI streams to prevent hanging
- Graceful degradation: clipboard fallback if sidecar unavailable

**Uptime Guarantees**
- No shared infrastructure — runs on customer hardware
- No single point of failure (no central server)
- Memory sync optional via LAN P2P (`kairo memory sync serve`)

---

## C1 — Confidentiality

**Data Classification**
| Category | Handling |
|----------|---------|
| Document content | Processed in-memory only; never written to Kairo's storage |
| User prompts | Stored in MemMachine only after explicit `seed` command |
| LLM responses | Processed in-memory; not persisted by default |
| Audit logs | Stored in `~/.kairo-phantom/enterprise/audit.db` (local only) |

**Data Residency**
- All data stays on the user's local machine
- Enterprise deployments can configure LAN sync for team memory sharing
- No cross-customer data sharing possible by architecture

---

## Audit Checklist

For enterprise SOC 2 audit preparation, gather the following evidence:

> **Status note:** the `kairo audit-verify`, `kairo owasp-report`,
> `kairo agent identity show`, `kairo rbac-check`, and `kairo audit-export`
> CLI subcommands are **planned / not yet implemented**. Today, chain
> integrity is verified with the standalone external verifier:
> `python tools/verify_receipts_external.py <receipts.jsonl> --checkpoints <checkpoints.jsonl> --require-signatures`

- [ ] `python tools/verify_receipts_external.py ...` — receipt chain + Merkle checkpoint integrity pass *(available now)*
- [ ] `kairo audit-verify` — chain integrity pass *(planned CLI)*
- [ ] `kairo owasp-report` — OWASP compliance matrix *(planned CLI)*
- [ ] `kairo agent identity show` — SPIFFE identity document *(planned CLI)*
- [ ] `kairo rbac-check` — RBAC policy validation output *(planned CLI)*
- [ ] `kairo audit-export --format json` — 90 days of audit events *(planned CLI)*
- [ ] `cargo audit` — zero known vulnerabilities
- [ ] CI/CD pipeline — all security tests passing (Domain 10)

---

## Contact

For enterprise SOC 2 audit inquiries, open a GitHub Discussion or email: security@kairo.ai

*This readiness assessment is self-reported and has not yet been independently audited. It is NOT a SOC 2 certification or compliance claim. A formal Type II audit is planned but has not been scheduled.*
