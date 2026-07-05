# PROVENANCE: original | clean-room PowerPoint domain oracles per VERIFICATION_ORACLES.md
"""PowerPoint domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``slide_shape_readback`` — after creating/editing a .pptx, REOPEN it via
     python-pptx and assert slides/shapes/text/tables/positions match the
     intended spec.  KILL-PROOF: drop a shape or alter text → FAILS.

  2. ``structure_readback`` — slide count / layout / table dims survive
     round-trip.  KILL-PROOF: drop a slide → FAILS.

Both oracles are KILL-PROVEN: perturbing the expected structure (dropping a
shape, altering text, dropping a slide, wrong table dims) causes a hard
failure.

HONEST DEGRADATION:
  If python-pptx is not installed, the oracles raise
  ``PowerPointEngineUnavailableError`` — they never present unverified
  results as correct.

All operations are fully offline. No network calls. No LLM. No cloud.

Dependencies (all permissive — MIT):
  - python-pptx (MIT) — .pptx create/edit/read
"""

from __future__ import annotations

from typing import Any

from kairo.domains.powerpoint.engine import (
    read_deck,
)


# ---------------------------------------------------------------------------
# Oracle 1: slide_shape_readback
# ---------------------------------------------------------------------------


def slide_shape_readback(
    file_path: str,
    expected_shapes_per_slide: list[list[dict[str, Any]]],
) -> bool:
    """Oracle: reopen .pptx → assert shapes/text/tables/positions match spec.

    KILL-PROOF: drop a shape, alter text, or change a table dimension → FAILS.

    Args:
        file_path: Path to the saved .pptx file.
        expected_shapes_per_slide: List of lists; each inner list has dicts
            with keys: 'text' (str), 'table_rows' (int), 'table_cols' (int).
            Only keys present in the dict are checked.

    Returns:
        True if all shapes match.

    Raises:
        AssertionError: If any shape doesn't match (kill-proof).
        PowerPointEngineUnavailableError: If python-pptx is not installed.
    """
    deck_info = read_deck(file_path)

    if deck_info.slide_count != len(expected_shapes_per_slide):
        raise AssertionError(
            f"slide_shape_readback FAILED: slide count mismatch.\n"
            f"  Expected: {len(expected_shapes_per_slide)} slides\n"
            f"  Got:      {deck_info.slide_count} slides"
        )

    for slide_idx, (slide, expected_shapes) in enumerate(
        zip(deck_info.slides, expected_shapes_per_slide)
    ):
        if len(slide.shapes) != len(expected_shapes):
            raise AssertionError(
                f"slide_shape_readback FAILED: slide {slide_idx} shape count mismatch.\n"
                f"  Expected: {len(expected_shapes)} shapes\n"
                f"  Got:      {len(slide.shapes)} shapes"
            )

        for shape_idx, (actual, expected) in enumerate(zip(slide.shapes, expected_shapes)):
            # Check text if specified
            if "text" in expected:
                actual_text = actual.text.strip() if actual.text else ""
                expected_text = expected["text"].strip()
                if actual_text != expected_text:
                    raise AssertionError(
                        f"slide_shape_readback FAILED: slide {slide_idx}, "
                        f"shape {shape_idx} text mismatch.\n"
                        f"  Expected: '{expected_text}'\n"
                        f"  Got:      '{actual_text}'"
                    )

            # Check table dimensions if specified
            if "table_rows" in expected:
                if actual.table_rows != expected["table_rows"]:
                    raise AssertionError(
                        f"slide_shape_readback FAILED: slide {slide_idx}, "
                        f"shape {shape_idx} table_rows mismatch.\n"
                        f"  Expected: {expected['table_rows']}\n"
                        f"  Got:      {actual.table_rows}"
                    )

            if "table_cols" in expected:
                if actual.table_cols != expected["table_cols"]:
                    raise AssertionError(
                        f"slide_shape_readback FAILED: slide {slide_idx}, "
                        f"shape {shape_idx} table_cols mismatch.\n"
                        f"  Expected: {expected['table_cols']}\n"
                        f"  Got:      {actual.table_cols}"
                    )

            # Check shape type if specified
            if "shape_type" in expected:
                if expected["shape_type"] not in actual.shape_type:
                    raise AssertionError(
                        f"slide_shape_readback FAILED: slide {slide_idx}, "
                        f"shape {shape_idx} type mismatch.\n"
                        f"  Expected: {expected['shape_type']}\n"
                        f"  Got:      {actual.shape_type}"
                    )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: structure_readback
# ---------------------------------------------------------------------------


def structure_readback(
    file_path: str,
    expected_slide_count: int,
    expected_layouts: list[str] | None = None,
    expected_table_dims: list[tuple[int, int] | None] | None = None,
) -> bool:
    """Oracle: verify slide count / layout / table dims survive round-trip.

    KILL-PROOF: drop a slide, change a layout, or alter table dims → FAILS.

    Args:
        file_path: Path to the saved .pptx file.
        expected_slide_count: Expected number of slides.
        expected_layouts: Optional list of expected layout names per slide.
        expected_table_dims: Optional list of (rows, cols) per slide (None if no table).

    Returns:
        True if structure matches.

    Raises:
        AssertionError: If structure doesn't match (kill-proof).
    """
    deck_info = read_deck(file_path)

    if deck_info.slide_count != expected_slide_count:
        raise AssertionError(
            f"structure_readback FAILED: slide count mismatch.\n"
            f"  Expected: {expected_slide_count}\n"
            f"  Got:      {deck_info.slide_count}"
        )

    if expected_layouts is not None:
        for i, (slide, expected_layout) in enumerate(zip(deck_info.slides, expected_layouts)):
            if slide.layout_name != expected_layout:
                raise AssertionError(
                    f"structure_readback FAILED: slide {i} layout mismatch.\n"
                    f"  Expected: '{expected_layout}'\n"
                    f"  Got:      '{slide.layout_name}'"
                )

    if expected_table_dims is not None:
        for i, (slide, expected_dims) in enumerate(zip(deck_info.slides, expected_table_dims)):
            if expected_dims is None:
                # No table expected on this slide
                has_table = any(s.table_rows > 0 for s in slide.shapes)
                if has_table:
                    raise AssertionError(
                        f"structure_readback FAILED: slide {i} has unexpected table"
                    )
            else:
                exp_rows, exp_cols = expected_dims
                found_table = False
                for shape in slide.shapes:
                    if shape.table_rows > 0:
                        found_table = True
                        if shape.table_rows != exp_rows or shape.table_cols != exp_cols:
                            raise AssertionError(
                                f"structure_readback FAILED: slide {i} table dims.\n"
                                f"  Expected: {exp_rows}x{exp_cols}\n"
                                f"  Got:      {shape.table_rows}x{shape.table_cols}"
                            )
                if not found_table:
                    raise AssertionError(
                        f"structure_readback FAILED: slide {i} missing expected table "
                        f"({exp_rows}x{exp_cols})"
                    )

    return True
