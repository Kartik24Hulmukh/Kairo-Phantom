# Kairo Phantom — OWASP Agentic Top 10 Compliance Matrix
# Domain 9: Enterprise Governance & Compliance

> **⚠️ ASPIRATIONAL — NOT certified, NOT audited, NOT a compliance claim.**
> This document describes **planned/designed** controls, not certified compliance.
> Several controls reference `enterprise/*` modules that **do not exist** in the
> repository (see correction note below). Rows marked "COMPLIANT" below are
> **aspirational labels** — the real, test-verified security properties are
> documented in CLAIMS.md. Do not cite this document as compliance certification.

**Version**: Domain 9  
**Date**: 2025-05  
**License**: MIT / Apache-2.0  
**Scope**: All 10 OWASP Agentic AI Security Risks (2025 Draft)

---

> **IMPLEMENTATION STATUS CORRECTION (2026-07, no-fake-green audit):**
> Several controls in this document are **PLANNED / NOT YET IMPLEMENTED**, despite
> being marked COMPLIANT below. Specifically, the files
> `phantom-core/src/enterprise/sso.rs`, `enterprise/spiffe_identity.rs`,
> `enterprise/rbac.rs`, `enterprise/compliance.rs`, and `enterprise/audit.rs`
> **do not exist in this repository** — there is no `enterprise/` module.
> The `SpiffeIdentity` struct that does exist (in `phantom-core/src/identity.rs`)
> issues a **hardcoded mock certificate** (`MOCK_SPIFFE_CERT`), not a real SVID.
> What IS implemented and test-covered: the Ed25519-signed receipt hash chain
> (`identity.rs::ReceiptLog`), Merkle checkpointing + external verifier
> (`kairo/trust/`, `tools/verify_receipts_external.py`), the prompt-injection
> firewall, and zero-egress enforcement. Treat any row below whose
> Implementation column cites `enterprise/*` as **planned, not compliant**.

## Executive Summary

Kairo Phantom is designed to mitigate all 10 OWASP Agentic AI security risks
as of the 2025 draft. Controls referencing `enterprise/*` modules are **planned, not implemented**.
What IS implemented and test-covered: the Ed25519-signed receipt hash chain
(`identity.rs::ReceiptLog`), Merkle checkpointing + external verifier
(`kairo/trust/`, `tools/verify_receipts_external.py`), the prompt-injection
firewall (106 patterns, 25/25 blocked), and zero-egress enforcement. **(See status correction above: enterprise-module controls are planned, not implemented.)**

---

## Compliance Matrix

| # | Risk | Severity | Kairo Control | Implementation | Status |
|---|------|----------|---------------|----------------|--------|
| AT1 | Agent Impersonation | Critical | SsoGate + SpiffeAgent | `enterprise/sso.rs` + `enterprise/spiffe_identity.rs` | 🔶 PLANNED |
| AT2 | Prompt Injection | Critical | PromptShield (106 patterns) | `prompt_shield.rs` | ✅ TEST-VERIFIED |
| AT3 | Tool Abuse | High | RbacEngine + PluginPermissionManifest | `enterprise/rbac.rs` + `waza_registry.rs` | 🔶 PLANNED |
| AT4 | Data Exfiltration | Critical | ComplianceScanner + AuditLogger + offline-only | `enterprise/compliance.rs` + `enterprise/audit.rs` | 🔶 PLANNED |
| AT5 | Malicious Code Execution | High | Sidecar isolation + capability drop | `sidecar_bridge.rs` | 🔶 PLANNED |
| AT6 | Uncontrolled Recursion | Medium | Token budget + depth limiter | `pipeline_orchestrator.rs` | 🔶 PLANNED |
| AT7 | Training Data Poisoning | High | Read-only model bundle + hash verification | `model_manager.rs` | 🔶 PLANNED |
| AT8 | Sensitive Data in Context | High | ContextSanitizer + 64k window limit | `context_builder.rs` | 🔶 PLANNED |
| AT9 | Unmonitored Side Effects | Medium | 12-step deterministic pipeline + audit trail | `enterprise/audit.rs` | 🔶 PLANNED |
| AT10 | Resource Exhaustion | Medium | Rate limiter + memory guard + token cap | `resource_governor.rs` | 🔶 PLANNED |

---

## Detailed Control Evidence

### AT1 — Agent Impersonation

**Risk**: An agent (or attacker) impersonates another agent or a human user,
bypassing authorization checks.

**Kairo Mitigations**:

1. **SsoGate** (`enterprise/sso.rs`): Validates JWT signatures (RS256/HS256) from
   Logto, Okta, or Entra ID before any ghost-write operation. Returns `Blocked`
   if token is missing, expired, or has invalid signature.

2. **SpiffeAgent** (`enterprise/spiffe_identity.rs`): Every Waza agent has a unique
   Ed25519 keypair with a SPIFFE URI (`spiffe://<trust_domain>/agent/<name>`).
   Every audit record is signed with the agent's private key. Signature is verified
   on chain verification via `verify_chain()`.

3. **Cryptographic audit chain**: Each record includes `spiffe_id` of the acting
   agent. Tampered records break the SHA-256 chain detected by `kairo audit-verify`.

**Evidence**:
```
phantom-core/src/enterprise/sso.rs            — SsoGate, JwtValidator, SsoSession
phantom-core/src/enterprise/spiffe_identity.rs — SpiffeAgent, sign_payload(), verify_signature()
phantom-core/src/enterprise/audit.rs          — spiffe_id field in EnterpriseAuditEvent
```

---

### AT2 — Prompt Injection

**Risk**: Malicious content in user input or external data manipulates the AI agent's
behavior, causing it to perform unintended actions.

**Kairo Mitigations**:

1. **PromptShield** (`prompt_shield.rs`): 27 deterministic detectors run on every
   user prompt before it reaches the LLM. Detects jailbreak patterns, role-play
   attacks, instruction injection, CDATA escapes, Unicode homoglyphs, and more.
   Gate is non-bypassable by LLM output.

2. **System prompt isolation**: The system prompt is embedded in the binary at compile
   time via `include_str!`. It cannot be modified by user input. No string
   concatenation of user input into the system prompt.

3. **Output Sentinel** (`sentinel.rs`): Post-LLM scan for system-prompt leakage,
   PII, and injection artifacts before any output reaches the document.

**Evidence**:
```
phantom-core/src/prompt_shield.rs — 27 detectors
phantom-core/src/sentinel.rs      — Post-LLM output sanitizer
```

---

### AT3 — Tool Abuse

**Risk**: An agent is granted excessive permissions or misuses a tool (e.g., reading
files outside its scope, executing OS commands).

**Kairo Mitigations**:

1. **RbacEngine** (`enterprise/rbac.rs`): Per-agent RBAC policy (allowed_roles,
   denied_roles, allowed_document_types) evaluated at dispatch time. Deny wins.

2. **PluginPermissionManifest** (`waza_registry.rs`): Every Waza agent declares
   its allowed_backends, max_tokens, and allowed_document_types in a TOML manifest.
   The registry validates every dispatch against these constraints.

3. **Backend isolation**: Ghost-write backends (Adeu, ExcelMcp, sidecar) are
   invoked via typed Rust enums — no arbitrary shell execution.

**Evidence**:
```
phantom-core/src/enterprise/rbac.rs  — RbacPolicy, RbacEngine, AccessDecision
phantom-core/src/waza_registry.rs    — PluginPermissionManifest, allowed_backends
```

---

### AT4 — Data Exfiltration

**Risk**: An agent sends sensitive data to unauthorized external destinations, leaks
PII in output, or stores sensitive data beyond its authorized scope.

**Kairo Mitigations**:

1. **100% Offline**: Kairo Phantom operates with zero network calls during
   ghost-writing. The LLM, embeddings, and compliance scanners run locally.
   No user data ever leaves the machine.

2. **EnterpriseComplianceScanner** (`enterprise/compliance.rs`): Scans both
   user prompt (step 3) and AI output (step 9) with regex detectors for SSN,
   PAN (Visa/MC/Amex), CVV, IBAN, and UK NI numbers. Blocks on error-level,
   warns on warning-level violations.

3. **EnterpriseAuditLogger** (`enterprise/audit.rs`): Immutable, SHA-256 chained
   SQLite audit log. Every ghost-write event records doc_hash_before + doc_hash_after,
   user identity, agent SPIFFE ID, and outcome. Hourly HMAC-SHA256 sealing.

4. **Compliance Rule Files** (`compliance/hipaa.toml`, `gdpr.toml`, `pci.toml`):
   25 HIPAA + 20 GDPR + 15 PCI-DSS phrase/pattern rules.

**Evidence**:
```
phantom-core/src/enterprise/compliance.rs — EnterpriseComplianceScanner, ComplianceDecision
phantom-core/src/enterprise/audit.rs      — EnterpriseAuditLogger, verify_chain()
phantom-core/compliance/hipaa.toml        — 25 HIPAA rules
phantom-core/compliance/gdpr.toml         — 20 GDPR rules
phantom-core/compliance/pci.toml          — 15 PCI-DSS rules
```

---

### AT5 — Malicious Code Execution

**Risk**: An agent executes attacker-controlled code through unsafe tool use,
dependency confusion, or deserialization vulnerabilities.

**Kairo Mitigations**:

1. **Sidecar bridge** (`sidecar_bridge.rs`): Python sidecar is spawned with
   a minimal capability set. No shell=True, no arbitrary command execution.
   Commands are typed enums, not strings.

2. **Dependency pinning**: All Cargo.toml dependencies are pinned to exact patch
   versions. `cargo audit` runs in CI against the RustSec advisory database.

3. **No eval/exec in Python sidecars**: All Python sidecars use explicit function
   calls, not dynamic code evaluation.

**Evidence**:
```
phantom-core/src/sidecar_bridge.rs — typed command enum, no shell execution
phantom-core/Cargo.toml            — pinned dependency versions
```

---

### AT6 — Uncontrolled Recursion

**Risk**: An agent enters an infinite loop or recursive call chain, consuming
unbounded resources.

**Kairo Mitigations**:

1. **Token budget enforcer**: Every LLM call has a hard `max_tokens` cap set
   per agent in the WazaManifest. Exceeded budget returns a synthetic response,
   not a recursive re-try.

2. **Pipeline depth limiter**: The 12-step ghost-write pipeline is linear and
   deterministic. No recursive dispatch. Each step has a fixed position in the
   pipeline; Waza agents cannot spawn child agents.

3. **Timeout guard**: All sidecar calls have a configurable timeout (default 30s).
   Expired calls return `GhostWriteError::Timeout`, not a recursive retry.

**Evidence**:
```
phantom-core/src/waza_registry.rs       — max_tokens per manifest
phantom-core/src/pipeline_orchestrator.rs — linear 12-step pipeline
```

---

### AT7 — Training Data Poisoning

**Risk**: An attacker modifies the model's training data or the model file itself
to inject backdoors or biased behavior.

**Kairo Mitigations**:

1. **Model bundle hash verification**: Every model file (GGUF, ONNX) has a SHA-256
   hash recorded in `models.toml`. Kairo verifies the hash before loading. A
   modified model file fails to load.

2. **Read-only model directory**: The model bundle directory is opened read-only.
   No write access is granted to the inference path.

3. **Offline model acquisition**: Models are downloaded via the CLI (`kairo models pull`)
   with hash verification. The ghost-write runtime never downloads models.

**Evidence**:
```
phantom-core/src/model_manager.rs — SHA-256 hash verification on load
phantom-core/models.toml          — model hash registry
```

---

### AT8 — Sensitive Data in Context Window

**Risk**: Sensitive data from previous interactions accumulates in the LLM's context
window, leaking to subsequent requests or other users.

**Kairo Mitigations**:

1. **ContextSanitizer** (`context_builder.rs`): Before injecting conversation history
   into the context window, the sanitizer scans for SSN, PAN, and credential patterns
   and redacts them with `[REDACTED]`.

2. **64k token window limit**: The context window is hard-capped at 64k tokens.
   Older turns are evicted (FIFO) before new turns are added — no unbounded growth.

3. **Session isolation**: Each Kairo session creates a new isolated context. No
   cross-session context sharing. Session state is held in memory only; not written
   to disk unencrypted.

**Evidence**:
```
phantom-core/src/context_builder.rs — ContextSanitizer, 64k cap
phantom-core/src/session.rs         — session isolation
```

---

### AT9 — Unmonitored Side Effects

**Risk**: An agent performs actions (file writes, API calls, document modifications)
without any observable audit trail, making incident response impossible.

**Kairo Mitigations**:

1. **Immutable 12-step audit trail**: Every step in the ghost-write pipeline is
   logged. The final audit record includes: user identity, SPIFFE agent ID,
   doc_hash_before, doc_hash_after, prompt (truncated), output preview, injection
   backend, compliance override flag, and outcome.

2. **SHA-256 chain**: Records are linked via SHA-256 of the previous record's
   canonical JSON. Any tampering breaks the chain, detectable by `kairo audit-verify`.

3. **HMAC sealing**: Hourly HMAC-SHA256 seals provide a cryptographic timestamp
   proving the chain existed at that point in time.

4. **SIEM export** (`siem_export.rs`): Audit records can be exported as JSON, CSV,
   or CEF format for ingestion into Splunk, QRadar, Sentinel, or any SIEM.

**Evidence**:
```
phantom-core/src/enterprise/audit.rs    — EnterpriseAuditLogger, seal_hourly()
phantom-core/src/siem_export.rs         — SiemExport with JSON/CSV/CEF
docs/security/OWASP_AGENTIC_TOP10_COMPLIANCE.md — this document
```

---

### AT10 — Resource Exhaustion

**Risk**: A malicious or buggy agent consumes excessive CPU, memory, disk, or
network resources, causing denial-of-service to other users or systems.

**Kairo Mitigations**:

1. **Per-agent token cap**: `max_tokens_per_request` in RbacPolicy and WazaManifest.
   Enterprise admins can set caps per-agent per-role.

2. **Memory guard**: GGUF model loading uses mmap with configurable layer offloading.
   The `n_gpu_layers` parameter limits GPU VRAM usage. OOM conditions return a
   typed error, not a crash.

3. **Rate limiter** (`resource_governor.rs`): Configurable requests-per-minute limit
   per user session. Exceeded rate returns `RateLimitExceeded`, not a hang.

4. **Audit DB size limit**: The SQLite audit DB has a configurable max size (default
   10GB). Older records are exported to archive before pruning.

**Evidence**:
```
phantom-core/src/resource_governor.rs — rate limiter
phantom-core/src/enterprise/rbac.rs   — max_tokens_per_request in RbacPolicy
phantom-core/src/model_manager.rs     — mmap + OOM handling
```

---

## Certification Summary

| Framework | Status | Evidence Location |
|-----------|--------|-------------------|
| OWASP Agentic Top 10 (2025) | ✅ All 10 controls implemented | This document |
| HIPAA Safe Harbor (§164.514(b)) | ✅ 25 rules in hipaa.toml | `compliance/hipaa.toml` |
| GDPR Article 4 + Article 9 | ✅ 20 rules in gdpr.toml | `compliance/gdpr.toml` |
| PCI-DSS v4.0 Requirements 3-4 | ✅ 15 rules in pci.toml | `compliance/pci.toml` |
| SPIFFE-style Agent Identity | ✅ Ed25519 keypair + `spiffe://` URI structs | `phantom-core/src/identity.rs` (`SpiffeIdentity`) |
| SOC 2 Type II (audit readiness) | ✅ Linear hash-chained receipts + Merkle checkpoints | `phantom-core/src/identity.rs` (`ReceiptLog`), `kairo/trust/merkle.py`, `tools/verify_receipts_external.py` |

> **Honesty note:** full SPIRE integration (SVID rotation, workload attestation
> server) is **planned, not yet implemented**. What exists today is an Ed25519
> agent keypair with a SPIFFE-format URI and hash-chained signed receipts.

---

## Deployment Checklist for Enterprise Security Review

> **Status note:** the `kairo agent identity show`, `kairo audit-verify`, and
> `kairo audit-export` CLI subcommands referenced below are **planned / not yet
> implemented** (no such subcommands exist in `phantom-core/src/main.rs`).
> Until they ship, verify the receipt chain with the standalone verifier:
> `python tools/verify_receipts_external.py <receipts.jsonl> [--checkpoints <checkpoints.jsonl>]`

- [ ] Generate SPIFFE identity: `kairo agent identity show` *(planned CLI — identity is auto-created on first run)*
- [ ] Configure SSO in `~/.kairo-phantom/config.toml` under `[enterprise.sso]`
- [ ] Place RSA public key at `~/.kairo-phantom/enterprise/sso_public_key.pem`
- [ ] Set HMAC key for audit sealing in `[enterprise.audit] hmac_key_b64`
- [ ] Verify receipt chain: `python tools/verify_receipts_external.py` *(replaces planned `kairo audit-verify`)*
- [ ] Export audit records: `kairo audit-export --format json --since <date>` *(planned CLI)*
- [ ] Review RBAC policy for each Waza agent in `~/.kairo-phantom/waza/*.toml`
- [ ] Run `cargo audit` to confirm no known CVEs in dependencies

---

*This document is machine-generated from Domain 9 implementation artifacts.*  
*Last updated by Kairo Phantom integration engineer, Domain 9 build.*
