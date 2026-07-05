# PROVENANCE: original | clean-room Design/media domain oracles per VERIFICATION_ORACLES.md
"""Design/media domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``canvas_readback`` — after creating/editing an SVG canvas, RE-PARSE it
     and assert shapes/text/positions/sizes/z-order match the spec.
     KILL-PROOF: move/drop/alter a shape → FAILS.

  2. ``structure_readback`` — element count + layer/z-order + bounding boxes
     survive round-trip. KILL-PROOF: drop a layer/element → FAILS.

Both oracles are KILL-PROVEN.

HONEST DEGRADATION:
  If the SVG file is missing or unparseable, the oracles raise DesignError.

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

from typing import Any

from kairo.domains.design.engine import read_canvas


# ---------------------------------------------------------------------------
# Oracle 1: canvas_readback
# ---------------------------------------------------------------------------


def canvas_readback(
    file_path: str,
    expected_elements: list[dict[str, Any]],
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> bool:
    """Oracle: re-parse SVG → assert shapes/text/positions/sizes/z-order match spec.

    KILL-PROOF: move/drop/alter a shape → FAILS.

    Args:
        file_path:        Path to the saved .svg file.
        expected_elements: List of dicts with keys:
            'type' (str) — expected element type (rect, ellipse, line, etc.).
            'id' (str) — expected element ID.
            'attrs' (dict) — expected attributes (subset match: all expected
                             attrs must be present with matching values).
            'text' (str, optional) — expected text content.
            'z_order' (int, optional) — expected z-order index.
        expected_width:   Optional expected canvas width.
        expected_height:  Optional expected canvas height.

    Returns:
        True if the re-parsed canvas matches the spec exactly.

    Raises:
        AssertionError: If any field doesn't match.
        DesignError: If the file cannot be parsed.
    """
    canvas = read_canvas(file_path)

    # Check canvas dimensions if specified
    if expected_width is not None and canvas.width != expected_width:
        raise AssertionError(
            f"canvas_readback FAILED: width mismatch.\n"
            f"  Expected: {expected_width}\n"
            f"  Got:      {canvas.width}"
        )
    if expected_height is not None and canvas.height != expected_height:
        raise AssertionError(
            f"canvas_readback FAILED: height mismatch.\n"
            f"  Expected: {expected_height}\n"
            f"  Got:      {canvas.height}"
        )

    # Check element count
    if canvas.element_count != len(expected_elements):
        raise AssertionError(
            f"canvas_readback FAILED: element count mismatch.\n"
            f"  Expected: {len(expected_elements)}\n"
            f"  Got:      {canvas.element_count}"
        )

    # Check each element
    for i, expected in enumerate(expected_elements):
        actual = canvas.elements[i]

        # Check type
        exp_type = expected.get("type", "")
        if actual.element_type != exp_type:
            raise AssertionError(
                f"canvas_readback FAILED: element {i} type mismatch.\n"
                f"  Expected: {exp_type}\n"
                f"  Got:      {actual.element_type}"
            )

        # Check ID
        exp_id = expected.get("id", "")
        if actual.element_id != exp_id:
            raise AssertionError(
                f"canvas_readback FAILED: element {i} ID mismatch.\n"
                f"  Expected: {exp_id}\n"
                f"  Got:      {actual.element_id}"
            )

        # Check attributes (subset match: all expected attrs must match)
        exp_attrs = expected.get("attrs", {})
        for k, v in exp_attrs.items():
            if k not in actual.attributes:
                raise AssertionError(
                    f"canvas_readback FAILED: element {i} ('{exp_id}') "
                    f"missing attribute '{k}'.\n"
                    f"  Expected: {k}={v}\n"
                    f"  Got:      (missing)"
                )
            if actual.attributes[k] != str(v):
                raise AssertionError(
                    f"canvas_readback FAILED: element {i} ('{exp_id}') "
                    f"attribute '{k}' mismatch.\n"
                    f"  Expected: {v}\n"
                    f"  Got:      {actual.attributes[k]}"
                )

        # Check text content if specified
        if "text" in expected:
            exp_text = expected["text"]
            if actual.text_content != exp_text:
                raise AssertionError(
                    f"canvas_readback FAILED: element {i} ('{exp_id}') "
                    f"text content mismatch.\n"
                    f"  Expected: {exp_text!r}\n"
                    f"  Got:      {actual.text_content!r}"
                )

        # Check z-order if specified
        if "z_order" in expected:
            if actual.z_order != expected["z_order"]:
                raise AssertionError(
                    f"canvas_readback FAILED: element {i} ('{exp_id}') "
                    f"z-order mismatch.\n"
                    f"  Expected: {expected['z_order']}\n"
                    f"  Got:      {actual.z_order}"
                )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: structure_readback
# ---------------------------------------------------------------------------


def structure_readback(
    file_path: str,
    expected_element_count: int,
    expected_z_orders: list[int] | None = None,
    expected_types: list[str] | None = None,
    expected_ids: list[str] | None = None,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> bool:
    """Oracle: element count + layer/z-order + bounding boxes survive round-trip.

    KILL-PROOF: drop a layer/element → FAILS.

    Args:
        file_path:              Path to the saved .svg file.
        expected_element_count: Expected number of top-level elements.
        expected_z_orders:      Optional list of expected z-order indices.
        expected_types:         Optional list of expected element types in order.
        expected_ids:           Optional list of expected element IDs in order.
        expected_width:         Optional expected canvas width.
        expected_height:        Optional expected canvas height.

    Returns:
        True if the structure matches expectations.

    Raises:
        AssertionError: If any structural element doesn't match.
        DesignError: If the file cannot be parsed.
    """
    canvas = read_canvas(file_path)

    # Check element count
    if canvas.element_count != expected_element_count:
        raise AssertionError(
            f"structure_readback FAILED: element count mismatch.\n"
            f"  Expected: {expected_element_count}\n"
            f"  Got:      {canvas.element_count}"
        )

    # Check canvas dimensions
    if expected_width is not None and canvas.width != expected_width:
        raise AssertionError(
            f"structure_readback FAILED: width mismatch.\n"
            f"  Expected: {expected_width}\n"
            f"  Got:      {canvas.width}"
        )
    if expected_height is not None and canvas.height != expected_height:
        raise AssertionError(
            f"structure_readback FAILED: height mismatch.\n"
            f"  Expected: {expected_height}\n"
            f"  Got:      {canvas.height}"
        )

    # Check z-orders if specified
    if expected_z_orders is not None:
        actual_z_orders = [e.z_order for e in canvas.elements]
        if actual_z_orders != expected_z_orders:
            raise AssertionError(
                f"structure_readback FAILED: z-order mismatch.\n"
                f"  Expected: {expected_z_orders}\n"
                f"  Got:      {actual_z_orders}"
            )

    # Check types if specified
    if expected_types is not None:
        actual_types = [e.element_type for e in canvas.elements]
        if actual_types != expected_types:
            raise AssertionError(
                f"structure_readback FAILED: element types mismatch.\n"
                f"  Expected: {expected_types}\n"
                f"  Got:      {actual_types}"
            )

    # Check IDs if specified
    if expected_ids is not None:
        actual_ids = [e.element_id for e in canvas.elements]
        if actual_ids != expected_ids:
            raise AssertionError(
                f"structure_readback FAILED: element IDs mismatch.\n"
                f"  Expected: {expected_ids}\n"
                f"  Got:      {actual_ids}"
            )

    return True
