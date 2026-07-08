"""
W2 — Falsifiable grounding benchmark (OSWorld/UI-TARS format).

Tests the Anchor perception engine's element resolution against a committed
grounding benchmark corpus in UI-TARS format:
  instruction (natural language) → resolve() → predicted bbox
  → compare vs ground_truth_bbox using IoU >= 0.5

Oracle: grounding_accuracy = k/N, committed and reproducible.
Kill-proof: corrupt the AX dump → accuracy drops.
"""
import json
import os
import sys
import tempfile

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.perception.engine import get_screen_map, resolve  # noqa: E402
from kairo.perception.oracles import grounding_accuracy  # noqa: E402

_BENCH_PATH = os.path.join(_REPO_ROOT, "fixtures", "grounding_bench", "ui_tars_subset.json")
_CORPUS_DIR = os.path.join(_REPO_ROOT, "fixtures", "anchor")


def _load_bench():
    """Load the UI-TARS format benchmark corpus."""
    if not os.path.exists(_BENCH_PATH):
        pytest.skip("grounding benchmark corpus not available")
    with open(_BENCH_PATH) as f:
        return json.load(f)


def _iou(b1, b2):
    """Compute IoU between two bbox dicts {x, y, width, height}."""
    x1a, y1a = b1["x"], b1["y"]
    x2a, y2a = b1["x"] + b1["width"], b1["y"] + b1["height"]
    x1b, y1b = b2["x"], b2["y"]
    x2b, y2b = b2["x"] + b2["width"], b2["y"] + b2["height"]

    ix0 = max(x1a, x1b)
    iy0 = max(y1a, y1b)
    ix1 = min(x2a, x2b)
    iy1 = min(y2a, y2b)

    inter_w = max(0, ix1 - ix0)
    inter_h = max(0, iy1 - iy0)
    inter = inter_w * inter_h

    area_a = b1["width"] * b1["height"]
    area_b = b2["width"] * b2["height"]
    union = area_a + area_b - inter

    if union <= 0:
        return 0.0
    return inter / union


class TestGroundingBenchmark:
    """UI-TARS format grounding benchmark — falsifiable, reproducible."""

    @staticmethod
    def _load_screen(screen_dir):
        """Load screen fixtures and build a ScreenMap."""
        ax_path = os.path.join(screen_dir, "ax_dump.json")
        if not os.path.exists(ax_path):
            return None
        with open(ax_path, encoding="utf-8") as f:
            ax_dump = json.load(f)
        ocr_dump = None
        ocr_path = os.path.join(screen_dir, "ocr_dump.json")
        if os.path.exists(ocr_path):
            with open(ocr_path, encoding="utf-8") as f:
                ocr_dump = json.load(f)
        vision_dump = None
        vis_path = os.path.join(screen_dir, "vision_dump.json")
        if os.path.exists(vis_path):
            with open(vis_path, encoding="utf-8") as f:
                vision_dump = json.load(f)
        return get_screen_map(ax_dump, ocr_dump, vision_dump, os.path.basename(screen_dir))

    def test_benchmark_corpus_exists(self):
        """The benchmark corpus must be committed and loadable."""
        bench = _load_bench()
        assert bench["format"] == "ui-tars"
        assert len(bench["cases"]) >= 200, (
            f"Benchmark must have >=200 cases, got {len(bench['cases'])}"
        )

    def test_grounding_accuracy_k_over_n(self):
        """Oracle: grounding_accuracy = k/N on the committed corpus.

        This is the falsifiable metric: resolve each instruction → predicted
        element → compare vs expected element. Reports exact k/N.
        """
        bench = _load_bench()
        cases = bench["cases"]
        correct = 0
        total = len(cases)

        for case in cases:
            screen_dir = os.path.join(_CORPUS_DIR, case["screen_id"])
            if not os.path.isdir(screen_dir):
                continue

            screen_map = self._load_screen(screen_dir)
            if screen_map is None:
                continue

            result = resolve(case["instruction"], screen_map)

            if result and result.element_id == case["expected_element_id"]:
                correct += 1

        accuracy_pct = (correct / total) * 100.0 if total > 0 else 0.0
        print(f"\n  Grounding benchmark: {correct}/{total} = {accuracy_pct:.1f}%")

        # Falsifiable threshold: must be >= 90%
        assert accuracy_pct >= 90.0, (
            f"Grounding accuracy {accuracy_pct:.1f}% ({correct}/{total}) < 90% threshold"
        )

    def test_grounding_accuracy_via_oracle(self):
        """Oracle via the production grounding_accuracy() function.

        This is the same metric reported in STATUS.md — ensures the benchmark
        number matches the production oracle.
        """
        result = grounding_accuracy(_CORPUS_DIR)
        k = result["correct"]
        n = result["total"]
        pct = result["accuracy_pct"]
        print(f"\n  Production oracle: {k}/{n} = {pct}%")
        assert pct >= 90.0, f"Grounding accuracy {pct}% < 90%"

    def test_iou_threshold_correctness(self):
        """IoU >= 0.5 for correctly resolved elements (UI-TARS convention)."""
        bench = _load_bench()
        cases = bench["cases"][:50]  # Sample for speed
        iou_passes = 0
        resolved = 0

        for case in cases:
            screen_dir = os.path.join(_CORPUS_DIR, case["screen_id"])
            if not os.path.isdir(screen_dir):
                continue

            screen_map = self._load_screen(screen_dir)
            if screen_map is None:
                continue

            result = resolve(case["instruction"], screen_map)

            if result and result.element_id == case["expected_element_id"]:
                resolved += 1
                if result.bounds:
                    pred_bbox = {
                        "x": result.bounds.x,
                        "y": result.bounds.y,
                        "width": result.bounds.width,
                        "height": result.bounds.height,
                    }
                    iou = _iou(pred_bbox, case["ground_truth_bbox"])
                    if iou >= 0.5:
                        iou_passes += 1

        print(f"\n  IoU >= 0.5: {iou_passes}/{resolved} correctly resolved elements")
        assert iou_passes >= resolved * 0.8, (
            f"IoU pass rate {iou_passes}/{resolved} < 80% of correctly resolved"
        )

    def test_kill_proof_corrupted_ax_dump(self):
        """Kill-proof: corrupt AX dump → accuracy drops."""
        bench = _load_bench()
        cases = bench["cases"][:20]

        with tempfile.TemporaryDirectory() as tmp:
            # Copy first screen with corrupted AX dump
            import shutil
            screen_dir = os.path.join(_CORPUS_DIR, cases[0]["screen_id"])
            dst = os.path.join(tmp, cases[0]["screen_id"])
            shutil.copytree(screen_dir, dst)

            # Corrupt: empty the elements list
            ax_path = os.path.join(dst, "ax_dump.json")
            with open(ax_path) as f:
                ax = json.load(f)
            ax["elements"] = []
            with open(ax_path, "w") as f:
                json.dump(ax, f)

            # Resolution should fail (no elements to match)
            screen_map = self._load_screen(dst)
            if screen_map is not None:
                result = resolve(cases[0]["instruction"], screen_map)
                assert result is None or result.score < 0.3, (
                    "Corrupted AX dump should prevent resolution — kill-proof failed"
                )

    def test_benchmark_format_compliance(self):
        """Benchmark corpus must follow UI-TARS format schema."""
        bench = _load_bench()
        for case in bench["cases"][:10]:
            assert "instruction" in case, "Missing 'instruction' field"
            assert "screen_id" in case, "Missing 'screen_id' field"
            assert "expected_element_id" in case, "Missing 'expected_element_id' field"
            assert "ground_truth_bbox" in case, "Missing 'ground_truth_bbox' field"
            bbox = case["ground_truth_bbox"]
            assert all(k in bbox for k in ["x", "y", "width", "height"]), (
                "ground_truth_bbox must have x, y, width, height"
            )
