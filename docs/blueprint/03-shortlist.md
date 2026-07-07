# Section 3 — The Shortlist: Highest-Leverage Integrations

> From 114 candidates, these are the repos that actually move Kairo-Phantom toward a defensible product. Each entry: **what it gives you**, **why it matters here specifically**, **integration cost**, and **the honest catch**.

Ranking philosophy: I am not ranking by GitHub stars. I am ranking by *marginal defensibility per unit of integration effort* for a Windows-first, local-first, receipt-signing computer-use agent. A 40k-star repo that duplicates what you already have scores lower than a 2k-star repo that removes your single biggest liability.

---

## Tier S — Do these or the product does not survive contact with reality

### S1. A real CUA grounding model / dataset lineage (OS-World, WindowsAgentArena, Agent-S, UI-TARS lineage)
- **What it gives you:** Ground-truth benchmarks and grounding data for "given a screenshot + goal, produce the correct click coordinate / action." This is the *actual hard part* of computer use, and it is the part Kairo currently hand-waves.
- **Why it matters here:** Kairo's differentiator is safe execution (receipts, ghost typing, air-gap). But execution safety on top of a **bad planner** just means you reliably and verifiably do the wrong thing. WindowsAgentArena in particular is the only serious public benchmark for *Windows* agents — which is Kairo's entire platform bet.
- **Integration cost:** High. You are not vendoring a library; you are adopting an eval harness and probably fine-tuning or at least prompt-engineering against it. Weeks, not days.
- **The catch:** WindowsAgentArena requires Azure VMs to run at scale; OSWorld is Linux-centric. You will spend real money on eval infra. But without a benchmark number you cannot claim "works," you can only claim "runs."

### S2. Caimeo / AgentDojo-style prompt-injection & agent-security benchmark
- **What it gives you:** An adversarial test suite for indirect prompt injection against tool-using agents — the exact attack class Kairo's `PromptShield` claims to defend.
- **Why it matters here:** Kairo's `prompt_shield.py` is a thin regex/heuristic layer (I read it — see §1). Right now the security claim is **unfalsifiable marketing**. Wiring in an injection benchmark converts "we have a PromptShield" into "we block X% of AgentDojo attacks at version N," which is the only version of that claim a buyer or auditor will accept.
- **Integration cost:** Medium. It is a test harness, not runtime code. Fits cleanly into the existing `tests/` layout.
- **The catch:** Your first score will be embarrassing. That is the point — you cannot improve an undefined number.

### S3. E2B / microVM or Windows Sandbox isolation layer
- **What it gives you:** Real OS-level isolation for the execution surface instead of "we run on your actual desktop and promise to be careful."
- **Why it matters here:** Kairo's ghost-typing/UIA injector operates on the *live user session*. That is a catastrophic blast radius: a mis-grounded click closes a real trade, deletes a real file, sends a real email. Isolation is the difference between "demo" and "something an enterprise will let past InfoSec."
- **Integration cost:** High on Windows (Windows Sandbox / Hyper-V), medium if you accept a Linux VM path first.
- **The catch:** Windows Sandbox is ephemeral and heavyweight; it partially defeats the "attach to the user's real running apps" value prop. This is a genuine product tension you must resolve deliberately, not accidentally.

---

## Tier A — Strong moat-per-effort, do these next

### A4. LiteLLM (model gateway)
- **What it gives you:** One interface across OpenAI/Anthropic/Google/local Ollama with fallback, retries, cost tracking.
- **Why it matters here:** Kairo already imports `litellm`. Lean into it: it makes the "local-first, bring-your-own-model, air-gappable" story real instead of aspirational, and it is the cleanest path to "runs fully offline with a local model" — a claim that would actually differentiate.
- **Integration cost:** Low. Already a dependency.
- **The catch:** Local models are dramatically worse at grounding (see S1). "Air-gapped" and "actually completes tasks" are currently in tension.

### A5. Model2Vec / static embeddings + sqlite-vec (already vendored)
- **What it gives you:** Fast, dependency-light local semantic memory/retrieval with zero network.
- **Why it matters here:** Perfectly aligned with local-first. This is a rare case where Kairo's existing choice is genuinely good — keep it and market it.
- **Integration cost:** Already present.
- **The catch:** Static embeddings underperform on nuanced retrieval; fine for tool/skill lookup, weak for long-horizon reasoning memory.

### A6. A hardened, audited signing/attestation lineage (Sigstore/in-toto patterns, TUF)
- **What it gives you:** The *correct* mental model and possibly reusable primitives for tamper-evident, verifiable action logs — supply-chain-grade instead of homemade.
- **Why it matters here:** Receipts are Kairo's headline moat. Right now they are "we Ed25519-sign a JSON blob," which any competent team can copy in a weekend (see §5). Adopting in-toto/Sigstore concepts (transparency log, attestation format, key rotation, revocation) turns a signature into an *auditable chain* — much harder to replicate and far more credible to compliance buyers.
- **Integration cost:** Medium-high (conceptual adoption + format work).
- **The catch:** Full transparency-log infrastructure is heavy; you likely adopt the *format and threat model*, not the whole Sigstore backend, at first.

### A7. Playwright / browser-use for the web-action subset
- **What it gives you:** Robust, well-maintained browser automation with real selectors and waits.
- **Why it matters here:** A huge fraction of "computer use" tasks are actually *browser* tasks. Doing those through pixel-grounded desktop clicking is strictly worse than doing them through a DOM. A browser fast-path massively raises real-world success rate.
- **Integration cost:** Medium.
- **The catch:** It bifurcates your architecture (desktop path + browser path). Worth it, but it is real surface area.

---

## Tier B — Useful accelerants, opportunistic

- **B8. Ollama** — turnkey local model serving; pairs with A4/A5 for the offline story. Low cost.
- **B9. A LangGraph/agent-orchestration lineage** — Kairo already has orchestration; borrow *durable-execution / checkpoint* patterns (resumable runs, human-in-the-loop interrupts) rather than the whole framework. Medium.
- **B10. An OCR / accessibility-tree extractor (e.g. a UIA/at-spi dumper, or a strong OCR)** — improves grounding cheaply on Windows by fusing the accessibility tree with pixels. Medium, high ROI on Windows specifically.
- **B11. A structured-output / function-calling schema layer (Pydantic-based, already in stack)** — keep; it is the right call for reliable tool invocation.
- **B12. A red-team corpus / jailbreak dataset** — feeds S2; converts safety from vibes to metrics.

---

## What I deliberately down-ranked (and why)

- **Generic "awesome-agents" list repos & framework kitchen sinks (AutoGPT-era, giant all-in-one frameworks):** high stars, near-zero marginal defensibility. Integrating them makes Kairo *look* like everyone else. Kairo's whole reason to exist is to *not* be a generic agent framework.
- **Voice / TTS / avatar repos:** irrelevant to the core thesis; pure distraction until the agent can reliably click a button.
- **Anything that assumes cloud-hosted execution:** directly contradicts the local-first / air-gap positioning. Adopting these would dissolve the moat, not build it.

---

## The one-sentence version

Spend your integration budget on **grounding quality (S1), falsifiable security (S2), and real isolation (S3)** — because those three are simultaneously Kairo's biggest current lies *and* its only credible path to a moat; everything else is optimization on top of a foundation that does not yet hold weight.
