"""Resolve vendored offline model paths for Kairo Python embeddings.

Product is offline-first: model weights are committed under
``kairo-sidecar/assets/models/`` and must load with no network.
"""

from __future__ import annotations

import os
from pathlib import Path

# HuggingFace model id this vendor tree corresponds to.
POTION_BASE_8M_HF_ID = "minishlab/potion-base-8M"
POTION_BASE_8M_DIRNAME = "potion-base-8M"


def _candidate_potion_dirs() -> list[Path]:
    """Ordered candidate directories for the vendored potion-base-8M model."""
    candidates: list[Path] = []

    env = os.environ.get("KAIRO_MODEL2VEC_PATH")
    if env:
        candidates.append(Path(env).expanduser())

    here = Path(__file__).resolve()
    # kairo-sidecar/sidecar/model_paths.py -> kairo-sidecar/assets/models/...
    candidates.append(here.parents[1] / "assets" / "models" / POTION_BASE_8M_DIRNAME)
    # Repo-root assets/ (alternate layout)
    # .../Kairo-Phantom/kairo-sidecar/sidecar -> parents[2] is repo root
    if len(here.parents) >= 3:
        candidates.append(here.parents[2] / "assets" / "models" / POTION_BASE_8M_DIRNAME)
        candidates.append(
            here.parents[2] / "kairo-sidecar" / "assets" / "models" / POTION_BASE_8M_DIRNAME
        )

    # CWD-relative (tests / CI often run from repo root or kairo-sidecar/)
    cwd = Path.cwd()
    candidates.append(cwd / "kairo-sidecar" / "assets" / "models" / POTION_BASE_8M_DIRNAME)
    candidates.append(cwd / "assets" / "models" / POTION_BASE_8M_DIRNAME)
    candidates.append(cwd / "sidecar" / ".." / "assets" / "models" / POTION_BASE_8M_DIRNAME)

    # De-dupe while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for p in candidates:
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def resolve_potion_base_8m_path() -> Path:
    """Return the local directory of the vendored potion-base-8M model.

    Raises:
        FileNotFoundError: if no candidate directory contains model weights.
    """
    required = ("model.safetensors", "config.json", "tokenizer.json")
    tried: list[str] = []
    for cand in _candidate_potion_dirs():
        tried.append(str(cand))
        if not cand.is_dir():
            continue
        if all((cand / name).is_file() for name in required):
            return cand.resolve()

    raise FileNotFoundError(
        "Vendored model2vec potion-base-8M not found. Expected files "
        f"{required} under one of: {tried}. "
        "Set KAIRO_MODEL2VEC_PATH to the model directory if relocated."
    )


def load_potion_base_8m_static_model():
    """Load model2vec StaticModel from the vendored local path (no network).

    Forces HF offline env vars for the duration of the load so huggingface_hub
    cannot phone home even if a code path tries.
    """
    from model2vec import StaticModel

    model_dir = resolve_potion_base_8m_path()

    # Belt-and-suspenders offline: mirror the Rust embedding path.
    prev_hf = os.environ.get("HF_HUB_OFFLINE")
    prev_tr = os.environ.get("TRANSFORMERS_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        return StaticModel.from_pretrained(str(model_dir), force_download=False)
    finally:
        # Restore prior values only if we overwrote something that was unset
        # differently — keep offline sticky once set (product default).
        if prev_hf is not None:
            os.environ["HF_HUB_OFFLINE"] = prev_hf
        else:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        if prev_tr is not None:
            os.environ["TRANSFORMERS_OFFLINE"] = prev_tr
        else:
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
