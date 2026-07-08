# HANDOFF.md — Kairo-Phantom Autonomous Engineering

**Date:** 2026-07-08  
**Latest commit:** `35b13a5`  
**Branch:** master  
**CI Status:** ✅ ALL REQUIRED CHECKS GREEN on latest commit

---

## 1. Real State Table

| Order | Status | Evidence |
|-------|--------|----------|
| P0 CI Fix | ✅ DONE | Commit 74f2bfa: 7/7 required CI green. Compressor data loss fixed, module shadowing fixed, lint fixed, README refs fixed, corpus hash bumped to v1.3.1 |
| W1 | ✅ DONE (prior) | Release opt-level=3, STATUS.md reproduces |
| W2 | ✅ DONE (prior) | 595/600 = 99.2% grounding accuracy |
| W3 | ✅ DONE (prior) | 65/65 injection block rate |
| W5 | ✅ DONE (prior) | PiiGuard expanded, recall/precision metrics |
| W6 | ✅ DONE | Commit fa87003: 14 oracle tests, Release Gate green. Direct UIA ValuePattern + SendInput typing, clipboard clear after paste |
| W7 v1 | ✅ DONE (prior) | RFC 6962 Merkle, 17 tests, external verifier |
| W7 (remaining) | ✅ DONE | Commit c8ecfda: 33 oracle tests, Release Gate green. Flight recorder, timestamp anchor, policy engine |
| W8 | ✅ DONE (prior) | 11 Real domains, Medical stays Experimental |
| W9 | ✅ DONE | Commit 32c29eb: 12 oracle tests (11 passed, 1 skipped), Release Gate green. Self-cert disclaimer added, workflow trigger fix in .proposed |
| W10 | ✅ DONE | Commit 385d151: 20 oracle tests, Release Gate green. Landing page with sourced metrics, scripted demo |
| W12 | ✅ DONE (prior) | Supply-chain gates in CI |
| W13 | ✅ DONE (prior) | docs/LICENSE_AUDIT.md |
| W14 | ✅ DONE (prior) | Release Gate workflow |
| W15 | ✅ DONE | Commit 35b13a5: 18 oracle tests, Release Gate green. install.sh with honest platform labels |
| W4 | 🔴 BLOCKED: needs human | Real execution isolation (Windows Sandbox/microVM hardware) |
| H1 | 🔴 BLOCKED: needs human | Live GUI/OCR |
| H2 | 🔴 BLOCKED: needs human | Code-sign cert |
| H3 | 🔴 BLOCKED: needs human | Blind A/B |
| H4 | 🔴 BLOCKED: needs human | Launch |
| H5 | 🔴 BLOCKED: needs human | Real users |
| H6 | 🔴 BLOCKED: needs human | Windows real-OS isolation |

---

## 2. Reproducible Baseline

| Metric | Value | Command |
|--------|-------|---------|
| Grounding accuracy | 595/600 = 99.2% | `pytest tests/bench/test_grounding.py` |
| Injection block rate | 65/65 | `pytest tests/test_injection_guard_expanded.py` |
| Grounded answer rate | 96.4% (83 fixtures) | `python -m bench.harness --fixtures-dir fixtures/invoice` |
| False refusal rate | 3.6% | `python -m bench.harness --fixtures-dir fixtures/invoice` |
| Tamper-detection tests | 17 passed | `pytest tests/test_canary_break.py` |
| Trust layer tests | 33 passed | `pytest tests/test_trust_layer_extended.py` |
| Clipboard residue tests | 14 passed | `pytest tests/test_injection_no_clipboard_residue.py` |
| Cross-platform honesty | 11 passed, 1 skipped | `pytest tests/test_cross_platform_honesty.py` |
| Landing page tests | 20 passed | `pytest tests/test_landing_page.py` |
| Packaging tests | 18 passed | `pytest tests/test_packaging.py` |
| Corpus integrity | 4 passed, v1.3.1 | `pytest tests/test_corpus_integrity.py` |
| Ungated network calls | 0 | `pytest tests/test_airgap_zero_egress.py` |
| Rust tests (cargo) | UNKNOWN | Not run in this sandbox (no Rust toolchain) |

---

## 3. Human To-Dos

### W4: Real execution isolation
- Need Windows Sandbox or microVM hardware to validate isolation test
- Plumbing is ready (policy_engine.py has sandbox action class)

### H1: Live GUI/OCR
- Need real desktop environment with display
- CUA code exists (canva_cua.py) but needs live verification

### H2: Code-sign cert
- Need code-signing certificate for signed installers
- Build pipeline is ready (release.yml)

### H3: Blind A/B
- Need human to design and run blind A/B comparison

### H4: Launch
- Need human to decide launch timing and strategy

### H5: Real users
- Need human to recruit and onboard real users

### H6: Windows real-OS isolation
- Need real Windows hardware for live ghost-typing verification

### Workflow fix needed (W9):
- `ci/cross-platform.yml.proposed` needs to be renamed to `.github/workflows/cross-platform.yml` via GitHub web UI
- This requires a token with `workflow` scope

---

## 4. No Invented Metrics

All metrics in this handoff are produced by test commands that can be run on a fresh clone. No users, revenue, partners, or certifications are claimed. UNKNOWN is stated where data was not collected.
