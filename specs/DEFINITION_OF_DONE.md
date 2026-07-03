# DEFINITION OF DONE — Kairo Phantom production gate

A capability is DONE only when every item is objectively true and reproducible on a
clean checkout via `make verify`. This is the contract behind every "green" claim.

## 1. Real behaviour, kill-proven
- A test asserts the REAL system outcome (not a mock).
- Kill-proof recorded: intentionally break the code → the test fails → restore → passes.

## 2. Mutation-tested
- Rust: `cargo-mutants` on changed crates → 0 unjustified survivors.
- Python: `mutmut` / `cosmic-ray` on changed modules → 0 unjustified survivors.
- Every survivor is either killed by a new assertion or justified in writing.

## 3. No-skip
- 0 skipped / xfail / `#[ignore]` tests in touched areas without a written waiver
  that itself has an expiry date and a tracking issue.

## 4. No-mock-in-prod (static)
- Semgrep rule (`ci/semgrep_no_mock.yml`) finds no mock/stub/placeholder reachable
  from a production entrypoint. Build fails if it does.

## 5. Deterministic oracle
- The domain oracle passes (see VERIFICATION_ORACLES.md): docx/xlsx/pptx read-back,
  LibreOffice recompute, packet/connection air-gap check, screenshot/UI-state diff,
  CUA Universal-Verifier rubric, C2PA verify.

## 6. Gauntlet scenario
- >=1 end-to-end scenario in the 200+ gauntlet exercises the capability and is green
  with zero skips. Long-horizon capabilities need a multi-step scenario.

## 7. Honest degradation
- If it depends on an external engine (adeu, DeepPresenter, Moonshine, LibreOffice),
  the missing-engine path fails loud or shows a truthful fallback — proven by a test
  that runs with the engine disabled and asserts the honest behaviour.

## 8. Trust artifacts
- Any action that mutates a user file emits a C2PA-compliant provenance receipt
  (crJSON + Ed25519 soft binding) AND an entry in the hash-chained signed audit log.
- Air-gap mode: the connection oracle asserts zero outbound packets for the flow.

## 9. Honesty label
- Domain status (`Real` vs `prompt-only`) is updated in STATUS.md and surfaced in the
  UI. Shipping a prompt-only domain labelled "Real" is a release blocker.

## 10. Observability
- OpenTelemetry span emitted; Sentry breadcrumb on failure; Opik eval logged for
  any LLM/grounding/style step.

## 11. Code provenance (clean-room / IP) — v2
- Every prod source file traces to either (a) an original ADR/spec (clean-room, per
  prompts/15) or (b) a BUNDLE-lane permissive dependency listed in THIRD_PARTY_LICENSES.md.
- `cleanroom_provenance` + `license_gate` CI jobs are green: no AGPL/GPL/no-license code in
  the shipped product, no copied blocks from STUDY sources, attribution complete.

## 12. Claim discipline — v2
- Every user-facing claim touched by this capability is literally true and demoable live in
  <60s (specs/CLAIM_DISCIPLINE.md). No unfalsifiable trust claims, no mislabelled domains.

## Production-ready declaration
Declared ONLY when the full gauntlet passes for real, zero skips, on all supported
platforms in CI, with the acceptance audit (13) signed.
