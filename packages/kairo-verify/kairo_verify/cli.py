"""Command-line interface for kairo-verify."""
import argparse
import json
import sys

from . import __version__
from .answer import answerability, ANSWERED
from .formats import SUPPORTED, PLANNED, detect
from .integrity import read_jsonl, verify_receipts, verify_checkpoints
from .obsigna import is_obsigna, verify_chain as obsigna_verify_chain


def _cmd_integrity(args):
    try:
        receipts = read_jsonl(args.receipts)
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    fmt = detect(receipts[0]) if receipts else "empty"
    checkpoints = []
    if fmt == "obsigna-agent-receipt":
        key_pem = None
        if args.key:
            try:
                with open(args.key, "r", encoding="utf-8") as fh:
                    key_pem = fh.read()
            except OSError as e:
                print(f"ERROR: cannot read key file: {e}", file=sys.stderr)
                return 2
        violations = obsigna_verify_chain(receipts, public_key_pem=key_pem)
    else:
        violations = verify_receipts(receipts, require_signatures=args.require_signatures)
        if args.checkpoints:
            try:
                checkpoints = read_jsonl(args.checkpoints)
            except (ValueError, OSError) as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            violations += verify_checkpoints(
                checkpoints, receipts, require_signatures=args.require_signatures
            )
    if args.json:
        print(json.dumps({
            "format": fmt,
            "receipts": len(receipts),
            "checkpoints": len(checkpoints),
            "violations": violations,
            "ok": not violations,
        }, indent=2))
    elif violations:
        print(f"FAIL ({fmt}) - {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
    else:
        print(
            f"OK ({fmt}) - all checks passed "
            f"({len(receipts)} receipts, {len(checkpoints)} checkpoints)"
        )
    return 1 if violations else 0


def _cmd_answer(args):
    try:
        receipts = read_jsonl(args.receipts)
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    determinations = answerability(receipts)
    if args.json:
        print(json.dumps({"receipts": len(receipts), "determinations": determinations}, indent=2))
        return 0
    print(f"Answerability report - {len(receipts)} receipts")
    print("(integrity and answerability are separate: a clean chain says nothing here)")
    for d in determinations:
        print(f"\n{d['id']}  {d['question']}")
        print(f"    {d['status']}")
        for seq in d["evidence"]:
            print(f"      evidence: receipt seq={seq}")
        for m in d["missing"]:
            print(f"      missing: {m}")
    return 0


def _cmd_formats(args):
    print("Supported now:")
    for s in SUPPORTED:
        print(f"  - {s}")
    print("Planned (not yet implemented):")
    for p in PLANNED:
        print(f"  - {p}")
    if args.path:
        try:
            records = read_jsonl(args.path)
        except (ValueError, OSError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        kinds = {}
        for r in records:
            kinds[detect(r)] = kinds.get(detect(r), 0) + 1
        print(f"\nDetected in {args.path}:")
        for k, n in sorted(kinds.items()):
            print(f"  - {k}: {n} record(s)")
    return 0


def _cmd_demo(args):
    from .demo import write_demo

    rp, cp = write_demo(args.out, n=args.receipts, typed=args.typed)
    print(f"wrote {rp}")
    print(f"wrote {cp}")
    print("try:")
    print(f"  kairo-verify integrity {rp} --checkpoints {cp}")
    print(f"  kairo-verify answer {rp}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="kairo-verify",
        description="Offline verifier for Kairo-Phantom execution receipts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("integrity", help="verify hash chain, signatures, Merkle checkpoints")
    p.add_argument("receipts", help="path to receipts.jsonl")
    p.add_argument("--checkpoints", help="path to checkpoints.jsonl (optional)")
    p.add_argument("--key", help="path to PEM Ed25519 public key (obsigna receipts)")
    p.add_argument("--require-signatures", action="store_true",
                   help="fail if signatures cannot be verified")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_integrity)

    p = sub.add_parser("answer", help="answerability report (D1-D4)")
    p.add_argument("receipts", help="path to receipts.jsonl")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_answer)

    p = sub.add_parser("formats", help="supported formats and optional detection")
    p.add_argument("path", nargs="?", help="optional file to auto-detect")
    p.set_defaults(func=_cmd_formats)

    p = sub.add_parser("demo", help="generate a real signed demo chain")
    p.add_argument("--out", default=".", help="output directory")
    p.add_argument("--receipts", type=int, default=5)
    p.add_argument("--typed", action="store_true",
                   help="emit typed events so all four determinations are answerable")
    p.set_defaults(func=_cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)
