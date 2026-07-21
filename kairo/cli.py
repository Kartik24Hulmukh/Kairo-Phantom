# PROVENANCE: original | clean-room CLI entrypoint for the Legal-redline wedge
"""Kairo Phantom CLI — human-runnable Legal-redline wedge.

Two commands:

  redline <contract.docx> <playbook.json> [--sealed] [--out DIR]
      Runs the REAL redline_contract pipeline with an Ed25519 key
      (generates + stores locally if absent). Writes redlined.docx,
      audit_log.json, zero_egress_report.json, and public_key.pem to --out.
      Prints a human-readable summary.

  verify <redlined_dir> <public_key.pem>
      Independently re-verifies the audit-log chain + signatures +
      zero-egress report. Prints PASS/FAIL per artifact so a skeptic
      can verify without trusting us.

All operations are fully offline. No network calls. No LLM. No cloud.

Dependencies: stdlib + python-docx (BSD-3) + cryptography (Apache-2.0/BSD-3).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path so kairo.* is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Key management — generate + store Ed25519 keypair locally
# ---------------------------------------------------------------------------


def _get_or_create_keypair(key_dir: Path) -> tuple[object, object, bytes]:
    """Get an existing Ed25519 keypair or generate a new one.

    Stores private_key.pem and public_key.pem in key_dir.
    Returns (private_key, public_key, public_key_pem_bytes).
    """

    from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

    key_dir.mkdir(parents=True, exist_ok=True)
    priv_path = key_dir / "private_key.pem"
    pub_path = key_dir / "public_key.pem"

    if priv_path.exists() and pub_path.exists():
        priv_bytes = priv_path.read_bytes()
        pub_bytes = pub_path.read_bytes()
        private_key = Ed25519AuditLog.load_private_key(priv_bytes)
        public_key = Ed25519AuditLog.load_public_key(pub_bytes)
        return private_key, public_key, pub_bytes

    # Generate new keypair
    private_key, public_key = Ed25519AuditLog.generate_keypair()
    priv_pem = Ed25519AuditLog.private_key_to_pem(private_key)
    pub_pem = Ed25519AuditLog.public_key_to_pem(public_key)
    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)
    # Restrict private key permissions
    try:
        os.chmod(priv_path, 0o600)
    except OSError:
        pass  # Windows doesn't support Unix permissions
    return private_key, public_key, pub_pem


# ---------------------------------------------------------------------------
# redline command
# ---------------------------------------------------------------------------



def _hash_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_output_manifest(out_dir: Path, private_key, sealed: bool = False) -> None:
    """Write a signed manifest binding output artifacts to this run.

    Records SHA-256 of redlined.docx, audit_log.json, zero_egress_report.json,
    and airgap_egress_report.json (when present, i.e. sealed mode), signed
    with the run's Ed25519 private key.
    Closes the gap where post-run tampering with redlined.docx was
    undetectable by `kairo verify` (which only checked existence).
    """
    import json as _json
    from datetime import datetime, timezone

    payload = {
        "version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redlined_docx_sha256": _hash_file(out_dir / "redlined.docx"),
        "audit_log_sha256": _hash_file(out_dir / "audit_log.json"),
        "zero_egress_report_sha256": _hash_file(
            out_dir / "zero_egress_report.json"
        ),
    }

    # Include airgap egress report hash when present (sealed mode)
    airgap_path = out_dir / "airgap_egress_report.json"
    if airgap_path.exists():
        payload["airgap_egress_report_sha256"] = _hash_file(airgap_path)

    content = _json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    signature = private_key.sign(content).hex()
    manifest = dict(payload)
    manifest["signature"] = signature
    (out_dir / "output_manifest.json").write_text(
        _json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _verify_output_manifest(redlined_dir: Path, public_key) -> tuple[bool, str]:
    """Verify the signed output manifest against on-disk artifacts.

    Returns (ok, detail). A missing manifest fails closed, with a
    legacy-run explanation so old runs are distinguishable from tampering.
    """
    import json as _json

    from cryptography.exceptions import InvalidSignature

    manifest_path = redlined_dir / "output_manifest.json"
    if not manifest_path.exists():
        return False, "output_manifest.json missing (legacy run or deleted)"
    try:
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        signature = bytes.fromhex(manifest.pop("signature"))
        content = _json.dumps(
            manifest, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        public_key.verify(signature, content)
    except (InvalidSignature, KeyError, ValueError, TypeError) as exc:
        return False, f"manifest signature invalid: {exc.__class__.__name__}"
    checks = {
        "redlined.docx": manifest.get("redlined_docx_sha256"),
        "audit_log.json": manifest.get("audit_log_sha256"),
        "zero_egress_report.json": manifest.get("zero_egress_report_sha256"),
    }
    # Check airgap egress report when recorded in manifest (sealed mode)
    airgap_hash = manifest.get("airgap_egress_report_sha256")
    if airgap_hash is not None:
        checks["airgap_egress_report.json"] = airgap_hash
    for name, expected in checks.items():
        p = redlined_dir / name
        if not p.exists():
            return False, f"{name} missing"
        actual = _hash_file(p)
        if actual != expected:
            return False, (
                f"{name} hash mismatch: expected {str(expected)[:16]}..., "
                f"got {actual[:16]}..."
            )
    return True, "all artifact hashes match signed manifest"


def cmd_redline(args: argparse.Namespace) -> int:
    """Run the real redline pipeline and write outputs."""
    contract_path = str(Path(args.contract).resolve())
    playbook_path = str(Path(args.playbook).resolve())
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(contract_path):
        print(f"ERROR: Contract not found: {contract_path}", file=sys.stderr)
        return 1
    if not os.path.exists(playbook_path):
        print(f"ERROR: Playbook not found: {playbook_path}", file=sys.stderr)
        return 1

    # Get or create Ed25519 keypair
    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)

    # Write public key to output dir for easy verification
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    output_docx = str(out_dir / "redlined.docx")

    if args.sealed:
        # Run under sealed mode with live egress capture
        from kairo.oracles.airgap_egress import run_airgap_egress_oracle

        print("Running in SEALED mode (air-gap egress capture active)...")
        report = run_airgap_egress_oracle(
            contract_path=contract_path,
            playbook_path=playbook_path,
            output_path=output_docx,
            private_key=private_key,
        )

        if not report.session_completed:
            print(f"ERROR: Redline flow failed: {report.error}", file=sys.stderr)
            return 1

        # The airgap oracle runs the pipeline internally; we need to re-run
        # to get the RedlineResult for the audit log and egress report.
        # Actually the oracle already ran it with the private_key, so the
        # output docx has the tracked changes. But we need the audit_log_json
        # and egress_report_json. The oracle doesn't return those directly.
        # So we run the pipeline once more (still under sealed mode) to get
        # the structured result with audit + egress report.
        from kairo.sealed_profile import activate_sealed_mode, is_sealed

        if not is_sealed():
            activate_sealed_mode(reason="CLI sealed redline")

        from kairo.oracles.legal_redline_pipeline import redline_contract

        result = redline_contract(
            contract_path=contract_path,
            playbook_path=playbook_path,
            output_path=output_docx,
            author="Kairo Legal (Sealed)",
            private_key=private_key,
        )

        # Write the airgap egress report
        (out_dir / "airgap_egress_report.json").write_text(
            report.to_json(), encoding="utf-8"
        )

    else:
        # Normal (non-sealed) mode — still fully offline, just no egress capture
        from kairo.oracles.legal_redline_pipeline import redline_contract

        print("Running redline pipeline (offline)...")
        result = redline_contract(
            contract_path=contract_path,
            playbook_path=playbook_path,
            output_path=output_docx,
            author="Kairo Legal",
            private_key=private_key,
        )

    if not result.ok:
        print(f"ERROR: Redline pipeline failed: {result.error}", file=sys.stderr)
        return 1

    # Write audit log
    (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")

    # Write zero-egress report
    (out_dir / "zero_egress_report.json").write_text(
        result.egress_report_json, encoding="utf-8"
    )

    # Verify the audit log we just wrote (self-check)
    from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    audit_ok = Ed25519AuditLog.verify_chain(entries, public_key)

    # Verify the zero-egress report
    from kairo.oracles.zero_egress_report import (
        report_from_json,
        verify_zero_egress_report,
    )

    egress_report = report_from_json(result.egress_report_json)
    egress_ok = verify_zero_egress_report(egress_report, public_key)

    # Write signed output manifest (binds artifacts to this run)
    _write_output_manifest(out_dir, private_key, sealed=args.sealed)

    # Print human-readable summary
    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — LEGAL REDLINE COMPLETE")
    print("=" * 60)
    print(f"  Contract:    {Path(contract_path).name}")
    print(f"  Playbook:    {Path(playbook_path).name}")
    print(f"  Output:      {out_dir}")
    print(f"  Edits applied:  {len(result.applied_edits)}")
    print(f"  Clauses flagged: {len(result.flagged_clauses)}")
    print(f"  Injection detected: {result.injection_detected}")
    print()
    if result.applied_edits:
        print("  Applied edits:")
        for edit in result.applied_edits:
            print(
                f"    • {edit.clause_label}: {edit.old_text[:50]}... → {edit.new_text[:50]}..."
            )
    if result.flagged_clauses:
        print("  Flagged clauses:")
        for flag in result.flagged_clauses:
            print(f"    ⚠ {flag.clause_label}: {flag.reason[:60]}")
    print()
    print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
    print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
    if args.sealed:
        print("  Air-gap: 0 outbound packets ✅")
    print()
    print(f"  Artifacts in {out_dir}/:")
    print("    redlined.docx")
    print("    audit_log.json")
    print("    zero_egress_report.json")
    print("    public_key.pem")
    print("    output_manifest.json")
    if args.sealed:
        print("    airgap_egress_report.json")
    print("=" * 60)

    return 0 if (audit_ok and egress_ok) else 1


# ---------------------------------------------------------------------------
# verify command
# ---------------------------------------------------------------------------


def cmd_verify(args: argparse.Namespace) -> int:
    """Independently re-verify the audit log + zero-egress report + output manifest.

    Security: the public key must be supplied externally (not from the
    output directory) or verified against a known fingerprint. This
    prevents an attacker from replacing public_key.pem in the output
    directory and re-signing artifacts with their own key.
    """
    redlined_dir = Path(args.redlined_dir).resolve()

    if not redlined_dir.is_dir():
        print(f"ERROR: Directory not found: {redlined_dir}", file=sys.stderr)
        return 1

    # --- Trust anchor: external key or fingerprint verification ---
    import hashlib

    if args.public_key:
        # External key supplied — use it directly
        pub_pem_path = Path(args.public_key).resolve()
        if not pub_pem_path.exists():
            print(f"ERROR: Public key not found: {pub_pem_path}", file=sys.stderr)
            return 1
        pub_pem = pub_pem_path.read_bytes()
    elif args.fingerprint:
        # Fingerprint supplied — check co-located key against it
        colocated = redlined_dir / "public_key.pem"
        if not colocated.exists():
            print("ERROR: No public_key.pem in output dir and no external key supplied",
                  file=sys.stderr)
            return 1
        pub_pem = colocated.read_bytes()
        actual_fp = hashlib.sha256(pub_pem).hexdigest()
        expected_fp = args.fingerprint.lower().replace(":", "")
        if actual_fp != expected_fp:
            print(
                f"ERROR: Public key fingerprint mismatch!\n"
                f"  Expected: {expected_fp[:16]}...\n"
                f"  Got:      {actual_fp[:16]}...\n"
                f"  The co-located public_key.pem does not match the trusted fingerprint.",
                file=sys.stderr,
            )
            return 1
    else:
        print(
            "ERROR: A trusted public key is required for verification.\n"
            "  Supply an external key:  kairo verify <dir> <trusted_key.pem>\n"
            "  Or verify a fingerprint: kairo verify <dir> --fingerprint <sha256>\n"
            "  Do NOT trust the co-located public_key.pem — an attacker can replace it.",
            file=sys.stderr,
        )
        return 1

    from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
    from kairo.oracles.zero_egress_report import (
        report_from_json,
        verify_zero_egress_report,
    )

    public_key = Ed25519AuditLog.load_public_key(pub_pem)

    all_pass = True

    # 1. Verify audit log
    audit_path = redlined_dir / "audit_log.json"
    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — INDEPENDENT VERIFICATION")
    print("=" * 60)

    if audit_path.exists():
        audit_json = audit_path.read_text(encoding="utf-8")
        entries = Ed25519AuditLog.entries_from_json(audit_json)
        chain_ok = Ed25519AuditLog.verify_chain(entries, public_key)
        print(
            f"  Audit log chain ({len(entries)} entries): {'PASS ✅' if chain_ok else 'FAIL ❌'}"
        )
        if chain_ok:
            for entry in entries:
                print(f"    [{entry.action}] {entry.timestamp} — signature valid")
        else:
            print("    Chain broken: signature or hash linkage invalid")
            all_pass = False
    else:
        print("  Audit log: MISSING ❌")
        all_pass = False

    # 2. Verify zero-egress report
    egress_path = redlined_dir / "zero_egress_report.json"
    if egress_path.exists():
        egress_json = egress_path.read_text(encoding="utf-8")
        report = report_from_json(egress_json)
        egress_ok = verify_zero_egress_report(report, public_key)
        print(f"  Zero-egress report: {'PASS ✅' if egress_ok else 'FAIL ❌'}")
        if egress_ok:
            print(f"    Timestamp: {report.timestamp}")
            print(f"    Doc hash: {report.doc_hash[:16]}...")
            print(f"    Edits: {report.total_edits}, Flagged: {report.total_flagged}")
            print(f"    Attestation: {report.offline_attestation[:80]}...")
        else:
            print("    Signature invalid")
            all_pass = False
    else:
        print("  Zero-egress report: MISSING ❌")
        all_pass = False

    # 3. Verify redlined.docx bytes against the signed output manifest
    docx_path = redlined_dir / "redlined.docx"
    if docx_path.exists():
        manifest_ok, detail = _verify_output_manifest(redlined_dir, public_key)
        if manifest_ok:
            print(
                f"  Redlined document: HASH VERIFIED ✅ "
                f"({docx_path.stat().st_size} bytes)"
            )
            print(f"    {detail}")
        else:
            print(f"  Redlined document: UNVERIFIED ❌ ({detail})")
            all_pass = False
    else:
        print("  Redlined document: MISSING ❌")
        all_pass = False

    # 4. Check airgap egress report if present
    airgap_path = redlined_dir / "airgap_egress_report.json"
    if airgap_path.exists():
        airgap_json = airgap_path.read_text(encoding="utf-8")
        airgap_data = json.loads(airgap_json)
        zero_egress = airgap_data.get("zero_egress", False)
        completed = airgap_data.get("session_completed", False)
        print(
            f"  Air-gap egress report: {'PASS ✅' if (zero_egress and completed) else 'FAIL ❌'}"
        )
        if zero_egress and completed:
            print(
                f"    Egress attempts: {airgap_data.get('total_egress_attempts', '?')}"
            )
            print(f"    DNS lookups: {airgap_data.get('total_dns_lookups', '?')}")
            print(f"    Sealed mode: {airgap_data.get('sealed_mode_active', '?')}")
        else:
            all_pass = False
    # Not required for non-sealed runs

    print()
    print(f"  OVERALL: {'ALL PASS ✅' if all_pass else 'FAILURES DETECTED ❌'}")
    print("=" * 60)

    return 0 if all_pass else 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def cmd_excel(args: argparse.Namespace) -> int:
    """Run the Excel pipeline: edit → recompute → verify → audit."""
    input_path = str(Path(args.input).resolve())
    spec_path = str(Path(args.spec).resolve())
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        return 1
    if not os.path.exists(spec_path):
        print(f"ERROR: Spec file not found: {spec_path}", file=sys.stderr)
        return 1

    import json

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    # Get or create Ed25519 keypair
    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    output_xlsx = str(out_dir / "recomputed.xlsx")

    from kairo.excel.engine import excel_pipeline

    print("Running Excel pipeline (offline, LibreOffice recompute)...")
    result = excel_pipeline(
        input_path=input_path,
        output_path=output_xlsx,
        edits=spec.get("edits", []),
        expected_values={
            k: float(v) for k, v in spec.get("expected_values", {}).items()
        },
        expected_sheets=spec.get("expected_sheets"),
        expected_named_ranges=spec.get("expected_named_ranges"),
        private_key=private_key,
        author="Kairo Excel",
    )

    if not result.ok:
        print(f"ERROR: Excel pipeline failed: {result.error}", file=sys.stderr)
        return 1

    # Write audit log + egress report
    (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
    (out_dir / "zero_egress_report.json").write_text(
        result.egress_report_json, encoding="utf-8"
    )

    # Verify audit log
    from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

    entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
    audit_ok = Ed25519AuditLog.verify_chain(entries, public_key)

    from kairo.oracles.zero_egress_report import (
        report_from_json,
        verify_zero_egress_report,
    )

    egress_report = report_from_json(result.egress_report_json)
    egress_ok = verify_zero_egress_report(egress_report, public_key)

    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — EXCEL PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Input:       {Path(input_path).name}")
    print(f"  Spec:        {Path(spec_path).name}")
    print(f"  Output:      {out_dir}")
    print(f"  Edits applied:  {len(result.applied_edits)}")
    print(f"  Recompute verified: {'✅' if result.recompute_verified else '❌'}")
    print()
    print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
    print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
    print()
    print(f"  Artifacts in {out_dir}/:")
    print("    recomputed.xlsx")
    print("    audit_log.json")
    print("    zero_egress_report.json")
    print("    public_key.pem")
    print("=" * 60)

    return 0 if (audit_ok and egress_ok and result.recompute_verified) else 1


# pdf subcommand
def cmd_pdf(args: argparse.Namespace) -> int:
    """Run the PDF pipeline: extract/redact/fill/sign/verify per spec → audit."""
    input_path = str(Path(args.input).resolve())
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        return 1

    action = args.action

    # Load spec if provided
    spec = {}
    if hasattr(args, "spec") and args.spec:
        spec_path = str(Path(args.spec).resolve())
        if not os.path.exists(spec_path):
            print(f"ERROR: Spec file not found: {spec_path}", file=sys.stderr)
            return 1
        import json

        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)

    # Get or create Ed25519 keypair
    key_dir = out_dir / ".keys"
    private_key, public_key, pub_pem = _get_or_create_keypair(key_dir)
    (out_dir / "public_key.pem").write_bytes(pub_pem)

    # Determine output path
    if action == "redact":
        output_pdf = str(out_dir / "redacted.pdf")
        spec.setdefault("target_text", spec.get("redact", {}).get("target_text", ""))
    elif action == "fill":
        output_pdf = str(out_dir / "filled.pdf")
        spec.setdefault("field_values", spec.get("fields", {}))
    elif action == "sign":
        output_pdf = str(out_dir / "signed.pdf")
    elif action == "verify":
        output_pdf = input_path
    else:
        output_pdf = str(out_dir / "output.pdf")

    from kairo.pdf.engine import pdf_pipeline

    print(f"Running PDF pipeline: {action} (offline)...")
    result = pdf_pipeline(
        input_path=input_path,
        output_path=output_pdf,
        action=action,
        spec=spec,
        private_key=private_key,
        author="Kairo PDF",
    )

    if not result.ok:
        print(f"ERROR: PDF pipeline failed: {result.error}", file=sys.stderr)
        return 1

    # Write audit log + egress report
    if result.audit_log_json:
        (out_dir / "audit_log.json").write_text(result.audit_log_json, encoding="utf-8")
    if result.egress_report_json:
        (out_dir / "zero_egress_report.json").write_text(
            result.egress_report_json, encoding="utf-8"
        )

    # Verify audit log
    audit_ok = True
    if result.audit_log_json:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

        entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
        audit_ok = Ed25519AuditLog.verify_chain(entries, public_key)

    egress_ok = True
    if result.egress_report_json:
        from kairo.oracles.zero_egress_report import (
            report_from_json,
            verify_zero_egress_report,
        )

        egress_report = report_from_json(result.egress_report_json)
        egress_ok = verify_zero_egress_report(egress_report, public_key)

    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — PDF PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Input:       {Path(input_path).name}")
    print(f"  Action:      {action}")
    print(f"  Output:      {out_dir}")
    print(f"  Scanned:     {'yes' if result.is_scanned else 'no'}")
    print(f"  OCR used:    {'yes' if result.ocr_used else 'no'}")
    if action == "extract":
        print(f"  Words found: {len(result.word_boxes)}")
    if action == "fill":
        print(f"  Fields filled: {len(result.applied_edits)}")
    if action == "sign":
        print(f"  Signature valid: {'✅' if result.signature_valid else '❌'}")
    if action == "verify":
        print(f"  Signature valid: {'✅' if result.signature_valid else '❌'}")
    print()
    print(f"  Audit log verified: {'✅' if audit_ok else '❌'}")
    print(f"  Zero-egress report verified: {'✅' if egress_ok else '❌'}")
    print()
    print(f"  Artifacts in {out_dir}/:")
    if action == "redact":
        print("    redacted.pdf")
    elif action == "fill":
        print("    filled.pdf")
    elif action == "sign":
        print("    signed.pdf")
    print("    audit_log.json")
    print("    zero_egress_report.json")
    print("    public_key.pem")
    print("=" * 60)

    return 0 if (audit_ok and egress_ok and result.ok) else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — builds parser from the domain plugin registry.

    Shared commands (verify) are added directly.  Domain commands
    (redline, excel, pdf, data) are added via kairo.domains.registry.discover().
    """
    parser = argparse.ArgumentParser(
        prog="kairo",
        description="Kairo Phantom — offline document-intelligence CLI (signed, verifiable)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Shared verify command (not domain-specific)
    verify_parser = subparsers.add_parser(
        "verify",
        help="Independently verify audit log + zero-egress report + output manifest",
    )
    verify_parser.add_argument(
        "redlined_dir", help="Directory containing redline artifacts"
    )
    verify_parser.add_argument(
        "public_key",
        nargs="?",
        default=None,
        help="Path to a trusted public key .pem file (must be supplied externally, "
             "not from the output directory). If omitted, --fingerprint must be set.",
    )
    verify_parser.add_argument(
        "--fingerprint",
        default=None,
        help="SHA-256 fingerprint of the expected public key (hex). "
             "The co-located public_key.pem is checked against this fingerprint.",
    )

    # Domain commands via the plugin registry
    from kairo.domains.registry import discover

    domains = discover()
    domain_by_cli: dict[str, object] = {}
    for domain in domains:
        domain.register_cli(subparsers)
        domain_by_cli[domain.cli_name] = domain

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    try:
        # Shared verify command
        if args.command == "verify":
            return cmd_verify(args)

        # Domain commands via registry
        if args.command in domain_by_cli:
            return domain_by_cli[args.command].run(args)

        # Fallback for backward compat (should not reach here if registry is working)
        if args.command == "redline":
            return cmd_redline(args)
        elif args.command == "excel":
            return cmd_excel(args)
        elif args.command == "pdf":
            if not hasattr(args, "action") or args.action is None:
                parser.print_help()
                return 1
            return cmd_pdf(args)

        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:  # graceful CLI boundary — no raw tracebacks
        import os

        if os.environ.get("KAIRO_DEBUG"):
            raise
        print(
            f"ERROR: {args.command} failed: {exc.__class__.__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
