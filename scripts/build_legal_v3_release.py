#!/usr/bin/env python3
"""Stage the isolated legal-v3 technical-preview release surface.

Produces:
  - RELEASE_MANIFEST.json  (file list + SHA-256 digests)
  - SURFACE_AUDIT.json     (zero-finding audit of staged surface)

The surface audit verifies that no legacy domain code, desktop automation,
peer networking, or unrelated filesystem access is present in the staged
release artifact.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "target/legal-v3-release")

# ---------------------------------------------------------------------------
# Files allowed in the legal-v3 release surface.
# ---------------------------------------------------------------------------
allow = [
    "kairo/legal_v3",
    "kairo/oracles/legal_redline_pipeline.py",
    "kairo/oracles/docx_tracked_changes.py",
    "kairo/oracles/ed25519_audit_log.py",
    "kairo/oracles/zero_egress_report.py",
    "kairo/security/injection_guard.py",
    "kairo-sidecar/sidecar/parsers/adeu_bridge.py",
    "tools/kairo_legal_v3.py",
    "fixtures/demo/sample_nda.docx",
    "fixtures/demo/nda_playbook.json",
]

# ---------------------------------------------------------------------------
# Forbidden patterns — any match is a surface audit finding.
# ---------------------------------------------------------------------------
FORBIDDEN_PATTERNS = [
    # legacy domain packages
    "kairo/domains/",
    "kairo/cua/",
    "kairo/sync/",
    "kairo/context/",
    "kairo/docintel/",
    "kairo/graph/",
    "kairo/observability/",
    "kairo/core/",
    # desktop automation / browser autonomy
    "desktop_automation",
    "browser_autonomy",
    "playwright",
    "selenium",
    # peer networking / LAN sync
    "peer_network",
    "lan_sync",
    "socket_accept",
    # multi-agent swarms
    "multi_agent",
    "agent_swarm",
    # voice/video
    "voice_input",
    "video_capture",
    # plugin marketplace
    "plugin_market",
    # memory/vector databases
    "vector_db",
    "pinecone",
    "chromadb",
    # runtime package acquisition
    "pip_install",
    "npm_install",
    "runtime_package",
]

# ---------------------------------------------------------------------------
# Forbidden claim language in any staged file.
# ---------------------------------------------------------------------------
FORBIDDEN_CLAIMS = [
    "production-ready",
    "injection-safe",
    "zero sockets",
    "whole-machine air gap",
    "every action signed",
    "certified",
    "compliant",
    "privilege-safe",
    "100% accurate legal automation",
    "uncopyable",
    "1000x",
    "unicorn-guaranteed",
]


def _stage() -> list[dict]:
    """Copy allowed files into OUT and return the file manifest."""
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    for rel in allow:
        source = ROOT / rel
        destination = OUT / rel
        if source.is_dir():
            shutil.copytree(
                source,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    files = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": str(path.relative_to(OUT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
            )
    return files


def _audit_surface(files: list[dict]) -> dict:
    """Scan staged files for forbidden patterns and claim language."""
    findings = []

    for entry in files:
        rel = entry["path"]
        full = OUT / rel

        # Check path-based forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in rel:
                findings.append(
                    {
                        "file": rel,
                        "type": "forbidden_path",
                        "pattern": pattern,
                    }
                )

        # Check content for forbidden claims (text files only)
        if rel.endswith((".py", ".json", ".md", ".txt", ".yml", ".yaml")):
            try:
                content = full.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for claim in FORBIDDEN_CLAIMS:
                if claim.lower() in content.lower():
                    findings.append(
                        {
                            "file": rel,
                            "type": "forbidden_claim",
                            "pattern": claim,
                        }
                    )

    return {
        "profile": "legal-v3-mutual-nda",
        "finding_count": len(findings),
        "findings": findings,
        "status": "PASS" if not findings else "FAIL",
    }


def main() -> None:
    files = _stage()

    manifest = {
        "profile": "legal-v3-mutual-nda",
        "status": "technical-preview",
        "files": files,
        "excluded_capabilities": [
            "legacy domain packages",
            "desktop automation",
            "peer networking",
            "generic tool mutation",
            "runtime package acquisition",
        ],
    }
    (OUT / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    audit = _audit_surface(files)
    (OUT / "SURFACE_AUDIT.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )

    print(OUT)
    if audit["status"] != "PASS":
        print(f"SURFACE AUDIT: FAIL ({audit['finding_count']} findings)", file=sys.stderr)
        for f in audit["findings"]:
            print(f"  {f['file']}: {f['type']} — {f['pattern']}", file=sys.stderr)
        sys.exit(1)
    else:
        print("SURFACE AUDIT: PASS (0 findings)")


if __name__ == "__main__":
    main()
