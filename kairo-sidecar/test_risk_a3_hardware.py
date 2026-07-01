"""
Risk A3: Hardware Variability (GPU/CPU/RAM).
Test: graceful degradation — no GPU → CPU PIL pipeline works (REAL, not mocked).
"""

import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))


class TestHardwareDegradation:
    """Hardware detection + graceful degradation must work."""

    def test_cpu_fallback_image_processor_works(self):
        """CPU PIL-based ImageProcessor must work without GPU (REAL processing)."""
        from sidecar.parsers.image_processor import ImageProcessor
        from PIL import Image
        import tempfile

        proc = ImageProcessor()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img = Image.new("RGB", (100, 100), color="red")
            img.save(f.name)
            img_path = f.name

        try:
            result = proc.resize(img_path, (50, 50))
            assert result is not None, "CPU image processing returned None"
        finally:
            os.unlink(img_path)

    def test_media_embeddings_raise_without_gpu(self):
        """MediaEmbeddings must raise RuntimeError (not silently succeed) without embed-anything."""
        from sidecar.parsers.media_embeddings import MediaEmbeddings

        with pytest.raises(RuntimeError):
            MediaEmbeddings()

    def test_adaptive_compute_difficulty_estimation(self):
        """estimate_difficulty must return a valid difficulty level."""
        from sidecar.adaptive_compute import estimate_difficulty

        difficulty = estimate_difficulty("write a memo", "word")
        assert difficulty in (
            "simple",
            "medium",
            "complex",
        ), f"Difficulty must be simple/medium/complex, got: {difficulty}"

    def test_adaptive_compute_budget_allocation(self):
        """get_compute_budget must return a valid budget for each difficulty."""
        from sidecar.adaptive_compute import get_compute_budget

        for difficulty in ("simple", "medium", "complex"):
            budget = get_compute_budget(difficulty)
            assert "N" in budget, f"Budget for {difficulty} missing N"
            assert (
                "thinking_token_budget" in budget
            ), f"Budget for {difficulty} missing thinking_token_budget"

    def test_complex_tasks_get_more_compute(self):
        """Complex tasks must get more compute budget than simple tasks."""
        from sidecar.adaptive_compute import estimate_difficulty, get_compute_budget

        simple = get_compute_budget(estimate_difficulty("hi", "word"))
        complex_ = get_compute_budget(
            estimate_difficulty("review this legal contract for liability clauses", "legal")
        )
        assert (
            complex_["thinking_token_budget"] >= simple["thinking_token_budget"]
        ), "Complex task got less compute than simple — degradation broken"
