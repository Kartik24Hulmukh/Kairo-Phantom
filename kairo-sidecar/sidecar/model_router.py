"""
sidecar/model_router.py — Kairo Phantom 4-Tier Model Selector
==============================================================
Determines which LiteLLM model alias to use based on request complexity.

Routing Logic
-------------
Tier              Traffic  Condition                                       Latency
kairo-fast          70%    complexity=simple, confidence≥0.75,            ~400ms
                           task_type in (insert/replace/explain),
                           tokens≤150
kairo-standard      25%    Everything else                                 ~1.8s
kairo-think          4%    complexity=complex,                             ~4s
                           waza_agent in (legal_reviewer, medical_scribe),
                           tokens>500
kairo-cloud          1%    requires_web_search=true OR tokens>1500          ~3s
                           (opt-in only)

Fallback chain: kairo-fast → kairo-standard → kairo-cloud
"""

import logging
from typing import Optional

log = logging.getLogger("kairo-sidecar.model_router")

# ─── Model Alias Constants ──────────────────────────────────────────────────
MODEL_FAST = "kairo-fast"  # 4B fine-tuned or qwen2.5:7b fallback
MODEL_STANDARD = "kairo-standard"  # qwen2.5:7b
MODEL_THINK = "kairo-think"  # qwen3:8b with reasoning
MODEL_CLOUD = "kairo-cloud"  # Claude Sonnet (opt-in)

# Default for backward compatibility
MODEL_DEFAULT = MODEL_STANDARD

# High-complexity waza agents that need reasoning tier
_THINK_AGENTS = frozenset({"legal_reviewer", "medical_scribe", "financial_analyst"})

# Simple task types that qualify for the fast tier
_FAST_TASK_TYPES = frozenset(
    {
        "insert",
        "insert_paragraph",
        "append",
        "replace",
        "replace_paragraph",
        "explain",
        "summarize",
        "title_update",
        "fix_typo",
        "format",
    }
)


def select_model(
    user_prompt: str = "",
    task_type: str = "",
    confidence: float = 1.0,
    waza_agent: str = "",
    requires_web_search: bool = False,
    estimated_tokens: int = 0,
    force_tier: Optional[str] = None,
) -> str:
    """
    Returns the LiteLLM model alias for this request.

    Parameters
    ----------
    user_prompt        : Raw user prompt text (used for token estimation if
                         estimated_tokens is not provided).
    task_type          : Operation type string (e.g. "insert_paragraph").
    confidence         : Classification confidence from intent gate (0–1).
    waza_agent         : Active Waza specialist agent name (if any).
    requires_web_search: True if the operation needs live web data.
    estimated_tokens   : Pre-computed token estimate; 0 = estimate from prompt.
    force_tier         : If set, bypasses all logic and returns this tier.

    Returns
    -------
    str — one of: "kairo-fast", "kairo-standard", "kairo-think", "kairo-cloud"
    """
    if force_tier:
        log.debug(f"model_router: force_tier={force_tier}")
        return force_tier

    # Estimate tokens from prompt if not provided
    if estimated_tokens <= 0 and user_prompt:
        # Rough 4-char-per-token heuristic
        estimated_tokens = max(1, len(user_prompt) // 4)

    # Tier 4 — Cloud (opt-in only, web search required or very long context)
    if requires_web_search or estimated_tokens > 1500:
        log.debug(
            f"model_router: → kairo-cloud (web_search={requires_web_search}, tokens={estimated_tokens})"
        )
        return MODEL_CLOUD

    # Tier 3 — Think (legal, medical, or high-complexity with many tokens)
    if waza_agent in _THINK_AGENTS or (estimated_tokens > 500 and confidence < 0.75):
        log.debug(
            f"model_router: → kairo-think (waza_agent={waza_agent!r}, tokens={estimated_tokens})"
        )
        return MODEL_THINK

    # Tier 1 — Fast (simple ops, high confidence, short prompt)
    normalized_task = task_type.lower().replace("-", "_")
    is_simple_task = any(normalized_task.startswith(t) for t in _FAST_TASK_TYPES)
    if is_simple_task and confidence >= 0.75 and estimated_tokens <= 150:
        log.debug(
            f"model_router: → kairo-fast (task={task_type!r}, conf={confidence:.2f}, tokens={estimated_tokens})"
        )
        return MODEL_FAST

    # Tier 2 — Standard (everything else)
    log.debug(
        f"model_router: → kairo-standard (task={task_type!r}, conf={confidence:.2f}, tokens={estimated_tokens})"
    )
    return MODEL_STANDARD


def model_tier_label(model_alias: str) -> str:
    """Returns a human-readable label for a model alias."""
    return {
        MODEL_FAST: "KairoDocWriter-4B (fast)",
        MODEL_STANDARD: "Qwen2.5-7B (standard)",
        MODEL_THINK: "Qwen3-8B reasoning (think)",
        MODEL_CLOUD: "Claude Sonnet (cloud)",
    }.get(model_alias, model_alias)
