#!/usr/bin/env python3
"""
Kairo-Phantom loop orchestrator (v1.2.1 — truth-gated).

House rule: NO FAKE GREEN. A task/gate is 'done' only when its script oracle
returns PASS, or a human attestation is backed by a SIGNED evidence MANIFEST
whose ARTIFACT content clears that gate's real definition of done.

v1.2.1 fixes (from the co-founder red-team of v1.2):
  - Human attestations now require a signed manifest (Ed25519, trust-rooted) +
    an artifact whose CONTENT is validated by a per-gate semantic validator
    (see validators.py). An empty `{}` file is rejected; G1's 99/100 readback
    is COMPUTED from individual run records, never trusted from a summary.
  - The history ledger is HASH-CHAIN VERIFIED on every load. If the chain is
    broken, mutating commands refuse to run and `status` prints a loud warning.
  - One file lock now covers the whole load -> modify -> save transaction
    (not just the write), preventing lost updates under concurrency.
  - Evidence must carry provenance (base_commit, env manifest) and be fresh;
    a base_commit mismatch or stale timestamp is rejected.
  - Gates with no feeding task (G0, G3, G4) can be attested directly and are
    validated the same way.

Usage:
  python3 orchestrator.py status
  python3 orchestrator.py next
  python3 orchestrator.py refresh
  python3 orchestrator.py run      --task T0
  python3 orchestrator.py attest   --task T3 --verdict pass --evidence <manifest.json> --note "..."
  python3 orchestrator.py wont_fix --task G4 --reason "..." --evidence <manifest.json>
  python3 orchestrator.py reset    --task T0
  python3 orchestrator.py verify                     # re-check the history chain

Optional flags on attest/wont_fix:
  --trust-roots <path>   (default: schemas/trust_roots.json)
  --base-commit <sha>    (overrides state.repo.head_commit for the freshness check)
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import validators as V

try:
    import fcntl
    HAVE_FCNTL = True
except Exception:
    HAVE_FCNTL = False

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
LOCK = os.path.join(HERE, ".state.lock")
DEFAULT_TRUST_ROOTS = os.path.join(HERE, "schemas", "trust_roots.json")
REPEAT_LIMIT = 2
TERMINAL_GREEN = "done"
TERMINAL_NONGREEN = "wont_fix"


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------- locking (fix: cover load->modify->save) ----------------

def acquire_lock():
    if not HAVE_FCNTL:
        return None
    fd = open(LOCK, "w")
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def release_lock(fd):
    if fd is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


# ---------------- state load/save ----------------

def load(require_intact_chain=False):
    with open(STATE) as f:
        s = json.load(f)
    ok, msg = V.verify_history_chain(s.get("history", []))
    s["_chain_ok"] = ok
    s["_chain_msg"] = msg
    if not ok and require_intact_chain:
        sys.exit(f"REFUSED: history ledger integrity check FAILED — {msg}. "
                 f"The state file was altered outside the orchestrator. "
                 f"Investigate before any mutation.")
    return s


def save(s):
    """Atomic write: temp file -> fsync -> os.replace. Caller holds the lock."""
    s.pop("_chain_ok", None)
    s.pop("_chain_msg", None)
    d = json.dumps(s, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=HERE, prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(d)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STATE)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def log(s, event, **kw):
    hist = s.setdefault("history", [])
    prev_hash = hist[-1]["hash"] if hist else "genesis"
    entry = {"ts": now(), "event": event, "prev_hash": prev_hash}
    entry.update(kw)
    body = json.dumps(entry, sort_keys=True)
    entry["hash"] = hashlib.sha256((prev_hash + body).encode()).hexdigest()
    hist.append(entry)


# ---------------- lookups ----------------

def find_task(s, tid):
    for t in s["tasks"]:
        if t["id"] == tid:
            return t
    return None


def task(s, tid):
    t = find_task(s, tid)
    if t is None:
        sys.exit(f"unknown task {tid}")
    return t


def deps_done(s, deps):
    done = {x["id"] for x in s["tasks"] if x["status"] == TERMINAL_GREEN}
    return all(d in done for d in (deps or []))


def effective_status(s, t):
    if t["status"] == "blocked" and deps_done(s, t.get("deps", [])):
        return "pending"
    return t["status"]


def refresh_blocked(s):
    changed = 0
    for t in s["tasks"]:
        if t["status"] == "blocked" and deps_done(s, t.get("deps", [])):
            t["status"] = "pending"
            changed += 1
    return changed


def parse_signature(output):
    for line in (output or "").splitlines():
        line = line.strip()
        if line.startswith("SIGNATURE:"):
            raw = line[len("SIGNATURE:"):].strip()
            try:
                obj = json.loads(raw)
                stable = {k: obj[k] for k in ("code", "subject", "count") if k in obj}
                canon = json.dumps(stable, sort_keys=True)
                return hashlib.sha1(canon.encode()).hexdigest()[:12] + ":" + stable.get("code", "?")
            except Exception:
                pass
    first = (output or "").strip().splitlines()
    line = first[0] if first else ""
    return hashlib.sha1(line.strip().lower().encode()).hexdigest()[:12] + ":" + line[:60]


def run_script(cmd):
    full = [sys.executable, os.path.join(HERE, cmd[0])] + [
        (os.path.join(HERE, c) if not c.startswith("/") else c) for c in cmd[1:]
    ]
    try:
        p = subprocess.run(full, capture_output=True, text=True, cwd=HERE, timeout=120)
    except Exception as e:
        return False, f"oracle crashed: {e}"
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out.strip()


# ---------------- evidence (manifest + signature + semantics) ----------------

def verify_attestation_evidence(target_id, evidence, here, trust_roots_path,
                                expected_commit, required_artifact=None):
    """Return (ok, record, message). Enforces:
      1. evidence is a real, non-empty, signed JSON manifest
      2. Ed25519 signature verifies against a trust-rooted signer (fail-closed)
      3. provenance/freshness/artifact-hash checks
      4. the per-gate semantic validator passes on the artifact content
    """
    if not evidence:
        return False, None, "no --evidence manifest provided"
    cand = evidence if os.path.isabs(evidence) else os.path.join(here, evidence)
    if not os.path.exists(cand):
        return False, None, f"evidence file not found: {evidence} (arbitrary strings are rejected)"
    try:
        with open(cand) as f:
            manifest = json.load(f)
    except Exception:
        return False, None, ("evidence must be a signed JSON manifest — a bare artifact or "
                             "non-JSON string is not acceptable for a human gate")
    try:
        trust_roots = V.load_trust_roots(trust_roots_path)
        artifact_path = V.check_manifest_common(
            manifest, here, target_id, expected_commit=expected_commit)
        if required_artifact and not manifest["artifact"]["path"].replace("\\", "/").endswith(required_artifact):
            return False, None, (f"this gate requires artifact '{required_artifact}', "
                                 f"manifest points to '{manifest['artifact']['path']}'")
        signer = V.verify_signature(manifest, trust_roots)
        detail = V.validate(target_id, manifest, artifact_path, here)
    except V.EvidenceError as e:
        return False, None, str(e)
    rec = {
        "kind": "signed_manifest",
        "manifest": os.path.relpath(cand, here),
        "artifact": manifest["artifact"]["path"],
        "artifact_sha256": manifest["artifact"]["sha256"],
        "signer": signer,
        "base_commit": manifest["base_commit"],
        "created_at": manifest["created_at"],
        "validated": detail,
    }
    return True, rec, f"signed by '{signer}'; {detail}"


def verify_plain_evidence(evidence, here):
    """Lighter check used by wont_fix: require a real file (decision note or
    manifest). Non-file strings are rejected, but no gate semantics are run."""
    if not evidence:
        return True, None, "no evidence file"
    cand = evidence if os.path.isabs(evidence) else os.path.join(here, evidence)
    if not os.path.exists(cand):
        return False, None, f"evidence file not found: {evidence}"
    return True, {"kind": "file", "artifact": evidence, "sha256": V.sha256_file(cand)}, "file recorded"


# ---------------- read-only commands ----------------

ICON = {"done": "[DONE]", "pending": "[ pend]", "in_progress": "[work]",
        "blocked": "[lock]", "halted": "[HALT]", "awaiting_oracle": "[oracl]",
        "wont_fix": "[WONT]"}


def chain_banner(s):
    if not s.get("_chain_ok", True):
        print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"!! LEDGER INTEGRITY FAILURE: {s.get('_chain_msg')}")
        print("!! state.json history was altered outside the orchestrator.")
        print("!! Mutating commands are refused until this is investigated.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")


def cmd_status(s):
    chain_banner(s)
    print("\n=== GATES ===")
    for gid, g in s["gates"].items():
        print(f"  {ICON.get(g['status'],'?')} {gid} (day {g['day']}): {g['title']} [{g['status']}]")
    print("\n=== TASKS (effective, read-only) ===")
    for t in s["tasks"]:
        eff = effective_status(s, t)
        deps = ",".join(t.get("deps", [])) or "-"
        n = len(t.get("attempts", []))
        gate = f" gate={t['gate']}" if t.get("gate") else ""
        print(f"  {ICON.get(eff,'?')} {t['id']}: {t['title']} [{eff}] deps={deps}{gate} attempts={n}")
    hp = [t for t in s["tasks"] if t["status"] == "halted"]
    if hp:
        print("\n!! HALTED — human decision required (change APPROACH or wont_fix):")
        for t in hp:
            last = t["attempts"][-1] if t.get("attempts") else {}
            print(f"  {t['id']}: last signature = {last.get('signature','?')}")
    print(f"\n(chain: {s.get('_chain_msg')}) (status is read-only; 'refresh' promotes blocked->pending)\n")


def cmd_next(s):
    actionable = [t for t in s["tasks"] if effective_status(s, t) in ("pending", "in_progress")]
    if not actionable:
        print("No actionable task. Everything is done, blocked, halted, or wont_fix. Run 'status'.")
        return
    t = actionable[0]
    print(f"NEXT: {t['id']} — {t['title']}")
    print(f"Task card: tasks/{t['id']}_*.md")
    print(f"Oracle: {json.dumps(t['oracle'])}")
    print("(next is read-only)")


def cmd_verify(s):
    ok, msg = V.verify_history_chain(s.get("history", []))
    print(("[OK] " if ok else "[FAIL] ") + msg)
    sys.exit(0 if ok else 1)


# ---------------- mutating commands ----------------

def record(s, t, passed, output, kind):
    sig = parse_signature(output) if not passed else "PASS"
    attempts = t.setdefault("attempts", [])
    attempts.append({"ts": now(), "kind": kind, "passed": passed, "signature": sig, "output": output[:2000]})
    log(s, "oracle_run", task=t["id"], passed=passed, signature=sig)
    if passed:
        t["status"] = TERMINAL_GREEN
        if t.get("gate"):
            s["gates"][t["gate"]]["status"] = "pending"
        refresh_blocked(s)
        print(f"[PASS] {t['id']}")
        return
    sigs = [a["signature"] for a in attempts if not a["passed"]]
    if len(sigs) >= REPEAT_LIMIT and len(set(sigs[-REPEAT_LIMIT:])) == 1:
        t["status"] = "halted"
        print(f"[HALT] {t['id']} anti-thrash: same failure signature {REPEAT_LIMIT}x.")
        print("   A human must change the APPROACH (not retry) or mark wont_fix.")
    elif len(attempts) >= t.get("max_iterations", s["defaults"]["max_iterations"]):
        t["status"] = "halted"
        print(f"[HALT] {t['id']} budget: {len(attempts)} iterations used.")
    else:
        t["status"] = "in_progress"
        print(f"[FAIL] {t['id']} — iterate. signature={sig}")
    print("---- oracle output ----")
    print(output[:1200])


def cmd_run(s, tid):
    refresh_blocked(s)
    t = task(s, tid)
    if t["status"] in (TERMINAL_GREEN, TERMINAL_NONGREEN):
        sys.exit(f"{tid} is {t['status']}; reset it first if you really mean to re-run.")
    if t["status"] == "blocked":
        sys.exit(f"{tid} is blocked; deps not done: {t.get('deps')}")
    if t["oracle"]["type"] != "script":
        sys.exit(f"{tid} uses a '{t['oracle']['type']}' oracle. Use: attest --task {tid} --verdict pass --evidence <manifest>")
    passed, out = run_script(t["oracle"]["cmd"])
    if passed and t["oracle"].get("then"):
        p2, o2 = run_script(t["oracle"]["then"])
        passed, out = (passed and p2), out + "\n" + o2
    record(s, t, passed, out, kind="script")


def cmd_attest(s, tid, verdict, note, evidence, reopen, trust_roots_path, base_commit):
    refresh_blocked(s)
    expected_commit = base_commit or (s.get("repo", {}) or {}).get("head_commit")
    is_gate = tid in s["gates"]
    t = None if is_gate else task(s, tid)

    # dependency + terminal-state guards
    if is_gate:
        g = s["gates"][tid]
        if not deps_done(s, g.get("deps", [])):
            sys.exit(f"REJECTED: gate {tid} has unmet deps {g.get('deps')}. Attestation refused.")
        cur = g["status"]
    else:
        if t["status"] == "blocked" or not deps_done(s, t.get("deps", [])):
            sys.exit(f"REJECTED: {tid} is blocked; unmet deps {t.get('deps')}. Attestation refused.")
        if t["oracle"]["type"] == "script":
            sys.exit(f"REJECTED: {tid} has a script oracle; use 'run --task {tid}', not attest.")
        cur = t["status"]
    if cur in (TERMINAL_GREEN, TERMINAL_NONGREEN) and not reopen:
        sys.exit(f"REJECTED: {tid} is already '{cur}'. Pass --reopen to re-attest (human decision).")

    if verdict != "pass":
        if is_gate:
            s["gates"][tid]["status"] = "pending"
        else:
            t.setdefault("attempts", []).append({"ts": now(), "kind": "attestation", "passed": False, "signature": "attest_fail", "output": note[:2000]})
            t["status"] = "in_progress"
        log(s, "attestation", target=tid, passed=False, note=note)
        print(f"[FAIL] {tid} attested fail — iterate.")
        return

    required_artifact = None if is_gate else t["oracle"].get("artifact")
    ok, rec, msg = verify_attestation_evidence(
        tid, evidence, HERE, trust_roots_path, expected_commit, required_artifact)
    if not ok:
        sys.exit(f"REJECTED: attestation PASS needs verifiable, sufficient evidence.\n  -> {msg}")
    log(s, "attestation", target=tid, passed=True,
        evidence_sha256=rec["artifact_sha256"], signer=rec["signer"], note=note)
    if is_gate:
        g = s["gates"][tid]
        g["status"] = TERMINAL_GREEN
        g["evidence"] = rec
    else:
        t.setdefault("attempts", []).append({"ts": now(), "kind": "attestation", "passed": True, "signature": "PASS", "output": msg[:2000]})
        t["status"] = TERMINAL_GREEN
        t["evidence"] = rec
        if t.get("gate"):
            s["gates"][t["gate"]]["status"] = TERMINAL_GREEN
            s["gates"][t["gate"]]["evidence"] = rec
        refresh_blocked(s)
    print(f"[PASS] {tid} attested. {msg}")


def cmd_wont_fix(s, tid, reason, evidence):
    if not reason:
        sys.exit("wont_fix requires --reason")
    ok, rec, msg = verify_plain_evidence(evidence, HERE)
    if evidence and not ok:
        sys.exit(f"REJECTED: wont_fix evidence unverifiable. {msg}")
    if tid in s["gates"]:
        s["gates"][tid]["status"] = TERMINAL_NONGREEN
        s["gates"][tid]["wont_fix"] = {"reason": reason, "evidence": rec}
    else:
        t = task(s, tid)
        t["status"] = TERMINAL_NONGREEN
        t["wont_fix"] = {"reason": reason, "evidence": rec}
    log(s, "wont_fix", target=tid, reason=reason, evidence_sha256=(rec or {}).get("sha256"))
    print(f"[WONT_FIX] {tid} marked terminal non-green. Reason: {reason}")
    print("   NOTE: dependents remain blocked; this is NOT equivalent to 'done'.")


def cmd_refresh(s):
    n = refresh_blocked(s)
    log(s, "refresh", promoted=n)
    print(f"refresh: promoted {n} task(s) blocked->pending")


def cmd_reset(s, tid):
    t = task(s, tid)
    t["attempts"] = []
    t.pop("wont_fix", None)
    t.pop("evidence", None)
    t["status"] = "pending" if deps_done(s, t.get("deps", [])) else "blocked"
    log(s, "reset", task=tid)
    print(f"reset {tid} -> {t['status']}")


MUTATING = {"run", "attest", "reset", "wont_fix", "refresh"}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status"); sub.add_parser("next")
    sub.add_parser("refresh"); sub.add_parser("verify")
    for name in ("run", "reset"):
        p = sub.add_parser(name); p.add_argument("--task", required=True)
    pa = sub.add_parser("attest")
    pa.add_argument("--task", required=True)
    pa.add_argument("--verdict", required=True, choices=["pass", "fail"])
    pa.add_argument("--note", default="")
    pa.add_argument("--evidence", default="")
    pa.add_argument("--reopen", action="store_true")
    pa.add_argument("--trust-roots", default=DEFAULT_TRUST_ROOTS)
    pa.add_argument("--base-commit", default="")
    pw = sub.add_parser("wont_fix")
    pw.add_argument("--task", required=True)
    pw.add_argument("--reason", required=True)
    pw.add_argument("--evidence", default="")
    a = ap.parse_args()

    mutating = a.cmd in MUTATING
    lock_fd = acquire_lock() if mutating else None
    try:
        s = load(require_intact_chain=mutating)
        if a.cmd == "status": cmd_status(s)
        elif a.cmd == "next": cmd_next(s)
        elif a.cmd == "verify": cmd_verify(s)
        elif a.cmd == "refresh": cmd_refresh(s)
        elif a.cmd == "run": cmd_run(s, a.task)
        elif a.cmd == "attest":
            cmd_attest(s, a.task, a.verdict, a.note, a.evidence, a.reopen,
                       a.trust_roots, a.base_commit)
        elif a.cmd == "wont_fix": cmd_wont_fix(s, a.task, a.reason, a.evidence)
        elif a.cmd == "reset": cmd_reset(s, a.task)
        if mutating:
            save(s)
    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    main()
