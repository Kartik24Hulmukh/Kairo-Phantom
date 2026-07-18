# Open production-readiness blockers

**Last updated:** 2026-07-18

These blockers require external hosts, customers, counsel, or infrastructure
that cannot be resolved in code alone. Each is tracked honestly — no
overclaim.

## Code-resolvable (deferred, tracked for next iteration)

1. **OS keychain/HSM key custody** — demo Ed25519 keypairs are file-based.
   `scripts/keychain_store.py` exists for macOS but is not integrated into
   the legal-v3 transaction path. Test key generation must remain available
   for fixtures.

2. **Authenticated OS IPC for legacy daemon/sidecar** — legal-v3 release
   excludes unauthenticated mutation routes, but the legacy daemon/sidecar
   surfaces are not yet OS-authenticated with nonce/expiry/replay protection.

## External (require hosts, customers, counsel, or auditors)

3. **Authenticated OS IPC for legacy daemon/sidecar** — legal-v3 release
   excludes unauthenticated mutation routes, but the legacy daemon/sidecar
   surfaces are not yet OS-authenticated with nonce/expiry/replay protection.
   (Partially code-resolvable — quarantine is in place, full rewrite deferred.)

4. **OS sandboxing for parser/sidecar processes** — no OS-level sandbox
   (seccomp, seatbelt, AppContainer) is applied to the DOCX executor or
   sidecar parser.

5. **Signed Windows/macOS/Linux installers** — no signed installers or
   clean-host validation has been performed.

6. **Full historical Python/Rust regression suite** — cargo/pytest full
   suite requires Rust toolchain and CI runners not available in this
   environment.

7. **External security assessment** — no founder-free clean-room
   reproduction or third-party security review has been conducted.

8. **Rights-cleared partner NDAs and legal-expert adjudication** — no
   real customer documents or legal-expert review exists.

9. **Paid-pilot evidence** — no reviewer-time baseline, second-batch
    demand, or paid-pilot data exists.

10. **Privacy/retention/incident-response legal review** — no external
    privacy/compliance review has been conducted.

11. **CI integration on protected main branch** — the legal-v3-gates
    workflow is added but branch protection rules must be configured
    by the repository administrator.

## Pre-existing overclaims (not introduced by legal-v3)

12. **Pre-existing overclaim language** — `kairo/oracles/production_ops.py`
    contains a CycloneDX SBOM format reference that is not a legal-v3
    claim. This predates legal-v3 and is not in the legal-v3 surface.
    A future cleanup pass should address it.
