"""
E2E conftest — anti-fake-green enforcement.

The e2e suite (test_ask_your_docs_pdf.py, FROZEN) exercises SEMANTIC
retrieval (paraphrase questions with zero lexical overlap). If model2vec is
missing, RetrievalIndex would silently fall back to hash embeddings, and the
paraphrase test would fail confusingly — or worse, a lexical-overlap question
could pass without semantics ever being exercised (latent fake-green).

Setting KAIRO_REQUIRE_SEMANTIC=1 here makes a missing model a HARD, explicit
error at index-build time instead of a silent quality downgrade.

Model weights are VENDORED at:
    kairo-sidecar/assets/models/potion-base-8M/
Loaders resolve that path offline (HF_HUB_OFFLINE=1). No HuggingFace download
is required for e2e — real semantic embeddings, no hash fallback, no network.
"""

import os

# Must be set before kairo.docintel.retrieval initializes its embedding backend.
os.environ["KAIRO_REQUIRE_SEMANTIC"] = "1"
# Product / CI offline-first: never allow huggingface_hub to phone home.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
