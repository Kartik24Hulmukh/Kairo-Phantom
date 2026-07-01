"""
sidecar/adaptive_compute.py — Adaptive Inference-Time Compute ("Deep Think").
Estimates task difficulty and dynamically allocates reasoning/thinking budget.
"""

import logging
from typing import Dict, Any

log = logging.getLogger("kairo-sidecar.adaptive_compute")

# Budget table: difficulty → compute parameters
_BUDGET_TABLE: Dict[str, Dict[str, Any]] = {
    "complex": {
        "N": 3,
        "use_best_of_n": True,
        "reasoning_model_hint": "kairo-think",
        "max_retries": 2,
        "thinking_token_budget": 8000,
    },
    "medium": {
        "N": 1,
        "use_best_of_n": False,
        "reasoning_model_hint": "kairo-standard",
        "max_retries": 1,
        "thinking_token_budget": 2000,
    },
    "simple": {
        "N": 1,
        "use_best_of_n": False,
        "reasoning_model_hint": "kairo-fast",
        "max_retries": 1,
        "thinking_token_budget": 0,
    },
}

# High-stakes keywords that immediately promote to complex difficulty
_COMPLEX_KEYWORDS = [
    "contract",
    "agreement",
    "indemnification",
    "liability",
    "redline",
    "review",
    "audit",
    "financial",
    "medical",
    "patient",
    "diagnose",
    "legal",
]

# Agents that always warrant complex difficulty
_COMPLEX_AGENTS = {"legal_reviewer", "medical_scribe", "financial_analyst"}


def estimate_difficulty(
    user_prompt: str,
    domain: str,
    waza_agent: str = "general",
    document_length: int = 0,
    document_page_count: int = 0,
) -> str:
    """
    Estimates task difficulty as 'simple', 'medium', or 'complex' based on prompt, domain,
    agent, document character count, and page count.
    """
    p_lower = user_prompt.lower()

    # 1. High-stakes keywords immediately promote to complex
    if any(k in p_lower for k in _COMPLEX_KEYWORDS):
        log.debug("[AdaptiveCompute] Promoted to complex due to high-stakes keyword")
        return "complex"

    # 2. Agent checks
    if waza_agent in _COMPLEX_AGENTS:
        return "complex"

    # 3. Document size checks (character length or page count)
    if document_length > 10000:  # large document (characters)
        log.debug("[AdaptiveCompute] Promoted to complex due to document length")
        return "complex"
    if document_page_count > 5:  # multi-page documents need more reasoning
        log.debug("[AdaptiveCompute] Promoted to complex due to page count")
        return "complex"

    # 4. Simple check
    if len(user_prompt) < 50 and not any(
        k in p_lower for k in ("summary", "explain", "rewrite", "fix")
    ):
        return "simple"

    return "medium"


def get_compute_budget(difficulty: str) -> Dict[str, Any]:
    """
    Returns the compute budget (number of candidates N, model tier hint, thinking token budget, etc.)
    based on difficulty. Always returns a valid budget dict even for unknown difficulty strings.
    """
    return _BUDGET_TABLE.get(difficulty, _BUDGET_TABLE["medium"]).copy()
