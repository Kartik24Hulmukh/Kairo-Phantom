# T3 — Demo Hardening (100-run pinned)

**Gate:** G1 · **Deps:** T0 · **Budget:** human-paced · **Oracle:** attestation + `runs/g1_100run_report.json`

## Goal
Move the desktop causal chain from Experimental to demonstrably reliable on **stock Win11**, and record the single unedited killer-demo take.

## Work items
- [ ] Pin hardware + OS build; script the 6-step demo (seal → delegate → work+attack → assess → tamper → contrast).
- [ ] Run the workflow 100× headless; emit `runs/g1_100run_report.json` with: readback matches, tamper-catches, canary detections, EVIDENCE_GAP count.
- [ ] **TPM appears as platform-state corroboration only** — never labeled as the egress witness.
- [ ] Record the single-take demo; store its checksum.

## Definition of done (attestation → G1)
PASS requires: ≥99/100 readback; 100/100 tamper caught; 100% required canaries; 0 silent gaps.
```bash
python3 orchestrator.py attest --task T3 --verdict pass \
  --evidence <sha256 runs/g1_100run_report.json + recording checksum> \
  --note "100-run gate met on Win11 build XXXXX; demo recorded"
```

## If it fails
Narrow to ONE deterministic task and freeze external work until green (canonical plan Part 10, G1 fail action).
