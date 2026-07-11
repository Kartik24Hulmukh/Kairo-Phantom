# T2 — Mode A vs Mode B Blind Comparative Evidence Test  ⭐ THE COMPANY THESIS

**Gate:** G2 (make/break) · **Deps:** T0, T3, T4 · **Budget:** human-paced · **Oracle:** attestation (+ evidence)

## Goal
Answer the one question the whole sprint exists for: **does independently-observed desktop outcome + scoped boundary evidence make an assessor prefer Kairo, and a buyer pay?** This is more valuable than any competitor matrix.

## Protocol (blind)
Run ONE synthetic regulated workflow twice, producing two evidence packs:
- **Mode A — gateway receipt only:** identity, request, policy, allow/deny, tool result.
- **Mode B — Kairo full:** + OS action observation, app pre/post state, independent readback, artifact hash, host network observation, external witness observation, explicit known gaps.

Give both packs to ≥3 assessors **without telling them which Kairo produced.** Ask each, in writing:
1. Which pack would you rely on?
2. What deployment decision could it support?
3. What is still insufficient?
4. Would the extra evidence change deployment approval?
5. Would your organization pay for it?

## Definition of done (attestation → G2)
```bash
python3 orchestrator.py attest --task T2 --verdict pass \
  --evidence <sha256 of signed assessor statements> \
  --note "assessor A + B preferred Mode B in writing; 3 reviewing"
```
PASS requires ≥1 assessor prefers Mode B *and states why in writing*; ≥3 reviewing.

## If it fails
Do not spend another quarter adding capability. Re-examine the thesis — AGA may have shown the extra layer isn't needed.
