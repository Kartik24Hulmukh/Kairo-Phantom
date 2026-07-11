#!/usr/bin/env python3
"""
Kairo-Phantom loop orchestrator (v1.2 — integrity-hardened).

Drives the AGA-response sprint as self-correcting, oracle-gated loops.
House rule: NO FAKE GREEN. A task is 'done' only when its oracle returns PASS
or a human attestation is backed by a real, hash-verified evidence file.

v1.2 integrity fixes (from Kairo_phantom_v1.1_final_updates.md sections 4.1-4.6):
  - attest REJECTS a task that is blocked, has unmet deps, or is already done
    (unless --reopen is passed by a human).
  - attest evidence must be a REAL FILE (a structured JSON pointer OR an artifact
    file). Arbitrary strings like '--evidence bananas' are rejected. The file's
    sha256 is recomputed and appended to the (hash-chained) history.
  - `status` and `next` are strictly NON-MUTATING (no save, no side effects).
    Effective statuses are computed in memory only.
  - `wont_fix` is a real terminal, NON-GREEN state (not equal to done). Its
    dependents stay blocked unless a human resets them.
  - state.json is written ATOMICALLY (temp file -> fsync -> os.replace) under a
    file lock, and every history event is hash-chained (prev_hash -> hash).
  - anti-thrash uses the oracle's STRUCTURED signature line when present
    ('SIGNATURE: {json}'), else falls back to the normalized first output line.

Usage:
  python3 orchestrator.py status                      # read-only board
  python3 orchestrator.py next                         # read-only: next actionable
  python3 orchestrator.py refresh                      # promote blocked->pending (mutates)
  python3 orchestrator.py run     --task T0            # run a script oracle
  python3 orchestrator.py attest  --task T3 --verdict pass --evidence runs/g1.json --note "..."
  python3 orchestrator.py wont_fix --task G4 --reason "..." --evidence docs/decision.md
  python3 orchestrator.py reset   --task T0            # clear attempts (human decision)
"""
import argparse, json, os, subprocess, sys, datetime, hashlib, tempfile
try:
    import fcntl
    HAVE_FCNTL = True
except Exception:
    HAVE_FCNTL = False

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
LOCK = os.path.join(HERE, ".state.lock")
REPEAT_LIMIT = 2
TERMINAL_GREEN = "done"
TERMINAL_NONGREEN = "wont_fix"


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load():
    with open(STATE) as f:
        return json.load(f)


def save(s):
    """Atomic write: temp file -> fsync -> os.replace, under a best-effort lock."""
    lock_fd = None
    if HAVE_FCNTL:
        lock_fd = open(LOCK, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
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
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


def log(s, event, **kw):
    """Append a hash-chained history event."""
    hist = s.setdefault("history", [])
    prev_hash = hist[-1]["hash"] if hist else "genesis"
    entry = {"ts": now(), "event": event, "prev_hash": prev_hash}
    entry.update(kw)
    body = json.dumps(entry, sort_keys=True)
    entry["hash"] = hashlib.sha256((prev_hash + body).encode()).hexdigest()
    hist.append(entry)


def task(s, tid):
    for t in s["tasks"]:
        if t["id"] == tid:
            return t
    sys.exit(f"unknown task {tid}")


def deps_done(s, t):
    done = {x["id"] for x in s["tasks"] if x["status"] == TERMINAL_GREEN}
    return all(d in done for d in t.get("deps", []))


def effective_status(s, t):
    """Pure function: what a task's status WOULD be, without mutating state.
    A stored terminal/active status wins; a stored 'blocked' becomes 'pending'
    only for display when deps are satisfied."""
    st = t["status"]
    if st == "blocked" and deps_done(s, t):
        return "pending"
    return st


def refresh_blocked(s):
    """MUTATING: promote blocked->pending when deps are satisfied."""
    changed = 0
    for t in s["tasks"]:
        if t["status"] == "blocked" and deps_done(s, t):
            t["status"] = "pending"
            changed += 1
    return changed


def parse_signature(output):
    """Prefer a structured 'SIGNATURE: {json}' line from the oracle; hash canonical
    JSON of stable fields. Fall back to the normalized first line for legacy oracles."""
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


# ---------------- evidence verification (fix 4.2) ----------------

def verify_evidence(evidence, required_artifact=None):
    """Return (ok, record_dict, message).
    Accepts either:
      (a) a path to a JSON pointer file with at least {path, sha256} (optionally
          type/created_at/signer/signature). We recompute the pointed file's hash
          and require it to match the declared sha256.
      (b) a direct path to an evidence artifact file, whose hash we record.
    Arbitrary non-file strings are REJECTED. If required_artifact is set, the
    resolved artifact path must end with it."""
    if not evidence:
        return False, None, "no --evidence provided"
    cand = evidence if os.path.isabs(evidence) else os.path.join(HERE, evidence)
    if not os.path.exists(cand):
        return False, None, f"evidence file not found: {evidence} (arbitrary strings are rejected)"
    # Is it a JSON pointer?
    pointer = None
    if cand.endswith(".json"):
        try:
            with open(cand) as f:
                obj = json.load(f)
            if isinstance(obj, dict) and "path" in obj and "sha256" in obj:
                pointer = obj
        except Exception:
            pointer = None
    if pointer is not None:
        target = pointer["path"]
        tpath = target if os.path.isabs(target) else os.path.join(HERE, target)
        if not os.path.exists(tpath):
            return False, None, f"pointer target missing: {target}"
        actual = sha256_file(tpath)
        if actual.lower() != str(pointer["sha256"]).lower():
            return False, None, f"HASH MISMATCH for {target}: declared {pointer['sha256'][:16]}... actual {actual[:16]}..."
        artifact_path, artifact_hash = target, actual
        rec = {"kind": "pointer", "pointer": cand, "artifact": target,
               "sha256": actual, "signer": pointer.get("signer"),
               "created_at": pointer.get("created_at"),
               "signature": pointer.get("signature")}
    else:
        artifact_path, artifact_hash = evidence, sha256_file(cand)
        rec = {"kind": "file", "artifact": evidence, "sha256": artifact_hash}
    if required_artifact and not artifact_path.replace("\\", "/").endswith(required_artifact):
        return False, None, f"this task requires artifact '{required_artifact}', got '{artifact_path}'"
    return True, rec, f"verified {rec['kind']} sha256={artifact_hash[:16]}..."


# ---------------- read-only commands (fix 4.3: no save) ----------------

ICON = {"done": "[DONE]", "pending": "[ pend]", "in_progress": "[work]",
        "blocked": "[lock]", "halted": "[HALT]", "awaiting_oracle": "[oracl]",
        "wont_fix": "[WONT]"}


def cmd_status(s):
    print("\n=== GATES ===")
    for gid, g in s["gates"].items():
        print(f"  {ICON.get(g['status'],'?')} {gid} (day {g['day']}): {g['title']} [{g['status']}]")
    print("\n=== TASKS (effective, read-only) ===")
    for t in s["tasks"]:
        eff = effective_status(s, t)
        deps = ",".join(t.get("deps", [])) or "-"
        n = len(t.get("attempts", []))
        print(f"  {ICON.get(eff,'?')} {t['id']}: {t['title']} [{eff}] deps={deps} attempts={n}")
    hp = [t for t in s["tasks"] if t["status"] == "halted"]
    if hp:
        print("\n!! HALTED — human decision required (change APPROACH or wont_fix):")
        for t in hp:
            last = t["attempts"][-1] if t.get("attempts") else {}
            print(f"  {t['id']}: last signature = {last.get('signature','?')}")
            print(f"       detail: {last.get('output','')[:160]}")
    print("\n(status is read-only; run 'refresh' to promote blocked->pending)\n")


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


# ---------------- mutating commands ----------------

def record(s, t, passed, output, kind):
    sig = parse_signature(output) if not passed else "PASS"
    attempts = t.setdefault("attempts", [])
    attempts.append({"ts": now(), "kind": kind, "passed": passed, "signature": sig, "output": output[:2000]})
    log(s, "oracle_run", task=t["id"], passed=passed, signature=sig)
    if passed:
        t["status"] = TERMINAL_GREEN
        if t.get("gate"):
            # task passing makes its gate human-attestable; it does NOT auto-pass the gate
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
        sys.exit(f"{tid} uses a '{t['oracle']['type']}' oracle. Use: attest --task {tid} --verdict pass --evidence <file>")
    passed, out = run_script(t["oracle"]["cmd"])
    if passed and t["oracle"].get("then"):
        p2, o2 = run_script(t["oracle"]["then"])
        passed, out = (passed and p2), out + "\n" + o2
    record(s, t, passed, out, kind="script")


def cmd_attest(s, tid, verdict, note, evidence, reopen):
    refresh_blocked(s)
    t = task(s, tid)
    # fix 4.1: cannot attest a blocked / unmet-dep / already-terminal task
    if t["status"] == "blocked" or not deps_done(s, t):
        sys.exit(f"REJECTED: {tid} is blocked; unmet deps {t.get('deps')}. Attestation refused.")
    if t["status"] in (TERMINAL_GREEN, TERMINAL_NONGREEN) and not reopen:
        sys.exit(f"REJECTED: {tid} is already '{t['status']}'. Pass --reopen to re-attest (human decision).")
    if t["oracle"]["type"] == "script":
        sys.exit(f"REJECTED: {tid} has a script oracle; use 'run --task {tid}', not attest.")
    if verdict == "pass":
        ok, rec, msg = verify_evidence(evidence, t["oracle"].get("artifact"))
        if not ok:
            sys.exit(f"REJECTED: attestation PASS needs verifiable evidence. {msg}")
        out = f"attestation verdict=pass note={note} evidence={json.dumps(rec)}"
        t.setdefault("attempts", []).append({"ts": now(), "kind": "attestation", "passed": True, "signature": "PASS", "output": out[:2000]})
        t["status"] = TERMINAL_GREEN
        t["evidence"] = rec
        log(s, "attestation", task=tid, passed=True, evidence_sha256=rec["sha256"], note=note)
        if t.get("gate"):
            s["gates"][t["gate"]]["status"] = TERMINAL_GREEN
            s["gates"][t["gate"]]["evidence_sha256"] = rec["sha256"]
        refresh_blocked(s)
        print(f"[PASS] {tid} attested. {msg}")
    else:
        t.setdefault("attempts", []).append({"ts": now(), "kind": "attestation", "passed": False, "signature": "attest_fail", "output": note[:2000]})
        t["status"] = "in_progress"
        log(s, "attestation", task=tid, passed=False, note=note)
        print(f"[FAIL] {tid} attested fail — iterate.")


def cmd_wont_fix(s, tid, reason, evidence):
    """fix 4.4: terminal NON-GREEN state. Dependents stay blocked."""
    if not reason:
        sys.exit("wont_fix requires --reason")
    ok, rec, msg = verify_evidence(evidence) if evidence else (True, None, "no evidence file")
    if evidence and not ok:
        sys.exit(f"REJECTED: wont_fix evidence unverifiable. {msg}")
    # accept tasks or gates
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
    t["status"] = "pending" if deps_done(s, t) else "blocked"
    log(s, "reset", task=tid)
    print(f"reset {tid} -> {t['status']}")


MUTATING = {"run", "attest", "reset", "wont_fix", "refresh"}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status"); sub.add_parser("next"); sub.add_parser("refresh")
    for name in ("run", "reset"):
        p = sub.add_parser(name); p.add_argument("--task", required=True)
    pa = sub.add_parser("attest")
    pa.add_argument("--task", required=True)
    pa.add_argument("--verdict", required=True, choices=["pass", "fail"])
    pa.add_argument("--note", default="")
    pa.add_argument("--evidence", default="")
    pa.add_argument("--reopen", action="store_true")
    pw = sub.add_parser("wont_fix")
    pw.add_argument("--task", required=True)
    pw.add_argument("--reason", required=True)
    pw.add_argument("--evidence", default="")
    a = ap.parse_args()
    s = load()
    if a.cmd == "status": cmd_status(s)
    elif a.cmd == "next": cmd_next(s)
    elif a.cmd == "refresh": cmd_refresh(s)
    elif a.cmd == "run": cmd_run(s, a.task)
    elif a.cmd == "attest": cmd_attest(s, a.task, a.verdict, a.note, a.evidence, a.reopen)
    elif a.cmd == "wont_fix": cmd_wont_fix(s, a.task, a.reason, a.evidence)
    elif a.cmd == "reset": cmd_reset(s, a.task)
    # fix 4.3: ONLY persist for mutating commands
    if a.cmd in MUTATING:
        save(s)


if __name__ == "__main__":
    main()
