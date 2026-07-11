#!/usr/bin/env python3
"""
Integrity self-test for the Kairo-Phantom loop (v1.2.1).

Anyone can run this to confirm the loop REFUSES fake green and DETECTS ledger
tampering. It builds a throwaway environment in a temp dir (never touches the
real state.json), generates a demo signing key, and asserts:

  1. attesting with an empty `{}` file is REJECTED
  2. attesting with an unsigned manifest is REJECTED
  3. attesting with a manifest signed by an UNTRUSTED key is REJECTED
  4. a genuine signed manifest + valid 100-run report is ACCEPTED (positive path)
  5. a report with readback 98/100 is REJECTED (semantics, not file existence)
  6. a manually altered history event is DETECTED by `verify` / refused by mutation

Run:  python3 tools/selftest_loop.py
Exit code 0 = all integrity properties hold.
"""
import base64, json, os, shutil, subprocess, sys, tempfile, hashlib, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.dirname(HERE)
sys.path.insert(0, LOOP)
import validators as V
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PY = sys.executable
PASS, FAIL = "\033[92mOK\033[0m", "\033[91mFAIL\033[0m"
results = []


def run(env_dir, *args):
    cmd = [PY, os.path.join(env_dir, "orchestrator.py"), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=env_dir)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{PASS if cond else FAIL}] {name}" + (f"  — {detail}" if detail and not cond else ""))


def sign(manifest, seed, signer):
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    manifest["signer"] = signer
    body = {k: v for k, v in manifest.items() if k != "signature"}
    manifest["signature"] = base64.b64encode(sk.sign(V.canonical(body))).decode()
    return manifest


def make_report(readback_ok=100, n=100):
    runs = []
    for i in range(1, n + 1):
        runs.append({
            "i": i,
            "readback_match": i <= readback_ok,
            "tamper_injected": True,
            "tamper_detected": True,
            "canary_present": True,
            "gap": False,
            "ts": f"2026-07-20T10:{i % 60:02d}:00",
        })
    return {
        "workflow": "demo-contract-redline",
        "os": "Windows 11 (build 26100)",
        "recording": {"path": "rec.mp4", "sha256": "deadbeef"},
        "runs": runs,
    }


def main():
    print("Kairo-Phantom loop integrity self-test (v1.2.1)\n")
    tmp = tempfile.mkdtemp(prefix="kairo-selftest-")
    env = os.path.join(tmp, "loop")
    shutil.copytree(LOOP, env)
    # minimal isolated state: single task T3 (deps [], gate G1) so we can test attest directly
    state = {
        "project": "selftest", "version": "1.2.1",
        "repo": {"head_commit": ""},
        "defaults": {"max_iterations": 4, "antithrash_repeat_limit": 2},
        "gates": {"G1": {"title": "G1", "day": 30, "status": "blocked", "deps": ["T3"], "oracle": "attestation"}},
        "tasks": [{"id": "T3", "title": "demo", "phase": "1", "deps": [], "status": "pending",
                   "oracle": {"type": "attestation", "requires_evidence": True, "artifact": "runs/g1_100run_report.json"},
                   "gate": "G1", "attempts": []}],
        "history": [],
    }
    statep = os.path.join(env, "state.json")
    json.dump(state, open(statep, "w"), indent=2)
    os.makedirs(os.path.join(env, "runs"), exist_ok=True)
    os.makedirs(os.path.join(env, "evidence"), exist_ok=True)

    # demo key + trust roots
    seed = Ed25519PrivateKey.generate().private_bytes_raw()
    pub = base64.b64encode(Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()).decode()
    roots = os.path.join(env, "schemas", "trust_roots.json")
    json.dump({"signers": {"demo-founder": pub}}, open(roots, "w"))
    untrusted_seed = Ed25519PrivateKey.generate().private_bytes_raw()

    def manifest_for(report_path):
        return {
            "target": "T3", "base_commit": "demo000",
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "env": {"os": "Windows 11", "toolchain": "py3.11/rust1.79", "lockfile_sha256": "abc"},
            "artifact": {"path": os.path.abspath(report_path), "sha256": V.sha256_file(report_path)},
        }

    # 1. empty {}
    empty = os.path.join(env, "runs", "g1_100run_report.json")
    open(empty, "w").write("{}")
    empty_manifest = os.path.join(env, "evidence", "empty.json")
    open(empty_manifest, "w").write("{}")
    rc, out = run(env, "attest", "--task", "T3", "--verdict", "pass", "--evidence", empty_manifest)
    check("empty {} manifest is REJECTED", rc != 0 and "REJECTED" in out, out.strip()[-200:])

    # good report
    good = os.path.join(env, "runs", "g1_100run_report.json")
    json.dump(make_report(100), open(good, "w"))

    # 2. unsigned manifest
    m = manifest_for(good)
    unsigned = os.path.join(env, "evidence", "unsigned.json")
    json.dump(m, open(unsigned, "w"))
    rc, out = run(env, "attest", "--task", "T3", "--verdict", "pass", "--evidence", unsigned)
    check("unsigned manifest is REJECTED", rc != 0 and "REJECTED" in out, out.strip()[-200:])

    # 3. untrusted signer
    m = manifest_for(good)
    sign(m, untrusted_seed, "stranger")
    untrusted = os.path.join(env, "evidence", "untrusted.json")
    json.dump(m, open(untrusted, "w"))
    rc, out = run(env, "attest", "--task", "T3", "--verdict", "pass", "--evidence", untrusted)
    check("untrusted signer is REJECTED", rc != 0 and "REJECTED" in out, out.strip()[-200:])

    # 4. genuine signed manifest + valid report -> ACCEPTED
    m = manifest_for(good)
    sign(m, seed, "demo-founder")
    goodman = os.path.join(env, "evidence", "good.json")
    json.dump(m, open(goodman, "w"))
    rc, out = run(env, "attest", "--task", "T3", "--verdict", "pass", "--evidence", goodman)
    check("genuine signed manifest + valid 100-run report is ACCEPTED", rc == 0 and "[PASS]" in out, out.strip()[-200:])

    # reset T3 for the negative-semantics test
    run(env, "reset", "--task", "T3")

    # 5. readback 98/100 -> REJECTED (semantic)
    bad = os.path.join(env, "runs", "g1_100run_report.json")
    json.dump(make_report(readback_ok=98), open(bad, "w"))
    m = manifest_for(bad)
    sign(m, seed, "demo-founder")
    badman = os.path.join(env, "evidence", "bad.json")
    json.dump(m, open(badman, "w"))
    rc, out = run(env, "attest", "--task", "T3", "--verdict", "pass", "--evidence", badman)
    check("readback 98/100 is REJECTED (semantic, computed from records)", rc != 0 and "REJECTED" in out, out.strip()[-200:])

    # 6. tamper the history ledger -> detected
    st = json.load(open(statep))
    if st.get("history"):
        st["history"][0]["note"] = "TAMPERED"
        json.dump(st, open(statep, "w"), indent=2)
        rc, out = run(env, "verify")
        check("altered history event is DETECTED by verify", rc != 0 and "FAIL" in out, out.strip()[-200:])
        rc, out = run(env, "refresh")
        check("mutation REFUSED while ledger is broken", rc != 0 and "REFUSED" in out, out.strip()[-200:])
    else:
        check("history present to tamper", False, "no history events recorded")

    shutil.rmtree(tmp, ignore_errors=True)
    ok = all(results)
    print(f"\n{'ALL INTEGRITY PROPERTIES HOLD' if ok else 'INTEGRITY TEST FAILED'} — {sum(results)}/{len(results)} checks passed")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
