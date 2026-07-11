# T2A — Desktop-Outcome Value Test (blind Mode A vs Mode B)  ⭐ THE COMPANY THESIS

**Gate:** G2 (make/break) · **Deps:** T0, T3 · **Runs:** after the 100-run desktop gate, BEFORE the boundary witness (T6) · **Oracle:** attestation (signed manifest + assessor report)

## Why this is split from T2B
The v1.2 plan bundled desktop-outcome evidence and network-boundary evidence into one test — but T2's Mode B required dual-witness network evidence that only T6 produces, and T6 came *after* T2. That is a dependency contradiction. T2A now asks ONLY the desktop-outcome question, which you can answer right after T3. The boundary question moves to **T2B** (after T6).

## The one question
**Does independently-observed desktop OUTCOME evidence make an assessor prefer Kairo — and a buyer pay?**

## Protocol (blind)
Run ONE synthetic regulated workflow twice, producing two packs:
- **Mode A — gateway receipt only:** identity, request, policy decision, allow/deny, tool result.
- **Mode B — Kairo desktop outcome:** + OS action observation, app pre/post state, independent readback, artifact hash. *(No network-boundary claims here — that is T2B.)*

Give both to ≥3 assessors **without telling them which is Kairo.** Ask in writing: (1) which pack would you rely on? (2) what deployment decision could it support? (3) what is still insufficient? (4) would the extra evidence change deployment approval? (5) would your organization pay?

## Definition of done (attestation → G2)
Record a signed assessor report and attest:
```bash
python3 orchestrator.py attest --task T2A --verdict pass \
  --evidence evidence/t2a_assessors.json --note "blind Mode A/B desktop-outcome test"
```
The manifest's artifact must be a JSON report with: `blind: true`, `assessors` (≥3), ≥1 with `prefers:"B"` **and a written `reason`**, and willingness-to-pay recorded (`would_pay`). The validator enforces this; a bare file will NOT pass.

## If it fails
Do not spend another quarter adding capability. Re-examine the thesis — AGA may have shown the extra outcome layer isn't decision-changing.
