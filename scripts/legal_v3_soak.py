#!/usr/bin/env python3
"""Run N iterations of the full legal-v3 propose -> verify cycle.

Reports pass/fail counts and writes a JSON soak report to bench/.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kairo.legal_v3.transaction import (  # noqa: E402
    approve,
    execute,
    generate_keypair,
    propose,
    verify_bundle,
)


def run_once(work: Path) -> bool:
    """Execute one full cycle and return True if verify passes."""
    shutil.copy2(ROOT / "fixtures/demo/sample_nda.docx", work / "nda.docx")
    shutil.copy2(ROOT / "fixtures/demo/nda_playbook.json", work / "playbook.json")

    prod = generate_keypair("producer")
    app = generate_keypair("approver")
    obs = generate_keypair("observer")

    proposal = propose(
        str(work), "nda.docx", "playbook.json", "out.docx", prod
    )
    approval = approve(proposal, app)
    keys = {
        prod["key_id"]: prod["public"],
        app["key_id"]: app["public"],
    }
    bundle_path = work / "bundle"
    execute(
        str(work), proposal, approval, keys, obs, str(bundle_path)
    )
    result = verify_bundle(str(bundle_path))
    return result["ok"] is True


def main() -> None:
    parser = argparse.ArgumentParser(description="Legal-v3 synthetic soak")
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args()

    passed = 0
    failed = 0
    failures: list[str] = []
    start = time.monotonic()

    for i in range(args.runs):
        work = Path(tempfile.mkdtemp(prefix=f"soak-{i:03d}-"))
        try:
            ok = run_once(work)
            if ok:
                passed += 1
            else:
                failed += 1
                failures.append(f"run {i}: verify returned ok=False")
        except Exception as exc:
            failed += 1
            failures.append(f"run {i}: {exc}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    elapsed = time.monotonic() - start

    report = {
        "runs": args.runs,
        "passed": passed,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 3),
        "failures": failures,
        "scope": "synthetic mutual-NDA fixture on sandbox Linux",
    }

    report_path = ROOT / "bench" / "LEGAL_V3_SOAK_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"SOAK: {passed}/{args.runs} passed, {failed} failed ({elapsed:.1f}s)")
    if failures:
        for f in failures[:10]:
            print(f"  {f}", file=sys.stderr)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
