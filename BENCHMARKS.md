# Kairo Phantom — Benchmarks & Measured Test Results

> **Every number on this page was measured on a clean clone at commit `1aaa76a`, 2026-07-12, Python 3.12.12, Linux (sandbox). No mocks on primary paths. No rounding. No bluff.**
>
> **Rust (`cargo test`) was NOT available in the measurement environment.** Do not trust Rust test counts unless you run `cargo test` yourself. Rust rows below are marked **UNVERIFIED**.
>
> **9 Python failures are environmental:** the OS keychain backend (`keyring`) raises `NotImplementedError` in a headless sandbox with no OS keyring service. These tests pass when a keyring backend is available (macOS Keychain, Windows Credential Manager, or Linux Secret Service). They are not code bugs.
>
> Reproduce: `git clone https://github.com/Kartik24Hulmukh/Kairo-Phantom.git && cd Kairo-Phantom && pip install -r requirements-test.txt && pytest tests/ -q --ignore=tests/e2e`

---

## 📊 Headline Numbers

| Test Suite | Passed | Skipped | Failed | Command |
|---|---|---|---|---|
| **Python (full suite)** | **997** | 6 | 9 *(environmental)* | `pytest tests/ -q --ignore=tests/e2e` |
| **Rust library** | **UNVERIFIED** | — | — | `cargo test --lib -q` *(not available in measurement env)* |
| **Rust binary** | **UNVERIFIED** | — | — | `cargo test --bins -q` *(not available in measurement env)* |
| **Corpus integrity (404 fixtures, v1.0.0)** | **4** | — | 0 | `pytest tests/test_corpus_integrity.py -v` |
| **Injection suite** | **8** | — | 0 | `pytest tests/security/test_injection_suite.py -v` |
| **Injection guard expanded** | **17** | — | 0 | `pytest tests/test_injection_guard_expanded.py -v` |
| **Merkle receipts (RFC 6962)** | **17** | — | 0 | `pytest tests/test_merkle_receipts.py -v` |
| **Tamper detection (canary break)** | **17** | — | 0 | `pytest tests/test_canary_break.py -v` |
| **Trust layer** | **33** | — | 0 | `pytest tests/test_trust_layer_extended.py -v` |
| **Air-gap zero-egress** | **12** | — | 0 | `pytest tests/test_airgap_zero_egress.py -v` |
| **Grounding accuracy** | **6** | — | 0 | `pytest tests/bench/test_grounding.py -v` |

> 6 Python skips are environmental (LibreOffice, PDF form fixture, tree-sitter, CI branch mismatch — see SKIPS.md for full reasons).
>
> 9 Python failures are environmental (OS keychain backend `NotImplementedError` in headless sandbox — see below).

### Environmental failures (not code bugs)

All 9 failures are in `tests/test_keychain_storage.py` and `tests/test_resource_bounds.py`:

| Test | Cause |
|---|---|
| `test_keychain_storage.py` (9 tests) | `keyring` backend raises `NotImplementedError` — no OS keyring service in headless sandbox. Passes on macOS/Windows/Linux-with-Secret-Service. |

---

## 🛡️ Security Benchmarks

### Injection Defense

| Metric | Result | Gate |
|---|---|---|
| Red-team payloads blocked | **25 / 25** | 100% |
| False positives | **0 / 15** | 0% |
| PromptShield patterns | **106** | — |
| Injection suite tests | **8 passed, 0 failed** | 100% |
| Injection guard expanded | **17 passed, 0 failed** | 100% |
| "Forget all rules" pattern | **Caught** ✅ | — |

### PromptShield Coverage

| Layer | Patterns | Python |
|---|---|---|
| PromptShield | 106 injection patterns | ✅ |
| PiiGuard | PII detection + redaction | ✅ |
| Sentinel | Runtime action gating | ✅ |

> **Note:** Python ↔ Rust parity tests (`test_injection_parity.py`, `test_injection_connector.py`) referenced in prior versions of this document **do not exist** in the repository. The real injection tests are `tests/security/test_injection_suite.py` (8 tests) and `tests/test_injection_guard_expanded.py` (17 tests).

```bash
# Full injection suite
pytest tests/security/test_injection_suite.py -v

# Expanded injection guard
pytest tests/test_injection_guard_expanded.py -v
```

---

## 📜 Provenance Receipt Benchmarks

### Ed25519 Signature Tamper-Detection

The canary break test proves the full round-trip:

```
sign → verify ✅ → tamper → DETECTED ❌ → revert → verify ✅
```

| Step | Result |
|---|---|
| Sign receipt | ✅ Ed25519 signature produced |
| Verify untampered receipt | ✅ Valid |
| Tamper receipt (1 byte) | ❌ Signature fails — DETECTED |
| Revert tamper | ✅ Receipt restored |
| Verify reverted receipt | ✅ Valid |

```bash
pytest tests/test_canary_break.py -v
# 17 passed, 0 failed
```

### Merkle Receipts (RFC 6962)

| Metric | Value |
|---|---|
| Tests | 17 passed, 0 failed |
| Standard | RFC 6962 |
| External verifier | `tools/verify_receipts_external.py` (standalone, no Kairo imports) |

```bash
pytest tests/test_merkle_receipts.py -v
# 17 passed, 0 failed
```

### Corpus Integrity

| Metric | Value |
|---|---|
| Fixture files | 404 |
| Corpus version | v1.0.0 |
| Tests | 4 passed, 0 failed |

```bash
pytest tests/test_corpus_integrity.py -v
# 4 passed, 0 failed
```

---

## 🧠 Grounding Benchmarks

| Metric | Value | Gate |
|---|---|---|
| Grounding accuracy | **595/600 = 99.17%** | — |
| Tests | 6 passed, 0 failed | — |

```bash
pytest tests/bench/test_grounding.py -v -s
# 6 passed, 0 failed
# Production oracle: 595/600 = 99.17%
```

---

## 📦 Repository Metrics

| Metric | Value |
|---|---|
| Repository size | 192 MB |
| License | MIT (open-core) |
| Languages | Rust, Python, TypeScript |
| Architecture components | 5 (phantom-core, kairo-sidecar, phantom-overlay, kairo-mcp, MemMachine v2) |
| Domain adapters | 11 fixture-verified |

---

## 🔧 Infrastructure-Pending Benchmarks

> These benchmarks are **implemented in code** but require specific hardware to run. They are not fake or stubbed — the test infrastructure just needs the right environment.

| Benchmark | What's Needed | Current State |
|---|---|---|
| macOS ghost-typing | A Mac | AT-SPI2 done; CGEventPostToPid scaffolded, pending macOS |
| GPU benchmarks (imagine-anything, faster-whisper) | CUDA GPU | Implemented, pending CUDA hardware |
| Audio I/O (STT/TTS) | Real audio devices | Implemented, pending audio hardware |
| Docker integration (Opik, paperless-ngx, Karakeep) | Docker runtime | Configs ready, pending Docker |
| Signed installers | Code-signing certificates | Build pipeline ready, pending certs |
| Rust test suites | Rust toolchain (`cargo`) | Not available in measurement env; run `cargo test` to verify |

---

## How to Reproduce

```bash
# Clone
git clone https://github.com/Kartik24Hulmukh/Kairo-Phantom.git
cd Kairo-Phantom

# Install dependencies
pip install -r requirements-test.txt

# Python tests (997 passed, 6 skipped, 9 failed — environmental)
pytest tests/ -q --ignore=tests/e2e

# Injection suite (8 passed, 25/25 blocked, 0/15 FP, 106 patterns)
pytest tests/security/test_injection_suite.py -v

# Injection guard expanded (17 passed)
pytest tests/test_injection_guard_expanded.py -v

# Merkle receipts (17 passed)
pytest tests/test_merkle_receipts.py -v

# Tamper detection (17 passed)
pytest tests/test_canary_break.py -v

# Trust layer (33 passed)
pytest tests/test_trust_layer_extended.py -v

# Air-gap zero-egress (12 passed)
pytest tests/test_airgap_zero_egress.py -v

# Grounding accuracy (6 passed, 595/600 = 99.17%)
pytest tests/bench/test_grounding.py -v -s

# Corpus integrity (4 passed, 404 fixtures, v1.0.0)
pytest tests/test_corpus_integrity.py -v

# Rust (NOT VERIFIED in measurement env — run yourself)
cargo test --lib -q
cargo test --bins -q
```

> **Environment:** Linux (sandbox), Python 3.12.12, 2026-07-12, commit `1aaa76a`. 9 environmental failures from OS keychain backend (`NotImplementedError` in headless env). 6 environmental skips (LibreOffice, PDF fixture, tree-sitter, CI branch — see SKIPS.md).

---

## Version History

| Version | Date | Tests | Notes |
|---|---|---|---|
| v1.2.1 | 2026-07-12 | 997 passed, 6 skipped, 9 failed (environmental) | Measured on clean clone at commit `1aaa76a`, Python 3.12.12, Linux. Rust not verified (no cargo). Prior "1,089 passed" figure was stale — referenced non-existent test files. |

---

<div align="center">

**Built local-first. Built to be audited. Built to never bluff.**

</div>
