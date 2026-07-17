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

2. **DSSE/in-toto portable envelopes** — JSON Schema 2020-12 schemas exist
   in `schemas/legal_v3/` but evidence bundles are not yet wrapped in
   DSSE/in-toto statements for portable third-party verification.

3. **Trust-policy input for verifier** — `verify_bundle` uses hardcoded
   allowlists. A configurable trust-policy file (allowed clauses, key
   trust roots, expiry policy) should be added as a verifier input.

## External (require hosts, customers, counsel, or auditors)

4. **Authenticated OS IPC for legacy daemon/sidecar** — legal-v3 release
   excludes unauthenticated mutation routes, but the legacy daemon/sidecar
   surfaces are not yet OS-authenticated with nonce/expiry/replay protection.

5. **OS sandboxing for parser/sidecar processes** — no OS-level sandbox
   (seccomp, seatbelt, AppContainer) is applied to the DOCX executor or
   sidecar parser.

6. **Signed Windows/macOS/Linux installers** — no signed installers or
   clean-host validation has been performed.

7. **Full historical Python/Rust regression suite** — cargo/pytest full
   suite requires Rust toolchain and CI runners not available in this
   environment.

8. **External security assessment** — no founder-free clean-room
   reproduction or third-party security review has been conducted.

9. **Rights-cleared partner NDAs and legal-expert adjudication** — no
   real customer documents or legal-expert review exists.

10. **Paid-pilot evidence** — no reviewer-time baseline, second-batch
    demand, or paid-pilot data exists.

11. **Privacy/retention/incident-response legal review** — no external
    privacy/compliance review has been conducted.

12. **CI integration on protected main branch** — the legal-v3-gates
    workflow is added but branch protection rules must be configured
    by the repository administrator.
