# T6 — Boundary Witness (Scoped Zero-Egress Evidence)

**Gate:** none (feeds G1/demo credibility) · **Deps:** T0 · **Budget:** human-paced · **Oracle:** attestation + `runs/boundarybench_report.json`

## Goal
Make the zero-egress claim honest and independently witnessed — the single most important technical correction from the red-team (research.md 2.3).

## Architecture (all five, in order)
1. **TPM** — measured platform state. Optional corroboration, **not** the egress witness.
2. **Host sensor** — attributes network behavior to processes/interfaces (eBPF/WFP/ETW).
3. **External witness** — separately-administered device observing traffic across specified physical paths.
4. **Canaries** — prove the observers are active during the interval.
5. **Coverage declaration** — lists what was and was NOT observed.

## Required claim wording (only this)
> "No outbound packet was observed across the declared and tested interfaces during the nonce-bound interval; all required canaries were detected; unobserved channels are listed."

Never: "the second device / TPM proves no data left the machine."

## Definition of done (attestation)
```bash
python3 orchestrator.py attest --task T6 --verdict pass \
  --evidence <sha256 runs/boundarybench_report.json> \
  --note "host + external witness agree; interface inventory + canary coverage + blind spots published"
```
PASS requires: host + external witness agreement; published interface inventory; canary coverage; explicit blind spots (Wi-Fi/BT/cellular/USB-net/2nd-NIC/firmware).

## Benchmark home
This feeds **BoundaryBench** (network/offline). AGA/Microsoft are tested in **EvidenceBench** (completeness), not here — unless a deployment claims air-gap.
