# Kairo-Phantom — Branch Protection & Definition of Done (CORRECTED v3)

## BRANCH PROTECTION SETTINGS (enable on `master`)

These are the **exact required status checks** to configure in GitHub Settings →
Branches → Branch protection rules → `master`. Every check below must be set to
**"Require status checks to pass before merging"** and **"Require branches to be
up to date before merging"**.

### Required Status Checks for MERGING PRs (Tier 1 — every push/PR)

| Check Name (job) | Workflow | Why Required |
|---|---|---|
| `🔑 Secret Scan (gitleaks)` | `verify.yml` / `secrets-scan` | A real PAT was leaked before. Blocks any hardcoded secret from merging. |
| `🐍 Python Lint+Format+Types` | `verify.yml` / `python-lint` | Ruff + mypy enforce code quality and type safety. Ratcheted — GREEN on current code. |
| `🐍 Python Tests (CPU, no-skip enforced)` | `verify.yml` / `python-test` | Full CPU-safe test suite passes on Ubuntu. Coverage floor 25% (measured baseline 27%). Zero skips (conftest runtime enforcement). |
| `🐍 Python Tests (Windows, real COM)` | `verify.yml` / `windows-python-test` | Windows-only tests run for real on windows-latest with real win32com. (FIX 2) |
| `🦀 Rust Build+Clippy+Test` | `verify.yml` / `rust` | `cargo fmt --check` + `clippy -D warnings` + `build --release` + `test` for all workspace members EXCEPT phantom-overlay (Tauri). (FIX 1) |
| `🛡️ Supply Chain (pip-audit + cargo-deny + license)` | `verify.yml` / `security` | No new/direct CVEs; known transitive CVEs explicitly reviewed; licenses checked; SBOM generated. |
| `🌐 Cross-Platform Compile (macos-latest)` | `verify.yml` / `cross-compile` | macOS release build compiles (excluding Tauri). |
| `🌐 Cross-Platform Compile (windows-latest)` | `verify.yml` / `cross-compile` | Windows release build compiles (excluding Tauri). |
| `✅ CI Pass (aggregate)` | `verify.yml` / `ci-pass` | Single aggregate check — verifies all above jobs succeeded. |

### RELEASE-ONLY Gate (Tier 2 — NOT a merge-required check)

| Check Name (job) | Workflow | Why NOT Merge-Required |
|---|---|---|
| `✅ GPU Verify Pass (aggregate)` | `gpu-verify.yml` / `gpu-verify-pass` | **RELEASE GATE ONLY.** This runs on `workflow_dispatch` + `schedule` + `workflow_call` only. There is no self-hosted GPU runner yet — requiring it for merges would block every PR forever. It blocks releases via the release workflow's `workflow_call` to `gpu-verify.yml`. |

> **IMPORTANT (ISSUE 12):** `gpu-verify-pass` is **never** a required status check
> for merging PRs to master. It is a release gate only.

### Additional Protection Settings

- **Require pull request reviews before merging**: at least 1 approval.
- **Require review from Code Owners**: enabled (see `CODEOWNERS` file).
- **Dismiss stale pull request approvals when new commits are pushed**: enabled.
- **Require linear history**: enabled (rebase only, no merge commits).
- **Do not allow bypassing the above settings**: enabled for admins too.
- **Restrict who can push to matching branches**: no direct pushes; PRs only.
- **Require conversation resolution before merging**: enabled.

---

## PRODUCTION-READINESS CHECKLIST — "Definition of Done"

A green badge on `master` (Tier 1) + green `gpu-verify-pass` (Tier 2, release)
certifies that ALL of the following is true. Each item maps to the gate that
enforces it.

### 1. Code Quality

| Item | Enforced By | Failure Condition |
|---|---|---|
| Python code passes ruff lint (E9+F) | `python-lint` job | Any ruff violation → red |
| Python code is formatted (ruff format) | `python-lint` job | Any unformatted file → red |
| Python code passes mypy (ratcheted) | `python-lint` job | Any type error in enabled codes → red |
| Rust code is formatted (cargo fmt) | `rust` job | `cargo fmt --check` diff → red |
| Rust code has zero clippy warnings | `rust` job | Any clippy warning → red (`-D warnings`) |

### 2. Tests

| Item | Enforced By | Failure Condition |
|---|---|---|
| Full CPU-safe Python test suite passes (Ubuntu) | `python-test` job | Any test failure → red |
| Zero test skips in tests/ (conftest runtime) | `python-test` + `conftest.py` | Any skip/skipif/xfail in tests/ → red |
| Windows-only tests run for real (real win32com) | `windows-python-test` job | Any test failure on Windows → red |
| no_skip_gates.py is BLOCKING | `python-test` job | Any forbidden skip pattern in repo → red |
| Python coverage ≥ 25% (ratcheted from 27%) | `python-test` job | `--cov-fail-under=25` → red |
| Rust workspace tests pass (excl. Tauri) | `rust` job | Any `cargo test` failure → red |
| Kairo Facts verification passes | `rust` job | `kairo-phantom verify` exits non-zero → red |

### 3. Build

| Item | Enforced By | Failure Condition |
|---|---|---|
| Rust release build succeeds (excl. phantom-overlay) | `rust` + `cross-compile` | `cargo build --release --workspace --exclude phantom-overlay` fails → red |
| macOS release build compiles (excl. Tauri) | `cross-compile` (macos-latest) | Build failure → red |
| Windows release build compiles (excl. Tauri) | `cross-compile` (windows-latest) | Build failure → red |
| Tauri app builds with system deps (release only) | `release.yml` | Tauri build fails on any platform → red |

> **NOTE (FIX 1):** The Tauri crate (`phantom-overlay`) is EXCLUDED from Tier 1
> workspace builds because it requires platform-specific system libraries
> (libwebkit2gtk-4.1-dev, libgtk-3-dev, etc. on Linux) that are not available
> on a clean GitHub-hosted runner. Tauri is built only in `release.yml` where
> the proper system deps are installed per-platform.

### 4. Security & Supply Chain

| Item | Enforced By | Failure Condition |
|---|---|---|
| No hardcoded secrets in repo | `secrets-scan` (gitleaks) | Any secret detected → red |
| No new/direct Python CVEs | `security` (pip-audit) | Any CVE not in `.pip-audit-ignore` → red |
| No new/direct Rust CVEs | `security` (cargo-deny) | Any advisory not in `deny.toml` ignore → red |
| No disallowed licenses | `security` (cargo-deny) | Any GPL/AGPL/SSPL/BUSL license → red |
| No yanked crates in lockfile | `security` (cargo-deny) | Any yanked crate → red |
| SBOM generated (CycloneDX) | `security` (anchore/sbom-action) | SBOM generation fails → red |

### 5. Live Inference (Tier 2 — RELEASE GATE ONLY, not merge)

| Item | Enforced By | Failure Condition |
|---|---|---|
| Qwen2.5-VL-7B vision grounding works on real GPU | `gpu-verify.yml` / `live-vlm-grounding` | `ground_element()` returns no result → red |
| faster-whisper CUDA STT transcribes real audio | `gpu-verify.yml` / `live-stt` | Transcription fails or CUDA unavailable → red |
| embed-anything CLIP produces 512-dim embeddings | `gpu-verify.yml` / `live-embeddings` | `embed_image()` returns None, wrong dim, or all zeros → red |
| Full Domain 9 media suite passes on GPU | `gpu-verify.yml` / `live-domain9-media` | Any test in `test_domain9_media.py` fails → red |

### 6. Artifact Integrity & Release

| Item | Enforced By | Failure Condition |
|---|---|---|
| SBOM regenerated in-run (deterministic) | `release.yml` (sbom-action) | SBOM generation fails → red |
| Ed25519 audit chain verified | `rust` job + `release.yml` | `kairo-phantom verify` fails → red |
| Tauri signing keys configured | Release workflow env | Missing `TAURI_PRIVATE_KEY` secret → release fails |
| CHANGELOG updated for release | `release.yml` (publish-release) | No CHANGELOG entry for tag → release fails |
| SHA-256 checksums generated | `release.yml` | Checksum generation fails → red |

### 7. Reproducibility

| Item | Enforced By | Failure Condition |
|---|---|---|
| Rust toolchain pinned | `rust-toolchain.toml` | Build uses unpinned toolchain → inconsistent |
| All GitHub Actions pinned to commit SHAs | `verify.yml` / `gpu-verify.yml` / `release.yml` | Every `uses:` is a 40-char SHA (FIX 3) |
| Dependencies locked | `Cargo.lock` + `requirements*.txt` | Unlocked deps → non-reproducible build |

> **SHA Pinning (FIX 3):** Every `uses:` in all three workflows is pinned to a
> full 40-character commit SHA with a trailing version comment:
> - `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4`
> - `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5`
> - `dtolnay/rust-toolchain@e97e2d8cc328f1b50210efc529dca0028893a2d9 # v1`
> - `Swatinem/rust-cache@9d47c6ad4b02e050fd481d890b2ea34778fd09d6 # v2.7.8`
> - `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4`
> - `actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4`
> - `actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4`
> - `taiki-e/install-action@682e7d9e49c5e653d371fc6adbda67653461378a # v2`
> - `gitleaks/gitleaks-action@ff581471f0a7c5d94a90ab49a89b61c3c3c4179f # v2.3.9`
> - `anchore/sbom-action@f8b57238804167525748f1ffd0c29c7e4dc6cb7f # v0.17.0`
> - `softprops/action-gh-release@72e2aa257a956c42a15f4887e07f01b9a9f9b1cf # v2.0.9`

---

## What "Green" Means

When the Tier 1 `ci-pass` check is green on `master`, the following is
**guaranteed**:

1. The code compiles and passes all CPU tests (Ubuntu, macOS, Windows) — excluding
   the Tauri crate which requires platform-specific system deps (built in release).
2. No secrets are leaked in the repository.
3. No unreviewed CVEs exist in any dependency (Python or Rust).
4. No disallowed licenses are present.
5. An SBOM has been generated and is available as an artifact.
6. The Ed25519 audit chain is intact and tamper-evident.
7. Python coverage is at or above 25% (ratcheting upward).
8. Zero tests in tests/ are skipped (conftest runtime enforcement).
9. Windows-only tests run for real on windows-latest (real win32com automation).
10. The build is reproducible (pinned toolchains, locked deps, all actions pinned to SHAs).

When the Tier 2 `gpu-verify-pass` is ALSO green (release gate):

11. Live VLM grounding (Qwen2.5-VL-7B) works on real GPU hardware.
12. Live STT (faster-whisper CUDA) transcribes real audio.
13. Live CLIP embeddings (embed-anything) produce correct 512-dim vectors.
14. The full Domain 9 media suite passes on GPU.

If any of these is false, the build is red, and no merge (Tier 1) or release
(Tier 1 + Tier 2) is possible.

---

## NOTE on Rust Coverage (ISSUE 16)

There is no Rust coverage gate in the current CI. Rust coverage measurement
requires `cargo-tarpaulin` or `cargo-llvm-cov`, which need a higher-RAM
environment (the repo's INFRA_PENDING notes they OOM in 3.8 GB). When a Rust
coverage gate is added, it will be documented here with the measured baseline
and ratchet plan.