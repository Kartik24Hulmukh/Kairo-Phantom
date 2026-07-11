# T2B — Boundary-Evidence Value Test (blind Mode B1 vs B2)

**Gate:** none (informs G3 pricing / build-or-not) · **Deps:** T2A, T6 · **Runs:** AFTER the boundary witness exists · **Oracle:** attestation (signed manifest + assessor report)

## Why this exists separately
Network-boundary evidence is expensive to build (T6). Only build the *pitch* around it if buyers actually value it. T2B asks the second commercial question in isolation, using real dual-witness evidence that now exists.

## The one question
**Do buyers pay EXTRA for scoped network-boundary evidence on top of desktop-outcome evidence?**

## Protocol (blind)
- **Mode B1 — desktop outcome only:** the T2A Mode B pack.
- **Mode B2 — + boundary:** + host network observation + independent external witness + declared coverage/gaps.

Same blind ≥3-assessor protocol as T2A.

## Definition of done (attestation)
```bash
python3 orchestrator.py attest --task T2B --verdict pass \
  --evidence evidence/t2b_assessors.json --note "blind boundary-value test"
```
Artifact JSON needs: `blind: true`, `assessors` (≥3), ≥1 with `prefers:"B2"` **and a written `reason`**.

## If it fails
Do NOT lead the pitch with the network witness. Keep it as an option for the minority of buyers whose deployment constraint requires it. This is a real, money-saving falsification.
