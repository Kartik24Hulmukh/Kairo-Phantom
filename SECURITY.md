# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | ✅ Active security updates |
| < 0.3   | ⚠️ End of life |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security issues privately:

1. Go to the [GitHub Security Advisories](https://github.com/Kartik24Hulmukh/Kairo-Phantom/security/advisories/new) page for this repository.
2. Click **"Report a vulnerability"**.
3. Fill in the details: affected version, reproduction steps, and potential impact.

We will acknowledge your report within **48 hours** and provide a resolution timeline within **7 days**.

## Security Architecture

Kairo-Phantom is designed with security as a core constraint:

- **Zero telemetry by default.** No data leaves your machine. In sealed mode (`KAIRO_SEALED=1`), zero outbound connections are established — verified by the air-gap oracle (`pytest tests/test_airgap_zero_egress.py`).
- **Reference monitor.** The primary load-bearing security layer gates every action. PromptShield blocks 106 injection patterns; 25/25 red-team payloads blocked, 0/15 false positives.
- **Signed audit trail.** Every action is Ed25519-signed and hash-chained. Tamper any byte → verification fails. Independently verifiable via `tools/verify_receipts_external.py`.
- **Sealed build profile.** Static scan + runtime oracle confirm no network symbols in the sealed build.
- **No vendored secrets.** Kairo-Phantom contains zero hardcoded API keys, tokens, or credentials.

## Disclosure Policy

We follow responsible disclosure. Once a fix is ready, we will:

1. Release a patched version.
2. Publish a GitHub Security Advisory with full details.
3. Credit the reporter (unless they prefer anonymity).
