import json
import os
from pathlib import Path

REGISTRY_PATH = Path(os.path.expanduser("~")) / ".kairo-phantom" / "domain_registry.json"

DEFAULT_REGISTRY = {
    "Word": "Real",
    "Excel": "Real",
    "PowerPoint": "Real",
    "PDF": "Real",
    "Design": "Real",
    "Email": "Real",
    "Terminal": "Real",
    "Browser": "Real",
}


def load_registry() -> dict[str, str]:
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        save_registry(DEFAULT_REGISTRY)
        return DEFAULT_REGISTRY.copy()
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_REGISTRY.copy()


def save_registry(data: dict[str, str]):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def set_domain_mode(domain: str, mode: str):
    data = load_registry()
    normalized_domain = domain
    for k in data:
        if k.lower() == domain.lower():
            normalized_domain = k
            break
    if mode in ("Real", "PromptOnly"):
        data[normalized_domain] = mode
        save_registry(data)


def get_domain_mode(domain: str) -> str:
    data = load_registry()
    domain_lower = domain.lower()
    for k, v in data.items():
        if k.lower() == domain_lower:
            return v
    return "Real"


def get_prompt_only_domains() -> list[str]:
    """Returns domain names currently registered as PromptOnly (thin expert domains)."""
    data = load_registry()
    return [k for k, v in data.items() if v == "PromptOnly"]


def get_public_domains() -> list[str]:
    """Returns domain names with full Real capability suitable for public marketing endpoints."""
    data = load_registry()
    return [k for k, v in data.items() if v == "Real"]
