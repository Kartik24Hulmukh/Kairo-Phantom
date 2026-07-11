# T1 — Competitive Verification + Freedom-to-Operate

**Gate:** none (informs everything) · **Deps:** T0 · **Budget:** human-paced · **Oracle:** attestation (+ evidence)

## Goal
Replace assumptions about AGA with verified facts, and remove patent risk before any "novel/patentable" claim is ever made public.

## Work items
- [ ] Clone/run AGA's public demo; verify an AGA **sample bundle with AGA's own verifier**; write `docs/competitive/aga_bundle_analysis.md` — exactly what it proves and what it does not.
- [ ] Note any gateway-bypass path **only** under responsible disclosure; no unauthorized probing.
- [ ] Retrieve patent **19/433,835** from USPTO Patent Center (primary source, NOT research.md); commission a counsel claim-chart; prior-art search (in-toto, SCITT, RATS, reference monitors, remote attestation, receipt chains, policy gateways).
- [ ] **Freeze** all public "novel/patentable/first" claims until the FTO memo lands.

## Definition of done (attestation)
```bash
python3 orchestrator.py attest --task T1 --verdict pass \
  --evidence <sha256 of aga_bundle_analysis.md + fto_memo.pdf> \
  --note "AGA bundle verified; FTO memo received; novelty claims frozen pending counsel"
```

## Residual risk
A pending application can be narrowed/rejected/invalidated — AGA does not own the category. But do not rely on that; get the written opinion.
