"""
E2E conftest — anti-fake-green enforcement.

The e2e suite (test_ask_your_docs_pdf.py, FROZEN) exercises SEMANTIC
retrieval (paraphrase questions with zero lexical overlap). If model2vec is
missing, RetrievalIndex would silently fall back to hash embeddings, and the
paraphrase test would fail confusingly — or worse, a lexical-overlap question
could pass without semantics ever being exercised (latent fake-green).

Setting KAIRO_REQUIRE_SEMANTIC=1 here makes a missing model a HARD, explicit
error at index-build time instead of a silent quality downgrade.

To cache the model (one-time, network required):
    python -c "from model2vec import StaticModel; \
               StaticModel.from_pretrained('minishlab/potion-base-8M')"
"""

import os

# Must be set before kairo.docintel.retrieval initializes its embedding backend.
os.environ["KAIRO_REQUIRE_SEMANTIC"] = "1"
