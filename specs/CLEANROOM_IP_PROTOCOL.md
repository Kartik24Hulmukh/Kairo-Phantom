# CLEAN-ROOM & IP PROTOCOL — "it's legitimately ours on launch day"

> Goal: leverage the best ideas from 80+ repos and the research literature, ship 100x
> faster, and have **zero copyright/license claim exposure** when Kairo Phantom launches.
> The rule is simple: **you may copy IDEAS freely; you may never copy expression
> (code, text, assets) except from permissively-licensed sources, with attribution.**

## 1. The three lanes (every external repo lands in exactly one)

| Lane | Sources | What you may take | How it ships |
|---|---|---|---|
| **BUNDLE** | MIT · Apache-2.0 · BSD · ISC (see REPO_VERIFICATION) | code, as a dependency (unmodified) or vendored with NOTICE | `NOTICE` + `THIRD_PARTY_LICENSES.md` attribution; keep the upstream LICENSE header |
| **STUDY→REIMPLEMENT** | AGPL/GPL repos, **and** no-license (NOASSERTION/None) repos, **and** research papers | the **idea, algorithm, architecture** only | you write **original** code from a spec you author; nothing is copied |
| **EXTERNAL-TOOL** | AGPL/GPL **dev tools** (k6, xk6, grafana, semgrep), SaaS SDKs (Applitools, Meticulous) | run them in CI / at dev time | never distributed inside the product → no bundling obligation |

If a repo cannot be cleanly placed in BUNDLE or EXTERNAL-TOOL, it is **STUDY→REIMPLEMENT by default** — including every NOASSERTION/None repo. **No license means all rights reserved; copying a single function is infringement.**

## 2. The clean-room reimplementation loop (for STUDY sources)
This is how you legally turn a good idea from an AGPL/no-license repo into original Kairo code.

```
A. READ the source repo to understand WHAT it does and WHY it works.
B. WRITE a plain-English CAPABILITY SPEC in your own words (specs/ADR/ADR-xxx.md):
   - the behaviour, inputs/outputs, the algorithmic insight, the edge cases.
   - Do NOT paste their code or comments into the spec.
C. CLOSE the source. Hand ONLY the spec to the build agent (or a fresh model context).
D. The build agent IMPLEMENTS from the spec, never having seen the source code.
E. Prove it works with your own oracle (Definition of Done). Original tests, original code.
F. Record provenance: ADR links the idea's origin ("inspired by X's approach to Y")
   but asserts "implemented clean-room from spec, no code copied."
```
The "two-person" ideal (one reads, another writes) maps perfectly to your **frontier-model
split**: use one model to author the spec (idea extraction) and a **different** fresh
context to implement (see prompts/14). That is a genuine clean-room barrier, cheaply.

## 3. Hard bans (the launch-killers) — enforced by ci/license_gate.yml + cleanroom_provenance.yml
- ❌ Any file, function, or >10 consecutive lines copied from an AGPL/GPL/NOASSERTION repo.
- ❌ Vendoring an AGPL/GPL library into the shipped product (dev-tool use in CI is fine).
- ❌ Copying README prose, docs, prompt text, or datasets from a no-license repo.
- ❌ Reusing a distinctive project **name**, logo, or trade-dress ("clawdcursor", "cellar",
  "Skyvern"-alikes). Kairo Phantom is your name; keep it clean.
- ❌ Shipping model weights whose license forbids commercial/derivative use — check each
  GGUF/LoRA base (llama.cpp is MIT for the runtime; the **weights** have their own license).
- ❌ Copying test fixtures / golden files from another repo.

## 4. Attribution you DO owe (BUNDLE lane)
For every MIT/Apache/BSD/ISC dependency you ship:
- keep its LICENSE text in `THIRD_PARTY_LICENSES.md`,
- Apache-2.0 deps: preserve any `NOTICE` file contents,
- do not imply endorsement by the upstream authors.
This is cheap, standard, and fully protects the "we built the product" claim while
honestly crediting the libraries underneath — exactly how every reputable product ships.

## 5. Model-weight & training-data provenance (the part most teams miss)
- The on-device style-adapter (prompt 09) is trained on the **user's own documents** on the
  **user's own machine** → the user owns the input and the resulting LoRA. Kairo never
  receives or trains on it. Document this in the privacy spec; it is also the moat (G5).
- The base model must have a license permitting local, commercial, derivative use. Record
  the exact base + license in `MODEL_CARD.md`. Do not assume "open weights" == "any use."

## 6. Definition-of-Done addition (code provenance gate)
A capability is not DONE unless: every prod source file is either (a) original work traceable
to an ADR/spec, or (b) a BUNDLE-lane dependency listed in `THIRD_PARTY_LICENSES.md`. The
`cleanroom_provenance` CI job fails the build if a prod file matches neither.

## 7. The one-paragraph launch statement (keep this true)
> "Kairo Phantom is original software. It depends on well-known open-source libraries under
> permissive licenses (see THIRD_PARTY_LICENSES.md) and implements published techniques from
> the research literature. No AGPL/GPL/unlicensed source code is included or derived from in
> the shipped product. The on-device personalization is trained locally on the user's own
> data, which the user owns."
If that paragraph is true on launch day, there is no copy claim to make against you.
