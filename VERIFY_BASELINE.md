# VERIFY_BASELINE — Fresh-clone verification results

**Date:** 2026-07-08  
**Commit:** 85d0f70  
**Branch:** master  
**Method:** Fresh clone + venv setup + full pytest run

---

## G1: Fresh-clone full pytest

**Command:** `KAIRO_OFFLINE=1 KAIRO_FORCE_CPU=1 KAIRO_SEALED=1 KAIRO_REQUIRE_SEMANTIC=1 python -m pytest tests/*.py --timeout=60 --timeout-method=thread`

**Result:** 886 passed, 6 skipped, 0 failed, 0 errors

Run in 5 parallel batches (to avoid OOM in single process):
- Batch 1 (10 files): 188 passed, 6 skipped
- Batch 2 (10 files): 169 passed
- Batch 3 (10 files): 119 passed
- Batch 4 (10 files): 150 passed
- Batch 5 (17 files): 260 passed

**cargo test --workspace:** UNKNOWN (Rust toolchain not installed in this sandbox; phantom-core builds without Tauri GUI libs but cargo is not available here)

## G2: Test files referenced in README/docs exist

**Result:** 3 MISSING (pre-existing, not introduced by this work)

| File | Status |
|------|--------|
| tests/test_corpus_integrity.py | EXISTS ✓ |
| tests/test_injection_connector.py | MISSING ✗ (referenced in README.md lines 98, 237, 239) |
| tests/test_injection_parity.py | MISSING ✗ (referenced in README.md lines 98, 237, 238) |
| tests/test_oracle_signature.py | MISSING ✗ (referenced in README.md lines 96, 207) |

**Verdict:** README references 3 nonexistent test files. These are pre-existing documentation errors, not introduced by this work. Should be fixed in a future work order or README should be corrected.

## G3: Corpus integrity test

**Command:** `python -m pytest tests/test_corpus_integrity.py -v`

**Result:** 4 passed in 0.35s
- test_corpus_hash_file_exists PASSED
- test_corpus_fingerprint_matches_committed PASSED
- test_corpus_version_is_set PASSED
- test_corpus_integrity_detects_tampering PASSED

**Verdict:** Corpus fingerprint matches committed. ✓

## G4: Release profile is real

**File:** Cargo.toml `[profile.release]`

```toml
[profile.release]
opt-level = 3
lto = "thin"
codegen-units = 16
strip = "symbols"
```

**Verdict:** TRUE — release profile has genuine optimization settings (opt-level=3, thin LTO, symbol stripping). This was fixed in a prior session (was previously opt-level=0, lto=false, strip=none while claiming "full optimization"). ✓

## G5: CI-vs-local parity

**CI workflows:** 15 workflow files in .github/workflows/

**root_suite.yml** (the main test suite):
- CI runs: 4-way shard matrix + e2e shard, with pytest-xdist --dist loadfile
- CI installs: kairo-sidecar/requirements.txt + requirements-test.txt + pytest pytest-asyncio pytest-xdist pytest-timeout anyio
- CI env: KAIRO_OFFLINE=1, KAIRO_FORCE_CPU=1, KAIRO_REQUIRE_SEMANTIC=1
- CI timeout: --timeout=120 --timeout-method=thread, timeout-minutes: 30

**Local runs:** Same env vars, same test files, pytest-timeout installed.

**Gaps:**
- CI uses Python 3.12 (actions/setup-python); local sandbox uses Python 3.12.12 — MATCH
- CI caches model2vec model; local sandbox doesn't have it (KAIRO_OFFLINE=1 uses hash fallback, but KAIRO_REQUIRE_SEMANTIC=1 would fail — however, tests that need embeddings use test mode)
- CI runs cargo test in verify.yml; not run locally (no Rust toolchain in sandbox)
- CI has supply_chain.yml, sealed_no_network.yml, acceptance_gauntlet.yml, gui_gauntlet.yml, gpu-verify.yml — these are separate gates not duplicated locally

**Verdict:** Root test suite parity is GOOD. The main gap is cargo test (no Rust toolchain in sandbox). Other CI workflows (supply chain, sealed network, GUI, GPU) are separate gates.

---

## CI Hang Fix Summary

**Root cause:** `levenshtein_ratio()` in `kernel/core/grounding.py` used a full O(n*m) DP matrix with no length cap. When the ingestor produced a single chunk from a 500-line document (~30k words, ~189k chars), `best_fuzzy_match()` scanned ~30k windows, each calling `levenshtein_ratio` on the full chunk text — quadratic blowup that hung for 6+ hours.

**Hanging tests identified:**
- `tests/test_ipc_robustness.py::TestIPCRobustness::test_oversized_content_handled_without_hang` (shard 4)
- `tests/test_resource_bounds.py::TestResourceBounds::test_large_document_handled_without_oom` (shard 1)

**Layer 1 (fail-fast):** Added pytest-timeout to CI + `--timeout=120 --timeout-method=thread` + `timeout-minutes: 30`

**Layer 2 (production fix):**
- `levenshtein_ratio`: cap inputs to 200 chars, early bail on length ratio < 0.5, rolling rows
- `best_fuzzy_match`: cap windows to 500 with even subsampling
- `kairo/context/compressor.py`: fix UnboundLocalError in fallback path

**Evidence:** Both tests now PASS. Full suite 886 passed, 6 skipped, 0 failed.

---

## Claims Audit

| Claim | Status |
|-------|--------|
| Release profile is optimized (opt-level=3) | TRUE ✓ |
| Corpus fingerprint matches committed | TRUE ✓ |
| 887 tests in root suite | CLOSE — 886 passed + 6 skipped = 892 collected (claim was approximate) |
| Merkle receipts (W7) | TRUE — 17 tests in test_merkle_receipts.py all pass |
| No-fake-green hardening | TRUE — KAIRO_REQUIRE_SEMANTIC=1 enforced in CI |
| README references test_injection_connector.py | FALSE — file does not exist |
| README references test_injection_parity.py | FALSE — file does not exist |
| README references test_oracle_signature.py | FALSE — file does not exist |
