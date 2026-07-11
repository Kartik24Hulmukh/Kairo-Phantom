#!/usr/bin/env python3
"""
score_evidence_manifest.py — ILLUSTRATIVE evidence-COVERAGE evaluator.

!!! READ THIS FIRST (renamed from verify_evidence_pack.py in v1.2) !!!
This is an *illustrative schema/coverage evaluator*. It DOES NOT cryptographically
verify evidence, and it does NOT establish that the claimed observations actually
occurred. It recomputes a simple SHA-256 hash chain for continuity and then READS
self-declared booleans from the pack's `dimensions` object to print a coverage
(sufficiency) report. A pack that merely *says* `"desktop_action_observation": true`
will be scored as if it were observed — that is by design here, and it is exactly
why this file must not be called 'the verifier'.

What a REAL KSEE verifier must independently check (NOT done here — see canonical
plan Part 7 and updates §3): canonical encoding; Ed25519 receipt signatures;
pinned/trusted signer identities; hash-chain continuity; Merkle inclusion proofs;
session nonce / replay protection; policy & delegation signatures; artifact bytes
vs recorded hashes; host-witness signatures; external-witness signatures;
overlapping observation intervals; canary results; interface inventory; TPM quote;
and the causal-graph relationships between all of the above.

Real cryptographic receipt verification lives (separately) in
`tools/verify_receipts_external.py` in the product repo. Keep the two separate
until they are properly integrated; do NOT market this script as the reference
KSEE verifier.

Input: a JSON evidence pack (see schemas/evidence_pack.example.json).
Exit 0 normally (it is a coverage report, not a pass/fail) UNLESS the hash chain
is broken, which is a hard FAIL (exit 1) — a broken chain is never sufficient.

Usage: python3 score_evidence_manifest.py pack.json
"""
import json, sys, hashlib

DIMS = [
    ("receipt_integrity", 0),
    ("signer_provenance", 1),
    ("policy_binding", 1),
    ("desktop_action_observation", 2),
    ("artifact_state_verification", 2),
    ("host_network_observation", 2),
    ("external_witness_corroboration", 3),
]
CHANNELS = ["wifi", "bluetooth", "cellular", "usb_net", "second_nic", "firmware"]


def check_integrity(pack):
    prev = pack.get("genesis", "")
    for e in pack.get("entries", []):
        body = json.dumps(e.get("body", {}), sort_keys=True)
        h = hashlib.sha256((prev + body).encode()).hexdigest()
        if e.get("prev") != prev:
            return False, f"chain broken at entry {e.get('seq')}: prev mismatch"
        if e.get("hash") != h:
            return False, f"tamper at entry {e.get('seq')}: hash mismatch"
        prev = h
    return True, "chain intact"


def status(pack, dim):
    v = pack.get("dimensions", {}).get(dim)
    if v is True or v == "pass":
        return "PASS (self-declared)"
    if v == "incomplete":
        return "INCOMPLETE"
    return "NOT OBSERVED"


def main(argv):
    if len(argv) < 2:
        print("usage: score_evidence_manifest.py pack.json"); return 2
    with open(argv[1]) as f:
        pack = json.load(f)

    ok, msg = check_integrity(pack)
    label = lambda k, v: print(f"  {k:<40}{v}")
    print(f"\nKSEE COVERAGE report (illustrative; self-declared) — pack '{pack.get('id','?')}' (OS: {pack.get('os','?')})")
    print("NOTE: dimension values below are SELF-DECLARED and NOT cryptographically verified.")
    print("-" * 68)
    label("receipt_integrity (hash-chain only):", "PASS" if ok else f"FAIL ({msg})")
    if not ok:
        print("\nOVERALL: FAIL — a broken chain is never sufficient.")
        return 1

    level = 0
    for dim, contributes in DIMS[1:]:
        st = status(pack, dim)
        label(dim + ":", st)
        if st.startswith("PASS"):
            level = max(level, contributes)
    for dim, contributes in DIMS[1:]:
        if not status(pack, dim).startswith("PASS") and contributes <= level:
            level = contributes - 1

    print("  network channels (declared):")
    obs = pack.get("observed_channels", {})
    for ch in CHANNELS:
        label("    " + ch + ":", str(obs.get(ch, "NOT OBSERVED")).upper())
    print("-" * 68)
    print(f"  DECLARED COVERAGE LEVEL:                  KSEE-L{max(level,0)} (self-declared)")
    print("  This is a COVERAGE report, not verification. An assessor decides sufficiency,")
    print("  and a real verifier must check signatures/witnesses before any of this is trusted.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
