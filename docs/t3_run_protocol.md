# T3 Demo Hardening — Run Protocol

**Gate:** G1 · **Task:** T3 · **Oracle:** `validate_G1_desktop` on `runs/g1_100run_report.json`

This document specifies the exact steps a human operator follows to execute the
100-run G1 gate on stock Windows 11 and produce the evidence artifact that
`validate_G1_desktop` will accept. It is deliberately turnkey: no decisions are
left to the operator at run time.

---

## 0. Prerequisites

| Item | Requirement |
|------|-------------|
| **OS** | Windows 11 (build 26100 or later), stock — no custom kernel, no hardened image |
| **Python** | 3.11.x or 3.12.x |
| **Rust** | stable (1.79+) — only if phantom-core needs rebuilding |
| **Hardware** | The pinned machine recorded in `HARDWARE.md` (same model/build for all 100 runs) |
| **Screen recorder** | OBS Studio or equivalent; must produce a single unedited MP4 |
| **Signing key** | Ed25519 private key at `~/.kairo/kartik.key` (generated via `loop-engineering/tools/keygen.py`) |
| **Trust root** | Public key registered in `loop-engineering/schemas/trust_roots.json` under `kartik-founder` |
| **Task config** | A JSON file specifying the redline workflow (see §2) — the harness is parameterized, not hardcoded |

---

## 1. Pin the environment

```powershell
# Record the exact OS build
winver
# Record the exact commit you're running on
git rev-parse HEAD
# Record lockfile hashes
certutil -hashfile Cargo.lock SHA256
certutil -hashfile kairo-sidecar\requirements.txt SHA256
```

Write these values into the evidence manifest's `env` block (see §6).

---

## 2. Prepare the task config

The harness (`tools/run_g1.py`) takes a `--task-config` JSON file so the
redline workflow is not hardcoded. The founder will lock the final workflow
spec; until then, the config is the single input point.

Example `task_config.json`:

```json
{
  "workflow": "contract-redline-demo",
  "steps": [
    {"id": "seal",    "action": "seal_document",    "params": {"input": "demo_contract.docx"}},
    {"id": "delegate","action": "delegate_to_agent", "params": {"agent": "kairo-phantom"}},
    {"id": "work",    "action": "execute_redline",   "params": {"rules": "rules/default_rules.json"}},
    {"id": "attack",  "action": "inject_tamper",     "params": {"target_step": "work"}},
    {"id": "assess",  "action": "assess_outcome",    "params": {}},
    {"id": "contrast","action": "contrast_runs",     "params": {}}
  ],
  "canary_checks": [
    {"id": "receipt_chain_intact",  "type": "hash_chain"},
    {"id": "merkle_root_consistent","type": "merkle"},
    {"id": "no_unexpected_egress",  "type": "egress_monitor"}
  ],
  "tamper": {
    "method": "mutate_receipt_field",
    "field": "outcome",
    "value": "TAMPERED_VALUE"
  }
}
```

The `tamper` block is critical: the harness will **actually mutate** a receipt
entry and then run `tools/verify_receipts_external.py` to confirm the verifier
flags it. This is a real tamper, not a stub.

---

## 3. Start the screen recorder

Start OBS (or equivalent) recording **before** the first run. Do not stop,
pause, or edit the recording until all 100 runs are complete. The recording
must be a single continuous take.

```powershell
# Record the output path — you'll need it for the recording checksum
# The MP4 file path goes into the report's recording.path field
```

---

## 4. Run the 100-run gate

```powershell
python tools\run_g1.py --task-config task_config.json --runs 100 --output runs\g1_100run_report.json --os "Windows 11 (build 26100)"
```

The harness will, for each run:
1. Execute the 6-step workflow from the task config.
2. Emit a receipt to a JSONL file (hash-chained, per `verify_receipts_external.py`).
3. Check readback: compare the agent's output against the sealed ground truth.
4. Inject a tamper (mutate a receipt field) and run the external verifier to
   confirm it is detected.
5. Check all canaries from the task config.
6. Record any silent gaps (steps where evidence was missing).
7. Append a per-run record to the report's `runs` array.

After all 100 runs, the harness computes the recording SHA-256 and writes the
final report JSON.

---

## 5. Verify the report locally (before attestation)

```powershell
# Quick check: run the validator directly on the report
python -c "import sys; sys.path.insert(0,'loop-engineering'); import validators as V; V.validate_G1_desktop({}, 'runs/g1_100run_report.json', '.')"
```

If this prints `G1 OK — computed from 100 records...`, the report is valid.
If it raises `EvidenceError`, read the message — it will tell you exactly which
field failed.

---

## 6. Create and sign the evidence manifest

Copy `loop-engineering/schemas/EXAMPLE_evidence_manifest.json`, fill in the
real values, then sign it:

```powershell
# 1. Compute the artifact hash
python -c "import hashlib; print(hashlib.sha256(open('runs/g1_100run_report.json','rb').read()).hexdigest())"

# 2. Fill in the manifest (base_commit, created_at, env, artifact.sha256)
#    Save as evidence/t3_g1_manifest.json

# 3. Sign it
python loop-engineering\tools\sign_manifest.py --key ~/.kairo/kartik.key --manifest evidence\t3_g1_manifest.json
```

---

## 7. Attest T3

```powershell
python loop-engineering\orchestrator.py attest --task T3 --verdict pass --evidence evidence\t3_g1_manifest.json --note "100-run gate met on Win11 build XXXXX; demo recorded"
```

The orchestrator will:
1. Load and structurally validate the manifest.
2. Verify the Ed25519 signature against `trust_roots.json`.
3. Check provenance (base_commit matches HEAD, freshness, artifact hash).
4. Run `validate_G1_desktop` on the artifact content.
5. If all pass, record the attestation in `state.json` and flip G1 to done.

---

## 8. If it fails

Narrow to ONE deterministic task and freeze external work until green
(canonical plan Part 10, G1 fail action). Do not retry blindly — use the
anti-thrash rule: if the same failure signature occurs twice, change approach
or mark `wont_fix` with a written reason.

---

## Report schema (what `validate_G1_desktop` expects)

```json
{
  "workflow": "string — the workflow name from task config",
  "os": "Windows 11 (build XXXXX)",
  "recording": {
    "path": "path/to/demo_recording.mp4",
    "sha256": "hex digest of the recording file"
  },
  "runs": [
    {
      "i": 1,
      "readback_match": true,
      "tamper_injected": true,
      "tamper_detected": true,
      "canary_present": true,
      "gap": false,
      "ts": "2026-07-20T10:00:00"
    }
  ]
}
```

**Validator bar (computed from per-run records, never from a summary):**
- ≥ 100 runs
- readback_match ≥ 99/100
- tamper_detected = 100% of injected tampers (≥ 1 must be injected)
- canary_present = 100% of runs
- gap = 0 (no silent gaps)
- os contains "Windows 11"
- recording.sha256 present

---

## Smoke vs. real artifact — do not confuse

| File | Purpose | Runs | Validator result |
|------|---------|------|------------------|
| `runs/g1_smoke_report.json` | Schema wiring proof — 99 runs, every field correct | 99 | **FAIL** — "only 99 runs (<100)" |
| `runs/g1_100run_report.json` | Real gate artifact — produced only by the human 100-run protocol | 100 | PASS (when all fields meet bar) |

The smoke report is committed to the repo to prove the harness produces
validator-parseable records. It must **never** be used as evidence for T3
attestation. The 100-run report is produced only by executing §4 above on real
Windows 11 hardware.
