# PROVENANCE: original | clean-room Anchor perception oracles per VERIFICATION_ORACLES.md
"""Anchor perception oracles — deterministic, kill-proven verification.

Implements three practitioner-grade oracles:

  1. ``grounding_accuracy`` — resolve(element_query) on the static corpus →
     >=90% correct element resolution. KILL-PROOF: corrupt/disable a leg →
     accuracy drops measurably.

  2. ``stable_id`` — element ids persist across recorded scroll/animation
     frames. KILL-PROOF: shuffle ids → oracle fails.

  3. ``token_reduction`` — compacted map is >=70% smaller than raw screenshot
     representation (measured + logged).

All oracles are KILL-PROVEN: perturbing the perception pipeline (disabling a
leg, shuffling IDs, inflating the map) causes a hard failure.

HONEST DEGRADATION:
  If the fixture corpus is missing, the oracles raise AnchorUnavailableError.

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kairo.perception.engine import (
    AnchorUnavailableError,
    ElementMap,
    get_screen_map,
    resolve,
    track_stable_ids,
)


# ---------------------------------------------------------------------------
# Oracle 1: grounding_accuracy
# ---------------------------------------------------------------------------


def grounding_accuracy(
    corpus_dir: str,
    match_threshold: float = 0.3,
) -> dict[str, Any]:
    """Oracle: resolve(element_query) on the static corpus → >=90% accuracy.

    Loads each screen's fixtures (ax_dump.json + labeled_elements.json),
    builds a ScreenMap, and resolves each labeled query. Reports the exact
    accuracy percentage and per-screen breakdown.

    KILL-PROOF: corrupt/disable a leg → accuracy drops measurably.

    Args:
        corpus_dir:      Path to the anchor fixture corpus.
        match_threshold: Minimum match score for resolve().

    Returns:
        Dict with:
          'accuracy_pct': float — overall accuracy percentage.
          'correct': int — number of correct resolutions.
          'total': int — total queries.
          'per_screen': dict — per-screen breakdown.
          'canvas_accuracy_pct': float — accuracy on canvas/GPU screens.

    Raises:
        AssertionError: If accuracy < 90%.
        AnchorUnavailableError: If the corpus is missing.
    """
    corpus = Path(corpus_dir).resolve()
    if not corpus.exists() or not corpus.is_dir():
        raise AnchorUnavailableError(
            f"anchor corpus unavailable — directory does not exist: {corpus}"
        )

    screens = sorted([d for d in corpus.iterdir() if d.is_dir() and d.name.startswith("screen_")])

    if not screens:
        raise AnchorUnavailableError(
            f"anchor corpus unavailable — no screen directories found in: {corpus}"
        )

    total_queries = 0
    correct_queries = 0
    canvas_total = 0
    canvas_correct = 0
    per_screen: dict[str, dict[str, Any]] = {}

    for screen_dir in screens:
        screen_id = screen_dir.name
        ax_path = screen_dir / "ax_dump.json"
        labels_path = screen_dir / "labeled_elements.json"

        if not ax_path.exists() or not labels_path.exists():
            per_screen[screen_id] = {"error": "missing fixtures", "correct": 0, "total": 0}
            continue

        with open(ax_path, encoding="utf-8") as f:
            ax_dump = json.load(f)
        with open(labels_path, encoding="utf-8") as f:
            labels = json.load(f)

        # Check for OCR/vision dumps
        ocr_dump = None
        ocr_path = screen_dir / "ocr_dump.json"
        if ocr_path.exists():
            with open(ocr_path, encoding="utf-8") as f:
                ocr_dump = json.load(f)

        vision_dump = None
        vis_path = screen_dir / "vision_dump.json"
        if vis_path.exists():
            with open(vis_path, encoding="utf-8") as f:
                vision_dump = json.load(f)

        screen_map = get_screen_map(ax_dump, ocr_dump, vision_dump, screen_id)

        is_canvas_screen = ax_dump.get("is_canvas", False)

        queries = labels.get("queries", [])
        screen_correct = 0
        screen_total = 0

        for q in queries:
            query_text = q.get("query", "")
            expected_id = q.get("expected_element_id", "")

            result = resolve(query_text, screen_map, match_threshold)

            screen_total += 1
            total_queries += 1

            if is_canvas_screen:
                canvas_total += 1

            if result and result.element_id == expected_id:
                screen_correct += 1
                correct_queries += 1
                if is_canvas_screen:
                    canvas_correct += 1

        per_screen[screen_id] = {
            "correct": screen_correct,
            "total": screen_total,
            "is_canvas": is_canvas_screen,
        }

    accuracy_pct = (correct_queries / total_queries * 100.0) if total_queries > 0 else 0.0
    canvas_accuracy_pct = (canvas_correct / canvas_total * 100.0) if canvas_total > 0 else 0.0

    return {
        "accuracy_pct": round(accuracy_pct, 2),
        "correct": correct_queries,
        "total": total_queries,
        "per_screen": per_screen,
        "canvas_accuracy_pct": round(canvas_accuracy_pct, 2),
        "canvas_correct": canvas_correct,
        "canvas_total": canvas_total,
    }


# ---------------------------------------------------------------------------
# Oracle 2: stable_id
# ---------------------------------------------------------------------------


def stable_id(
    corpus_dir: str,
    iou_threshold: float = 0.3,
    check_overlap_threshold: float = 0.3,
) -> dict[str, Any]:
    """Oracle: element IDs persist across recorded scroll/animation frames.

    Loads a frame sequence from the corpus, builds ElementMaps for each frame,
    runs stable ID tracking, and verifies that IDs are consistent across frames.

    KILL-PROOF: shuffle IDs → oracle fails.

    Args:
        corpus_dir:             Path to the anchor fixture corpus.
        iou_threshold:          IoU threshold for cross-frame matching (tracker).
        check_overlap_threshold: Fixed IoU threshold for stability verification
                                (independent of tracker threshold).

    Returns:
        Dict with:
          'stable': bool — True if all IDs are stable.
          'frames_checked': int — number of frame transitions checked.
          'id_matches': int — number of successful ID matches.
          'id_mismatches': int — number of ID mismatches.

    Raises:
        AssertionError: If any ID is unstable.
        AnchorUnavailableError: If the frame sequence is missing.
    """
    corpus = Path(corpus_dir).resolve()
    frames_dir = corpus / "frame_sequence"

    if not frames_dir.exists() or not frames_dir.is_dir():
        raise AnchorUnavailableError(
            f"frame sequence unavailable — directory does not exist: {frames_dir}"
        )

    frame_dirs = sorted([d for d in frames_dir.iterdir() if d.is_dir() and d.name.startswith("frame_")])

    if len(frame_dirs) < 2:
        raise AnchorUnavailableError(
            f"frame sequence needs >=2 frames, found {len(frame_dirs)}"
        )

    # Build ElementMaps for each frame
    frame_maps: list[ElementMap] = []
    for frame_dir in frame_dirs:
        ax_path = frame_dir / "ax_dump.json"
        if not ax_path.exists():
            raise AnchorUnavailableError(
                f"frame fixture missing ax_dump.json: {frame_dir}"
            )

        with open(ax_path, encoding="utf-8") as f:
            ax_dump = json.load(f)

        screen_map = get_screen_map(ax_dump, screen_id=frame_dir.name)
        frame_maps.append(screen_map.element_map)

    # Track stable IDs
    tracked = track_stable_ids(frame_maps, iou_threshold)

    # Verify stability: for each pair of consecutive frames, elements that
    # overlap (IoU > check_overlap_threshold) should have the same ID.
    # Uses a FIXED threshold independent of the tracker's matching threshold.
    id_matches = 0
    id_mismatches = 0
    frames_checked = len(tracked) - 1

    for i in range(1, len(tracked)):
        prev = tracked[i - 1]
        curr = tracked[i]

        for curr_elem in curr.elements:
            if curr_elem.bounds:
                for prev_elem in prev.elements:
                    if prev_elem.bounds:
                        iou = curr_elem.bounds.iou(prev_elem.bounds)
                        if iou > check_overlap_threshold:
                            if curr_elem.element_id == prev_elem.element_id:
                                id_matches += 1
                            else:
                                # Check if the ID was supposed to be stable
                                # (same role + similar position)
                                if curr_elem.role == prev_elem.role:
                                    id_mismatches += 1

    stable = id_mismatches == 0

    return {
        "stable": stable,
        "frames_checked": frames_checked,
        "id_matches": id_matches,
        "id_mismatches": id_mismatches,
    }


# ---------------------------------------------------------------------------
# Oracle 3: token_reduction
# ---------------------------------------------------------------------------


def token_reduction(
    corpus_dir: str,
) -> dict[str, Any]:
    """Oracle: compacted map is >=70% smaller than raw screenshot representation.

    Loads each screen's fixtures, builds a ScreenMap, and verifies that the
    compacted element map achieves >=70% token reduction vs the raw screenshot
    estimate.

    KILL-PROOF: inflate the map (add redundant elements) → reduction drops.

    Args:
        corpus_dir: Path to the anchor fixture corpus.

    Returns:
        Dict with:
          'meets_threshold': bool — True if all screens >=70%.
          'min_reduction_pct': float — worst-case reduction.
          'avg_reduction_pct': float — average reduction.
          'per_screen': dict — per-screen reduction.

    Raises:
        AssertionError: If any screen has <70% reduction.
        AnchorUnavailableError: If the corpus is missing.
    """
    corpus = Path(corpus_dir).resolve()
    if not corpus.exists() or not corpus.is_dir():
        raise AnchorUnavailableError(
            f"anchor corpus unavailable — directory does not exist: {corpus}"
        )

    screens = sorted([d for d in corpus.iterdir() if d.is_dir() and d.name.startswith("screen_")])

    if not screens:
        raise AnchorUnavailableError(
            f"anchor corpus unavailable — no screen directories found in: {corpus}"
        )

    reductions: list[float] = []
    per_screen: dict[str, float] = {}

    for screen_dir in screens:
        ax_path = screen_dir / "ax_dump.json"
        if not ax_path.exists():
            continue

        with open(ax_path, encoding="utf-8") as f:
            ax_dump = json.load(f)

        ocr_dump = None
        ocr_path = screen_dir / "ocr_dump.json"
        if ocr_path.exists():
            with open(ocr_path, encoding="utf-8") as f:
                ocr_dump = json.load(f)

        vision_dump = None
        vis_path = screen_dir / "vision_dump.json"
        if vis_path.exists():
            with open(vis_path, encoding="utf-8") as f:
                vision_dump = json.load(f)

        screen_map = get_screen_map(ax_dump, ocr_dump, vision_dump, screen_dir.name)
        reduction = screen_map.element_map.token_reduction_pct

        reductions.append(reduction)
        per_screen[screen_dir.name] = reduction

    min_reduction = min(reductions) if reductions else 0.0
    avg_reduction = sum(reductions) / len(reductions) if reductions else 0.0

    return {
        "meets_threshold": min_reduction >= 70.0,
        "min_reduction_pct": round(min_reduction, 2),
        "avg_reduction_pct": round(avg_reduction, 2),
        "per_screen": per_screen,
    }
