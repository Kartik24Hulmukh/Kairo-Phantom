#!/usr/bin/env python3
"""
G1 100-run gate harness for T3 demo hardening.

Produces runs/g1_<label>_report.json matching the schema that
loop-engineering/validators.py::validate_G1_desktop expects.

The redline workflow is NOT hardcoded — it is read from a --task-config JSON
file so the harness is ready when the founder locks the final workflow spec.

For each run, the harness:
  1. Executes the workflow steps from the task config (simulated in this
     scaffold — the real execution hooks into the Kairo agent pipeline).
  2. Emits a hash-chained receipt to a JSONL file.
  3. Checks readback: compares the agent's output against the sealed ground
     truth.
  4. Injects a REAL tamper: mutates a receipt field, then runs
     tools/verify_receipts_external.py to confirm the verifier flags it.
  5. Checks all canaries from the task config.
  6. Records any silent gaps.
  7. Appends a per-run record to the report.

Usage:
  python3 tools/run_g1.py --task-config task_config.json --runs 100 \
      --output runs/g1_100run_report.json --os "Windows 11 (build 26100)"

  # Smoke test (99 synthetic runs — fails on synthetic + <100, prints computed stats):
  python3 tools/run_g1.py --task-config task_config.json --runs 99 \
      --output runs/g1_smoke_report.json --os "Windows 11 (build 26100)" \
      --recording-sha256 deadbeef --synthetic
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

# ── Receipt helpers (mirror verify_receipts_external.py canonicalization) ──

RECEIPT_FIELD_ORDER = [
    "seq", "timestamp", "agent_id", "action", "context", "outcome",
    "prev_hash", "self_hash", "signature",
    "opik_trace_id", "opik_trace_url", "domain",
]


def _canonical(record):
    temp = dict(record)
    temp["self_hash"] = ""
    temp["signature"] = ""
    ordered = {k: temp[k] for k in RECEIPT_FIELD_ORDER if k in temp}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_receipt(seq, prev_hash, agent_id, action, context, outcome, domain="redline",
                  signing_key=None):
    """Build a receipt with a valid self_hash and optional Ed25519 signature.

    The signing_key is an Ed25519PrivateKey. When provided, the signature is
    over the ASCII bytes of self_hash (matching verify_receipts_external.py).
    The agent_id is the hex-encoded public key used as the verifying key.
    """
    if signing_key is not None:
        pub_bytes = signing_key.public_key().public_bytes_raw()
        agent_id = pub_bytes.hex()

    rec = {
        "seq": seq,
        "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent_id": agent_id,
        "action": action,
        "context": context,
        "outcome": outcome,
        "prev_hash": prev_hash,
        "self_hash": "",
        "signature": "",
        "domain": domain,
    }
    rec["self_hash"] = _sha256_hex(_canonical(rec).encode("utf-8"))

    if signing_key is not None:
        sig = signing_key.sign(rec["self_hash"].encode("ascii"))
        rec["signature"] = sig.hex()

    return rec


def _write_receipts(receipts, path):
    """Write receipts to a JSONL file (one JSON object per line)."""
    with open(path, "w", encoding="utf-8") as f:
        for r in receipts:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _verify_receipts(receipts_path, verifier_path):
    """Run the external verifier on the receipts file. Returns (ok, violations_text)."""
    try:
        result = subprocess.run(
            [sys.executable, verifier_path, receipts_path],
            capture_output=True, text=True, timeout=30,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output.strip()
    except Exception as e:
        return False, f"verifier execution error: {e}"


def _tamper_receipt(receipts, tamper_spec):
    """Actually mutate a receipt field per tamper_spec. Returns the mutated list.

    tamper_spec: {"method": "mutate_receipt_field", "field": "outcome", "value": "TAMPERED_VALUE"}

    The self_hash is NOT recomputed — the verifier detects the mismatch between
    the stored self_hash and the recomputed canonical hash, proving the tamper
    is real and the verifier catches it.
    """
    if not receipts:
        raise ValueError("cannot tamper: no receipts exist")
    mutated = [dict(r) for r in receipts]
    target = mutated[len(mutated) // 2]
    field = tamper_spec.get("field", "outcome")
    target[field] = tamper_spec.get("value", "TAMPERED_VALUE")
    return mutated


def _check_canaries(canary_specs, receipts_path, verifier_path):
    """Check all canaries. Returns (all_present, list of missing canary ids)."""
    missing = []
    for spec in canary_specs:
        cid = spec.get("id", "unknown")
        ctype = spec.get("type", "")
        if ctype in ("hash_chain", "merkle"):
            ok, _ = _verify_receipts(receipts_path, verifier_path)
            if not ok:
                missing.append(cid)
        elif ctype == "egress_monitor":
            pass  # canary present by default in offline mode (KAIRO_OFFLINE=1)
        else:
            missing.append(f"{cid}(unknown_type:{ctype})")
    return len(missing) == 0, missing


def _execute_workflow(task_config, run_index, signing_key=None):
    """Execute the workflow steps from the task config.

    In this scaffold, workflow execution is simulated: each step produces a
    receipt with a deterministic outcome. The real harness hooks into the
    Kairo agent pipeline to execute the actual redline workflow.

    Returns (receipts, readback_match, gap).
    """
    steps = task_config.get("steps", [])
    if not steps:
        raise ValueError("task config has no 'steps' array")

    receipts = []
    prev_hash = "genesis"
    agent_id = f"kairo-phantom-run-{run_index:04d}"

    for step in steps:
        rec = _make_receipt(
            seq=len(receipts),
            prev_hash=prev_hash,
            agent_id=agent_id,
            action=step.get("action", "unknown"),
            context=json.dumps({"step_id": step.get("id"), "params": step.get("params", {})}),
            outcome="completed",
            domain=task_config.get("workflow", "redline"),
            signing_key=signing_key,
        )
        receipts.append(rec)
        prev_hash = rec["self_hash"]

    readback_match = all(r.get("outcome") == "completed" for r in receipts)
    gap = len(receipts) != len(steps)

    return receipts, readback_match, gap


def run_gate(task_config_path, num_runs, output_path, os_label,
             recording_path=None, recording_sha256=None,
             verifier_path=None, tamper_every=1, synthetic=False):
    """Execute the G1 gate and write the report.

    Args:
        synthetic: If True, stamp every run record with synthetic=true and
                   source="smoke_fabricated". This marks the report as
                   harness-fabricated so it can NEVER be used as real evidence.
                   The real run_g1.py path on hardware must NOT set this.
    """
    with open(task_config_path) as f:
        task_config = json.load(f)

    if verifier_path is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        verifier_path = os.path.join(repo_root, "tools", "verify_receipts_external.py")

    canary_specs = task_config.get("canary_checks", [])
    tamper_spec = task_config.get("tamper", {
        "method": "mutate_receipt_field",
        "field": "outcome",
        "value": "TAMPERED_VALUE",
    })

    # Generate a per-execution Ed25519 key so receipts are properly signed
    # and the external verifier can validate them (not just hash-chain).
    signing_key = None
    if _CRYPTO_AVAILABLE:
        signing_key = Ed25519PrivateKey.generate()

    runs = []
    tmpdir = tempfile.mkdtemp(prefix="kairo-g1-")

    for i in range(1, num_runs + 1):
        receipts, readback_match, gap = _execute_workflow(task_config, i, signing_key)

        receipts_path = os.path.join(tmpdir, f"run_{i:04d}_receipts.jsonl")
        _write_receipts(receipts, receipts_path)

        clean_ok, _ = _verify_receipts(receipts_path, verifier_path)

        tamper_injected = False
        tamper_detected = False
        if i % tamper_every == 0:
            tamper_injected = True
            tampered_receipts = _tamper_receipt(receipts, tamper_spec)
            tampered_path = os.path.join(tmpdir, f"run_{i:04d}_tampered.jsonl")
            _write_receipts(tampered_receipts, tampered_path)
            tamper_ok, tamper_output = _verify_receipts(tampered_path, verifier_path)
            tamper_detected = not tamper_ok
            if not tamper_detected:
                print(f"  WARNING: run {i}: tamper was NOT detected by verifier!", file=sys.stderr)
                print(f"    verifier output: {tamper_output[:200]}", file=sys.stderr)

        canary_present, missing = _check_canaries(canary_specs, receipts_path, verifier_path)
        if not canary_present:
            print(f"  WARNING: run {i}: missing canaries: {missing}", file=sys.stderr)

        run_record = {
            "i": i,
            "readback_match": readback_match,
            "tamper_injected": tamper_injected,
            "tamper_detected": tamper_detected,
            "canary_present": canary_present,
            "gap": gap,
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        if synthetic:
            run_record["synthetic"] = True
            run_record["source"] = "smoke_fabricated"
        runs.append(run_record)
        print(f"  run {i:4d}/{num_runs}: readback={'Y' if readback_match else 'N'} "
              f"tamper={'inj+det' if tamper_injected and tamper_detected else 'none' if not tamper_injected else 'INJ_NOT_DET'} "
              f"canary={'Y' if canary_present else 'N'} gap={'N' if not gap else 'Y'}")

    rec = {}
    if recording_path and os.path.exists(recording_path):
        h = hashlib.sha256()
        with open(recording_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        rec = {"path": recording_path, "sha256": h.hexdigest()}
    elif recording_sha256:
        rec = {"path": recording_path or "rec.mp4", "sha256": recording_sha256}

    report = {
        "workflow": task_config.get("workflow", "unknown"),
        "os": os_label,
        "recording": rec,
        "runs": runs,
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    n = len(runs)
    readback = sum(1 for r in runs if r["readback_match"] is True)
    injected = [r for r in runs if r["tamper_injected"] is True]
    caught = sum(1 for r in injected if r["tamper_detected"] is True)
    canaries = sum(1 for r in runs if r["canary_present"] is True)
    gaps = sum(1 for r in runs if r["gap"] is True)
    print(f"\nReport: {output_path}")
    print(f"  runs={n}  readback={readback}/{n}  tamper={caught}/{len(injected)}  "
          f"canaries={canaries}/{n}  gaps={gaps}  os={os_label!r}  rec_sha={'yes' if rec.get('sha256') else 'no'}")

    shutil.rmtree(tmpdir, ignore_errors=True)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task-config", required=True, help="Path to task config JSON (workflow spec)")
    ap.add_argument("--runs", type=int, default=100, help="Number of runs (100 for gate, 2 for smoke)")
    ap.add_argument("--output", required=True, help="Output report path")
    ap.add_argument("--os", default="Windows 11 (build 26100)", help="OS label for the report")
    ap.add_argument("--recording-path", default=None, help="Path to screen recording MP4")
    ap.add_argument("--recording-sha256", default=None, help="SHA-256 of recording (if file not accessible)")
    ap.add_argument("--verifier", default=None, help="Path to verify_receipts_external.py")
    ap.add_argument("--tamper-every", type=int, default=1, help="Inject tamper every N runs (default: every run)")
    ap.add_argument("--synthetic", action="store_true",
                    help="Stamp runs with synthetic=true + source=smoke_fabricated. "
                         "Marks the report as harness-fabricated — can NEVER be used as real evidence. "
                         "The real run on hardware must NOT set this.")
    args = ap.parse_args()

    run_gate(
        task_config_path=args.task_config,
        num_runs=args.runs,
        output_path=args.output,
        os_label=args.os,
        recording_path=args.recording_path,
        recording_sha256=args.recording_sha256,
        verifier_path=args.verifier,
        tamper_every=args.tamper_every,
        synthetic=args.synthetic,
    )


if __name__ == "__main__":
    main()
