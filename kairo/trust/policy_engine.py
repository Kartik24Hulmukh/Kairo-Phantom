"""
W7 Trust Layer — Policy-as-Code Engine.

A simple, deterministic policy engine for high-risk action classes.
Policies are defined as Python functions that return ALLOW/DENY/REQUIRE_HUMAN.

This is intentionally simple (no OPA/Cedar runtime dependency) — the goal
is to have a testable, auditable policy layer that can be extended later.

Policy classes:
- ALLOW: action is permitted without human review
- DENY: action is blocked unconditionally
- REQUIRE_HUMAN: action requires human co-sign (WebAuthn tap)

Built-in policies:
- file_delete: DENY destructive file operations
- network_access: DENY in sealed mode, REQUIRE_HUMAN otherwise
- clipboard_write: REQUIRE_HUMAN (W6 — clipboard is a leak vector)
- code_execution: REQUIRE_HUMAN for arbitrary code, ALLOW for safe commands
- data_export: REQUIRE_HUMAN for large exports, ALLOW for small
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    "PolicyDecision",
    "PolicyContext",
    "PolicyResult",
    "PolicyEngine",
    "register_policy",
    "evaluate_policy",
]


class PolicyDecision(Enum):
    """Possible policy decisions."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HUMAN = "require_human"


@dataclass
class PolicyContext:
    """Context for a policy evaluation."""
    action: str  # e.g. "file_delete", "network_access", "clipboard_write"
    target: str  # e.g. file path, URL, clipboard content
    agent_id: str = ""
    sealed_mode: bool = False
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class PolicyResult:
    """Result of a policy evaluation."""
    decision: PolicyDecision
    reason: str
    policy_name: str
    context: PolicyContext


# Type for policy functions
PolicyFunc = Callable[[PolicyContext], PolicyResult]


class PolicyEngine:
    """
    Simple policy-as-code engine.

    Policies are registered functions that take a PolicyContext and return
    a PolicyResult. The engine evaluates all matching policies and returns
    the most restrictive decision.
    """

    def __init__(self) -> None:
        self._policies: Dict[str, List[PolicyFunc]] = {}

    def register(self, action: str, policy: PolicyFunc) -> None:
        """Register a policy function for an action class."""
        if action not in self._policies:
            self._policies[action] = []
        self._policies[action].append(policy)

    def evaluate(self, ctx: PolicyContext) -> PolicyResult:
        """
        Evaluate all policies for the given action.

        Returns the most restrictive decision:
        DENY > REQUIRE_HUMAN > ALLOW
        """
        policies = self._policies.get(ctx.action, [])
        if not policies:
            # No policy registered — default to REQUIRE_HUMAN for safety
            return PolicyResult(
                decision=PolicyDecision.REQUIRE_HUMAN,
                reason=f"No policy registered for action '{ctx.action}' — defaulting to require human",
                policy_name="default",
                context=ctx,
            )

        results = [p(ctx) for p in policies]

        # Find most restrictive
        priority = {PolicyDecision.DENY: 0, PolicyDecision.REQUIRE_HUMAN: 1, PolicyDecision.ALLOW: 2}
        most_restrictive = min(results, key=lambda r: priority[r.decision])
        return most_restrictive

    def list_policies(self) -> Dict[str, List[str]]:
        """List all registered policy names by action."""
        return {
            action: [p.__name__ for p in policies]
            for action, policies in self._policies.items()
        }


# Global engine instance
_engine = PolicyEngine()


def register_policy(action: str, policy: PolicyFunc) -> None:
    """Register a policy on the global engine."""
    _engine.register(action, policy)


def evaluate_policy(ctx: PolicyContext) -> PolicyResult:
    """Evaluate a policy on the global engine."""
    return _engine.evaluate(ctx)


# ── Built-in Policies ────────────────────────────────────────────────────────

def _policy_file_delete(ctx: PolicyContext) -> PolicyResult:
    """DENY destructive file operations."""
    dangerous_patterns = ["/etc/", "/boot/", "/sys/", "/proc/", "C:\\Windows\\System32"]
    target_lower = ctx.target.lower()
    for pattern in dangerous_patterns:
        if pattern.lower() in target_lower:
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason=f"File deletion blocked: target '{ctx.target}' matches protected path pattern '{pattern}'",
                policy_name="file_delete_protected_paths",
                context=ctx,
            )
    # Non-protected paths require human review
    return PolicyResult(
        decision=PolicyDecision.REQUIRE_HUMAN,
        reason="File deletion requires human review",
        policy_name="file_delete_human_review",
        context=ctx,
    )


def _policy_network_access(ctx: PolicyContext) -> PolicyResult:
    """DENY network access in sealed mode, REQUIRE_HUMAN otherwise."""
    if ctx.sealed_mode:
        return PolicyResult(
            decision=PolicyDecision.DENY,
            reason="Network access DENIED in sealed mode (KAIRO_SEALED=1)",
            policy_name="network_sealed_deny",
            context=ctx,
        )
    return PolicyResult(
        decision=PolicyDecision.REQUIRE_HUMAN,
        reason="Network access requires human review (non-sealed mode)",
        policy_name="network_human_review",
        context=ctx,
    )


def _policy_clipboard_write(ctx: PolicyContext) -> PolicyResult:
    """REQUIRE_HUMAN for clipboard writes (W6 — clipboard is a leak vector)."""
    return PolicyResult(
        decision=PolicyDecision.REQUIRE_HUMAN,
        reason="Clipboard write requires human review (injection leak vector — see W6)",
        policy_name="clipboard_human_review",
        context=ctx,
    )


def _policy_code_execution(ctx: PolicyContext) -> PolicyResult:
    """REQUIRE_HUMAN for arbitrary code execution, ALLOW for safe commands."""
    safe_commands = ["ls", "cat", "echo", "pwd", "whoami", "date", "head", "tail", "wc"]
    cmd = ctx.target.split()[0] if ctx.target.split() else ""
    if cmd in safe_commands:
        return PolicyResult(
            decision=PolicyDecision.ALLOW,
            reason=f"Command '{cmd}' is in the safe list",
            policy_name="code_execution_safe_list",
            context=ctx,
        )
    return PolicyResult(
        decision=PolicyDecision.REQUIRE_HUMAN,
        reason=f"Command '{cmd}' requires human review (not in safe list)",
        policy_name="code_execution_human_review",
        context=ctx,
    )


def _policy_data_export(ctx: PolicyContext) -> PolicyResult:
    """REQUIRE_HUMAN for large data exports, ALLOW for small."""
    size = ctx.metadata.get("size_bytes", 0)
    if size > 10 * 1024 * 1024:  # 10 MB
        return PolicyResult(
            decision=PolicyDecision.REQUIRE_HUMAN,
            reason=f"Data export requires human review (size={size} bytes > 10MB threshold)",
            policy_name="data_export_large",
            context=ctx,
        )
    return PolicyResult(
        decision=PolicyDecision.ALLOW,
        reason=f"Data export allowed (size={size} bytes <= 10MB threshold)",
        policy_name="data_export_small",
        context=ctx,
    )


# Register built-in policies
register_policy("file_delete", _policy_file_delete)
register_policy("network_access", _policy_network_access)
register_policy("clipboard_write", _policy_clipboard_write)
register_policy("code_execution", _policy_code_execution)
register_policy("data_export", _policy_data_export)
