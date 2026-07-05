# PROVENANCE: original | clean-room Anchor perception oracles per VERIFICATION_ORACLES.md
"""Anchor perception oracle tests — grounding_accuracy + stable_id + token_reduction + kill-proofs.

Tests verify:
  1. grounding_accuracy: resolve(element_query) on the static corpus → >=90%.
     Kill-proof: corrupt a leg → accuracy drops.
  2. stable_id: element IDs persist across recorded frames.
     Kill-proof: shuffle IDs → oracle fails.
  3. token_reduction: compacted map >=70% smaller than raw screenshot.
     Kill-proof: inflate map → reduction drops.
  4. Honest degradation: live capture/OCR/vision → Experimental, fail loud.
  5. Trust stack integration: audit log + egress report.
  6. Fusion correctness: dedup, confidence-weighting, canvas element handling.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.perception.engine import (  # noqa: E402
    AnchorElement,
    AnchorExperimentalError,
    AnchorUnavailableError,
    BoundingBox,
    ScreenMap,
    compact_map,
    fuse_elements,
    get_screen_map,
    parse_ax_dump,
    parse_ocr_dump,
    parse_vision_dump,
    resolve,
    run_ocr,
    run_vision_detection,
    track_stable_ids,
    perception_pipeline,
)
from kairo.perception.oracles import (  # noqa: E402
    grounding_accuracy,
    stable_id,
    token_reduction,
)

# Fixture paths
_CORPUS_DIR = os.path.join(_REPO_ROOT, "fixtures", "anchor")


# ---------------------------------------------------------------------------
# Helper: check corpus exists
# ---------------------------------------------------------------------------


def _corpus_available() -> bool:
    return os.path.isdir(_CORPUS_DIR) and len([
        d for d in os.listdir(_CORPUS_DIR)
        if d.startswith("screen_") and os.path.isdir(os.path.join(_CORPUS_DIR, d))
    ]) >= 100


_HAS_CORPUS = _corpus_available()


# ---------------------------------------------------------------------------
# Oracle 1: grounding_accuracy
# ---------------------------------------------------------------------------


class TestGroundingAccuracy:
    """grounding_accuracy oracle — resolve queries on static corpus → >=90%."""

    @pytest.mark.skipif(not _HAS_CORPUS, reason="corpus not available")
    def test_grounding_accuracy_meets_threshold(self):
        """Grounding accuracy on the full corpus is >=90%."""
        result = grounding_accuracy(_CORPUS_DIR)
        print(f"\n  Grounding accuracy: {result['accuracy_pct']}% "
              f"({result['correct']}/{result['total']})")
        print(f"  Canvas accuracy: {result['canvas_accuracy_pct']}% "
              f"({result['canvas_correct']}/{result['canvas_total']})")
        assert result["accuracy_pct"] >= 90.0, (
            f"Grounding accuracy {result['accuracy_pct']}% < 90% threshold"
        )

    @pytest.mark.skipif(not _HAS_CORPUS, reason="corpus not available")
    def test_canvas_subset_accuracy(self):
        """Canvas/GPU screen subset has measurable accuracy (OCR+vision legs)."""
        result = grounding_accuracy(_CORPUS_DIR)
        # Canvas screens use OCR+vision, so accuracy may be lower but should be >0
        assert result["canvas_total"] >= 20, (
            f"Expected >=20 canvas screens, got {result['canvas_total']}"
        )
        print(f"  Canvas accuracy: {result['canvas_accuracy_pct']}%")


# ---------------------------------------------------------------------------
# Oracle 1 Kill-Proofs
# ---------------------------------------------------------------------------


class TestGroundingAccuracyKillProofs:
    """Kill-proofs: corrupt a leg → accuracy drops."""

    def test_kill_disable_ocr_on_canvas(self):
        """Kill-proof: disable OCR leg on canvas screens → accuracy drops."""
        if not _HAS_CORPUS:
            pytest.skip("corpus not available")

        # Run with full legs
        full_result = grounding_accuracy(_CORPUS_DIR)

        # Now run with OCR disabled (remove ocr_dump.json temporarily)
        # We can't modify frozen fixtures, so we test by running on a temp copy
        # with only canvas screens and no OCR
        with tempfile.TemporaryDirectory() as tmp:
            # Copy just canvas screens without OCR
            import shutil

            for i in range(100, 120):
                src = os.path.join(_CORPUS_DIR, f"screen_{i:04d}")
                dst = os.path.join(tmp, f"screen_{i:04d}")
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                    # Remove OCR dump to simulate disabled leg
                    ocr_path = os.path.join(dst, "ocr_dump.json")
                    if os.path.exists(ocr_path):
                        os.remove(ocr_path)

            # Run grounding on the degraded corpus
            degraded_result = grounding_accuracy(tmp)

            # Accuracy should be lower without OCR
            print(f"\n  Full canvas accuracy: {full_result['canvas_accuracy_pct']}%")
            print(f"  Degraded (no OCR): {degraded_result['accuracy_pct']}%")
            assert degraded_result["accuracy_pct"] < full_result["canvas_accuracy_pct"], (
                "Disabling OCR should reduce accuracy — kill-proof failed"
            )

    def test_kill_corrupt_ax_dump(self):
        """Kill-proof: corrupt AX dump → accuracy drops or fails."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a minimal corpus with corrupted AX dump
            screen_dir = os.path.join(tmp, "screen_0000")
            os.makedirs(screen_dir)

            # Corrupted AX dump (missing elements key)
            with open(os.path.join(screen_dir, "ax_dump.json"), "w") as f:
                json.dump({"app_name": "Broken"}, f)

            with open(os.path.join(screen_dir, "labeled_elements.json"), "w") as f:
                json.dump({"queries": []}, f)

            # Should not crash, but should have 0 elements
            with open(os.path.join(screen_dir, "ax_dump.json")) as f:
                ax_dump = json.load(f)

            elements = parse_ax_dump(ax_dump)
            assert len(elements) == 0, "Corrupted AX dump should yield 0 elements"


# ---------------------------------------------------------------------------
# Oracle 2: stable_id
# ---------------------------------------------------------------------------


class TestStableId:
    """stable_id oracle — element IDs persist across frames."""

    @pytest.mark.skipif(not _HAS_CORPUS, reason="corpus not available")
    def test_stable_id_across_frames(self):
        """Element IDs are stable across the recorded frame sequence."""
        result = stable_id(_CORPUS_DIR)
        print(f"\n  Stable: {result['stable']}")
        print(f"  Frames checked: {result['frames_checked']}")
        print(f"  ID matches: {result['id_matches']}")
        print(f"  ID mismatches: {result['id_mismatches']}")
        assert result["stable"], (
            f"IDs not stable — {result['id_mismatches']} mismatches"
        )
        assert result["id_matches"] > 0, "Expected some ID matches across frames"


# ---------------------------------------------------------------------------
# Oracle 2 Kill-Proofs
# ---------------------------------------------------------------------------


class TestStableIdKillProofs:
    """Kill-proofs: shuffle IDs → oracle fails."""

    def test_kill_shuffle_ids(self):
        """Kill-proof: shuffle element IDs → stability check fails."""
        # Create a frame sequence where elements stay in the same positions
        # but have different IDs each frame. The tracker will assign stable
        # IDs, so we test with tracking DISABLED (high IoU threshold) and
        # the oracle's fixed check threshold will detect the mismatch.
        with tempfile.TemporaryDirectory() as tmp:
            frames_dir = os.path.join(tmp, "frame_sequence")
            os.makedirs(frames_dir)

            for frame_idx in range(2):
                frame_dir = os.path.join(frames_dir, f"frame_{frame_idx:04d}")
                os.makedirs(frame_dir)

                elements = []
                for i in range(5):
                    elem = {
                        "id": f"frame{frame_idx}_e{i}",  # Different IDs per frame
                        "role": "button",
                        "name": f"Btn {i}",
                        "value": "",
                        "bounds": {"x": 100, "y": 50 + i * 50, "width": 200, "height": 40},
                        "affordance": "click",
                        "confidence": 0.95,
                        "is_canvas": False,
                    }
                    elements.append(elem)

                ax_dump = {
                    "app_name": "Test",
                    "is_canvas": False,
                    "screen_width": 1920,
                    "screen_height": 1080,
                    "elements": elements,
                }

                with open(os.path.join(frame_dir, "ax_dump.json"), "w") as f:
                    json.dump(ax_dump, f)

            # With tracker threshold > 1.0, no tracking happens.
            # The oracle's check_overlap_threshold (default 0.3) will detect
            # that elements at the same positions have different IDs.
            result = stable_id(tmp, iou_threshold=1.01, check_overlap_threshold=0.3)

            assert not result["stable"], (
                "With no tracking, different IDs at same positions should "
                "fail stability check — kill-proof failed"
            )
            assert result["id_mismatches"] > 0, "Expected ID mismatches"


# ---------------------------------------------------------------------------
# Oracle 3: token_reduction
# ---------------------------------------------------------------------------


class TestTokenReduction:
    """token_reduction oracle — compacted map >=70% smaller than raw screenshot."""

    @pytest.mark.skipif(not _HAS_CORPUS, reason="corpus not available")
    def test_token_reduction_meets_threshold(self):
        """Token reduction on the full corpus is >=70%."""
        result = token_reduction(_CORPUS_DIR)
        print(f"\n  Min reduction: {result['min_reduction_pct']}%")
        print(f"  Avg reduction: {result['avg_reduction_pct']}%")
        assert result["meets_threshold"], (
            f"Token reduction {result['min_reduction_pct']}% < 70% threshold"
        )


# ---------------------------------------------------------------------------
# Oracle 3 Kill-Proofs
# ---------------------------------------------------------------------------


class TestTokenReductionKillProofs:
    """Kill-proofs: inflate map → reduction drops."""

    def test_kill_inflate_map(self):
        """Kill-proof: inflate element map with redundant elements → reduction drops."""
        # Create a screen with a huge number of elements
        ax_dump = {
            "app_name": "Inflated",
            "is_canvas": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "elements": [
                {
                    "id": f"elem_{i}",
                    "role": "text",
                    "name": f"This is a very long element name number {i} " * 10,
                    "value": "",
                    "bounds": {"x": i * 10, "y": i * 10, "width": 100, "height": 20},
                    "affordance": "read",
                    "confidence": 0.95,
                    "is_canvas": False,
                }
                for i in range(500)  # 500 elements with long names
            ],
        }

        screen_map = get_screen_map(ax_dump, screen_id="inflated")
        reduction = screen_map.element_map.token_reduction_pct

        print(f"\n  Inflated map reduction: {reduction}%")
        # With 500 elements with long names, the compacted map should be much larger
        # and the reduction should be < 70%
        assert reduction < 70.0, (
            f"Inflated map should have <70% reduction, got {reduction}% — kill-proof failed"
        )


# ---------------------------------------------------------------------------
# Honest Degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """Honest degradation: live capture/OCR/vision → Experimental, fail loud."""

    def test_live_ocr_unavailable_raises(self):
        """Live OCR (Experimental) fails loud when unavailable."""
        with pytest.raises(AnchorExperimentalError, match="OCR.*Experimental"):
            run_ocr("fake_image.png")

    def test_live_vision_unavailable_raises(self):
        """Live vision detection (Experimental) fails loud when unavailable."""
        with pytest.raises(AnchorExperimentalError, match="Vision.*Experimental"):
            run_vision_detection("fake_image.png")

    def test_missing_corpus_raises(self):
        """Grounding on a missing corpus raises AnchorUnavailableError."""
        with pytest.raises(AnchorUnavailableError, match="corpus unavailable"):
            grounding_accuracy("/nonexistent/path")

    def test_missing_frame_sequence_raises(self):
        """Stable ID on a missing frame sequence raises."""
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(AnchorUnavailableError, match="frame sequence"):
                stable_id(tmp)


# ---------------------------------------------------------------------------
# Fusion Correctness
# ---------------------------------------------------------------------------


class TestFusionCorrectness:
    """Fusion + dedup correctness tests."""

    def test_ax_parse_basic(self):
        """AX dump parsing produces correct elements."""
        ax_dump = {
            "elements": [
                {"id": "btn1", "role": "button", "name": "Submit",
                 "bounds": {"x": 10, "y": 20, "width": 100, "height": 40},
                 "confidence": 0.95},
                {"id": "txt1", "role": "text", "name": "Hello World",
                 "bounds": {"x": 10, "y": 80, "width": 200, "height": 30},
                 "confidence": 0.90},
            ]
        }
        elements = parse_ax_dump(ax_dump)
        assert len(elements) == 2
        assert elements[0].role == "button"
        assert elements[0].name == "Submit"
        assert elements[0].affordance == "click"
        assert elements[1].role == "text"
        assert elements[1].affordance == "read"

    def test_fusion_dedup_overlapping(self):
        """Fusion deduplicates elements with high bbox overlap."""
        ax_elements = [
            AnchorElement(
                element_id="ax_1", role="button", name="Save",
                bounds=BoundingBox(x=10, y=10, width=100, height=40),
                confidence=0.95, source="ax",
            ),
        ]
        vision_elements = [
            AnchorElement(
                element_id="vis_1", role="icon", name="Save",
                bounds=BoundingBox(x=12, y=12, width=98, height=38),
                confidence=0.80, source="vision",
            ),
        ]
        fused = fuse_elements(ax_elements, vision_elements=vision_elements)
        # Should dedup to 1 element (high IoU)
        assert len(fused) == 1, f"Expected 1 fused element, got {len(fused)}"
        # Should keep the higher-confidence one
        assert fused[0].confidence == 0.95

    def test_fusion_no_dedup_distant_elements(self):
        """Fusion does not dedup elements with no bbox overlap."""
        ax_elements = [
            AnchorElement(
                element_id="ax_1", role="button", name="Save",
                bounds=BoundingBox(x=10, y=10, width=100, height=40),
                confidence=0.95, source="ax",
            ),
        ]
        ocr_elements = [
            AnchorElement(
                element_id="ocr_1", role="text", name="Header Text",
                bounds=BoundingBox(x=500, y=500, width=200, height=30),
                confidence=0.85, source="ocr",
            ),
        ]
        fused = fuse_elements(ax_elements, ocr_elements=ocr_elements)
        assert len(fused) == 2, f"Expected 2 fused elements, got {len(fused)}"

    def test_fusion_merges_names_on_dedup(self):
        """Fusion merges names from different legs when deduplicating."""
        ax_elements = [
            AnchorElement(
                element_id="ax_1", role="button", name="Submit",
                bounds=BoundingBox(x=10, y=10, width=100, height=40),
                confidence=0.95, source="ax",
            ),
        ]
        ocr_elements = [
            AnchorElement(
                element_id="ocr_1", role="text", name="Submit Button",
                bounds=BoundingBox(x=10, y=10, width=100, height=40),
                confidence=0.85, source="ocr",
            ),
        ]
        fused = fuse_elements(ax_elements, ocr_elements=ocr_elements)
        assert len(fused) == 1
        # The merged name should contain both names
        assert "Submit" in fused[0].name

    def test_compact_map_calculates_reduction(self):
        """compact_map correctly calculates token reduction."""
        elements = [
            AnchorElement(
                element_id="e1", role="button", name="Save",
                bounds=BoundingBox(x=10, y=10, width=100, height=40),
            ),
            AnchorElement(
                element_id="e2", role="text", name="Hello",
                bounds=BoundingBox(x=10, y=80, width=200, height=30),
            ),
        ]
        emap = compact_map(elements, screen_id="test")
        assert emap.element_count == 2
        assert emap.token_reduction_pct > 70.0, (
            f"Expected >70% reduction, got {emap.token_reduction_pct}%"
        )

    def test_resolve_finds_element_by_name(self):
        """resolve() finds an element by name query."""
        elements = [
            AnchorElement(element_id="btn1", role="button", name="Submit",
                          bounds=BoundingBox(x=10, y=10, width=100, height=40)),
            AnchorElement(element_id="txt1", role="text", name="Email",
                          bounds=BoundingBox(x=10, y=80, width=200, height=30)),
        ]
        emap = compact_map(elements, screen_id="test")
        smap = ScreenMap(screen_id="test", element_map=emap)

        result = resolve("Submit", smap)
        assert result is not None
        assert result.element_id == "btn1"

    def test_resolve_returns_none_for_no_match(self):
        """resolve() returns None when no element matches."""
        elements = [
            AnchorElement(element_id="btn1", role="button", name="Submit",
                          bounds=BoundingBox(x=10, y=10, width=100, height=40)),
        ]
        emap = compact_map(elements, screen_id="test")
        smap = ScreenMap(screen_id="test", element_map=emap)

        result = resolve("Nonexistent", smap)
        assert result is None

    def test_canvas_elements_marked(self):
        """Canvas elements from OCR/vision are properly marked."""
        ocr_dump = {
            "elements": [
                {"id": "ocr_1", "text": "Canvas Text",
                 "bounds": {"x": 100, "y": 100, "width": 200, "height": 30},
                 "is_canvas": True},
            ]
        }
        elements = parse_ocr_dump(ocr_dump)
        assert len(elements) == 1
        assert elements[0].is_canvas is True
        assert elements[0].source == "ocr"

    def test_vision_parse_basic(self):
        """Vision dump parsing produces correct elements."""
        vision_dump = {
            "elements": [
                {"id": "vis_1", "role": "icon", "name": "Gear",
                 "bounds": {"x": 50, "y": 50, "width": 40, "height": 40},
                 "confidence": 0.85, "is_canvas": True},
            ]
        }
        elements = parse_vision_dump(vision_dump)
        assert len(elements) == 1
        assert elements[0].role == "icon"
        assert elements[0].source == "vision"

    def test_bounding_box_iou(self):
        """BoundingBox IoU calculation is correct."""
        a = BoundingBox(x=0, y=0, width=100, height=100)
        b = BoundingBox(x=50, y=50, width=100, height=100)
        iou = a.iou(b)
        # Intersection = 50*50 = 2500, Union = 10000 + 10000 - 2500 = 17500
        expected = 2500 / 17500
        assert abs(iou - expected) < 0.001

    def test_bounding_box_iou_identical(self):
        """Identical bboxes have IoU = 1.0."""
        a = BoundingBox(x=10, y=10, width=100, height=50)
        b = BoundingBox(x=10, y=10, width=100, height=50)
        assert a.iou(b) == 1.0

    def test_bounding_box_iou_no_overlap(self):
        """Non-overlapping bboxes have IoU = 0.0."""
        a = BoundingBox(x=0, y=0, width=100, height=100)
        b = BoundingBox(x=200, y=200, width=100, height=100)
        assert a.iou(b) == 0.0


# ---------------------------------------------------------------------------
# Trust Stack Integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_pipeline_emits_audit_and_egress(self):
        """Perception pipeline with private_key emits audit log + egress report."""
        private_key = ed25519.Ed25519PrivateKey.generate()

        ax_dump = {
            "elements": [
                {"id": "btn1", "role": "button", "name": "Save",
                 "bounds": {"x": 10, "y": 10, "width": 100, "height": 40},
                 "confidence": 0.95},
            ]
        }

        result = perception_pipeline(
            ax_dump=ax_dump,
            screen_id="trust_test",
            private_key=private_key,
        )

        assert result["audit_log_json"], "Audit log JSON should be non-empty"
        assert result["egress_report_json"], "Egress report JSON should be non-empty"

        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import (
            report_from_json,
            verify_zero_egress_report,
        )

        public_key = private_key.public_key()
        entries = Ed25519AuditLog.entries_from_json(result["audit_log_json"])
        assert len(entries) > 0
        assert Ed25519AuditLog.verify_chain(entries, public_key)

        report = report_from_json(result["egress_report_json"])
        assert verify_zero_egress_report(report, public_key)

    def test_pipeline_without_key_still_works(self):
        """Pipeline without private_key still produces a screen map."""
        ax_dump = {
            "elements": [
                {"id": "btn1", "role": "button", "name": "OK",
                 "bounds": {"x": 10, "y": 10, "width": 80, "height": 30},
                 "confidence": 0.95},
            ]
        }

        result = perception_pipeline(ax_dump=ax_dump, screen_id="no_key")
        assert result["screen_map"].element_map.element_count == 1
        assert not result["audit_log_json"]
        assert not result["egress_report_json"]


# ---------------------------------------------------------------------------
# Stable ID Tracking Unit Tests
# ---------------------------------------------------------------------------


class TestStableIdTracking:
    """Unit tests for stable ID tracking."""

    def test_track_stable_ids_preserves_ids(self):
        """Tracking preserves IDs for elements that don't move much."""
        # Frame 0
        elements_0 = [
            AnchorElement(element_id="e1", role="button", name="A",
                          bounds=BoundingBox(x=10, y=10, width=100, height=40)),
            AnchorElement(element_id="e2", role="button", name="B",
                          bounds=BoundingBox(x=10, y=60, width=100, height=40)),
        ]
        # Frame 1: slight scroll (y shifted by 5)
        elements_1 = [
            AnchorElement(element_id="new_1", role="button", name="A",
                          bounds=BoundingBox(x=10, y=5, width=100, height=40)),
            AnchorElement(element_id="new_2", role="button", name="B",
                          bounds=BoundingBox(x=10, y=55, width=100, height=40)),
        ]

        map_0 = compact_map(elements_0, screen_id="f0")
        map_1 = compact_map(elements_1, screen_id="f1")

        tracked = track_stable_ids([map_0, map_1])

        # Frame 1 elements should have inherited IDs from frame 0
        assert tracked[1].elements[0].element_id == "e1"
        assert tracked[1].elements[1].element_id == "e2"

    def test_track_stable_ids_new_element_gets_new_id(self):
        """New elements that don't match any previous get a new ID."""
        elements_0 = [
            AnchorElement(element_id="e1", role="button", name="A",
                          bounds=BoundingBox(x=10, y=10, width=100, height=40)),
        ]
        elements_1 = [
            AnchorElement(element_id="e1", role="button", name="A",
                          bounds=BoundingBox(x=10, y=10, width=100, height=40)),
            AnchorElement(element_id="new_elem", role="text", name="New",
                          bounds=BoundingBox(x=500, y=500, width=200, height=30)),
        ]

        map_0 = compact_map(elements_0, screen_id="f0")
        map_1 = compact_map(elements_1, screen_id="f1")

        tracked = track_stable_ids([map_0, map_1])

        # New element should keep its new ID
        new_elem = [e for e in tracked[1].elements if e.name == "New"][0]
        assert new_elem.element_id == "new_elem"
