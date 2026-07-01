"""
LangfuseEval — Evaluation scaffold using Langfuse datasets (Domain 10)

If langfuse is not installed, the class raises RuntimeError on init — NEVER
silently falls back to a mock. The caller must handle the absence explicitly.

This module provides:
  - create_dataset(name) → dataset_id
  - add_dataset_item(dataset_id, input, expected) → item_id
  - run_eval(dataset_id, recall_fn) → evaluation results dict
"""

from __future__ import annotations

import logging
from typing import Dict, List, Callable

log = logging.getLogger("kairo-sidecar.langfuse_eval")

# ── Detect langfuse availability ──
try:
    from langfuse import Langfuse as _Langfuse

    HAS_LANGFUSE = True
except ImportError:
    HAS_LANGFUSE = False
    _Langfuse = None


class LangfuseEval:
    """
    Langfuse evaluation scaffold for memory recall quality testing.

    Requires langfuse to be installed and configured (LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY environment variables).
    """

    def __init__(self):
        if not HAS_LANGFUSE:
            raise RuntimeError("langfuse not installed. pip install langfuse")
        self.client = _Langfuse()

    def create_dataset(self, name: str) -> str:
        """
        Create a new evaluation dataset.

        Returns the dataset ID.
        """
        dataset = self.client.create_dataset(name=name)
        return dataset.id if hasattr(dataset, "id") else str(dataset)

    def add_dataset_item(
        self,
        dataset_id: str,
        input: str,
        expected: str,
    ) -> str:
        """
        Add an item to an existing dataset.

        Returns the item ID.
        """
        item = self.client.create_dataset_item(
            dataset_id=dataset_id,
            input=input,
            expected_output=expected,
        )
        return item.id if hasattr(item, "id") else str(item)

    def run_eval(
        self,
        dataset_id: str,
        recall_fn: Callable[[str], List[Dict]],
    ) -> Dict:
        """
        Run evaluation against a dataset.

        Args:
            dataset_id: The dataset to evaluate against
            recall_fn: A function that takes a query string and returns
                       a list of memory dicts (with at least a 'memory' or
                       'text' key)

        Returns:
            Dict with:
              - total: number of items evaluated
              - passed: number of items where expected output was found
              - failed: number of items where expected output was NOT found
              - results: list of per-item results
        """
        # Fetch dataset items
        dataset_items = self.client.get_dataset_items(dataset_id=dataset_id)

        results = []
        passed = 0
        failed = 0

        for item in dataset_items:
            input_text = item.input if hasattr(item, "input") else item.get("input", "")
            expected = (
                item.expected_output
                if hasattr(item, "expected_output")
                else item.get("expected_output", "")
            )

            # Run recall function
            recalled = recall_fn(input_text)

            # Check if expected output appears in any recalled memory
            recalled_texts = []
            for mem in recalled:
                text = mem.get("memory", mem.get("text", mem.get("content", "")))
                recalled_texts.append(text)

            is_pass = any(expected.lower() in text.lower() for text in recalled_texts if text)

            if is_pass:
                passed += 1
            else:
                failed += 1

            results.append(
                {
                    "input": input_text,
                    "expected": expected,
                    "recalled_count": len(recalled),
                    "passed": is_pass,
                }
            )

        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "results": results,
        }
