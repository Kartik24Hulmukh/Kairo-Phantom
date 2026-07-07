# 1. Kairo-Phantom Audit

## 1.1 What it actually is (verified from source)

Kairo-Phantom is a **local-first autonomous desktop agent** that drives *real* applications (Word, Excel, PowerPoint, IDEs, Figma, browsers) by synthesizing keyboard/mouse input into the live OS accessibility layer, and emits a **cryptographically signed provenance receipt** for every action. It is not a chat app. It is a "hands on your real desktop" agent with a proof layer.

This is a real, large, multi-language system — not vaporware:

| Component | Language | LOC (measured) | Role |
|---|---|---|---|
| `phantom-core` | Rust | 41,975 | The "hands": ghost-typing via Win32 UIAutomation (Windows) / AT-SPI2 (Linux); CUA planner+executor; capture; CRDT/collab |
| `kairo-sidecar` | Python | 82,243 | The "brain": LangGraph orchestration, security triad, MemMachine v2 memory, receipts, air-gap, LLM routing, connectors |
| `kairo-mcp` | Python | (in-tree) | MCP server exposing 12 "domains" to Telegram/Discord/Email |
| `phantom-overlay` | Tauri 2 (Rust+TS) | (in-tree) | Desktop UI overlay + system tray |

Workspace is a Cargo multi-crate + a large Python package. The "12 domains" (Word, Excel, PPT, PDF, Legal, Design, Code, Voice, Media, Memory, Export, Security) are implemented as sidecar modules + Rust injectors, not stubs.

## 1.2 Architecture & data flow (as built)

```
User / connector (Telegram, Discord, Email, Overlay UI)
        │  inbound text  ──►  PromptShield.scan()  (gate BEFORE anything runs)
        ▼
kairo-mcp (MCP server)  ── routes tool calls ──►  kairo-sidecar :7438  (the brain)
        │                                              │
        │                          LangGraph router → intent gate → domain registry
        │                          → oracle_dispatcher (per-domain "oracles" = verifiers)
        │                          → llm_caller / model_router (litellm; Ollama in air-gap)
        │                          → MemMachine v2 (SQLite + model2vec potion-8M recall)
        │                                              │
        │   command_protocol / ipc  ◄─────────────────┘
        ▼
phantom-core (Rust daemon)  ── HumanizedInjector → PlatformInjector
        │   (clipboard-set → focus window → Home+Shift+End+Ctrl+V line-replace)
        ▼
YOUR REAL APPS  ──►  action result read-back  ──►  oracle verifies  ──►  Ed25519 receipt (hash-chained)
```

Key real mechanisms I confirmed in source:
- **Injection strategy (`phantom-core/src/injector.rs`)**: deliberately *not* backspace-based. It sets clipboard first, brings window to top, waits for focus, then `Home → Shift+End → Ctrl+V` to atomically replace the prompt line. This is a mature, focus-race-aware design — the comments show real battle scars.
- **Receipts (`kairo-sidecar/sidecar/sign_oracles.py`, `provenance_emit.py`, `observability/provenance_bridge.py`)**: real `cryptography` Ed25519 keygen/sign/verify over file contents. Hash-chaining (`chain_prev`) is present in the receipt schema.
- **Security triad (`sidecar/safety/`)**: `prompt_shield.py` (209 LOC, HARD+SOFT regex patterns, claims parity with `phantom-core/src/guardrails.rs`), `pii_guard.py` (92 LOC — thin), `bmc_gate.py`, `security_enhanced.py` (423 LOC).
- **CUA stack (`phantom-core/src/cua/`, 3,327 LOC)**: `cua_planner.rs` (845), `cua_executor.rs` (645), `cua_gate.rs` (601), `vlm_bridge.rs` (430), `world_model.rs` (202). A real visual-language-model-driven computer-use loop with a gate and a world model.
- **Collab/CRDT (`phantom-core/src/collaborative/`, `crdt.rs`, `kairo-hocuspocus-server.js`)**: Yjs/`yrs` peer sync — real-time multi-agent/multi-user document editing scaffolding.
- **Connectors/bridges (`sidecar/connectors/`)**: Telegram, Discord, Email, plus bridges to OpenHands, Karakeep, Paperless-ngx.

## 1.3 Strengths (what is genuinely good)

1. **A real proof layer.** Signed, hash-chained receipts for agent actions is a legitimately differentiated primitive. Most agent frameworks have *zero* verifiable provenance. This is the crown jewel.
2. **Real OS-level actuation in Rust.** Ghost-typing via UIAutomation/AT-SPI2 is hard, unglamorous systems work that most competitors fake with screenshots + coordinate clicking. Having it in Rust with a platform-abstraction trait (`PlatformInjector`) is a moat ingredient.
3. **Local-first / air-gap posture.** `KAIRO_AIR_GAP=true`, Ollama/Qwen3 local inference, "zero ungated network calls in core" as a *design constraint* is a real enterprise wedge (legal, healthcare, defense, finance).
4. **Rust↔Python security parity as a discipline.** Even if imperfect, treating the guardrail patterns as a *synced spec* across two runtimes is unusually rigorous.
5. **Oracle/verifier pattern.** Per-domain "oracles" that read back the actual app state to confirm the action happened is the correct way to defeat hallucination. This is the second crown jewel and pairs perfectly with receipts.
6. **Breadth is real.** 12 domains, MCP surface, CRDT collab, VLM CUA — this is a lot of genuinely-built surface, not a thin demo.

## 1.4 Gaps & weaknesses (brutal, verified)

1. **Test claims do not reproduce (CRITICAL).** README: "813 passed, 6 skipped, 0 failed." Reality in a clean env: **795 passed, 60 failed, 7 skipped, 1 collection error.** Named proof files `tests/test_oracle_signature.py` and `tests/test_injection_parity.py` **do not exist**. Failures cluster in `test_replication.py` (11), `test_pack_benchmarks.py` (11), `test_sidecar_lifecycle.py` (5), `test_scope_discipline.py` (5), `test_resource_bounds.py`, `test_concurrency.py`, `test_ipc_robustness.py`, `test_determinism.py`. These are exactly the categories that matter for "production-ready": lifecycle, concurrency, IPC, determinism, resource bounds.
2. **The tamper-detection corpus test FAILS.** `tests/test_corpus_integrity.py::test_corpus_fingerprint_matches_committed` fails on a hash mismatch. The one artifact that underpins "no bluff" is currently red.
3. **"Release" build is a debug build.** `opt-level = 0, lto = false` under `[profile.release]`. Ships slow, large, unstripped binaries. Contradicts every performance/production claim.
4. **Self-certification sprawl.** ~50 root-level markdown "reports" (`PRODUCTION_CERTIFICATION_REPORT.md`, `MASTER_GAUNTLET_REPORT.json`, `RELEASE_REPORT.md`, `PREMORTEM.md`…). This is a classic *claims-exceed-verification* smell. Reviewers trust green CI, not a folder of self-graded certificates.
5. **No real git history.** HEAD is a single squashed commit by a `kairo-build` bot. Impossible to audit how the system evolved; hostile to contributors; weak provenance for an org that sells provenance.
6. **PiiGuard is thin (92 LOC).** For a product claiming "0/50 false positives" PII redaction across legal/medical data, 92 lines of regex is under-built vs the marketing.
7. **Platform coverage is uneven.** macOS ghost-typing is scaffolded only (`CGEventPostToPid` pending hardware). Voice/Media/GPU paths are hardware-gated and thus effectively unverified.
8. **Dependency & bridge sprawl = attack + supply-chain surface.** Bridges to OpenHands/Karakeep/Paperless, `litellm`, `headroom-ai`, `model2vec`, `sqlite-vec`, `duckdb`, Ollama, Tauri, Yjs. Each is a CVE inlet and a licensing question.
9. **Clipboard-based injection is fragile & leaky.** The core inject path mutates the user's system clipboard. That is a data-exfil vector (other apps read clipboard), a race condition source (they wrote a `clipboard_mutex.py` because of it), and a correctness risk on locked/secure fields.
10. **Determinism is claimed but red.** `test_determinism.py` fails. An agent that "shows its work" must be reproducible; non-determinism poisons the receipt's evidentiary value.

## 1.5 Biggest risks before launch (ranked)

| Rank | Risk | Why it's lethal |
|---|---|---|
| 1 | **Credibility collapse** — someone runs the tests, they don't match the badges, and posts it. | The entire brand is "verify it yourself." One reproducible failure thread on HN/Reddit ends the trust story permanently. |
| 2 | **Receipt/oracle integrity failing** (corpus test red, determinism red). | If the proof layer isn't provably correct, the differentiator becomes a liability ("they sign receipts that don't verify"). |
| 3 | **Ghost-typing safety** — an agent with keyboard/clipboard control on real apps can send an email, delete a file, or paste secrets into the wrong window. | One viral "it typed my password into Slack" incident is fatal for a security-positioned product. |
| 4 | **Prompt-injection → real-world action.** Inbound Telegram/email text can steer an agent that has OS control. PromptShield is the only gate; if it's bypassable, injection becomes RCE-on-desktop. | This is the highest-severity security class for *any* actuating agent. |
| 5 | **Performance reality** — unoptimized "release" + Python brain in the hot path. | Ghost-typing latency and end-to-end action time will feel slow; demos will underwhelm. |
| 6 | **Legal exposure** — automating third-party apps (Office, Figma) + driving them headlessly can violate ToS; PII handling touches GDPR/HIPAA. | Enterprise buyers' legal teams will block adoption without clear answers. |

**Bottom line:** Kairo-Phantom is a rare, real, defensible core wrapped in an over-claimed shell. The work is not to "add features" — it is to **make every claim true, make the proof layer bulletproof, and fuse the differentiators into a moat.** The rest of this blueprint does exactly that.
