#!/usr/bin/env python3
"""
Oracle: validate CLAIMS.md + SKIPS.md structure and internal consistency.
Exit 0 = valid, 1 = problems.

Checks:
  1. CLAIMS.md has all three buckets (REAL / EXPERIMENTAL / NONE YET).
  2. The R12-vs-N1 wording trap: if CLAIMS says 'third-party-verifiable' it must
     also say no third party has verified yet (research.md 3.1).
  3. Zero-egress rows must not claim whole-machine (research.md 3.2/3.4).
  4. SKIPS.md has no unfilled <fill> rows AND documents exactly 7 skips.
  5. No 'deterministic replay' language (research.md 3.5).

Usage: python3 check_claims_consistency.py CLAIMS.md SKIPS.md
"""
import re, sys


def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def main(argv):
    if len(argv) < 3:
        print("usage: check_claims_consistency.py CLAIMS.md SKIPS.md"); return 2
    claims, skips = read(argv[1]), read(argv[2])
    problems = []

    if claims is None:
        problems.append(f"CLAIMS file missing: {argv[1]}")
    else:
        low = claims.lower()
        for bucket in ("real", "experimental", "none yet"):
            if bucket not in low:
                problems.append(f"CLAIMS.md missing bucket: '{bucket}'")
        if "third-party-verifiable" in low and "no independent third party has yet" not in low and "no third party has verified" not in low:
            problems.append("CLAIMS.md: 'third-party-verifiable' present without the 'not yet verified' caveat (research 3.1)")
        if re.search(r"whole[- ]machine zero[- ]egress", low):
            problems.append("CLAIMS.md: claims whole-machine zero-egress (research 3.2/3.4) — scope to tested interfaces")
        if "deterministic replay" in low and "not \"deterministic" not in low and "renamed" not in low:
            problems.append("CLAIMS.md: 'deterministic replay' present (research 3.5) — rename to evidence/state-transition replay")

    if skips is None:
        problems.append(f"SKIPS file missing: {argv[2]}")
    else:
        fills = skips.count("<fill")
        if fills:
            problems.append(f"SKIPS.md has {fills} unfilled <fill> placeholder(s) — document every skip before claiming they are documented")
        # count skip rows: table rows beginning with '| <n> |'
        rows = re.findall(r"^\|\s*\d+\s*\|", skips, re.M)
        if len(rows) != 7:
            problems.append(f"SKIPS.md documents {len(rows)} skips; expected 7 to match '1005 passed / 7 skipped'")

    if problems:
        for p in problems:
            print("FAIL: " + p)
        print(f"\n{len(problems)} problem(s).")
        return 1
    print("OK: CLAIMS.md + SKIPS.md consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
