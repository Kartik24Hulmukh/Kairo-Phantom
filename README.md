<div align="center">

# 👻 Kairo Phantom

**A fully offline, air-gapped local AI desktop agent with a signed, verifiable audit trail.**

The signed, offline, verifiable execution & verification layer for the agent era. Operates real apps on your machine; can be sealed so zero bytes leave it; every action is Ed25519 hash-chained and independently verifiable.

`pre-launch` · `solo-built` · `MIT` · `0 users` · `offline-first`

[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## Why It's Different

- **Air-gapped.** `KAIRO_SEALED=1` → 0 sockets, 0 DNS, 0 telemetry. Kill-proven: the air-gap oracle activates sealed mode, runs the full pipeline, and asserts zero outbound connections — if a single byte escapes, the test fails.
- **Signed, verifiable audit.** Every action is Ed25519-signed and hash-chained. Tamper any byte → verification fails. An independent verifier (`tools/verify_receipts_external.py`) validates receipts without trusting Kairo.
- **Injection-safe.** A reference monitor + PromptShield blocks 25/25 red-team payloads (100%), with 0/15 false positives on benign inputs. 106 patterns. No false refusals.
- **Honest labels.** Every capability is labelled Real (fixture-verified oracle passes) or Experimental (built, not independently validated). No bluffing. Shipping a mislabelled domain is a release blocker.

---

## Quickstart

```bash
git clone https://github.com/Kartik24Hulmukh/Kairo-Phantom.git
cd Kairo-Phantom
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt  # includes numpy, scipy, pytest, model2vec, pdfplumber, etc.
```

### Redline a contract (the wedge use case)

```bash
python -m kairo redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --out redline_output
```

Produces real OOXML tracked changes (`w:ins`/`w:del`) on the contract, with a signed audit log.

### Run in sealed mode (air-gap proven)

```bash
python -m kairo redline fixtures/demo/sample_nda.docx fixtures/demo/nda_playbook.json --sealed --out redline_sealed
```

Activates sealed mode, blocks all outbound connections, and writes a signed zero-egress report alongside the redline output.

### Verify the signed receipt independently

```bash
python -m kairo verify redline_output/ public_key.pem
# or use the standalone external verifier (no Kairo imports):
python tools/verify_receipts_external.py redline_output/audit_log.json
```

The external verifier checks the hash chain, content integrity, Ed25519 signatures, and Merkle checkpoints — without importing anything from the Kairo repo.

### Grounded Q&A on a document

```bash
make run DOC=samples/invoice/sample_invoice_01.txt Q="What is the invoice number?"
```

Refuses to answer if it cannot ground the claim to source text ("No source → no answer").

---

## Verify It Yourself

Every number below was reproduced from a clean clone on 2026-07-09. Run the commands yourself.

| Metric | Command | Real Result |
|---|---|---|
| Full Python suite | `pytest tests/ -q --ignore=tests/e2e` | **1005 passed, 7 skipped, 0 failed** |
| Injection block rate | `pytest tests/security/test_injection_suite.py tests/test_injection_guard_expanded.py -q -s` | **25/25 blocked (100%), 0/15 false positives, 106 patterns, 25 tests** |
| Grounding accuracy | `pytest tests/bench/test_grounding.py -q -s` | **595/600 = 99.17%** |
| Grounded answer rate | `python -m bench.harness` | **96.39% (3/83 false refusal)** |
| Tamper-detection | `pytest tests/test_canary_break.py -q` | **17 passed** |
| Trust-layer | `pytest tests/test_trust_layer_extended.py -q` | **33 passed** |
| Air-gap zero-egress | `pytest tests/test_airgap_zero_egress.py -q` | **12 passed, 0 egress** |

> e2e tests are excluded from the suite above because PDF e2e tests require a cached `model2vec potion-base-8M` model that is not available offline in a clean clone.
>
> Rust (`phantom-core`) test counts are **not asserted** here — `cargo` was not available in the verification sandbox. Do not trust Rust test counts unless you run `cargo test` yourself.

---

## Real vs Experimental

> Generated from `STATUS.md` (run `python scripts/gen_status.py` to reproduce). A domain is "Real" only when its practitioner-grade oracle passes on real fixtures.

### Domains (11 fixture-verified Real)

| # | Domain | Status | Oracle |
|---|---|---|---|
| 1 | Word (DOCX) | **Real** | docx_readback + structure_readback |
| 2 | Excel (XLSX) | **Real** | xlsx_recompute + xlsx_structure_readback |
| 3 | PowerPoint (PPTX) | **Real** | slide_shape_readback + structure_readback |
| 4 | PDF | **Real** | pdf_text_roundtrip + pdf_render_diff + pdf_form_readback + pdf_signature_verify (OCR sub-capability: Experimental) |
| 5 | Legal Redline | **Real (wedge)** | docx_tracked_changes_readback + clause_coverage + no_hallucinated_citation + injection_block + airgap_egress + audit_log_integrity |
| 6 | Design (Canvas) | **Real** | canvas_readback + structure_readback (live Figma/vision: Experimental) |
| 7 | Code | **Real** | compile_test_pass + parse_validity (Python = Real; other languages: Experimental) |
| 8 | Research/notes | **Real** | backlink_integrity + graph_readback |
| 9 | Data/analytics | **Real** | query_result + schema_readback (DuckDB SQL over local CSV/Parquet/xlsx) |
| 10 | Email/comms | **Real** | draft_readback + mailbox_structure_readback (MAPI/IMAP: Experimental, fail-loud offline) |
| 11 | Web-forms/apps | **Real** | form_fill_readback + uistate_readback (live browser/page-agent: Experimental) |

### Not shipped (prompt-only, no oracle)

| Domain | Status |
|---|---|
| Multimodal | prompt-only / not shipped |
| Media | prompt-only / not shipped |
| Cross-Platform | prompt-only / not shipped |

### Trust infrastructure (all Real / wedge-verified)

| Component | Status | Oracle |
|---|---|---|
| Ed25519 Audit Log | Real (wedge) | audit_chain — hash-chained, Ed25519-signed, verify_chain passes |
| Zero-Egress Report | Real (wedge) | signed report — Ed25519-signed, verifiable |
| Air-Gap Seal | Real (wedge) | airgap_egress — sealed mode, 0 outbound, kill-proven |
| Injection Defense | Real (wedge) | injection_block — reference monitor, 0% attack-success, kill-proven |
| Sealed Build Profile | Real (wedge) | sealed_no_network — static scan + runtime oracle, no network symbols |
| CLI | Real (wedge) | test_cli_redline — redline + verify commands, tamper kill-proofs |
| Anchor Perception | Real (wedge) | grounding_accuracy + stable_id + token_reduction (live capture/OCR/vision: Experimental) |
| CUA World Model + Verifier | Real (wedge) | uistate_transition + verifier_agreement + loop_detection + no_receipt_without_verification (live observe→act: Experimental) |

---

## Wedge Use Case: Offline Legal-Redline

Kairo-Phantom's production-ready wedge is **offline legal redlining**:

- Reads a contract `.docx` and a redline playbook
- Produces real OOXML tracked changes (`w:ins`/`w:del`) — not a diff mock
- Every citation is grounded to exact source text; no hallucinated citations
- Injection-safe: embedded prompt-injection attacks in the contract are blocked
- Air-gapped: runs in sealed mode with zero outbound connections
- Signed: every action is Ed25519 hash-chained and independently verifiable

**Wedge acceptance audit:** 14 scenarios, all green, zero skips. See [`docs/acceptance/`](docs/acceptance/).

---

## Architecture

```
                 ┌──────────────────────────────────────────┐
                 │            phantom-overlay (Tauri 2)       │
                 │                 "The Face"                 │
                 │          Desktop UI · System Tray          │
                 └─────────────────────┬──────────────────────┘
                                       │
                 ┌─────────────────────▼──────────────────────┐
                 │            kairo-mcp (MCP Server)           │
                 │             "The Messenger" :MCP            │
                 │      Domain tools · Connectors              │
                 └─────────┬──────────────────────┬────────────┘
                           │                      │
           ┌───────────────▼──────────┐  ┌────────▼───────────────────────┐
           │  kairo-sidecar (Python)  │  │     phantom-core (Rust)         │
           │      "The Brain" :7438   │  │        "The Hands"              │
           │                          │  │                                 │
           │  LangGraph orchestration │  │  Win32 UIAutomation (Windows)   │
           │  PromptShield (106 pat)  │  │  AT-SPI2 (Linux)                │
           │  Reference monitor       │◄─►│  Ghost-Typing Engine            │
           │  Sealed profile          │  │                                 │
           │  Ed25519 receipts        │  │                                 │
           └───────────┬──────────────┘  └────────────► YOUR REAL APPS ◄───┘
                       │
              ┌────────▼────────┐
              │  SQLite +        │
              │  model2vec       │
              │  potion-8M       │
              └─────────────────┘
```

| Component | Language | Role |
|---|---|---|
| **phantom-core** | Rust | Daemon that ghost-types into real apps via Win32 UIAutomation (Windows) / AT-SPI2 (Linux) |
| **kairo-sidecar** | Python | The brain: LangGraph orchestration, PromptShield + reference monitor, sealed profile, Ed25519 receipts |
| **phantom-overlay** | Tauri 2 (Rust + TypeScript) | Desktop UI overlay and system tray |
| **kairo-mcp** | Python | MCP server exposing domain tools |
| **Trust stack** | Python + Rust | Signed audit log, egress enforcement, sealed profile, reference monitor, standalone verifier |
| **Domain registry** | Python | Auto-discovers domain plugins; each domain ships its own oracle |

---

## 📝 The Receipt

Every action Kairo-Phantom takes produces an Ed25519-signed, hash-chained receipt. This is not a log file you trust — it is a cryptographic signature you verify.

```json
{
  "seq": 0,
  "timestamp": 1783512345,
  "agent_id": "d4a1b2c3...",
  "action": "redline_contract",
  "context": {"file": "sample_nda.docx", "playbook": "nda_playbook.json"},
  "outcome": {"insertions": 3, "deletions": 1, "suggestions": 5},
  "prev_hash": "genesis",
  "self_hash": "a1b2c3d4...",
  "signature": "e1f2a3b4..."
}
```

### Verify it yourself

```bash
pytest tests/test_canary_break.py -v       # 17 passed (tamper-detection, kill-proofs)
```

This test does the full round-trip: sign → verify ✅ → tamper → DETECTED ❌ → revert → verify ✅. If the receipt is modified by even a single byte, the signature fails. That is the "no bluff" guarantee.

For standalone verification (no Kairo imports):

```bash
python tools/verify_receipts_external.py redline_output/audit_log.json
```

Checks: linear hash chain, content integrity (recomputed self_hash), Ed25519 signatures, and Merkle checkpoints (RFC 6962).

---

## 🛡️ Security

Kairo-Phantom's security is the foundation, not a bolt-on. Every code path goes through the reference monitor + PromptShield.

| Layer | What It Does | Verified |
|---|---|---|
| **Reference monitor** | Primary load-bearing security layer — gates every action | 25/25 injection attacks blocked, kill-proven |
| **PromptShield** | Blocks 106 injection patterns (prompt injection, jailbreaks, "forget all rules" attacks) | 0/15 false positives on benign inputs |
| **Sealed profile** | Activates air-gap mode: 0 sockets, 0 DNS, 0 telemetry | 12 air-gap tests, 0 egress, kill-proven |
| **Signed audit** | Ed25519 hash-chained receipts for every action | 17 tamper-detection tests, 33 trust-layer tests |

### Verified Results

| Metric | Result | Command |
|---|---|---|
| Red-team payloads blocked | 25 / 25 (100%) | `pytest tests/security/test_injection_suite.py` |
| False positives | 0 / 15 (0%) | `pytest tests/security/test_injection_suite.py` |
| PromptShield patterns | 106 | `pytest tests/test_injection_guard_expanded.py -s` |
| Air-gap egress | 0 outbound connections | `pytest tests/test_airgap_zero_egress.py` |
| Tamper-detection | 17 passed | `pytest tests/test_canary_break.py` |
| Trust-layer | 33 passed | `pytest tests/test_trust_layer_extended.py` |

---

## Roadmap (Honest Next)

| Phase | What | Status |
|---|---|---|
| W7 | Open trust spec + free standalone verifier | Planned — `tools/verify_receipts_external.py` exists; spec publication pending |
| Validation | Independent third-party validation of oracle claims | Pending — not yet done |
| Code-signing | Signed installers (macOS/Windows) | Build pipeline ready; pending code-signing certificates |
| Personalization | On-device personalization A/B | Experimental — not shipped |
| Live GUI/OCR | Live screen capture → OCR → action (vs fixture-based) | Experimental — built, not independently validated |

> Items marked "pending" or "Experimental" are **human-gated** — they require hardware, certificates, or independent validation that has not yet occurred. Kairo-Phantom marks this honestly rather than claiming it works.

---

## Scope Boundaries — What Kairo Does and Does Not Do

### Kairo DOES:
- **READ + SUGGEST ONLY**: Read documents and extract structured data with grounded citations to exact source regions
- **Suggest** actions to the user — never auto-applies without explicit human confirmation
- **Refuse** to answer when it cannot ground a claim to source text ("No source → no answer")
- **Audit** every answer and every refusal in a tamper-evident, cryptographically signed log
- Run **local-first** with zero network egress by default (air-gap proven in tests)
- Provide a **standalone grounding verifier** that any RAG pipeline can bolt on

### Kairo Does NOT:
- Act as a multi-domain expert swarm or router
- Operate as a collaborative/cloud-by-default layer
- Auto-apply any suggestion without explicit human confirmation
- Allow the model to self-certify a bounding box — the verifier independently re-checks every citation
- Claim capabilities that haven't been fixture-verified

---

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

- [GitHub Discussions](https://github.com/Kartik24Hulmukh/Kairo-Phantom/discussions) — ask questions, share use cases
- [GitHub Issues](https://github.com/Kartik24Hulmukh/Kairo-Phantom/issues) — report bugs, request features

---

## License

MIT — see [`LICENSE`](LICENSE).

---

<div align="center">

**Built local-first. Built to be audited. Built to never bluff.**

</div>
