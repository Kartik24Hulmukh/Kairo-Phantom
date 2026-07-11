#!/usr/bin/env python3
"""
Oracle: scan public docs for banned phrases *asserted as fact*. Exit 0 = clean, 1 = violations.

Design: flag a genuine ASSERTION, not a CITATION. A banned phrase is allowed when it
appears inside quotes (teaching "never say X") or on a negation/correction line
("do not say", "is false", "dead", "replace", the ban list itself). It is flagged
only when a document states it plainly and positively.

Usage: python3 check_forbidden_claims.py FILE [FILE ...]
"""
import re, sys

BANNED = [
    (r"injection[- ]safe", "pattern detector is not a general injection defence",
     "blocked all 25 attacks in the current fixture suite"),
    (r"\b0 competitors\b|\bzero competitors\b", "false; AGA et al. exist",
     "nearest rival: Attested Intelligence (AGA)"),
    (r"only (one|product|company) (that exists|in this category|in the (world|market))", "AGA disproves it",
     "designed to bind desktop outcome + scoped boundary evidence"),
    (r"aug(ust)?\.?\s*0?2,?\s*2026", "dead EU deadline; high-risk/Art.12 is now Dec 2 2027",
     "Dec 2, 2027 (Digital Omnibus) -- verify OJ text"),
    (r"FIPS[- ]validated|FIPS certified", "module is not validated; algorithm only",
     "Ed25519 is an approved algorithm (FIPS 186-5); module not validated"),
    (r"EU AI Act certified|regulator[- ]approved|guarantees? compliance", "we never claim compliance",
     "produces evidence supporting an assessor's evaluation"),
    (r"zero bytes left the (entire )?machine|no data left the machine", "TPM/2nd device cannot prove whole-machine",
     "no outbound packet observed across the declared/tested interfaces; unobserved channels listed"),
    (r"deterministic replay|bit[- ]identical replay", "we don't promise deterministic agent replay",
     "evidence & state-transition replay"),
    (r"(can also )?verif(y|ies) other platforms", "cross-vendor verifier is None yet",
     "designed to normalize other platforms' evidence into the KSEE draft profile"),
    (r"the open standard for sovereign", "a schema+CLI is not a standard",
     "KSEE draft evidence profile"),
    (r"can'?t copy (this|us)|cannot copy (this|us)|by construction", "wrappers can add observers",
     "gateway-only evidence can't establish downstream desktop state without observers"),
    (r"0 unjustified skips", "'unjustified' is a human judgment, not auditable",
     "1005 passed, 7 documented skips, 0 failed (see SKIPS.md)"),
    # --- T1 §6 DROPPED claims (competitor already does it) ---
    (r"nobody proves runtime", "AGA proves runtime governance decisions",
     "AGA produces decision evidence at the gateway/tool boundary"),
    (r"first cryptographic governance layer", "AGA and Microsoft AGT both exist",
     "designed to bind desktop outcome evidence to governance receipts"),
    (r"invented offline[- ]verifiable agent evidence", "AGA has an offline verifier; SCITT/in-toto predate both",
     "offline-verifiable with the included standalone verifier; no independent third party has verified yet"),
    (r"no competitor has two[- ]process enforcement", "AGA has two-process key separation (gateway holds keys, agent doesn't)",
     "gateway-only evidence cannot establish downstream desktop state without additional observers"),
    (r"only product in this category", "AGA, Microsoft AGT, OPAQUE, Kiteworks all exist",
     "designed to bind desktop outcome evidence to governance receipts"),
    # --- T1 §6 FROZEN-pending-counsel claims ---
    (r"\bpatentable\b", "FTO requires licensed-attorney judgment; freeze until counsel opinion",
     "FTO opinion pending from counsel (see docs/t1_competitor_memo.md)"),
    (r"\bKairo'?s? mechanisms? (are|is) novel\b|\bour (approach|technology) is novel\b|\bwe are novel\b", "FTO requires licensed-attorney judgment; freeze until counsel opinion",
     "FTO opinion pending from counsel (see docs/t1_competitor_memo.md)"),
    (r"first to bind desktop outcome", "cannot assert 'first' without exhaustive search; freeze until counsel opinion",
     "designed to bind desktop outcome evidence to governance receipts"),
]

NEG = re.compile(
    r"(never|do not|don'?t|\bnot\b|banned|prohibit|forbid|instead of|replace|remove|"
    r"is false|\bfalse\b|\bdead\b|stale|\bwrong\b|previously|avoid|stop\b|too absolute|"
    r"drop the|drop dead|\bkill(s|ed)?\b|caveat|verify)", re.I)

QUOTES = '"\u201c\u201d\u2018\u2019'


def is_quoted(line, start):
    toggles = sum(1 for ch in line[:start] if ch in QUOTES)
    return toggles % 2 == 1


def scan(path):
    hits = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return [(0, f"FILE NOT FOUND: {path}", "")]
    for i, line in enumerate(lines, 1):
        teaching = bool(NEG.search(line))
        for rx, why, fix in BANNED:
            for m in re.finditer(rx, line, re.I):
                if teaching or is_quoted(line, m.start()):
                    continue
                hits.append((i, f"{path}:{i}: asserted banned phrase '{m.group(0)}' -- {why}", f"use: {fix}"))
                break
    return hits


def main(argv):
    if len(argv) < 2:
        print("usage: check_forbidden_claims.py FILE [FILE ...]"); return 2
    all_hits = []
    for p in argv[1:]:
        all_hits += scan(p)
    if not all_hits:
        print("OK: 0 asserted forbidden claims across %d file(s)." % (len(argv) - 1)); return 0
    for _, msg, fix in all_hits:
        print("FAIL: " + msg)
        print("      " + fix)
    print(f"\n{len(all_hits)} violation(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
