"""DSSE/in-toto envelope wrapper for portable legal-v3 evidence bundles.

Wraps a legal-v3 evidence bundle in a DSSE (Dead Simple Signing Envelope)
statement so it can be verified by any DSSE-compatible verifier, not just
the built-in verify_bundle.

Reference: https://github.com/secure-systems-lab/dsse

DSSE envelope format:
  {
    "payload": "<base64-encoded JSON>",
    "payloadType": "application/vnd.kairo.legal-v3.bundle+json",
    "signatures": [
      {"sig": "<base64 signature>", "keyid": "<key id>"}
    ]
  }

in-toto statement (wrapped inside the DSSE payload):
  {
    "_type": "https://in-toto.io/Statement/v1",
    "subject": [
      {"name": "<output filename>", "digest": {"sha256": "<hash>"}}
    ],
    "predicateType": "https://kairo.phantom/legal-v3/v1",
    "predicate": { <full legal-v3 bundle> }
  }
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

PAYLOAD_TYPE = "application/vnd.kairo.legal-v3.bundle+json"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://kairo.phantom/legal-v3/v1"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


def create_statement(bundle: dict[str, Any]) -> dict[str, Any]:
    """Create an in-toto v1 Statement wrapping a legal-v3 bundle.

    The bundle's output artifact becomes the Statement subject, and the
    full bundle is embedded as the predicate.
    """
    output_name = bundle.get("proposal", {}).get("output", "output.docx")
    # Output hash is in the ARTIFACT_READBACK event payload (event index 6)
    events = bundle.get("events", [])
    output_sha = ""
    for ev in events:
        if ev.get("event_type") == "ARTIFACT_READBACK":
            output_sha = ev.get("payload", {}).get("output_sha256", "")
            break

    # Also include source and playbook as subjects
    subjects = []
    if output_sha:
        subjects.append(
            {"name": output_name, "digest": {"sha256": output_sha}}
        )
    source_name = bundle.get("proposal", {}).get("source", "source.docx")
    source_sha = bundle.get("proposal", {}).get("source_sha256", "")
    if source_sha:
        subjects.append(
            {"name": source_name, "digest": {"sha256": source_sha}}
        )

    return {
        "_type": STATEMENT_TYPE,
        "subject": subjects,
        "predicateType": PREDICATE_TYPE,
        "predicate": bundle,
    }


def create_envelope(
    bundle: dict[str, Any],
    signatures: list[dict[str, str]],
) -> dict[str, Any]:
    """Create a DSSE envelope wrapping an in-toto Statement.

    *signatures* is a list of {"sig": base64, "keyid": str} entries,
    typically the observer's signature over the statement payload.
    """
    statement = create_statement(bundle)
    payload_bytes = json.dumps(
        statement, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

    return {
        "payload": _b64(payload_bytes),
        "payloadType": PAYLOAD_TYPE,
        "signatures": signatures,
    }


def verify_envelope(
    envelope: dict[str, Any],
    verify_signature_fn=None,
) -> dict[str, Any]:
    """Verify a DSSE envelope structure and return the decoded statement.

    This performs structural validation only. Cryptographic signature
    verification requires a *verify_signature_fn* callback with the
    signature: (payload_bytes, signature_b64, key_id) -> bool.

    Returns the decoded in-toto Statement.
    """
    if "payload" not in envelope:
        raise ValueError("DSSE envelope missing 'payload'")
    if "payloadType" not in envelope:
        raise ValueError("DSSE envelope missing 'payloadType'")
    if "signatures" not in envelope:
        raise ValueError("DSSE envelope missing 'signatures'")

    if envelope["payloadType"] != PAYLOAD_TYPE:
        raise ValueError(
            f"unexpected payloadType: {envelope['payloadType']}"
        )

    payload_bytes = _b64d(envelope["payload"])
    statement = json.loads(payload_bytes)

    # Validate in-toto statement structure
    if statement.get("_type") != STATEMENT_TYPE:
        raise ValueError(
            f"unexpected statement type: {statement.get('_type')}"
        )
    if "subject" not in statement:
        raise ValueError("in-toto statement missing 'subject'")
    if "predicateType" not in statement:
        raise ValueError("in-toto statement missing 'predicateType'")
    if statement["predicateType"] != PREDICATE_TYPE:
        raise ValueError(
            f"unexpected predicateType: {statement['predicateType']}"
        )
    if "predicate" not in statement:
        raise ValueError("in-toto statement missing 'predicate'")

    # Verify signatures if a callback is provided
    if verify_signature_fn is not None:
        for sig_entry in envelope["signatures"]:
            sig = sig_entry.get("sig", "")
            keyid = sig_entry.get("keyid", "")
            if not verify_signature_fn(payload_bytes, sig, keyid):
                raise ValueError(
                    f"signature verification failed for keyid={keyid}"
                )

    return statement


def wrap_bundle(
    bundle_path: str,
    output_path: str | None = None,
    signatures: list[dict[str, str]] | None = None,
) -> str:
    """Convenience: load a bundle from disk, wrap in DSSE, write to disk.

    Returns the path to the written envelope file.
    """
    bp = Path(bundle_path)
    bundle = json.loads((bp / "bundle.json").read_text(encoding="utf-8"))

    if signatures is None:
        # Extract observer signature from the last event (RUN_CLOSED)
        signatures = []
        events = bundle.get("events", [])
        if events:
            last_event = events[-1]
            signatures.append(
                {
                    "sig": last_event.get("signature", ""),
                    "keyid": last_event.get("observer_key_id", ""),
                }
            )

    envelope = create_envelope(bundle, signatures)

    if output_path is None:
        output_path = str(bp / "bundle.dsse.json")

    Path(output_path).write_text(
        json.dumps(envelope, indent=2) + "\n", encoding="utf-8"
    )
    return output_path
