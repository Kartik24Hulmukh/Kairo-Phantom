#!/usr/bin/env python3
"""CLI for isolated legal-v3 mutual-NDA governed transactions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kairo.legal_v3.transaction import (
    approve,
    execute,
    generate_keypair,
    propose,
    verify_bundle,
)


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(path: str, value: dict) -> None:
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Kairo Legal v3 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    keygen = sub.add_parser("keygen")
    keygen.add_argument("role")
    keygen.add_argument("out")

    propose_p = sub.add_parser("propose")
    propose_p.add_argument("root")
    propose_p.add_argument("source")
    propose_p.add_argument("playbook")
    propose_p.add_argument("output")
    propose_p.add_argument("producer_key")
    propose_p.add_argument("out")

    approve_p = sub.add_parser("approve")
    approve_p.add_argument("proposal")
    approve_p.add_argument("approver_key")
    approve_p.add_argument("out")

    execute_p = sub.add_parser("execute")
    execute_p.add_argument("root")
    execute_p.add_argument("proposal")
    execute_p.add_argument("approval")
    execute_p.add_argument("producer_key")
    execute_p.add_argument("approver_key")
    execute_p.add_argument("observer_key")
    execute_p.add_argument("bundle")

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("bundle")

    args = parser.parse_args()
    try:
        if args.cmd == "keygen":
            dump(args.out, generate_keypair(args.role))
        elif args.cmd == "propose":
            dump(
                args.out,
                propose(
                    args.root,
                    args.source,
                    args.playbook,
                    args.output,
                    load(args.producer_key),
                ),
            )
        elif args.cmd == "approve":
            dump(args.out, approve(load(args.proposal), load(args.approver_key)))
        elif args.cmd == "execute":
            producer = load(args.producer_key)
            approver = load(args.approver_key)
            observer = load(args.observer_key)
            keys = {
                producer["key_id"]: producer["public"],
                approver["key_id"]: approver["public"],
            }
            execute(
                args.root,
                load(args.proposal),
                load(args.approval),
                keys,
                observer,
                args.bundle,
            )
        else:
            report = verify_bundle(args.bundle)
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
