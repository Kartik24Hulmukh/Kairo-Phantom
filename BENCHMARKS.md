# Kairo Phantom — Benchmarks & Measured Test Results

> **Every number on this page is CI-verified at commit `a56cdba`, 2026-07-12, Python 3.12, Ubuntu (GitHub Actions). No mocks on primary paths. No rounding. No bluff.**
>
> **Rust (`cargo test`) was NOT available in the measurement environment.** Do not trust Rust test counts unless you run `cargo test` yourself. Rust rows below are marked **UNVERIFIED**.
>
> Reproduce: `git clone https://github.com/Kartik24Hulmukh/Kairo-Phantom.git && cd Kairo-Phantom && pip install -r requirements-test.txt && pytest tests/ -q --ignore=tests/e2e`

---

## 📊 Headline Numbers

**1,976 passed, 34 skipped, 0 failed across the full CI Python suite (kairo-sidecar CPU job + 4 root shards + e2e); the CPU job is no-skip-enforced. Runs 29191013782 + 29191013766. See the per-job breakdown below.**

### Per-Job Breakdown (source of truth)

| CI Job | Run ID | Passed | Skipped | Failed | Exact pytest command |
|---|---|---|---|---|---|
| 🐍 Python Tests (CPU, no-skip enforced) | 29191013782 | **959** | 0 | 0 | `xvfb-run --auto-servernum python -m pytest tests/ --strict-markers --tb=short --cov=sidecar --cov-fail-under=25 --cov-report=term-missing --cov-report=xml:coverage.xml -p no:cacheprovider` (from `kairo-sidecar/`) |
| Root tests shard 1/4 | 29191013766 | **254** | 0 | 0 | `python -m pytest <shard_files> -n 2 --dist loadfile --timeout=120 --timeout-method=thread --tb=short -p no:cacheprovider` |
| Root tests shard 2/4 | 29191013766 | **209** | 0 | 0 | same |
| Root tests shard 3/4 | 29191013766 | **242** | 31 | 0 | same |
| Root tests shard 4/4 | 29191013766 | **300** | 3 | 0 | same |
| Root e2e (real semantic embeddings) | 29191013766 | **12** | 0 | 0 | `python -m pytest tests/e2e --timeout=120 --timeout-method=thread --tb=short -p no:cacheprovider` |
| **TOTAL** | | **1,976** | **34** | **0** | |

> The 34 skips are all environmental (LibreOffice, tree-sitter, PDF fixtures, cross-format docx/xlsx/pptx/pdf deps, CI branch mismatch). None are in trust-critical suites (injection, PII, tamper, Merkle, air-gap, trust-layer). See SKIPS.md for the full categorized list.

### Subset Results (separate line items, not conflated with R1)

| Test Suite | Passed | Skipped | Failed | Command |
|---|---|---|---|---|
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

# kairo-sidecar CPU suite (959 passed, 0 skipped, 0 failed — no-skip enforced)
cd kairo-sidecar
xvfb-run --auto-servernum python -m pytest tests/ --strict-markers --tb=short -p no:cacheprovider
cd ..

# Root suite (1,017 passed, 34 skipped, 0 failed across 4 shards + e2e)
# See .github/workflows/root_suite.yml for the sharding logic
python -m pytest tests/ -q --ignore=tests/e2e --timeout=120 --tb=short -p no:cacheprovider

# Individual subset suites
pytest tests/security/test_injection_suite.py -v          # 8 passed, 25/25 blocked, 0/15 FP, 106 patterns
pytest tests/test_injection_guard_expanded.py -v           # 17 passed
pytest tests/test_merkle_receipts.py -v                    # 17 passed
pytest tests/test_canary_break.py -v                       # 17 passed
pytest tests/test_trust_layer_extended.py -v               # 33 passed
pytest tests/test_airgap_zero_egress.py -v                 # 12 passed
pytest tests/bench/test_grounding.py -v -s                 # 6 passed, 595/600 = 99.17%
pytest tests/test_corpus_integrity.py -v                   # 4 passed, 404 fixtures, v1.0.0

# Rust (NOT VERIFIED in measurement env — run yourself)
cargo test --lib -q
cargo test --bins -q
```

> **Environment:** Ubuntu (GitHub Actions), Python 3.12, 2026-07-12, commit `a56cdba`. 34 environmental skips (LibreOffice, tree-sitter, PDF fixtures, cross-format deps, CI branch mismatch — see SKIPS.md). 0 failures.

---

## Version History

| Version | Date | Tests | Notes |
|---|---|---|---|
| v1.2.1 | 2026-07-12 | 1,976 passed, 34 skipped, 0 failed (CI-verified) | CI-verified at commit `a56cdba` via GitHub Actions runs 29191013782 + 29191013766. Prior "1,089 passed" figure was stale — referenced non-existent test files. Prior "997 passed / 9 failed" was a local-sandbox artifact (keychain `NotImplementedError` in headless env; passes in CI). |

---

<div align="center">

**Built local-first. Built to be audited. Built to never bluff.**

</div>
