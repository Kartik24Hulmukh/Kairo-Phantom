# 2. Repo Intelligence Table (all 114 reference repos)

**How to read this.** *Superpower* = the one thing it does exceptionally well. *Steal conceptually* = the mechanism worth re-implementing (not copying). *Rel* = relevance to Kairo-Phantom, 1–10. *License* = adoption-safety flag: 🟢 permissive (MIT/BSD/Apache/MPL-file-level), 🟡 weak-copyleft/attention (MPL link, LGPL, dual), 🔴 strong-copyleft/proprietary/SaaS (AGPL/GPL/BSL/FSL/commercial — **do not link/embed; study only**), ⚪ unverifiable (personal/obscure repo — treat all claims with suspicion, do not depend on).

> Licenses move; **re-verify every 🟡/🔴 before shipping** (see §6 legal kill-list). "Study only" means learn the technique and write your own clean-room implementation.

## Cluster A — Agent frameworks & orchestration

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| langgenius/dify | Visual LLM-app/agent builder w/ workflow graph + tool ecosystem | Node-graph workflow engine; tool/plugin registry; observability of each step | 8 | 🔴 open-core, commercial clauses — study only |
| OpenHands/OpenHands | Autonomous SWE agent w/ sandboxed runtime + event stream | Event-sourced agent loop; sandboxed action execution; replayable trajectories | 9 | 🟢 MIT |
| camel-ai/camel | Multi-agent "role-play" society & task decomposition | Role/typed-message protocol between agents; task graph | 7 | 🟢 Apache-2.0 |
| camel-ai/owl | Multi-agent automation on top of CAMEL, strong benchmarks | Optimized multi-agent worker assignment | 6 | 🟢 Apache-2.0 |
| eigent-ai/eigent | Desktop multi-agent workforce (CAMEL-based) | Local multi-agent workforce UX; task queue | 7 | 🟡 verify (Apache/ELv2 mix) |
| ruvnet/ruflo (ruv/flow) | Swarm orchestration + agentic dev flows | Swarm topology + shared blackboard memory | 6 | 🟢 MIT (verify) |
| bmad-code-org/BMAD-METHOD | Structured agentic dev methodology (agents-as-roles) | Repeatable role/prompt "method" packaging; spec→plan→build pipeline | 7 | 🟢 MIT |
| gsd-build/get-shit-done | Opinionated autonomous build loop | Tight plan/execute/verify cycle with guardrails | 5 | ⚪ |
| NousResearch/hermes-agent | Agent atop Hermes models, tool-use focus | Tool-call schema + function-calling loop | 5 | 🟡 verify |
| mco-org/squad / 2FastLabs/agent-squad | Team-of-agents coordination | Manager→worker delegation + result merge | 5 | ⚪/🟡 |
| code-yeongyu/oh-my-openagent | Personal open agent | Lightweight agent skeleton | 3 | ⚪ |
| hamishivi/tmax | RL/agent experimentation | Reward-shaped agent training loop | 4 | ⚪ |
| garrytan/gbrain | Personal "brain"/memory agent | Long-term memory scaffolding | 3 | ⚪ |
| affaan-m/ECC | Agent/coding experiment | — | 2 | ⚪ |
| oh-my-pi (can1357) | Systems/agent experiment | Low-level tricks | 3 | ⚪ |
| Kuberwastaken/claurst, AmrDab/clawdcursor, Yeachan-Heo/gajae-code, Yeachan-Heo/claw-code, DietrichGebert/ponytail | Claude/Cursor wrappers & coding agents | Editor-integration patterns; prompt scaffolds | 3 | ⚪ |
| deonmenezes/mantishack, koala73/worldmonitor, Panniantong/Agent-Reach | Niche agent apps | Domain framing; outreach automation | 3 | ⚪ |
| ashishpatel26/500-AI-Agents-Projects | Catalog of agent project ideas | Breadth map of use cases | 4 | 🟢 MIT (content) |

## Cluster B — Computer-use / browser & desktop automation (core to Kairo)

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| microsoft/playwright | Best-in-class cross-browser automation + auto-wait + trace viewer | Auto-waiting actionability checks; **trace viewer** (time-travel debugging of automation); selector engine | 10 | 🟢 Apache-2.0 |
| browser-use/browser-use | LLM-driven browser agent w/ DOM+vision | DOM-tree → compact action space for the model; element indexing | 9 | 🟡 verify (MIT-ish) |
| browserbase/stagehand | Structured, resilient browser acts (act/extract/observe) | **act/extract/observe** primitive triad; self-healing selectors | 9 | 🟢 MIT |
| Skyvern-AI/skyvern | Vision+LLM web automation, resilient to layout change | Visual grounding of targets; retry-on-drift | 8 | 🔴 AGPL-3.0 — study only |
| alibaba/page-agent | On-page agent operating live DOM | In-page action executor + observation | 7 | 🟡 verify |
| LvcidPsyche/auto-browser | Browser automation | Task→browser action mapping | 4 | ⚪ |
| daijro/camoufox | Stealth/anti-fingerprint Firefox | Fingerprint hardening; humanized input timing | 6 | 🟡 MPL/Firefox-derived — study only |
| replayio/replay-cli | Deterministic record/replay of browser runs | **Deterministic replay** of nondeterministic sessions | 8 | 🟢 (verify) |
| nexu-io/html-anything, VILA-Lab/FigMirror, vibeflowing-inc/vibe_figma | HTML/Figma manipulation & mirroring | Design-file diff/mirror; DOM→design mapping | 6 | 🟡/⚪ |

## Cluster C — Testing, QA, visual & contract testing (Kairo's verification stack)

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| vitest-dev/vitest | Fast, Vite-native unit test runner | In-process, watch-mode, parallel test engine ergonomics | 7 | 🟢 MIT |
| testing-library/react-testing-library | Test from the user's POV (a11y-first queries) | Query-by-role/label testing philosophy for the overlay UI | 6 | 🟢 MIT |
| storybookjs/storybook | Component workbench + visual states | Isolated component states as testable artifacts | 6 | 🟢 MIT |
| mswjs/msw | Network mocking at the service-worker/interceptor layer | **Deterministic network mocking** for air-gap + tests | 8 | 🟢 MIT |
| pact-foundation/pact-js | Consumer-driven **contract testing** | Contract tests between sidecar↔core↔MCP (schema drift guard) | 8 | 🟢 MIT |
| testcontainers/testcontainers-node | Real deps in ephemeral containers for tests | Spin real Ollama/DB in CI hermetically | 7 | 🟢 MIT |
| applitools/eyes.sdk.javascript | AI visual diffing at scale | Perceptual visual assertions for ghost-typed output | 6 | 🔴 commercial SaaS SDK — study only |
| chromaui/chromatic-cli | Hosted visual regression for Storybook | Snapshot baseline + review workflow | 5 | 🔴 proprietary SaaS — study only |
| percy/cli | Visual regression pipeline | Cross-env visual baselines | 5 | 🔴 SaaS (CLI BSD) — study only |
| OctoMind-dev/debugtopus + octomind-mcp | Auto-generated E2E tests + MCP surface | LLM-authored E2E from app exploration; test-gen via MCP | 7 | 🟡 verify |
| alwaysmeticulous/meticulous-sdk | Record real sessions → auto visual tests, zero-maintenance | **Session-recording → regression suite** without hand-written assertions | 8 | 🔴 proprietary — study only |
| checkly/checkly-cli | Monitoring-as-code (synthetic checks) | Synthetics-as-code for post-launch canaries | 6 | 🟢 (verify) MIT-ish |

## Cluster D — Performance, load, chaos & observability

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| grafana/k6 | Scriptable load testing (JS) w/ great DX | Load scenarios-as-code; thresholds as pass/fail gates | 8 | 🔴 AGPL-3.0 — study only |
| grafana/xk6-disruptor | **Fault injection** (latency/errors) as k6 ext | Chaos primitives: inject latency/faults into deps | 8 | 🔴 AGPL-3.0 — study only |
| artilleryio/artillery | Load + smoke testing, serverless-scale | Distributed load generation | 6 | 🟡 MPL-2.0 |
| clinicjs/node-clinic | Node perf diagnosis (flame/bubbleprof) | Automated perf-bottleneck diagnosis reports | 6 | 🟢 MIT |
| GoogleChrome/lighthouse-ci | Perf/a11y budgets in CI | **Budgets-as-gates** (fail build on regression) | 7 | 🟢 Apache-2.0 |
| grafana/grafana | Dashboards/alerting standard | Dashboard/alert model | 7 | 🔴 AGPL-3.0 — study only |
| open-telemetry/opentelemetry-js | Vendor-neutral tracing/metrics/logs standard | **OTel spans across sidecar↔core↔apps**; trace every action | 9 | 🟢 Apache-2.0 |
| getsentry/sentry-javascript | Best-in-class error capture + context | Crash/error grouping, breadcrumbs, release health | 8 | 🔴 BSL/FSL (SDK MIT-ish; server BSL) — verify, SDK likely OK |
| comet-ml/opik | LLM eval + tracing + guardrail scoring | **LLM-as-judge eval harness**; trace scoring; prompt regression | 8 | 🟡 Apache-2.0 (verify components) |
| Helicone/helicone | LLM observability proxy (cost/latency/caching) | Proxy-layer LLM telemetry + caching + rate-limit | 7 | 🟡 Apache-2.0 (verify) |
| headroomlabs-ai/headroom (`headroom-ai`) | Already a Kairo dep — LLM infra/eval | (already integrated) budget/eval hooks | 6 | 🟡 verify |

## Cluster E — Security, SAST/DAST, secrets, red-team (Kairo's security posture)

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| returntocorp/semgrep | Fast, rule-based SAST w/ custom rules | **Custom taint/injection rules** for Kairo's own code + user macros | 9 | 🟡 LGPL-2.1 (engine) / rules mixed — verify |
| github/codeql | Deep semantic code query (dataflow) | Dataflow queries to prove no secret→network path | 8 | 🔴 GitHub-only license (free OSS) — study only |
| gitleaks/gitleaks | Secret scanning (git history + live) | Pre-commit + runtime secret detection in receipts/logs | 8 | 🟢 MIT |
| snyk/cli | Dependency/vuln + license scanning | SCA + license policy enforcement in CI | 6 | 🔴 proprietary CLI — use hosted or replace w/ OSS (osv-scanner/grype) |
| zaproxy/zaproxy | DAST proxy for web attack simulation | Active-scan the MCP/HTTP surfaces | 6 | �repro Apache-2.0 🟢 |
| dequelabs/axe-core | Accessibility rule engine | A11y auditing of overlay + verifiable a11y of ghost-typed output | 7 | 🟡 MPL-2.0 |
| mukul975/Anthropic-Cybersecurity-Skills | Curated cyber "skills" for LLMs | Skill packaging for security tasks | 5 | ⚪ |
| microsoft/RAMPART | Defensive/guardrail framework | Policy-enforcement patterns | 5 | 🟡 verify |
| Unclecheng-li/VulnClaw | Vuln-hunting agent | Automated vuln triage loop | 4 | ⚪ |
| MHSanaei/3x-ui | Xray/VPN panel (network) | Not aligned — network tunneling; **avoid** | 2 | 🔴 GPL — irrelevant |
| elder-plinius/T3MP3ST, OBLITERATUS, GLOSSOPETRAE | Jailbreak/red-team prompt corpora | **Adversarial corpus** to harden PromptShield (as attack test-set only) | 6 | ⚪ study-as-attacker-data only |

## Cluster F — RAG, OCR, docs, memory & knowledge (Kairo's document brain)

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| infiniflow/ragflow | Deep-doc RAG w/ layout-aware parsing | **Layout-aware chunking**; citation-grounded answers | 8 | 🔴 Apache-2.0 w/ restrictions — verify; study |
| lumina-ai-inc/chunkr | High-quality doc chunking/segmentation | Vision-based document segmentation → clean chunks | 8 | 🟡 (verify) |
| allenai/olmocr | SOTA OCR for messy PDFs | OCR pipeline for scanned/complex docs | 7 | 🟡 Apache-2.0 (verify model license) |
| baidu/Unlimited-OCR | Large-scale OCR | OCR throughput patterns | 5 | 🟡 verify |
| paperless-ngx/paperless-ngx | Document management + tagging + OCR | Doc lifecycle: ingest→OCR→classify→archive; already bridged | 7 | 🔴 GPL-3.0 — bridge via API only, don't embed |
| karakeep-app/karakeep | Bookmark/knowledge hoard w/ AI | Save→enrich→recall loop; already bridged | 6 | 🟡 AGPL? verify — API-only |
| lfnovo/open-notebook | Open NotebookLM-style research | Source-grounded notebook + citations | 6 | 🟡 verify |
| anyproto/anytype-ts | Local-first knowledge graph, E2E-encrypted | **Local-first CRDT object model**; encrypted sync | 7 | 🔴 custom/copyleft — study only |
| ianarawjo/ChainForge | Prompt eval/comparison lab | **Prompt A/B eval grids**; response scoring | 7 | 🟢 MIT |
| safishamsi/graphify | Code/knowledge graph (Kairo emits graphify.json!) | Codebase→graph for context; already used | 6 | ⚪ verify |
| latent-spaces/brag, tinyfish-io/bigset, Agent-Reach | Retrieval/dataset/outreach niches | Set-building; retrieval framing | 4 | ⚪ |

## Cluster G — Infra, sandboxes, dev-envs, runtime & terminals

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| daytonaio/daytona | Secure elastic **agent sandboxes** (fast VM/container) | **Isolated execution sandbox** for risky agent actions | 9 | 🟡 AGPL/Apache mix — verify; study |
| opensandbox-group/OpenSandbox | Open agent sandbox runtime | Snapshot/restore sandbox state | 7 | 🟡 verify |
| devspace-sh/devspace (+ Waishnav) | K8s dev-envs, fast inner loop | Declarative dev-env + hot-reload into cluster | 5 | 🟢 Apache-2.0 |
| manaflow-ai/cmux | Parallel agent runs in isolated workspaces | **Fan-out N agents in parallel sandboxes**, compare | 8 | 🟡 verify |
| tmux/tmux | Terminal multiplexing standard | PTY session mgmt for headless tool control | 5 | 🟢 ISC |
| ggml-org/llama.cpp | Efficient local LLM inference (GGUF/quant) | **On-device inference** for air-gap; quantized models | 9 | 🟢 MIT |
| OpenBMB/VoxCPM | On-device speech (TTS/STT) | Local voice I/O for Voice domain | 6 | 🟡 verify |
| OpenBMB/PilotDeck | Device/agent piloting | Remote device control patterns | 4 | ⚪ |
| syncthing/syncthing | P2P encrypted file sync, no server | **Serverless E2E sync** for local-first receipts/docs | 7 | 🟢 MPL-2.0 |
| decolua/9router, koala73/worldmonitor | Routing / monitoring niches | Model routing; world-state monitor | 4 | ⚪ |
| baidu-baige/LoongForge, EvoMap/evolver, context-labs/HALO, halo-dev/halo, ghostwright/ghost-os | Forge/evolution/CMS/OS-niche | Assorted infra ideas | 3 | ⚪/🟡 |

## Cluster H — Voice, media & pipelines

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| pipecat-ai/pipecat | Real-time voice/multimodal agent pipelines | **Streaming media pipeline** (VAD→STT→LLM→TTS) w/ low latency | 8 | 🟢 BSD-2 |
| bradautomates/claude-video | LLM-driven video creation | Scripted video-gen pipeline | 4 | ⚪ |

## Cluster I — Foundational libs & DX

| Repo | Superpower | Steal conceptually | Rel | License |
|---|---|---|---|---|
| colinhacks/zod | TS-first runtime schema validation + inference | **Schema-at-the-boundary**: validate every IPC/tool/receipt payload; single source of truth for types | 9 | 🟢 MIT |
| paperclipai/paperclip | Visual→code design tooling | Design-source→code sync | 4 | 🟡 verify |
| refinedev/refine | React meta-framework for internal tools/CRUD | Admin/console scaffolding for Kairo's dashboard | 5 | 🟢 MIT |
| anthropics/knowledge-work-plugins | Reference plugins for knowledge work | Plugin/skill schema & packaging | 6 | 🟢 MIT (verify) |
| zzet/gortex, gortex | (obscure) | — | 2 | ⚪ |
| skalesapp/skales | App/agent platform | Platform packaging | 3 | ⚪ |
| dyad-sh/dyad | Local AI app builder (open Lovable/v0-like) | Local app-gen UX; provider-agnostic | 6 | 🟢 Apache-2.0 (verify) |
| aaif-goose/goose (Block's Goose) | Extensible on-machine dev agent w/ MCP | **MCP-native extension model**; on-machine tool exec | 8 | 🟢 Apache-2.0 |
| johannesjo/parallel-code | Parallel coding-agent runs | Parallel task fan-out UX | 5 | ⚪/🟢 |
| kagent-dev/kagent | Cloud-native (K8s) agents | Agent-as-controller; declarative agents | 6 | 🟢 Apache-2.0 |
| stophobia/deerflow2.0-enhanced | DeerFlow research-agent fork | Deep-research multi-step flow | 5 | 🟡 verify (MIT base) |
| gortex/T3MP3ST/OBLITERATUS/GLOSSOPETRAE (elder-plinius) | Red-team/jailbreak artistry | Attack corpora only | 5 | ⚪ |

## Score summary (what to actually pay attention to)

**Rel 9–10 (must mine deeply):** playwright, OpenHands, browser-use, stagehand, zod, semgrep, opentelemetry-js, llama.cpp, daytona, comet-ml/opik.
**Rel 8 (strong):** dify, skyvern, replay-cli, msw, pact-js, meticulous, k6, xk6-disruptor, sentry-js, gitleaks, ragflow, chunkr, cmux, pipecat, goose, ChainForge, syncthing, codeql.
**Rel ≤4 / ⚪:** the large tail of personal/obscure repos — noted for completeness, not for dependency. Mine for ideas at most; never take a hard dependency on an unverifiable, single-author repo.
