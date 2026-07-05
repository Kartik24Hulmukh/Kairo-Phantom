# PROVENANCE: original | clean-room Anchor perception engine per ANCHOR_ARCHITECTURE.md + R5
"""Anchor perception engine — multi-modal fusion for screen grounding.

Implements the three-leg fusion pipeline:
  1. AX-tree leg: parse accessibility tree dumps → {role, name, value, bounds}
  2. OCR leg: text extraction from canvas (Experimental — olmocr/Tesseract)
  3. Vision leg: icon/shape detection (Experimental — live inference)

Fusion merges legs into a unified element graph with bbox-overlap dedup
(UFO² pattern), confidence-weighting, and token compaction (>=70% reduction).

SECURITY: All perceived text is UNTRUSTED (TAINTED). It feeds the out-of-band
taint model (prompts/05). Perceived text can inform content, never authorize
a capability.

HONEST DEGRADATION:
  - Live screen capture (UIA/AX/AT-SPI) → Experimental, fails loud if no display
  - Live OCR (olmocr) → Experimental, fails loud if model unavailable
  - Live vision detection → Experimental, fails loud if weights unavailable
  - AX-dump parsing + fusion + compaction + resolve on static corpus → Real

All operations are fully offline on the Real path. No network calls.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field as dc_field
from typing import Any

log = logging.getLogger("kairo.perception")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AnchorUnavailableError(RuntimeError):
    """Raised when a required perception resource is missing — honest degradation."""

    pass


class AnchorExperimentalError(RuntimeError):
    """Raised when an Experimental path (live capture/OCR/vision) is unavailable.

    These paths require external dependencies or hardware that cannot be
    satisfied in an offline/headless CI environment. They NEVER fake results.
    """

    pass


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------


@dataclass
class BoundingBox:
    """Axis-aligned bounding box in screen coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    def iou(self, other: BoundingBox) -> float:
        """Intersection-over-Union (Jaccard index) with another bbox."""
        ix = max(0, min(self.x2, other.x2) - max(self.x, other.x))
        iy = max(0, min(self.y2, other.y2) - max(self.y, other.y))
        intersection = ix * iy
        union = self.area + other.area - intersection
        if union <= 0:
            return 0.0
        return intersection / union

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class AnchorElement:
    """A single perceived UI element from any leg.

    All perceived text is UNTRUSTED (TAINTED) per prompts/05.

    Attributes:
        element_id:  Stable identifier (persisted across frames by trackers).
        role:        Element role (button, text, icon, canvas_object, etc.).
        name:        Element name/label (UNTRUSTED text from perception).
        value:       Element value if any (UNTRUSTED).
        bounds:      BoundingBox in screen coordinates.
        affordance:  What the element affords (click, type, scroll, etc.).
        confidence:  Confidence score [0.0, 1.0] from the source leg.
        source:      Which leg produced this: "ax", "ocr", "vision".
        is_canvas:   Whether this element is on a canvas/GPU surface (AX-blind).
    """

    element_id: str
    role: str
    name: str
    value: str = ""
    bounds: BoundingBox | None = None
    affordance: str = ""
    confidence: float = 1.0
    source: str = "ax"
    is_canvas: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "role": self.role,
            "name": self.name,
            "value": self.value,
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "affordance": self.affordance,
            "confidence": self.confidence,
            "source": self.source,
            "is_canvas": self.is_canvas,
        }


@dataclass
class ElementMap:
    """Fused, compacted element map for a single screen.

    The output of the perception pipeline — a token-efficient representation
    of all perceived UI elements.
    """

    screen_id: str
    elements: list[AnchorElement] = dc_field(default_factory=list)
    element_count: int = 0
    canvas_element_count: int = 0
    raw_token_estimate: int = 0
    compacted_token_estimate: int = 0
    token_reduction_pct: float = 0.0
    legs_used: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "element_count": self.element_count,
            "canvas_element_count": self.canvas_element_count,
            "elements": [e.to_dict() for e in self.elements],
            "raw_token_estimate": self.raw_token_estimate,
            "compacted_token_estimate": self.compacted_token_estimate,
            "token_reduction_pct": self.token_reduction_pct,
            "legs_used": self.legs_used,
        }


@dataclass
class ScreenMap:
    """Full screen map — the public API output of get_screen_map()."""

    screen_id: str
    element_map: ElementMap
    source: str = "fixture"  # "fixture" (Real) or "live" (Experimental)

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "source": self.source,
            "element_map": self.element_map.to_dict(),
        }


# ---------------------------------------------------------------------------
# Leg 1: AX-tree parsing (Real — operates on AX dumps from fixtures)
# ---------------------------------------------------------------------------


def parse_ax_dump(ax_dump: dict[str, Any]) -> list[AnchorElement]:
    """Parse an accessibility tree dump into AnchorElements.

    This is the Real path — it operates on pre-recorded AX dumps (JSON),
    not live screen capture. Live UIA/AX/AT-SPI capture is Experimental.

    Args:
        ax_dump: AX tree dump with 'elements' key containing element dicts.

    Returns:
        List of AnchorElement objects from the AX tree.

    Raises:
        AnchorUnavailableError: If the dump is malformed.
    """
    elements: list[AnchorElement] = []
    raw_elements = ax_dump.get("elements", [])

    if not isinstance(raw_elements, list):
        raise AnchorUnavailableError(
            "AX dump malformed — 'elements' must be a list"
        )

    for i, elem in enumerate(raw_elements):
        if not isinstance(elem, dict):
            continue

        bounds_data = elem.get("bounds", {})
        bounds = None
        if bounds_data and all(k in bounds_data for k in ("x", "y", "width", "height")):
            bounds = BoundingBox(
                x=int(bounds_data["x"]),
                y=int(bounds_data["y"]),
                width=int(bounds_data["width"]),
                height=int(bounds_data["height"]),
            )

        element = AnchorElement(
            element_id=elem.get("id", f"ax_{i}"),
            role=elem.get("role", "unknown"),
            name=elem.get("name", ""),
            value=elem.get("value", ""),
            bounds=bounds,
            affordance=elem.get("affordance", _infer_affordance(elem.get("role", ""))),
            confidence=elem.get("confidence", 0.95),
            source="ax",
            is_canvas=elem.get("is_canvas", False),
        )
        elements.append(element)

    return elements


def _infer_affordance(role: str) -> str:
    """Infer affordance from element role."""
    role_lower = role.lower()
    if "button" in role_lower:
        return "click"
    if "text" in role_lower and "edit" not in role_lower:
        return "read"
    if "edit" in role_lower or "input" in role_lower:
        return "type"
    if "combo" in role_lower or "list" in role_lower:
        return "select"
    if "scroll" in role_lower:
        return "scroll"
    if "menu" in role_lower:
        return "click"
    if "link" in role_lower:
        return "click"
    if "check" in role_lower:
        return "toggle"
    if "radio" in role_lower:
        return "select"
    return "click"


# ---------------------------------------------------------------------------
# Leg 2: OCR (Experimental — olmocr/Tesseract not available in CI)
# ---------------------------------------------------------------------------


def run_ocr(image_path: str) -> list[AnchorElement]:
    """Run OCR on an image to extract text elements.

    EXPERIMENTAL — requires olmocr (Apache-2.0) or Tesseract.
    Cannot run in an offline/headless CI environment without the model.

    Raises:
        AnchorExperimentalError: Always, unless OCR engine is available.
    """
    raise AnchorExperimentalError(
        "OCR leg is Experimental — olmocr/Tesseract not available in this "
        "environment. The AX-tree leg + fixture-provided detections are the "
        "Real, tested capability. OCR never fakes text extraction."
    )


def parse_ocr_dump(ocr_dump: dict[str, Any]) -> list[AnchorElement]:
    """Parse a pre-recorded OCR dump into AnchorElements.

    This is the Real path for OCR data — it operates on fixture-provided
    OCR results, not live OCR inference.

    Args:
        ocr_dump: OCR dump with 'elements' key containing text regions.

    Returns:
        List of AnchorElement objects from OCR.
    """
    elements: list[AnchorElement] = []
    raw_elements = ocr_dump.get("elements", [])

    for i, elem in enumerate(raw_elements):
        if not isinstance(elem, dict):
            continue

        bounds_data = elem.get("bounds", {})
        bounds = None
        if bounds_data and all(k in bounds_data for k in ("x", "y", "width", "height")):
            bounds = BoundingBox(
                x=int(bounds_data["x"]),
                y=int(bounds_data["y"]),
                width=int(bounds_data["width"]),
                height=int(bounds_data["height"]),
            )

        element = AnchorElement(
            element_id=elem.get("id", f"ocr_{i}"),
            role="text",
            name=elem.get("text", ""),
            value="",
            bounds=bounds,
            affordance="read",
            confidence=elem.get("confidence", 0.85),
            source="ocr",
            is_canvas=elem.get("is_canvas", True),  # OCR usually targets canvas
        )
        elements.append(element)

    return elements


# ---------------------------------------------------------------------------
# Leg 3: Vision detection (Experimental — live inference not available in CI)
# ---------------------------------------------------------------------------


def run_vision_detection(image_path: str) -> list[AnchorElement]:
    """Run vision detection on an image for icons/handles/shapes.

    EXPERIMENTAL — requires supervision (MIT) + detector weights.
    Cannot run in an offline/headless CI environment without weights.

    Raises:
        AnchorExperimentalError: Always, unless detector is available.
    """
    raise AnchorExperimentalError(
        "Vision detection leg is Experimental — supervision/detector weights "
        "not available in this environment. The AX-tree leg + fixture-provided "
        "detections are the Real, tested capability. Vision never fakes detections."
    )


def parse_vision_dump(vision_dump: dict[str, Any]) -> list[AnchorElement]:
    """Parse pre-recorded vision detections into AnchorElements.

    This is the Real path for vision data — it operates on fixture-provided
    detections, not live inference.

    Args:
        vision_dump: Vision dump with 'elements' key containing detected objects.

    Returns:
        List of AnchorElement objects from vision.
    """
    elements: list[AnchorElement] = []
    raw_elements = vision_dump.get("elements", [])

    for i, elem in enumerate(raw_elements):
        if not isinstance(elem, dict):
            continue

        bounds_data = elem.get("bounds", {})
        bounds = None
        if bounds_data and all(k in bounds_data for k in ("x", "y", "width", "height")):
            bounds = BoundingBox(
                x=int(bounds_data["x"]),
                y=int(bounds_data["y"]),
                width=int(bounds_data["width"]),
                height=int(bounds_data["height"]),
            )

        element = AnchorElement(
            element_id=elem.get("id", f"vis_{i}"),
            role=elem.get("role", "icon"),
            name=elem.get("name", ""),
            value="",
            bounds=bounds,
            affordance=elem.get("affordance", "click"),
            confidence=elem.get("confidence", 0.80),
            source="vision",
            is_canvas=elem.get("is_canvas", True),
        )
        elements.append(element)

    return elements


# ---------------------------------------------------------------------------
# Fusion + dedup (Real — UFO² pattern, clean-room)
# ---------------------------------------------------------------------------


def _compute_iou(a: BoundingBox, b: BoundingBox) -> float:
    """IoU between two bounding boxes."""
    return a.iou(b)


def fuse_elements(
    ax_elements: list[AnchorElement],
    ocr_elements: list[AnchorElement] | None = None,
    vision_elements: list[AnchorElement] | None = None,
    dedup_iou_threshold: float = 0.5,
) -> list[AnchorElement]:
    """Fuse elements from all legs with bbox-overlap dedup (UFO² pattern).

    Merges AX, OCR, and vision elements into a single list, deduplicating
    elements that have high bbox overlap (IoU > threshold). When duplicates
    are found, the element with higher confidence is kept, and names from
    lower-confidence elements are merged as aliases.

    Args:
        ax_elements:      Elements from the AX-tree leg.
        ocr_elements:     Elements from the OCR leg (optional).
        vision_elements:  Elements from the vision leg (optional).
        dedup_iou_threshold: IoU threshold for dedup (default 0.5).

    Returns:
        Fused, deduplicated list of AnchorElement objects.
    """
    all_elements: list[AnchorElement] = list(ax_elements)
    if ocr_elements:
        all_elements.extend(ocr_elements)
    if vision_elements:
        all_elements.extend(vision_elements)

    if not all_elements:
        return []

    # Sort by confidence descending — keep highest-confidence elements
    all_elements.sort(key=lambda e: e.confidence, reverse=True)

    fused: list[AnchorElement] = []
    used: set[int] = set()

    for i, elem in enumerate(all_elements):
        if i in used:
            continue

        # Check for overlaps with already-fused elements
        is_duplicate = False
        for j, kept in enumerate(fused):
            if elem.bounds and kept.bounds:
                iou = _compute_iou(elem.bounds, kept.bounds)
                if iou > dedup_iou_threshold:
                    # Merge: keep the higher-confidence one, augment name
                    if elem.confidence > kept.confidence:
                        # Replace kept with this element, merge names
                        merged_name = kept.name
                        if elem.name and elem.name != kept.name:
                            merged_name = f"{elem.name} (aka {kept.name})"
                        fused[j] = AnchorElement(
                            element_id=kept.element_id,  # Keep stable ID
                            role=elem.role,
                            name=merged_name,
                            value=elem.value or kept.value,
                            bounds=elem.bounds,
                            affordance=elem.affordance,
                            confidence=elem.confidence,
                            source=f"{kept.source}+{elem.source}",
                            is_canvas=elem.is_canvas or kept.is_canvas,
                        )
                    else:
                        # Keep the existing one, augment name if different
                        if elem.name and elem.name != kept.name:
                            existing = fused[j]
                            fused[j] = AnchorElement(
                                element_id=existing.element_id,
                                role=existing.role,
                                name=f"{existing.name} (aka {elem.name})",
                                value=existing.value,
                                bounds=existing.bounds,
                                affordance=existing.affordance,
                                confidence=existing.confidence,
                                source=existing.source,
                                is_canvas=existing.is_canvas,
                            )
                    is_duplicate = True
                    break

        if not is_duplicate:
            fused.append(elem)

    return fused


# ---------------------------------------------------------------------------
# Compaction (Real — token-efficient representation)
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def _estimate_raw_screenshot_tokens(width: int = 1920, height: int = 1080) -> int:
    """Estimate tokens for a raw screenshot (as base64 image to a VLM).

    A 1920x1080 PNG is ~2-5MB; as base64 to a VLM, it's typically
    ~1000-2000 tokens per 512x512 tile. For a 1920x1080 screen:
    (1920/512) * (1080/512) * ~1500 ≈ ~12000 tokens.
    """
    tiles_x = (width + 511) // 512
    tiles_y = (height + 511) // 512
    return tiles_x * tiles_y * 1500


def compact_map(elements: list[AnchorElement], screen_id: str = "") -> ElementMap:
    """Compact a list of elements into a token-efficient ElementMap.

    Measures token reduction vs raw screenshot representation.

    Args:
        elements:  Fused list of AnchorElement objects.
        screen_id: Identifier for the screen.

    Returns:
        ElementMap with compacted elements and token reduction metrics.
    """
    # Estimate raw screenshot tokens
    raw_tokens = _estimate_raw_screenshot_tokens()

    # Estimate compacted map tokens (JSON representation)
    compact_json = json.dumps([e.to_dict() for e in elements], separators=(",", ":"))
    compacted_tokens = _estimate_tokens(compact_json)

    # Calculate reduction
    if raw_tokens > 0:
        reduction_pct = ((raw_tokens - compacted_tokens) / raw_tokens) * 100.0
    else:
        reduction_pct = 0.0

    canvas_count = sum(1 for e in elements if e.is_canvas)

    return ElementMap(
        screen_id=screen_id,
        elements=elements,
        element_count=len(elements),
        canvas_element_count=canvas_count,
        raw_token_estimate=raw_tokens,
        compacted_token_estimate=compacted_tokens,
        token_reduction_pct=round(reduction_pct, 2),
        legs_used=list({e.source for e in elements}),
    )


# ---------------------------------------------------------------------------
# Public API: get_screen_map() and resolve()
# ---------------------------------------------------------------------------


def get_screen_map(
    ax_dump: dict[str, Any],
    ocr_dump: dict[str, Any] | None = None,
    vision_dump: dict[str, Any] | None = None,
    screen_id: str = "",
    source: str = "fixture",
) -> ScreenMap:
    """Build a full screen map from perception leg dumps.

    This is the main entry point for the perception pipeline. It:
    1. Parses each leg's dump into AnchorElements.
    2. Fuses elements with bbox-overlap dedup.
    3. Compacts into a token-efficient ElementMap.

    Args:
        ax_dump:     AX-tree dump (required — Real path).
        ocr_dump:    OCR dump (optional — fixture-provided for Real path).
        vision_dump: Vision dump (optional — fixture-provided for Real path).
        screen_id:   Screen identifier.
        source:      "fixture" (Real) or "live" (Experimental).

    Returns:
        ScreenMap with fused, compacted element map.
    """
    ax_elements = parse_ax_dump(ax_dump)

    ocr_elements = None
    if ocr_dump:
        ocr_elements = parse_ocr_dump(ocr_dump)

    vision_elements = None
    if vision_dump:
        vision_elements = parse_vision_dump(vision_dump)

    fused = fuse_elements(ax_elements, ocr_elements, vision_elements)
    element_map = compact_map(fused, screen_id=screen_id)

    return ScreenMap(
        screen_id=screen_id,
        element_map=element_map,
        source=source,
    )


def resolve(
    query: str,
    screen_map: ScreenMap,
    match_threshold: float = 0.3,
) -> AnchorElement | None:
    """Resolve a natural-language element query to a specific element.

    Matches the query against element names, roles, and affordances using
    a deterministic text-matching algorithm (no LLM, no embeddings — fully
    local and offline).

    Args:
        query:           Element query (e.g., "Submit button", "email field").
        screen_map:      ScreenMap to search.
        match_threshold: Minimum match score to return a result.

    Returns:
        Best-matching AnchorElement, or None if no element meets threshold.

    Note:
        All perceived text used for matching is UNTRUSTED (TAINTED).
        The query itself comes from the TRUSTED planner. Matching perceived
        text to a trusted query does not elevate the perceived text's taint
        label — it only locates an element for the planner to act on.
    """
    query_lower = query.lower().strip()
    query_tokens = set(query_lower.split())

    best_element: AnchorElement | None = None
    best_score: float = 0.0

    for element in screen_map.element_map.elements:
        score = _match_score(query_lower, query_tokens, element)
        if score > best_score:
            best_score = score
            best_element = element

    if best_score >= match_threshold:
        return best_element
    return None


def _match_score(query_lower: str, query_tokens: set[str], element: AnchorElement) -> float:
    """Compute a deterministic match score between query and element.

    Scoring:
    - Exact name match: 1.0
    - All query tokens in name: 0.9
    - Partial token overlap: proportional
    - Role match: bonus
    - Affordance match: bonus
    """
    name_lower = element.name.lower()
    role_lower = element.role.lower()
    affordance_lower = element.affordance.lower()

    if not name_lower and not role_lower:
        return 0.0

    score = 0.0

    # Exact name match
    if query_lower == name_lower:
        return 1.0

    # Name contains query
    if query_lower in name_lower:
        score = max(score, 0.85)

    # Query contains name
    if name_lower and name_lower in query_lower:
        score = max(score, 0.75)

    # Token overlap with name
    if name_lower:
        name_tokens = set(name_lower.split())
        if query_tokens and name_tokens:
            overlap = len(query_tokens & name_tokens)
            total = len(query_tokens | name_tokens)
            if total > 0:
                token_score = overlap / total
                score = max(score, token_score * 0.7)

    # Role match bonus
    for qt in query_tokens:
        if qt in role_lower:
            score += 0.1
            break

    # Affordance match bonus
    for qt in query_tokens:
        if qt in affordance_lower:
            score += 0.05
            break

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Stable ID tracking across frames
# ---------------------------------------------------------------------------


def track_stable_ids(
    frame_maps: list[ElementMap],
    iou_threshold: float = 0.3,
) -> list[ElementMap]:
    """Track stable element IDs across a sequence of frame maps.

    For each frame after the first, matches elements to the previous frame's
    elements by bbox overlap (IoU). If a match is found, the element's ID
    is carried forward from the previous frame, ensuring stable IDs across
    scroll/animation.

    Args:
        frame_maps:   List of ElementMap objects, one per frame.
        iou_threshold: IoU threshold for matching across frames.

    Returns:
        List of ElementMap objects with stable IDs assigned.
    """
    if not frame_maps:
        return []

    result = [frame_maps[0]]  # First frame keeps its IDs

    for frame_idx in range(1, len(frame_maps)):
        prev_map = result[-1]
        curr_map = frame_maps[frame_idx]

        updated_elements: list[AnchorElement] = []
        for elem in curr_map.elements:
            matched_id = None
            best_iou = 0.0

            for prev_elem in prev_map.elements:
                if elem.bounds and prev_elem.bounds:
                    iou = _compute_iou(elem.bounds, prev_elem.bounds)
                    if iou > best_iou and iou > iou_threshold:
                        # Also check role similarity
                        if elem.role == prev_elem.role or elem.name == prev_elem.name:
                            best_iou = iou
                            matched_id = prev_elem.element_id

            if matched_id:
                updated_elements.append(AnchorElement(
                    element_id=matched_id,
                    role=elem.role,
                    name=elem.name,
                    value=elem.value,
                    bounds=elem.bounds,
                    affordance=elem.affordance,
                    confidence=elem.confidence,
                    source=elem.source,
                    is_canvas=elem.is_canvas,
                ))
            else:
                updated_elements.append(elem)

        result.append(ElementMap(
            screen_id=curr_map.screen_id,
            elements=updated_elements,
            element_count=len(updated_elements),
            canvas_element_count=sum(1 for e in updated_elements if e.is_canvas),
            raw_token_estimate=curr_map.raw_token_estimate,
            compacted_token_estimate=curr_map.compacted_token_estimate,
            token_reduction_pct=curr_map.token_reduction_pct,
            legs_used=curr_map.legs_used,
        ))

    return result


# ---------------------------------------------------------------------------
# Pipeline with trust stack integration
# ---------------------------------------------------------------------------


def perception_pipeline(
    ax_dump: dict[str, Any],
    ocr_dump: dict[str, Any] | None = None,
    vision_dump: dict[str, Any] | None = None,
    screen_id: str = "",
    private_key: Any = None,
) -> dict[str, Any]:
    """Run the perception pipeline with trust stack integration.

    1. Parse legs → fuse → compact → ScreenMap.
    2. Emit Ed25519 audit log + zero-egress report (if private_key provided).

    Args:
        ax_dump:      AX-tree dump.
        ocr_dump:     OCR dump (optional).
        vision_dump:  Vision dump (optional).
        screen_id:    Screen identifier.
        private_key:  Optional Ed25519 private key.

    Returns:
        Dict with screen_map, audit_log_json, egress_report_json.
    """
    screen_map = get_screen_map(ax_dump, ocr_dump, vision_dump, screen_id)

    # Compute doc hash from the element map
    map_json = json.dumps(screen_map.element_map.to_dict(), sort_keys=True, default=str)
    doc_hash = hashlib.sha256(map_json.encode()).hexdigest()

    audit_log_json = ""
    egress_report_json = ""

    if private_key is not None:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import generate_zero_egress_report

        audit = Ed25519AuditLog(private_key)
        audit.log_run_started(doc_hash=doc_hash, playbook_id="perception_pipeline")

        for i, elem in enumerate(screen_map.element_map.elements):
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=f"element_{i}",
                clause_label=f"Element '{elem.name}' ({elem.role})",
                old_text="",
                new_text=f"Perceived element: role={elem.role}, name={elem.name}, "
                f"source={elem.source}, confidence={elem.confidence}",
                citation="anchor-perception",
                rationale="Element perceived via local fusion pipeline (UNTRUSTED text)",
            )

        total_edits = screen_map.element_map.element_count
        audit.log_run_completed(
            doc_hash=doc_hash,
            total_edits=total_edits,
            total_flagged=0,
            injection_detected=False,
        )

        audit_log_json = audit.to_json()

        egress_report = generate_zero_egress_report(
            doc_hash=doc_hash,
            playbook_id="perception_pipeline",
            total_edits=total_edits,
            total_flagged=0,
            injection_detected=False,
            audit_log_json=audit_log_json,
            private_key=private_key,
        )
        egress_report_json = egress_report.to_json()

    return {
        "screen_map": screen_map,
        "audit_log_json": audit_log_json,
        "egress_report_json": egress_report_json,
        "doc_hash": doc_hash,
    }
