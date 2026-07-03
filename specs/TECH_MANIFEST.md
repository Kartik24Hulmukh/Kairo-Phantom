# TECH MANIFEST v2 — adopt / study / avoid (licenses verified in-env 2026-07-03)

Supersedes v1. Existence + license = `[VERIFIED-ENV]` via GitHub API 2026-07-03.
Star magnitudes are **unverified** (the API returned inflated long-tail values) — never
decide on stars. Full table + honesty flags: research/REPO_VERIFICATION_2026-07-03.md.
Bundle/study/avoid rules: specs/CLEANROOM_IP_PROTOCOL.md.

## ADOPT — BUNDLE lane (permissive; may ship in the product, with attribution)
| Tech | License | Use in Kairo |
|---|---|---|
| roboflow/supervision | MIT | Anchor vision leg (trackers/OBB) |
| allenai/olmocr | Apache-2.0 | Anchor OCR leg |
| alibaba/page-agent | MIT | web-forms domain (#12) |
| ggml-org/llama.cpp | MIT | local inference (verify **weight** license separately, MODEL_CARD) |
| headroomlabs-ai/headroom | Apache-2.0 | screen-map token compaction |
| lahfir/agent-desktop | Apache-2.0 | cross-OS AX reference you MAY read as code |
| comet-ml/opik | Apache-2.0 | grounding/style eval (L8) |
| Helicone/helicone | Apache-2.0 | LLM obs, self-host (L8, off in air-gap) |
| microsoft/playwright | Apache-2.0 | L4 gauntlet harness |
| browserbase/stagehand | MIT | L4 agent-driven E2E |
| opensandbox-group/OpenSandbox | Apache-2.0 | parallel gauntlet sandboxes |
| camel-ai/camel · 2FastLabs/agent-squad | Apache-2.0 | optional multi-agent orchestration |
| ianarawjo/ChainForge | MIT | prompt battle-testing (dev) |
| checkly/checkly-cli | Apache-2.0 | synthetic monitoring (L7) |
| Unclecheng-li/VulnClaw | MIT | self-pentest in CI (also security backup wedge) |
| mukul975/Anthropic-Cybersecurity-Skills | Apache-2.0 | injection red-team corpus |
| C2PA spec/libs | open spec | provenance (fast-follow; audit-log first — see prompt 06) |
| **docling** | **MIT (IBM)** ✓verified 07-03 | **PDF domain primary** (layout/tables/reading-order, LLM-ready) — replaces AGPL PyMuPDF |
| **pdfplumber** | **MIT** ✓verified 07-03 | PDF deterministic coordinate/table read-back oracle |
| **pypdf** | BSD-3-Clause | PDF manipulation (merge/split/metadata) |
| **pypdfium2** | BSD-3-Clause (PDFium) | PDF images + render + page objects + annotations/forms (PyMuPDF image side) |
| **pikepdf** | MPL-2.0 (unmodified dep) | PDF content edit / redaction / encryption / attachments |
| **pyHanko** | MIT | PDF digital signatures (PAdES) |
| **turbovec** | **MIT** ✓verified 07-03 | on-device RAG/memory vector index (Google TurboQuant; 10M docs ~4GB) — R1 |
| **microsoft/OmniParser (v2)** | **CC-BY-4.0** ✓verified 07-03 | set-of-marks vision leg for legacy-app grounding (R5); attribution; verify weights |
| Gemma 3n / Phi-4-mini (MIT) / Qwen3 (Apache) / SmolLM3 (Apache) | model-specific | small on-device bases, hardware-tiered (R1) |

### ⚠️ PDF liability note (fix applied)
**PyMuPDF is AGPL-3.0 — removed from the shipped stack.** Do NOT substitute `pdfmux` or
`pymupdf4llm` claiming an "MIT path": they depend on PyMuPDF, and AGPL obligations flow
through a wrapper. `marker` is GPL-3.0 (study only). The permissive stack (Docling +
pdfplumber + pypdf + olmocr) is both **more capable** (layout+table+reading-order for LLM
ingestion) **and** legally clean.

## ADOPT — MPL-2.0 (file-level copyleft; ship as UNMODIFIED external dep only)
| Tech | License | Use |
|---|---|---|
| daijro/camoufox | MPL-2.0 | anti-detect browser IF web domain needs it; do not modify its files |
| axe-core · artillery · syncthing | MPL-2.0 | dev/CI or unmodified dep |

## ADOPT — TOOL lane (dev/CI only; AGPL/GPL/SaaS fine because NOT shipped)
| Tech | License | Use |
|---|---|---|
| grafana/k6 · grafana/xk6-disruptor · grafana/grafana | AGPL-3.0 | L5/L6/L7 in CI + self-host dashboards |
| returntocorp/semgrep | LGPL-2.1 | SAST (L1) |
| github/codeql · snyk/cli · zaproxy | mixed/Apache | L1 SAST/DAST |
| applitools eyes · meticulous-sdk | proprietary/SaaS | L4 visual + record/replay (dev) |
| percy/cli · chromatic-cli · replay-cli · lighthouse-ci · node-clinic | MIT/Apache | L4/L5 |
| vitest · RTL · storybook · msw · pact-js · testcontainers | MIT | L2/L3 |
| opentelemetry-js (Apache) · sentry-javascript (MIT SDK) | Apache/MIT | L7 (off in air-gap) |

## STUDY→REIMPLEMENT — clean-room only (AGPL or NO LICENSE). Copy IDEAS, never code.
| Tech | License | Idea to extract |
|---|---|---|
| AmrDab/clawdcursor | MIT (but reimplement fusion for originality + to add vision leg) | AX→OCR→pixels fusion + safety gate |
| Dilipod/cellar | NOASSERTION | per-element confidence scoring |
| yliust/Tactile · Haruhiyuki/vision-mcp | NOASSERTION | AX-first + vision-fallback ordering |
| Skyvern-AI/skyvern | AGPL-3.0 | web-task decomposition (idea only) — **never bundle** |
| lumina-ai-inc/chunkr | AGPL-3.0 | doc-layout parsing (idea only) |
| VILA-Lab/FigMirror | none | figure-forensics (backup wedge idea) |
| anthropics/knowledge-work-plugins | Apache-2.0 | domain-plugin architecture pattern |
| Fara/CUAVerifierBench · CUWM · CaMeL/Progent/FIDES · EdgeTune · LUMOS | papers | verifier, world-model, injection defense, on-device LoRA, semantic OS |

## AVOID — never bundle, never copy (verified copyleft/liability + optics)
| Tech | License | Reason |
|---|---|---|
| Skyvern (bundle) · chunkr · GLOSSOPETRAE · manushi4/Screenhand · PilotDeck · vibe_figma · bigset | AGPL-3.0 | AGPL: shipping/deriving = source-disclosure obligation |
| MHSanaei/3x-ui · paperless-ngx | GPL-3.0 | GPL bundling + off-thesis/optics |
| any NOASSERTION/None repo as CODE | all-rights-reserved | reimplement instead (prompts/15) |

## DIRECT COMPETITORS to watch (do not bundle)
Lapu AI (closed, horizontal desktop agent) · eigent-ai/eigent (Apache, horizontal "Cowork") ·
fandych/suora (local workbench) · WordLLMs / WordEX-MCP (Word-only). **None combine
domain-depth × provable-trust × on-device sovereignty.** That intersection is Kairo's moat.

## CORRECTION vs v1 (honesty)
- v1 said the grounding-layer market is "crowded / commoditizing." **Verified false:** the
  only grounding repos above ~600 stars are lahfir/agent-desktop and yliust/Tactile; the
  rest are single-digit-to-low-hundreds hobby repos, and several are abandoned. The reason
  to CONSUME grounding (not sell it) is **defensibility + focus**, not crowding.
- v1's "implausible star" flag was mostly stale-intuition: browser-use (102k)/headroom (56k)
  are real. But long-tail 2026 repos DO carry inflated in-env stars — treat all stars as unverified.
