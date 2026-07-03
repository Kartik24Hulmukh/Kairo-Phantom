# TECH LEVERAGE MATRIX — best idea from each repo → how Kairo absorbs it

Read with CLEANROOM_IP_PROTOCOL.md. Column **Lane**: BUNDLE (ship the dep) ·
REIMPL (clean-room from spec) · TOOL (CI/dev only) · IGNORE (off-thesis).
Column **Model**: which frontier context does the work (see prompts/14):
`Opus` = Opus 4.8 (architecture, spec authoring, hard reasoning, security);
`GLM` = GLM 5.2 (high-volume implementation, refactors, test generation, cheap loops).

## Perception & grounding (Anchor substrate)
| Repo | Best thing to take | Lane | Model | How Kairo makes it 100x better |
|---|---|---|---|---|
| AmrDab/clawdcursor | AX-tree→OCR→pixels fusion + single safety gate | REIMPL | Opus spec, GLM impl | Add a **vision leg** (supervision) the AX-only tools lack → works on canvas/GPU/Citrix where they go blind |
| lahfir/agent-desktop | Apache-licensed cross-OS AX traversal | BUNDLE/REIMPL | GLM | Reference for Win UIA / macOS AX / Linux AT-SPI parity; wrap behind one interface |
| roboflow/supervision | detections + **trackers (stable ids across frames)** + OBB anchors | BUNDLE | GLM | Trackers give stable element ids during animation; OBB handles rotated canvas objects |
| allenai/olmocr | high-accuracy document/screen OCR | BUNDLE | GLM | OCR leg of fusion; feeds tainted-content pipeline |
| headroomlabs-ai/headroom | screen-map **token compaction** | BUNDLE | Opus tune | The measurable "≥70% fewer tokens vs raw screenshot" claim (attacks the 45x cost pain) |
| Dilipod/cellar | 5-stream fusion + **per-element confidence scores** | REIMPL (no license) | Opus | Confidence-weighted arbitration between AX/OCR/vision legs |
| yliust/Tactile · Haruhiyuki/vision-mcp | AX-first + vision-fallback ordering | REIMPL (no license) | Opus | Informs the fusion arbitration policy only |
| alibaba/page-agent | in-page browser GUI agent | BUNDLE | GLM | Web-forms domain (#12) |

## CUA world-model + verification
| Source | Best thing | Lane | Model | Upgrade |
|---|---|---|---|---|
| Microsoft/Fara + CUAVerifierBench (paper) | rubric-based Universal Verifier (process+outcome) | REIMPL | Opus | Verify BEFORE emitting any receipt; kill-proof the verifier |
| Computer-Use World Model (paper) | predict-then-act next-UI-state | REIMPL | Opus | `world_model.predict()` gate: refuse actions whose predicted state fails a precondition |
| browser-use / stagehand | agent-driven E2E loop shape | BUNDLE (tests) | GLM | Used as the L4 gauntlet driver, not in prod |

## Security (out-of-band injection defense)
| Source | Best thing | Lane | Model | Upgrade |
|---|---|---|---|---|
| CaMeL / Progent / FIDES / RTBAS (papers) | capabilities + taint + privileged-planner quarantine (attack-success ~40%→~4-5%) | REIMPL | Opus | Perceived content is TAINTED; can inform, never authorize. Report adaptive-attack numbers honestly |
| mukul975/Anthropic-Cybersecurity-Skills | mapped skill taxonomy | BUNDLE (ref) | GLM | Red-team corpus generator for the injection oracle |
| Unclecheng-li/VulnClaw | local pentest-agent loop | BUNDLE | GLM | Self-test Kairo's own attack surface in CI |

## Provenance & trust
| Source | Best thing | Lane | Model | Upgrade |
|---|---|---|---|---|
| C2PA spec 2.4 | Content Credentials (crJSON + soft binding) | REIMPL (open spec) | Opus | **v1 ships hash-chained signed audit log first** (verifiable today); C2PA doc-receipts as fast-follow once verifiers exist (see fix G6) |
| syncthing (pattern) | provable P2P/LAN sync | REIMPL (MPL) | GLM | Only if collaboration/registry needs sync |

## Domain engines (real, not prompt-only)
| Source | Best thing | Lane | Model | Upgrade |
|---|---|---|---|---|
| python-docx / openpyxl / python-pptx (libs) | real file mutation + read-back | BUNDLE | GLM | Each domain gets a deterministic read-back oracle |
| **docling (MIT, IBM) + pdfplumber (MIT) + pypdf (BSD) + olmocr (Apache)** | permissive PDF layout/table/OCR/manipulation | BUNDLE | GLM | **Replaces AGPL PyMuPDF**; Docling gives layout+table+reading-order for LLM, pdfplumber gives deterministic coords for the oracle. Avoid pdfmux/pymupdf4llm (AGPL passthrough) + marker (GPL) |
| LibreOffice headless (tool) | **recompute Excel VALUES** (not formula strings) | TOOL | GLM | Fixes the "formula-string ≠ value" bug (fix in prompt 07) |
| anthropics/knowledge-work-plugins | domain-plugin architecture pattern | REIMPL (ref) | Opus | Shape of the Waza specialist marketplace |
| alibaba/page-agent | web forms | BUNDLE | GLM | domain #12 |

## Personalization (the moat — reframed as data sovereignty, fix G5)
| Source | Best thing | Lane | Model | Upgrade |
|---|---|---|---|---|
| EdgeTune (paper) | efficient on-device LoRA personalization | REIMPL | Opus spec, GLM impl | Train on user's own docs, on-device; **moat = data the org legally can't send to cloud**, not "better voice" |
| ggml-org/llama.cpp | local inference + LoRA runtime | BUNDLE | GLM | Default engine; verify base-weight license in MODEL_CARD |

## Eval, obs, orchestration (dev/prod support)
| Source | Best thing | Lane | Model | Upgrade |
|---|---|---|---|---|
| comet-ml/opik | grounding/style eval as first-class metric | BUNDLE | GLM | Regression gate on grounding accuracy per commit |
| Helicone/helicone | LLM-call obs (self-host) | BUNDLE | GLM | Off in air-gap; on in dev |
| camel-ai/camel · 2FastLabs/agent-squad | multi-agent orchestration (Apache) | BUNDLE (opt) | GLM | Only if planning needs multi-agent; prefer simplest path |
| ianarawjo/ChainForge | prompt battle-testing | TOOL | GLM | Harden the grounding/router prompts |
| opensandbox-group/OpenSandbox | parallel sandboxes | BUNDLE | GLM | Run the 200-gauntlet in parallel |
| latent-spaces/brag | build→launch video | TOOL (no license) | — | Make the hero demo video; do not bundle |

## L1–L8 quality pipeline (external tools — the engineering moat)
axe-core, semgrep, codeql, gitleaks, zaproxy, snyk (L1) · vitest/RTL/storybook/msw (L2) ·
pact-js/testcontainers (L3) · playwright/percy/chromatic/meticulous/replay (L4) ·
k6/artillery/lighthouse-ci/node-clinic (L5) · xk6-disruptor (L6) · otel/sentry/grafana/checkly (L7) ·
opik/helicone (L8). **All TOOL lane** — run in CI, never shipped. See ANCHOR/roadmap §6.

## IGNORE (off-thesis; do not spend time)
ECC, hermes-agent, gbrain, get-shit-done, oh-my-openagent, oh-my-pi, ruflo, paperclip, squad,
cmux, LoongForge, mantishack, gajae-code, ponytail, claw-code, worldmonitor, tmax,
500-AI-Agents-Projects, claude-video, BMAD-METHOD, kagent (K8s), 3x-ui, bigset, karakeep,
anytype-ts, open-notebook, html-anything, paperless-ngx, GLOSSOPETRAE, chunkr (AGPL), PilotDeck (AGPL).
Reason: general coding-agent harnesses / off-thesis apps / copyleft liabilities. Star counts
on several of these are inflated in-env and must not be treated as traction signals.
