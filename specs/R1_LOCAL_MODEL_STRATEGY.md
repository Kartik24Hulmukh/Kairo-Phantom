# R1 — LOCAL-MODEL STRATEGY: task-adequate quality on modest hardware, provably offline

> The tension: "runs offline on an 8 GB laptop" vs "output a professional trusts." This is the
> #1 product risk. Below is the concrete, up-to-date (2026-07-03) solution — incorporating your
> auto-discovery + small-model + quantization idea, corrected and extended. Honest claim per
> CLAIM_DISCIPLINE: **task-adequate parity with the oracle catching regressions**, NOT
> "100% of the original" (quantization is near-lossless on easy tasks, lossy on hard reasoning).

## The five levers that let a SMALL local model match a big one ON THE TASK
Small model ALONE is not enough. The win comes from stacking:

1. **Right small base, auto-selected by hardware** (your idea, made concrete):
   - On install, **auto-discover** existing local runtimes/models on the machine (the
     html-anything "scan PATH" pattern): Ollama, LM Studio, llama.cpp GGUFs, HF cache, and
     Google AI Edge / Gemma bundles. If none, offer a one-click pull.
   - **Hardware probe** (RAM, VRAM, CPU AVX, NPU) → pick tier:
     | Hardware | Base model | Footprint |
     |---|---|---|
     | ≤8 GB, no GPU | Phi-4-mini (MIT) or Gemma 3n E2B, Q4_K_M | ~2.8–4 GB |
     | 16 GB / iGPU | Qwen3 4B (Apache) or Gemma 3n E4B | ~4–6 GB |
     | GPU ≥12 GB VRAM | 8–14B class, Q5/Q6 | fits VRAM |
   - Multimodal (Gemma 3n) matters for the vision/grounding leg ("look at this screen").

2. **Quantization done right (GGUF via llama.cpp)**: default **Q4_K_M** (~75% memory cut,
   negligible loss on classification/summarization/extraction). Step to **Q5_K_M/Q6** only for
   reasoning-heavy steps. Keep a **fp16 reference** to measure quantization error per task.
   > Honesty: Q4 is NOT lossless. The domain oracle is what makes quantization safe — if a
   > quantized model regresses on a redline, the oracle fails and we fall back a tier.

3. **Retrieval beats parameters for knowledge tasks (this is where turbovec fits):**
   - A 4B model doesn't "know" contract law — it **retrieves** your firm's clause library,
     precedents, and house style, then edits. Knowledge lives in the corpus, not the weights.
   - **turbovec (MIT, verified)** = the on-device vector index: 10M docs in ~4 GB, faster than
     FAISS, built on Google's TurboQuant. Perfect for laptop-scale RAG with no cloud.
   - Pipeline: user docs → local embeddings → turbovec index → retrieve top-k → small model
     drafts grounded in retrieved text → oracle verifies against source (no hallucinated clauses).

4. **Domain + voice adapters (on-device LoRA, EdgeTune-class):** a small LoRA per domain
   (legal) and per user (voice). Trained locally on user-owned data → the data-sovereignty moat
   (G5). Adapters are ~MBs; hot-swap per task. This is what closes the "reads like a pro" gap.

5. **Speculative decoding + verifier loop for speed & correctness:**
   - Speculative decoding (tiny draft model + target) → 2–3x tokens/s on the same hardware.
   - **Verifier-gated generation:** the CUA Universal Verifier + domain oracle re-check output;
     on failure, escalate one model tier (or flag), never ship unverified. Quality is a *gate*,
     not a hope.

## Honest fallback ladder (proven, never silent — ties to R3)
```
try Tier-A local model (Q4) + RAG + LoRA
  → oracle pass? ship.
  → oracle fail? retry Tier-B (bigger/higher-quant) local model
     → still fail? DEGRADE HONESTLY: return best draft + a visible
       "low-confidence, human review recommended" flag + the oracle diff.
NEVER silently call the cloud. In air-gap mode the cloud path does not exist (R3).
```

## The R1 kill-test (week 1, before committing the beachhead)
Build a Tier-A stack (Phi-4-mini/Gemma 3n Q4 + turbovec RAG over a real clause library + a
legal LoRA from ~20 redlined contracts). Run 30 real redline tasks; a practicing lawyer scores
each pass/fail on professional adequacy.
- **≥80% pass on ≤8 GB hardware → the offline-on-modest-hardware thesis holds; build.**
- 60–79% → ship with a "review recommended" band + push more to RAG/adapter; re-test.
- **<60% → the 8 GB promise is false for legal; raise the hardware floor (16 GB) OR narrow the
  first domain to one where small-model+RAG is adequate (e.g. summarization/extraction).**

## What to auto-discover on install (the concrete feature)
- Model runtimes: Ollama, LM Studio, llama.cpp, Google AI Edge, vLLM (if GPU).
- Existing GGUFs / HF cache (don't re-download).
- Hardware: RAM/VRAM/CPU flags/NPU → tier selection + a one-line "why we picked this model."
- All local; the egress oracle proves the discovery + inference made zero network calls.
