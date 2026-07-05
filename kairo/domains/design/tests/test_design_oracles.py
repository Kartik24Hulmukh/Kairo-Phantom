# PROVENANCE: original | Design/media domain oracle tests per VERIFICATION_ORACLES.md
"""Design/media domain oracle tests — canvas_readback + structure_readback + kill-proofs.

Tests verify:
  1. canvas_readback: after creating an SVG, re-parse and assert shapes/text/
     positions/sizes/z-order match spec. Kill-proof: move/drop/alter → FAILS.
  2. structure_readback: element count + z-order + types survive round-trip.
     Kill-proof: drop an element → FAILS.
  3. Honest degradation: engine/lib missing → fail loud; live Figma/vision
     requested but unavailable → fail loud (Experimental).
  4. >=3 gauntlet scenarios: (a) multi-shape diagram, (b) text+shape layout,
     (c) edit existing canvas — each read-back verified.
  5. Trust stack integration: audit log + egress report.
  6. CLI integration: design subcommand works end-to-end.

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
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.domains.design.engine import (  # noqa: E402
    DesignError,
    DesignExperimentalError,
    create_canvas,
    design_pipeline,
    edit_canvas,
    live_figma_export,
    live_vision_detect,
    read_canvas,
    save_canvas,
)
from kairo.domains.design.oracles import (  # noqa: E402
    canvas_readback,
    structure_readback,
)

# Fixture paths
_FIX = os.path.join(_REPO_ROOT, "kairo", "domains", "design", "fixtures")
_SPEC_JSON = os.path.join(_FIX, "canvas_spec.json")
_GT_JSON = os.path.join(_FIX, "ground_truth.json")


# ---------------------------------------------------------------------------
# Helper: create a canvas from a spec and save to temp file
# ---------------------------------------------------------------------------


def _create_canvas_from_spec(spec: dict, tmpdir: str, filename: str = "test.svg") -> str:
    """Create an SVG from a spec dict and return the saved path."""
    svg_content = create_canvas(spec)
    out_path = os.path.join(tmpdir, filename)
    return save_canvas(svg_content, out_path)


def _load_ground_truth() -> dict:
    with open(_GT_JSON, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Oracle 1: canvas_readback
# ---------------------------------------------------------------------------


class TestCanvasReadback:
    """canvas_readback oracle — create, save, re-parse, verify all fields."""

    def test_basic_shapes_readback(self):
        """Create a canvas with basic shapes, re-parse, verify all match."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 800,
                "height": 600,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "20", "width": "100", "height": "50", "fill": "#FF0000"}},
                    {"type": "ellipse", "id": "e1", "attrs": {"cx": "200", "cy": "100", "rx": "40", "ry": "30", "fill": "#00FF00"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            expected = [
                {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "20", "width": "100", "height": "50", "fill": "#FF0000"}, "z_order": 0},
                {"type": "ellipse", "id": "e1", "attrs": {"cx": "200", "cy": "100", "rx": "40", "ry": "30", "fill": "#00FF00"}, "z_order": 1},
            ]
            result = canvas_readback(path, expected, expected_width=800, expected_height=600)
            assert result is True

    def test_text_element_readback(self):
        """Text element content is correctly read back."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "text", "id": "t1", "attrs": {"x": "10", "y": "20", "font-size": "16"}, "text": "Hello World"},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            expected = [
                {"type": "text", "id": "t1", "attrs": {"x": "10", "y": "20", "font-size": "16"}, "text": "Hello World", "z_order": 0},
            ]
            result = canvas_readback(path, expected, expected_width=400, expected_height=300)
            assert result is True

    def test_line_element_readback(self):
        """Line element with x1/y1/x2/y2 is correctly read back."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 500,
                "height": 400,
                "elements": [
                    {"type": "line", "id": "l1", "attrs": {"x1": "0", "y1": "0", "x2": "100", "y2": "200", "stroke": "#333", "stroke-width": "2"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            expected = [
                {"type": "line", "id": "l1", "attrs": {"x1": "0", "y1": "0", "x2": "100", "y2": "200", "stroke": "#333", "stroke-width": "2"}, "z_order": 0},
            ]
            result = canvas_readback(path, expected)
            assert result is True

    def test_z_order_readback(self):
        """Z-order (document order) is correctly read back."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 300,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "bottom", "attrs": {"x": "0", "y": "0", "width": "100", "height": "100"}},
                    {"type": "rect", "id": "middle", "attrs": {"x": "50", "y": "50", "width": "100", "height": "100"}},
                    {"type": "rect", "id": "top", "attrs": {"x": "100", "y": "100", "width": "100", "height": "100"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            expected = [
                {"type": "rect", "id": "bottom", "z_order": 0},
                {"type": "rect", "id": "middle", "z_order": 1},
                {"type": "rect", "id": "top", "z_order": 2},
            ]
            result = canvas_readback(path, expected)
            assert result is True

    def test_circle_element_readback(self):
        """Circle element with cx/cy/r is correctly read back."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 400,
                "elements": [
                    {"type": "circle", "id": "c1", "attrs": {"cx": "200", "cy": "200", "r": "50", "fill": "#5CB85C"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            expected = [
                {"type": "circle", "id": "c1", "attrs": {"cx": "200", "cy": "200", "r": "50", "fill": "#5CB85C"}, "z_order": 0},
            ]
            result = canvas_readback(path, expected)
            assert result is True


# ---------------------------------------------------------------------------
# Oracle 1 Kill-Proofs
# ---------------------------------------------------------------------------


class TestCanvasReadbackKillProofs:
    """Kill-proofs: perturbing the canvas → FAILS."""

    def test_kill_altered_position(self):
        """Kill-proof: alter expected position → readback FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "100", "y": "100", "width": "50", "height": "50"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            wrong_expected = [
                {"type": "rect", "id": "r1", "attrs": {"x": "999", "y": "100", "width": "50", "height": "50"}},
            ]
            with pytest.raises(AssertionError, match="attribute 'x' mismatch"):
                canvas_readback(path, wrong_expected)

    def test_kill_dropped_element(self):
        """Kill-proof: expect fewer elements than exist → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
                    {"type": "rect", "id": "r2", "attrs": {"x": "100", "y": "100", "width": "50", "height": "50"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            wrong_expected = [
                {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
            ]
            with pytest.raises(AssertionError, match="element count mismatch"):
                canvas_readback(path, wrong_expected)

    def test_kill_wrong_type(self):
        """Kill-proof: wrong element type → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            wrong_expected = [
                {"type": "circle", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
            ]
            with pytest.raises(AssertionError, match="type mismatch"):
                canvas_readback(path, wrong_expected)

    def test_kill_altered_text(self):
        """Kill-proof: altered text content → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "text", "id": "t1", "attrs": {"x": "10", "y": "20"}, "text": "Original"},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            wrong_expected = [
                {"type": "text", "id": "t1", "attrs": {"x": "10", "y": "20"}, "text": "TAMPERED"},
            ]
            with pytest.raises(AssertionError, match="text content mismatch"):
                canvas_readback(path, wrong_expected)


# ---------------------------------------------------------------------------
# Oracle 2: structure_readback
# ---------------------------------------------------------------------------


class TestStructureReadback:
    """structure_readback oracle — element count + z-order + types survive round-trip."""

    def test_basic_structure(self):
        """Basic canvas structure survives round-trip."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 800,
                "height": 600,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "100", "height": "50"}},
                    {"type": "ellipse", "id": "e1", "attrs": {"cx": "200", "cy": "100", "rx": "40", "ry": "30"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            result = structure_readback(
                path,
                expected_element_count=2,
                expected_types=["rect", "ellipse"],
                expected_ids=["r1", "e1"],
                expected_z_orders=[0, 1],
                expected_width=800,
                expected_height=600,
            )
            assert result is True

    def test_z_order_structure(self):
        """Z-order is preserved through round-trip."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 400,
                "elements": [
                    {"type": "rect", "id": "a", "attrs": {"x": "0", "y": "0", "width": "10", "height": "10"}},
                    {"type": "rect", "id": "b", "attrs": {"x": "0", "y": "0", "width": "10", "height": "10"}},
                    {"type": "rect", "id": "c", "attrs": {"x": "0", "y": "0", "width": "10", "height": "10"}},
                    {"type": "rect", "id": "d", "attrs": {"x": "0", "y": "0", "width": "10", "height": "10"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            result = structure_readback(
                path,
                expected_element_count=4,
                expected_z_orders=[0, 1, 2, 3],
            )
            assert result is True


# ---------------------------------------------------------------------------
# Oracle 2 Kill-Proofs
# ---------------------------------------------------------------------------


class TestStructureKillProofs:
    """Kill-proofs: wrong structure → FAILS."""

    def test_kill_wrong_element_count(self):
        """Kill-proof: wrong element count → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            with pytest.raises(AssertionError, match="element count mismatch"):
                structure_readback(path, expected_element_count=5)

    def test_kill_wrong_types(self):
        """Kill-proof: wrong element types → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
                    {"type": "ellipse", "id": "e1", "attrs": {"cx": "200", "cy": "100", "rx": "40", "ry": "30"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            with pytest.raises(AssertionError, match="element types mismatch"):
                structure_readback(
                    path,
                    expected_element_count=2,
                    expected_types=["circle", "line"],
                )

    def test_kill_wrong_ids(self):
        """Kill-proof: wrong element IDs → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "correct_id", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
                ],
            }
            path = _create_canvas_from_spec(spec, tmp)

            with pytest.raises(AssertionError, match="element IDs mismatch"):
                structure_readback(
                    path,
                    expected_element_count=1,
                    expected_ids=["wrong_id"],
                )


# ---------------------------------------------------------------------------
# Honest Degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """Honest degradation: live Figma/vision → Experimental, fail loud."""

    def test_live_figma_unavailable_raises(self):
        """Live Figma export (Experimental) fails loud when unavailable."""
        with pytest.raises(DesignExperimentalError, match="Figma.*Experimental"):
            live_figma_export("fake_key")

    def test_live_vision_unavailable_raises(self):
        """Live vision detection (Experimental) fails loud when unavailable."""
        with pytest.raises(DesignExperimentalError, match="vision.*Experimental"):
            live_vision_detect("fake_image.png")

    def test_missing_file_raises(self):
        """Reading a non-existent file raises DesignError."""
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = os.path.join(tmp, "nonexistent.svg")
            with pytest.raises(DesignError, match="SVG file not found"):
                read_canvas(bad_path)

    def test_empty_spec_raises(self):
        """Creating from an empty spec raises DesignError."""
        with pytest.raises(DesignError, match="at least one element"):
            create_canvas({"elements": []})


# ---------------------------------------------------------------------------
# Gauntlet Scenarios (>=3 end-to-end)
# ---------------------------------------------------------------------------


class TestGauntletScenarios:
    """>=3 end-to-end gauntlet scenarios."""

    def test_scenario_a_multi_shape_diagram(self):
        """Scenario (a): multi-shape diagram with rect+ellipse+line+circle."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["a_multi_shape_diagram"]

        with tempfile.TemporaryDirectory() as tmp:
            path = _create_canvas_from_spec(sc["spec"], tmp, "scenario_a.svg")

            # Verify structure
            struct_result = structure_readback(
                path,
                expected_element_count=sc["expected_element_count"],
                expected_types=sc["expected_types"],
                expected_ids=sc["expected_ids"],
                expected_z_orders=sc["expected_z_orders"],
                expected_width=sc["spec"]["width"],
                expected_height=sc["spec"]["height"],
            )
            assert struct_result is True

            # Verify content via read-back
            canvas_info = read_canvas(path)
            assert canvas_info.element_count == 4

            # Check specific attributes
            box1 = canvas_info.elements[0]
            assert box1.element_type == "rect"
            assert box1.attributes["x"] == "100"
            assert box1.attributes["fill"] == "#4A90D9"

    def test_scenario_b_text_shape_layout(self):
        """Scenario (b): text + shape layout."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["b_text_shape_layout"]

        with tempfile.TemporaryDirectory() as tmp:
            path = _create_canvas_from_spec(sc["spec"], tmp, "scenario_b.svg")

            # Verify structure
            struct_result = structure_readback(
                path,
                expected_element_count=sc["expected_element_count"],
                expected_types=sc["expected_types"],
                expected_width=sc["spec"]["width"],
                expected_height=sc["spec"]["height"],
            )
            assert struct_result is True

            # Verify text content
            canvas_info = read_canvas(path)
            heading = canvas_info.elements[0]
            assert heading.element_type == "text"
            assert heading.text_content == "Flow Diagram"

            step1_label = canvas_info.elements[2]
            assert step1_label.text_content == "Input"

    def test_scenario_c_edit_existing(self):
        """Scenario (c): edit an existing canvas (move + restyle)."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["c_edit_existing"]

        with tempfile.TemporaryDirectory() as tmp:
            # Create initial canvas
            path = _create_canvas_from_spec(sc["initial_spec"], tmp, "scenario_c.svg")

            # Verify initial state
            canvas_info = read_canvas(path)
            assert canvas_info.elements[0].attributes["x"] == "100"
            assert canvas_info.elements[0].attributes["fill"] == "#FF0000"

            # Apply edits
            edited_svg = edit_canvas(path, sc["edits"])
            edited_path = save_canvas(edited_svg, os.path.join(tmp, "edited.svg"))

            # Verify edited state
            edited_info = read_canvas(edited_path)
            assert edited_info.element_count == 2

            shape1 = edited_info.elements[0]
            assert shape1.element_id == "shape1"
            assert shape1.attributes["x"] == "200"
            assert shape1.attributes["y"] == "150"
            assert shape1.attributes["fill"] == "#0000FF"

            # shape2 should be unchanged
            shape2 = edited_info.elements[1]
            assert shape2.element_id == "shape2"
            assert shape2.attributes["x"] == "400"
            assert shape2.attributes["fill"] == "#00FF00"

    def test_full_spec_from_fixture(self):
        """Create from the full canvas_spec.json fixture and verify."""
        with open(_SPEC_JSON, encoding="utf-8") as f:
            spec = json.load(f)

        with tempfile.TemporaryDirectory() as tmp:
            path = _create_canvas_from_spec(spec, tmp, "full_spec.svg")

            canvas_info = read_canvas(path)
            assert canvas_info.element_count == 5
            assert canvas_info.width == 800
            assert canvas_info.height == 600

            # Check title text
            title = canvas_info.elements[3]
            assert title.element_type == "text"
            assert title.text_content == "Architecture Diagram"


# ---------------------------------------------------------------------------
# Trust Stack Integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_pipeline_emits_audit_and_egress(self):
        """Pipeline with private_key emits audit log + egress report."""
        private_key = ed25519.Ed25519PrivateKey.generate()

        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
                ],
            }
            out_path = os.path.join(tmp, "audit_test.svg")
            result = design_pipeline(
                spec=spec,
                output_path=out_path,
                private_key=private_key,
            )
            assert result.ok
            assert result.audit_log_json, "Audit log JSON should be non-empty"
            assert result.egress_report_json, "Egress report JSON should be non-empty"

            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
            from kairo.oracles.zero_egress_report import (
                report_from_json,
                verify_zero_egress_report,
            )

            public_key = private_key.public_key()
            entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
            assert len(entries) > 0
            assert Ed25519AuditLog.verify_chain(entries, public_key)

            report = report_from_json(result.egress_report_json)
            assert verify_zero_egress_report(report, public_key)

    def test_pipeline_without_key_still_works(self):
        """Pipeline without private_key still creates and reads back canvas."""
        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "width": 400,
                "height": 300,
                "elements": [
                    {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "50", "height": "50"}},
                ],
            }
            out_path = os.path.join(tmp, "no_key.svg")
            result = design_pipeline(spec=spec, output_path=out_path)
            assert result.ok
            assert result.canvas_info is not None
            assert result.canvas_info.element_count == 1
            assert not result.audit_log_json
            assert not result.egress_report_json


# ---------------------------------------------------------------------------
# CLI Integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """design CLI subcommand works end-to-end via registry."""

    def test_cli_create(self):
        """`kairo design create` creates an SVG from a spec file."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "design_output")

            spec_path = os.path.join(tmp, "spec.json")
            with open(spec_path, "w") as f:
                json.dump({
                    "width": 400,
                    "height": 300,
                    "elements": [
                        {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "100", "height": "50"}},
                    ]
                }, f)

            rc = main([
                "design", "create", spec_path,
                "--out", "cli_test.svg",
                "--outdir", out_dir,
            ])
            assert rc == 0, f"CLI create failed with exit code {rc}"

            # Verify the SVG was created
            svg_path = os.path.join(out_dir, "cli_test.svg")
            assert os.path.exists(svg_path)
            canvas_info = read_canvas(svg_path)
            assert canvas_info.element_count == 1

    def test_cli_inspect(self):
        """`kairo design inspect` reads back and displays SVG structure."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "design_output")

            # First create a canvas
            spec_path = os.path.join(tmp, "spec.json")
            with open(spec_path, "w") as f:
                json.dump({
                    "width": 400,
                    "height": 300,
                    "elements": [
                        {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "100", "height": "50"}},
                    ]
                }, f)

            rc = main(["design", "create", spec_path, "--outdir", out_dir])
            assert rc == 0

            # Now inspect
            svg_path = os.path.join(out_dir, "canvas_output.svg")
            rc = main(["design", "inspect", svg_path, "--outdir", out_dir])
            assert rc == 0, f"CLI inspect failed with exit code {rc}"

    def test_cli_edit(self):
        """`kairo design edit` applies edits to an existing SVG."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "design_output")

            # Create initial canvas
            spec_path = os.path.join(tmp, "spec.json")
            with open(spec_path, "w") as f:
                json.dump({
                    "width": 400,
                    "height": 300,
                    "elements": [
                        {"type": "rect", "id": "r1", "attrs": {"x": "10", "y": "10", "width": "100", "height": "50", "fill": "#FF0000"}},
                    ]
                }, f)

            rc = main(["design", "create", spec_path, "--outdir", out_dir])
            assert rc == 0

            # Create edits file
            edits_path = os.path.join(tmp, "edits.json")
            with open(edits_path, "w") as f:
                json.dump([
                    {"op": "move", "id": "r1", "attrs": {"x": "200", "y": "150"}},
                    {"op": "restyle", "id": "r1", "attrs": {"fill": "#0000FF"}}
                ], f)

            svg_path = os.path.join(out_dir, "canvas_output.svg")
            rc = main(["design", "edit", svg_path, edits_path, "--outdir", out_dir])
            assert rc == 0, f"CLI edit failed with exit code {rc}"

            # Verify the edit
            edited_path = os.path.join(out_dir, "edited_canvas.svg")
            canvas_info = read_canvas(edited_path)
            assert canvas_info.elements[0].attributes["x"] == "200"
            assert canvas_info.elements[0].attributes["fill"] == "#0000FF"
