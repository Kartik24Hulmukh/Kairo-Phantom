# License Audit — Kairo-Phantom

**Date:** 2026-07-08  
**Auditor:** Autonomous engineering agent (GLM-5.2)  
**License:** MIT (see [LICENSE](../LICENSE))

## 1. Project License

Kairo-Phantom is distributed under the **MIT License**.  
Copyright (c) 2026 Kairo Phantom Contributors.

## 2. Clean-Room Provenance

All shipped source files trace their provenance via:
- `# PROVENANCE: original` — clean-room original work
- `# PROVENANCE: ADR-<n>` — clean-room work per Architecture Decision Record
- `# PROVENANCE: vendored <pkg>@<ver> (MIT)` — vendored from MIT-licensed upstream

CI enforcement: `ci/cleanroom_provenance.yml` checks every file under `src/` 
for a provenance header and verifies referenced ADRs exist.

## 3. Dependency License Audit

### Rust Dependencies (via Cargo.toml workspace)

| Component | License | Compatible with MIT? |
|:---|:---|:---|
| Tokio | MIT | ✅ Yes |
| Serde | MIT / Apache-2.0 | ✅ Yes |
| serde_json | MIT / Apache-2.0 | ✅ Yes |
| anyhow | MIT / Apache-2.0 | ✅ Yes |
| tracing | MIT | ✅ Yes |
| tracing-subscriber | MIT | ✅ Yes |

### Python Dependencies (via requirements-test.txt)

| Component | License | Compatible with MIT? |
|:---|:---|:---|
| pytest | MIT | ✅ Yes |
| hypothesis | MPL-2.0 | ✅ Yes (MPL-2.0 is MIT-compatible for separate works) |
| pdfplumber | MIT | ✅ Yes |
| model2vec | MIT | ✅ Yes |
| python-docx | MIT | ✅ Yes |
| openpyxl | MIT | ✅ Yes |
| python-pptx | MIT / BSD-3-Clause | ✅ Yes |
| cryptography | Apache-2.0 / BSD-3-Clause | ✅ Yes |
| beautifulsoup4 | MIT | ✅ Yes |
| pydantic | MIT | ✅ Yes |
| fastapi | MIT | ✅ Yes |
| duckdb | MIT | ✅ Yes |
| imagehash | MIT | ✅ Yes |
| Pillow | HPND (MIT-like) | ✅ Yes |
| ebooklib | AGPL-3.0 | ⚠️ See below |
| odfpy | Apache-2.0 | ✅ Yes |
| striprtf | MIT | ✅ Yes |
| mammoth | BSD-2-Clause | ✅ Yes |
| litellm | MIT | ✅ Yes |
| sqlite-vec | MIT | ✅ Yes |
| headroom-ai | MIT | ✅ Yes |

### ⚠️ AGPL-3.0 Dependency: ebooklib

**`ebooklib` is licensed under AGPL-3.0.** This is a **copyleft** license that 
is NOT compatible with MIT distribution.

**Status:** ebooklib is listed in `requirements-test.txt` but is NOT imported 
by any shipped production code. It is only used in test/development paths 
for EPUB parsing. The production agent does not import or use ebooklib.

**Action required:** Either:
1. Remove ebooklib from requirements-test.txt if not needed, OR
2. Move it to a separate dev-only requirements file that is not installed 
   in production, OR
3. Replace with an MIT-licensed EPUB parser.

**Current risk:** LOW — ebooklib is not in the production import graph. 
But it should be removed from requirements-test.txt to avoid confusion.

## 4. No-License / Paper Code Audit

Searched for any code copied from:
- No-license repositories (GitHub repos without a LICENSE file)
- Academic paper reference implementations
- AGPL/GPL-licensed code snippets

**Result:** No code copied from no-license or paper-code sources was found. 
All source files carry `PROVENANCE: original` headers. The cleanroom provenance 
CI gate enforces this on every push.

## 5. Forbidden License Check

The following licenses are **forbidden** in shipped production code:
- AGPL-3.0 (copyleft, network-use trigger)
- GPL-3.0 (copyleft)
- GPL-2.0 (copyleft)
- SSPL (Server Side Public License)
- BUSL (Business Source License)
- CC-BY-NC (Non-Commercial)
- Unlicensed (no license file)

**Current violations:** None in production code. 
**Warning:** `ebooklib` (AGPL-3.0) is in requirements-test.txt but not in production imports.

## 6. CI Enforcement

| Gate | Workflow | Status |
|:---|:---|:---|
| Clean-room provenance headers | `ci/cleanroom_provenance.yml` | ✅ Active |
| cargo-deny advisories + licenses | `.github/workflows/supply_chain.yml` | ✅ Active |
| Secret scan (gitleaks + custom) | `.github/workflows/supply_chain.yml` | ✅ Active |
| SBOM generation (CycloneDX) | `.github/workflows/supply_chain.yml` | ✅ Active |

## 7. Conclusion

- **No license violations** in shipped production code.
- **One warning:** `ebooklib` (AGPL-3.0) in requirements-test.txt — not in production imports, should be removed or isolated.
- All shipped source is clean-room original (MIT-licensed).
- CI gates enforce provenance headers, advisory scanning, and license checking on every push.
