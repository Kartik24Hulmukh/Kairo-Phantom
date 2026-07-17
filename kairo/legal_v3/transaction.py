"""Governed mutual-NDA DOCX transaction: propose -> approve -> execute -> observe -> verify.

Isolated from Kairo's twelve legacy domains. This is a technical-preview path:
cryptographic integrity and artifact readback do not equal legal acceptance.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PROFILE = "kairo-legal-v3"
ACTION = "mutual_nda.redline"
MAX_BYTES = 25 * 1024 * 1024
EVENTS = (
    "INPUT_OBSERVED",
    "TRUST_CLASSIFIED",
    "POLICY_DECISION",
    "ACTION_INTENT",
    "APPROVAL_BOUND",
    "ACTION_ATTEMPT",
    "ARTIFACT_READBACK",
    "RUN_CLOSED",
)
ALLOWED_CLAUSES = {
    "governing_law",
    "liability_cap",
    "termination_notice",
    "confidentiality_survival",
    "indemnification_cap",
}


class LegalV3Error(RuntimeError):
    """Fail-closed transaction error."""


def canonical(value: Any) -> bytes:
    def walk(x: Any) -> Any:
        if isinstance(x, float):
            raise LegalV3Error("floats forbidden in signed objects")
        if isinstance(x, dict):
            return {k: walk(x[k]) for k in sorted(x)}
        if isinstance(x, list):
            return [walk(i) for i in x]
        if isinstance(x, int) and abs(x) > 9007199254740991:
            raise LegalV3Error("unsafe integer")
        return x

    return json.dumps(
        walk(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_regular(path: Path) -> bytes:
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise LegalV3Error("regular non-symlink file required")
    if st.st_size > MAX_BYTES:
        raise LegalV3Error("file too large")
    return path.read_bytes()


def generate_keypair(role: str) -> dict[str, str]:
    if role not in {"producer", "approver", "observer"}:
        raise LegalV3Error("invalid role")
    sk = Ed25519PrivateKey.generate()
    raw = sk.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = sk.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return {
        "role": role,
        "key_id": sha(pub)[:16],
        "private": base64.b64encode(raw).decode(),
        "public": base64.b64encode(pub).decode(),
    }


def sign(obj: dict[str, Any], key: dict[str, str]) -> str:
    sk = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key["private"]))
    return base64.b64encode(sk.sign(canonical(obj))).decode()


def verify_sig(obj: dict[str, Any], sig: str, pub_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(
            base64.b64decode(sig), canonical(obj)
        )
        return True
    except Exception:
        return False


def _load_json_bytes(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise LegalV3Error("invalid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise LegalV3Error("JSON object required")
    return value


def _allowed_playbook(playbook: dict[str, Any]) -> None:
    clauses = playbook.get("clauses")
    if not isinstance(clauses, list) or not clauses:
        raise LegalV3Error("clauses required")
    for clause in clauses:
        if not isinstance(clause, dict):
            raise LegalV3Error("invalid clause")
        if clause.get("clause_id") not in ALLOWED_CLAUSES:
            raise LegalV3Error("outside mutual-NDA operation set")
        for field in ("match_text", "replacement_text", "citation", "rationale"):
            if not isinstance(clause.get(field), str) or not clause[field].strip():
                raise LegalV3Error(f"missing {field}")


def _resolve_under_root(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise LegalV3Error("path escape")
    return candidate


def propose(
    root: str,
    source: str,
    playbook: str,
    output: str,
    producer_key: dict[str, str],
    ttl: int = 900,
) -> dict[str, Any]:
    if producer_key.get("role") != "producer":
        raise LegalV3Error("producer key required")
    rootp = Path(root).resolve()
    source_path = _resolve_under_root(rootp, source)
    playbook_path = _resolve_under_root(rootp, playbook)
    source_bytes = read_regular(source_path)
    playbook_bytes = read_regular(playbook_path)
    data = _load_json_bytes(playbook_bytes)
    _allowed_playbook(data)
    now = int(time.time())
    unsigned = {
        "profile": PROFILE,
        "proposal_id": uuid.uuid4().hex,
        "action": ACTION,
        "source": source,
        "playbook": playbook,
        "output": output,
        "source_sha256": sha(source_bytes),
        "playbook_sha256": sha(playbook_bytes),
        "clauses": data["clauses"],
        "issued_at": now,
        "expires_at": now + ttl,
        "producer_key_id": producer_key["key_id"],
    }
    proposal = {**unsigned, "intent_sha256": sha(canonical(unsigned))}
    proposal["signature"] = sign(
        {k: v for k, v in proposal.items() if k != "signature"}, producer_key
    )
    return proposal


def approve(
    proposal: dict[str, Any],
    approver_key: dict[str, str],
    ttl: int = 600,
) -> dict[str, Any]:
    if approver_key.get("role") != "approver":
        raise LegalV3Error("approver key required")
    now = int(time.time())
    unsigned = {
        "profile": PROFILE,
        "approval_id": uuid.uuid4().hex,
        "decision": "approve",
        "intent_sha256": proposal["intent_sha256"],
        "source_sha256": proposal["source_sha256"],
        "playbook_sha256": proposal["playbook_sha256"],
        "principal": approver_key["key_id"],
        "issued_at": now,
        "expires_at": min(now + ttl, proposal["expires_at"]),
        "nonce": uuid.uuid4().hex,
    }
    return {**unsigned, "signature": sign(unsigned, approver_key)}


def _verify_approval(
    proposal: dict[str, Any],
    approval: dict[str, Any],
    keys: dict[str, str],
) -> None:
    now = int(time.time())
    proposal_unsigned = {
        k: v for k, v in proposal.items() if k not in {"signature", "intent_sha256"}
    }
    if sha(canonical(proposal_unsigned)) != proposal.get("intent_sha256"):
        raise LegalV3Error("proposal digest mismatch")
    producer = proposal.get("producer_key_id")
    if producer not in keys or not verify_sig(
        {k: v for k, v in proposal.items() if k != "signature"},
        proposal.get("signature", ""),
        keys[producer],
    ):
        raise LegalV3Error("invalid proposal signature")
    if (
        approval.get("decision") != "approve"
        or not approval["issued_at"] <= now < approval["expires_at"]
        or now >= proposal["expires_at"]
    ):
        raise LegalV3Error("approval expired/denied")
    for field in ("intent_sha256", "source_sha256", "playbook_sha256"):
        if approval.get(field) != proposal.get(field):
            raise LegalV3Error("approval substitution")
    principal = approval.get("principal")
    if principal not in keys or not verify_sig(
        {k: v for k, v in approval.items() if k != "signature"},
        approval.get("signature", ""),
        keys[principal],
    ):
        raise LegalV3Error("invalid approval signature")


def _event(
    sequence: int,
    event_type: str,
    previous: str | None,
    payload: dict[str, Any],
    observer: dict[str, str],
) -> dict[str, Any]:
    unsigned = {
        "sequence": sequence,
        "event_type": event_type,
        "previous_event_sha256": previous,
        "payload": payload,
        "observer_key_id": observer["key_id"],
    }
    event_sha = sha(canonical(unsigned))
    return {
        **unsigned,
        "event_sha256": event_sha,
        "signature": sign(unsigned, observer),
    }


def execute(
    root: str,
    proposal: dict[str, Any],
    approval: dict[str, Any],
    keys: dict[str, str],
    observer_key: dict[str, str],
    bundle_dir: str,
) -> dict[str, Any]:
    if (
        observer_key.get("role") != "observer"
        or observer_key.get("key_id") == proposal.get("producer_key_id")
        or observer_key.get("key_id") == approval.get("principal")
    ):
        raise LegalV3Error("independent observer identity required")

    rootp = Path(root).resolve()
    source_path = _resolve_under_root(rootp, proposal["source"])
    playbook_path = _resolve_under_root(rootp, proposal["playbook"])
    output_path = _resolve_under_root(rootp, proposal["output"])
    if rootp not in output_path.parent.parents and output_path.parent != rootp:
        raise LegalV3Error("path escape")
    if output_path.exists() and output_path.is_symlink():
        raise LegalV3Error("symlink output")

    source_bytes = read_regular(source_path)
    playbook_bytes = read_regular(playbook_path)
    if (
        sha(source_bytes) != proposal["source_sha256"]
        or sha(playbook_bytes) != proposal["playbook_sha256"]
    ):
        raise LegalV3Error("source/playbook substitution")
    _verify_approval(proposal, approval, keys)

    from kairo.oracles.docx_tracked_changes import verify_docx_tracked_changes
    from kairo.oracles.legal_redline_pipeline import redline_contract

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".kairo-", suffix=".docx", dir=output_path.parent)
    os.close(fd)
    Path(tmp).unlink(missing_ok=True)
    result = redline_contract(
        str(source_path), str(playbook_path), tmp, author="Kairo Legal v3"
    )
    if not result.ok:
        Path(tmp).unlink(missing_ok=True)
        raise LegalV3Error(result.error)

    expected = [
        {"old": edit.old_text, "new": edit.new_text, "author": "Kairo Legal v3"}
        for edit in result.applied_edits
    ]
    verify_docx_tracked_changes(tmp, expected, forbid_extra_revisions=True)
    os.replace(tmp, output_path)
    output_bytes = read_regular(output_path)
    output_sha = sha(output_bytes)

    bundle = Path(bundle_dir)
    bundle.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, bundle / "source.docx")
    shutil.copy2(playbook_path, bundle / "playbook.json")
    shutil.copy2(output_path, bundle / "output.docx")

    base_payload = {
        "source_sha256": sha(source_bytes),
        "playbook_sha256": sha(playbook_bytes),
        "intent_sha256": proposal["intent_sha256"],
        "approval_id": approval["approval_id"],
        "output_sha256": output_sha,
        "applied_edits": expected,
        "flagged": [flag.__dict__ for flag in result.flagged_clauses],
    }
    events: list[dict[str, Any]] = []
    previous: str | None = None
    for index, event_type in enumerate(EVENTS):
        payload = {
            **base_payload,
            "status": "success" if event_type == "RUN_CLOSED" else "recorded",
        }
        event = _event(index, event_type, previous, payload, observer_key)
        events.append(event)
        previous = event["event_sha256"]

    manifest = {
        "profile": PROFILE,
        "run_id": uuid.uuid4().hex,
        "files": {
            "source": "source.docx",
            "playbook": "playbook.json",
            "output": "output.docx",
        },
        "proposal": proposal,
        "approval": approval,
        "public_keys": {**keys, observer_key["key_id"]: observer_key["public"]},
        "observer_key_id": observer_key["key_id"],
        "events": events,
        "verdicts": {
            "integrity": "unverified",
            "execution": "observed",
            "sufficiency": "complete_for_declared_boundary",
            "domain": "requires_human_review",
        },
    }
    (bundle / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_bundle(path: str) -> dict[str, Any]:
    bundle = Path(path).resolve()
    manifest = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    def check(ok: bool, name: str) -> None:
        checks.append({"ok": bool(ok), "check": name})

    for key, name in manifest["files"].items():
        file_path = (bundle / name).resolve()
        check(bundle in file_path.parents and file_path.is_file(), f"{key} path confinement")
        expected = manifest["events"][-1]["payload"][f"{key}_sha256"]
        check(
            bundle in file_path.parents and sha(read_regular(file_path)) == expected,
            f"{key} hash",
        )

    proposal = manifest["proposal"]
    proposal_unsigned = {
        k: v for k, v in proposal.items() if k not in {"signature", "intent_sha256"}
    }
    check(
        sha(canonical(proposal_unsigned)) == proposal.get("intent_sha256"),
        "proposal digest",
    )
    check(
        verify_sig(
            {k: v for k, v in proposal.items() if k != "signature"},
            proposal.get("signature", ""),
            manifest["public_keys"].get(proposal.get("producer_key_id"), ""),
        ),
        "proposal signature",
    )

    approval = manifest["approval"]
    check(
        all(
            approval.get(field) == proposal.get(field)
            for field in ("intent_sha256", "source_sha256", "playbook_sha256")
        ),
        "approval binding",
    )
    check(
        verify_sig(
            {k: v for k, v in approval.items() if k != "signature"},
            approval.get("signature", ""),
            manifest["public_keys"].get(approval.get("principal"), ""),
        ),
        "approval signature",
    )
    check(
        manifest["observer_key_id"]
        not in {proposal["producer_key_id"], approval["principal"]},
        "observer independence",
    )

    previous = None
    for index, event in enumerate(manifest["events"]):
        unsigned = {
            k: v for k, v in event.items() if k not in {"event_sha256", "signature"}
        }
        check(
            event["sequence"] == index and event["previous_event_sha256"] == previous,
            "sequence/parent",
        )
        check(sha(canonical(unsigned)) == event["event_sha256"], "event digest")
        check(
            verify_sig(
                unsigned,
                event["signature"],
                manifest["public_keys"][event["observer_key_id"]],
            ),
            "event signature",
        )
        previous = event["event_sha256"]

    check(
        tuple(event["event_type"] for event in manifest["events"]) == EVENTS,
        "mandatory state machine",
    )
    ok = all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "integrity": "pass" if ok else "fail",
        "execution": "pass" if ok else "unknown",
        "sufficiency": "complete_for_declared_boundary" if ok else "incomplete",
        "domain": "requires_human_review",
        "checks": checks,
    }
