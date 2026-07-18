"""Configurable trust-policy input for the legal-v3 verifier.

Instead of hardcoded allowlists, the verifier can accept a trust-policy
file that specifies:
  - allowed clause types
  - trusted key IDs (trust roots)
  - approval TTL (seconds)
  - whether observer key collision is rejected

This keeps fail-closed behavior while making the verifier configurable
for different deployment contexts (e.g. different partner NDAs may
allow different clause sets).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Default policy — matches the hardcoded values in transaction.py
DEFAULT_POLICY: dict[str, Any] = {
    "profile": "kairo-legal-v3",
    "allowed_clauses": [
        "governing_law",
        "liability_cap",
        "termination_notice",
        "confidentiality_survival",
        "indemnification_cap",
    ],
    "trusted_key_ids": None,  # None = accept any key present in bundle
    "approval_ttl_seconds": 600,
    "reject_observer_collision": True,
    "max_source_bytes": 26214400,  # 25 MiB
}


class TrustPolicyError(RuntimeError):
    """Raised when a trust policy is invalid or a check fails."""


def load_policy(path: str | None = None) -> dict[str, Any]:
    """Load a trust policy from a JSON file, or return the default.

    If *path* is None, returns the default policy (backward-compatible
    with the hardcoded allowlist behavior).
    """
    if path is None:
        return dict(DEFAULT_POLICY)

    p = Path(path)
    if not p.exists():
        raise TrustPolicyError(f"trust policy file not found: {path}")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrustPolicyError(f"invalid JSON in trust policy: {exc}") from exc

    # Validate required fields
    if "profile" not in data:
        raise TrustPolicyError("trust policy missing 'profile' field")
    if data["profile"] != "kairo-legal-v3":
        raise TrustPolicyError(
            f"trust policy profile mismatch: expected 'kairo-legal-v3', got '{data['profile']}'"
        )
    if "allowed_clauses" not in data:
        raise TrustPolicyError("trust policy missing 'allowed_clauses' field")
    if not isinstance(data["allowed_clauses"], list):
        raise TrustPolicyError("'allowed_clauses' must be a list")

    # Fill in defaults for optional fields
    for key, default in DEFAULT_POLICY.items():
        if key not in data:
            data[key] = default

    return data


def check_clause(policy: dict[str, Any], clause: str) -> bool:
    """Return True if *clause* is allowed by the policy."""
    return clause in policy["allowed_clauses"]


def check_key_trust(policy: dict[str, Any], key_id: str) -> bool:
    """Return True if *key_id* is trusted by the policy.

    If ``trusted_key_ids`` is None, any key present in the bundle is
    accepted (backward-compatible default).
    """
    trusted = policy.get("trusted_key_ids")
    if trusted is None:
        return True
    return key_id in trusted


def check_approval_ttl(policy: dict[str, Any], issued_at: int, approved_at: int) -> bool:
    """Return True if the approval was granted within the TTL window."""
    ttl = policy.get("approval_ttl_seconds", 600)
    return (approved_at - issued_at) <= ttl


def check_observer_collision(
    policy: dict[str, Any], observer_key_id: str, other_key_ids: list[str]
) -> bool:
    """Return True if the observer key does not collide with other keys.

    Returns True (pass) if the observer key is distinct from all other
    keys. Returns False if collision is detected and the policy rejects
    collisions.
    """
    if not policy.get("reject_observer_collision", True):
        return True  # policy allows collisions
    return observer_key_id not in other_key_ids


def check_source_size(policy: dict[str, Any], size_bytes: int) -> bool:
    """Return True if the source file size is within policy limits."""
    max_bytes = policy.get("max_source_bytes", 26214400)
    return size_bytes <= max_bytes


def write_default_policy(path: str) -> None:
    """Write the default trust policy to a JSON file (for reference)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(DEFAULT_POLICY, indent=2) + "\n", encoding="utf-8"
    )
