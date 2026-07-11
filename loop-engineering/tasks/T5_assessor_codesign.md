# T5 — Assessor Co-Design (KSEE draft v0.1)

**Gate:** none · **Deps:** T2 · **Budget:** human-paced · **Oracle:** attestation (+ evidence)

## Goal
Make KSEE legitimate by co-design, not by announcement. A free schema + CLI is not a standard (research.md 2.5).

## Sequence (do NOT skip a step)
1. Draft evidence questions.
2. Give three assessors sample packs.
3. Ask each to mark every evidence item sufficient / insufficient / not relevant.
4. Revise the profile from their feedback.
5. Credit reviewers (with permission).
6. Publish as **KSEE draft v0.1** (never "the standard").
7. Obtain ≥2 independent evidence producers before any v1.0 talk.

## Definition of done (attestation)
```bash
python3 orchestrator.py attest --task T5 --verdict pass \
  --evidence <sha256 of KSEE-draft-v0.1 + 3 assessor feedback forms> \
  --note "3 assessors reviewed; profile revised; draft published with credit"
```

## Legitimacy checklist (for v1.0, later)
≥2 independent producers · 2nd verifier implementation · public positive+negative vectors · stable versioning/IPR · a practitioner using it · an interop event · standards-community participation.
