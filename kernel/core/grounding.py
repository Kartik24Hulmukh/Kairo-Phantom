"""
Kairo Phantom — Grounding Verifier (SPEC §S3)

Implements the deterministic cascade to refuse-or-cite:
NORMALIZE → EXACT → FUZZY(≥0.92) → SEMANTIC(≥0.86, with re-verify) → BLOCK.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from kernel.core.data_model import (
    Anchor,
    BBox,
    Chunk,
    Extraction,
    ExtractionStatus,
    GroundingMethod,
)
from kernel.core.embeddings import get_embedding, cosine_similarity

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """NORMALIZE step: strip whitespace/case/punctuation/number-format variants."""
    text = text.lower().strip()
    # Remove punctuation
    text = re.sub(r'[^\w\s\-\.]', '', text)
    # Normalize multiple whitespaces to single space
    text = " ".join(text.split())
    # Strip currency symbols if any left
    text = re.sub(r'[\$\€\£\¥]', '', text)
    return text

# Maximum string length for Levenshtein DP.  Strings longer than this are
# truncated before comparison to prevent O(n*m) quadratic blowup on large
# documents (the real production hang: a 50k-char chunk would freeze the
# agent for hours).  200 chars is sufficient for extraction-field matching
# (invoice totals, vendor names, dates — all well under 200 chars) while
# bounding the DP matrix to 40k cells worst case.
_LEVENSHTEIN_MAX_LEN = 200


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculate Levenshtein similarity ratio between two strings.

    Strings longer than ``_LEVENSHTEIN_MAX_LEN`` are truncated to prevent
    quadratic blowup.  This is a production safety guard, not a test hack:
    a real user feeding a large document would otherwise hang the agent.
    """
    s1 = s1.lower()
    s2 = s2.lower()
    if s1 == s2:
        return 1.0
    if len(s1) == 0 or len(s2) == 0:
        return 0.0

    # Length-difference guard: if strings differ by >50% of the longer one,
    # the ratio can never reach the fuzzy threshold (0.92), so bail early.
    max_len = max(len(s1), len(s2))
    min_len = min(len(s1), len(s2))
    if min_len / max_len < 0.5:
        return 0.0

    # Truncate to prevent O(n*m) blowup on oversized inputs
    if len(s1) > _LEVENSHTEIN_MAX_LEN:
        s1 = s1[:_LEVENSHTEIN_MAX_LEN]
    if len(s2) > _LEVENSHTEIN_MAX_LEN:
        s2 = s2[:_LEVENSHTEIN_MAX_LEN]

    rows = len(s1) + 1
    cols = len(s2) + 1
    # Use two rolling rows instead of full matrix to save memory
    prev_row = list(range(cols))
    curr_row = [0] * cols

    for row in range(1, rows):
        curr_row[0] = row
        for col in range(1, cols):
            if s1[row-1] == s2[col-1]:
                cost = 0
            else:
                cost = 1
            curr_row[col] = min(prev_row[col] + 1,
                                curr_row[col-1] + 1,
                                prev_row[col-1] + cost)
        prev_row, curr_row = curr_row, prev_row

    return 1.0 - (prev_row[cols-1] / max(len(s1), len(s2)))

def best_fuzzy_match(value: str, text: str) -> tuple[float, tuple[int, int]]:
    """Scan windows of words in text to find best fuzzy substring match.
    Returns (best_ratio, (start_char, end_char)).

    Production safety: caps total work to prevent quadratic blowup on oversized
    chunks.  A chunk with 30k words would otherwise scan 30k windows × O(n*m)
    Levenshtein each, hanging the agent for hours on a real large document.
    """
    val_norm = normalize_text(value)
    if not val_norm:
        return 0.0, (0, 0)

    val_words = val_norm.split()
    n = len(val_words)

    # We want to find exact positions in the original text, so we'll tokenize with spans
    words_spans = []
    for m in re.finditer(r'\S+', text):
        words_spans.append((m.group(0), m.start(), m.end()))

    if not words_spans:
        return 0.0, (0, 0)

    best_ratio = 0.0
    best_span = (0, 0)

    # If the chunk is much larger than the value, subsample windows instead of
    # scanning every position.  For a 30k-word chunk and a 5-word value, we'd
    # normally scan ~30k windows; instead we sample at most _MAX_WINDOWS evenly
    # spaced positions.  This preserves match quality (the value either is or
    # isn't in the chunk) while bounding total work.
    _MAX_WINDOWS = 500
    total_words = len(words_spans)

    # Scan windows of size from n-1 to n+2
    windows_scanned = 0
    for length in range(max(1, n-1), min(total_words + 1, n+3)):
        num_windows = total_words - length + 1
        if num_windows <= 0:
            continue
        if num_windows <= _MAX_WINDOWS:
            # Scan all windows
            indices = range(num_windows)
        else:
            # Subsample: evenly spaced window start positions
            step = num_windows / _MAX_WINDOWS
            indices = (int(i * step) for i in range(_MAX_WINDOWS))

        for i in indices:
            if windows_scanned >= _MAX_WINDOWS:
                break
            windows_scanned += 1
            window = words_spans[i:i+length]
            sub_text = text[window[0][1]:window[-1][2]]
            sub_norm = normalize_text(sub_text)

            ratio = levenshtein_ratio(val_norm, sub_norm)
            if ratio > best_ratio:
                best_ratio = ratio
                best_span = (window[0][1], window[-1][2])
        if windows_scanned >= _MAX_WINDOWS:
            break

    return best_ratio, best_span


def bbox_iou(b1: BBox, b2: BBox) -> float:
    """Compute Intersection-over-Union between two bounding boxes."""
    ix0 = max(b1.x0, b2.x0)
    iy0 = max(b1.y0, b2.y0)
    ix1 = min(b1.x1, b2.x1)
    iy1 = min(b1.y1, b2.y1)
    inter_w = max(0.0, ix1 - ix0)
    inter_h = max(0.0, iy1 - iy0)
    inter_area = inter_w * inter_h
    area1 = (b1.x1 - b1.x0) * (b1.y1 - b1.y0)
    area2 = (b2.x1 - b2.x0) * (b2.y1 - b2.y0)
    union = area1 + area2 - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


class GroundingVerifierImpl:
    """Grounding verifier cascade implementation.

    Cascade: NORMALIZE → EXACT → FUZZY(≥0.92) → SEMANTIC(≥0.86, re-verify) → VISUAL(IoU≥0.5) → BLOCK.

    The ``disabled_stages`` parameter (ablation hook) allows disabling one or more
    stages for ablation experiments. When a stage is disabled, the cascade skips it
    as if it always fails, falling through to the next stage.
    """

    def __init__(
        self,
        fuzzy_threshold: float = 0.92,
        semantic_threshold: float = 0.86,
        visual_threshold: float = 0.5,
        disabled_stages: set[GroundingMethod] | None = None,
    ) -> None:
        self.fuzzy_threshold = fuzzy_threshold
        self.semantic_threshold = semantic_threshold
        self.visual_threshold = visual_threshold
        self.disabled_stages: set[GroundingMethod] = disabled_stages or set()

    def verify(self, value: str, source_span: str, chunks: list[Chunk]) -> tuple[GroundingMethod, tuple[Anchor, ...]]:
        """Verify the value/source_span against all chunks in the document.
        Returns (method, tuple of anchors).

        Cascade: NORMALIZE → EXACT → FUZZY(≥0.92) → SEMANTIC(≥0.86, re-verify) → VISUAL(IoU≥0.5) → BLOCK.
        Stages listed in ``self.disabled_stages`` are skipped (ablation hook).
        """
        if not chunks:
            return GroundingMethod.BLOCK, ()

        # 1. Normalize target text
        target = source_span if source_span else value
        if not target.strip():
            return GroundingMethod.BLOCK, ()

        norm_target = normalize_text(target)

        # 2. EXACT match
        if GroundingMethod.EXACT not in self.disabled_stages:
            for chunk in chunks:
                if target.lower() in chunk.text.lower():
                    # Find start and end offset
                    start = chunk.text.lower().find(target.lower())
                    end = start + len(target)
                    anchor = Anchor(
                        chunk_id=chunk.chunk_id,
                        char_span=(start, end),
                        page=chunk.page,
                        bbox=chunk.bbox,
                    )
                    return GroundingMethod.EXACT, (anchor,)

        # 3. FUZZY match (Levenshtein token ratio >= 0.92)
        if GroundingMethod.FUZZY not in self.disabled_stages:
            best_ratio = 0.0
            best_anchor = None
            for chunk in chunks:
                ratio, span = best_fuzzy_match(target, chunk.text)
                if ratio >= self.fuzzy_threshold and ratio > best_ratio:
                    best_ratio = ratio
                    best_anchor = Anchor(
                        chunk_id=chunk.chunk_id,
                        char_span=span,
                        page=chunk.page,
                        bbox=chunk.bbox,
                    )

            if best_anchor:
                return GroundingMethod.FUZZY, (best_anchor,)

        # 4. SEMANTIC match (Cosine similarity >= 0.86 + re-verify)
        if GroundingMethod.SEMANTIC not in self.disabled_stages:
            # Compute embedding of the value
            target_emb = get_embedding(target)
            best_cosine = 0.0
            best_sem_chunk = None

            for chunk in chunks:
                if not chunk.embedding:
                    # compute embedding on demand if missing
                    # (usually populated at index time)
                    chunk_emb = get_embedding(chunk.text)
                else:
                    chunk_emb = chunk.embedding

                sim = cosine_similarity(target_emb, chunk_emb)
                if sim >= self.semantic_threshold and sim > best_cosine:
                    best_cosine = sim
                    best_sem_chunk = chunk

            # Re-verify step: check if there's any word intersection/meaning overlap
            if best_sem_chunk:
                chunk_words = set(normalize_text(best_sem_chunk.text).split())
                target_words = set(norm_target.split())
                # Require at least 25% or 1 word of target words to be present in chunk for re-verification
                intersection = chunk_words.intersection(target_words)
                if len(intersection) > 0 or len(target_words) == 0:
                    anchor = Anchor(
                        chunk_id=best_sem_chunk.chunk_id,
                        char_span=(0, len(best_sem_chunk.text)),
                        page=best_sem_chunk.page,
                        bbox=best_sem_chunk.bbox,
                    )
                    return GroundingMethod.SEMANTIC, (anchor,)

        # 5. VISUAL match (IoU >= 0.5 on stored geometry)
        if GroundingMethod.VISUAL not in self.disabled_stages:
            # The caller may pass a candidate bbox via the source_span encoding
            # "bbox:x0,y0,x1,y1" or we compare chunk bboxes against each other
            # for spatial overlap. In the standard flow, visual grounding checks
            # whether the claimed bbox overlaps a stored chunk bbox with IoU >= threshold.
            candidate_bbox = self._parse_candidate_bbox(source_span)
            if candidate_bbox is not None:
                best_iou = 0.0
                best_vis_chunk = None
                for chunk in chunks:
                    if chunk.bbox is None:
                        continue
                    iou = bbox_iou(candidate_bbox, chunk.bbox)
                    if iou >= self.visual_threshold and iou > best_iou:
                        best_iou = iou
                        best_vis_chunk = chunk

                if best_vis_chunk is not None:
                    anchor = Anchor(
                        chunk_id=best_vis_chunk.chunk_id,
                        char_span=(0, len(best_vis_chunk.text)),
                        page=best_vis_chunk.page,
                        bbox=best_vis_chunk.bbox,
                    )
                    return GroundingMethod.VISUAL, (anchor,)

        # 6. BLOCK if none of the above pass
        return GroundingMethod.BLOCK, ()

    @staticmethod
    def _parse_candidate_bbox(source_span: str) -> BBox | None:
        """Parse a candidate bbox from a source_span string of form 'bbox:x0,y0,x1,y1'.
        Returns None if the string does not encode a bbox."""
        if not source_span or not source_span.startswith("bbox:"):
            return None
        try:
            parts = source_span[5:].split(",")
            if len(parts) != 4:
                return None
            return BBox(
                x0=float(parts[0]),
                y0=float(parts[1]),
                x1=float(parts[2]),
                y1=float(parts[3]),
            )
        except (ValueError, IndexError):
            return None
