# PROVENANCE: original | clean-room Research/notes domain oracles per VERIFICATION_ORACLES.md
"""Research/notes domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``backlink_integrity`` — every [[link]] resolves to an existing note;
     backlinks are bidirectionally consistent with forward links; no dangling
     links.  KILL-PROOF: add a link to a nonexistent note → FAILS.

  2. ``graph_readback`` — after an edit/rename, note count + link edges match
     the expected graph (renames update all referencing links).
     KILL-PROOF: rename a note but leave a stale link → FAILS.

Both oracles are KILL-PROVEN: perturbing the vault (dangling link, stale
reference, wrong edge count) causes a hard failure.

HONEST DEGRADATION:
  If the vault path is missing or unreadable, the oracles raise
  ``NotesVaultUnavailableError`` — they never claim success on an unparsed
  vault.

All operations are fully offline. No network calls. No LLM. No cloud.
No external dependencies (pure stdlib). No AGPL/GPL.
"""

from __future__ import annotations

from kairo.domains.notes.engine import (
    NotesVaultUnavailableError,
    parse_vault,
)


# ---------------------------------------------------------------------------
# Oracle 1: backlink_integrity
# ---------------------------------------------------------------------------


def backlink_integrity(vault_path: str) -> bool:
    """Oracle: every [[link]] resolves to an existing note; backlinks are
    bidirectionally consistent; no dangling links.

    KILL-PROOF: add a link to a nonexistent note → FAILS.

    Args:
        vault_path: Path to the vault directory.

    Returns:
        True if all links resolve and backlinks are consistent.

    Raises:
        AssertionError: If any link is dangling or backlinks are inconsistent.
        NotesVaultUnavailableError: If the vault path is missing.
    """
    graph = parse_vault(vault_path)

    # Check 1: no dangling links
    dangling = graph.get_dangling_links()
    if dangling:
        dangling_str = "; ".join(f"{s} → {t}" for s, t in dangling[:5])
        raise AssertionError(
            f"backlink_integrity FAILED: {len(dangling)} dangling link(s).\n"
            f"  Examples: {dangling_str}"
        )

    # Check 2: backlinks are bidirectionally consistent with forward links
    for name, note in graph.notes.items():
        for target in note.forward_links:
            if target in graph.notes:
                # name should appear in target's backlinks
                if name not in graph.notes[target].backlinks:
                    raise AssertionError(
                        f"backlink_integrity FAILED: '{name}' links to '{target}' "
                        f"but '{name}' is not in '{target}' backlinks.\n"
                        f"  '{target}' backlinks: {graph.notes[target].backlinks}"
                    )

    # Check 3: every backlink has a corresponding forward link
    for name, note in graph.notes.items():
        for source in note.backlinks:
            if source in graph.notes:
                if name not in graph.notes[source].forward_links:
                    raise AssertionError(
                        f"backlink_integrity FAILED: '{source}' has backlink to '{name}' "
                        f"but '{name}' is not in '{source}' forward links.\n"
                        f"  '{source}' forward links: {graph.notes[source].forward_links}"
                    )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: graph_readback
# ---------------------------------------------------------------------------


def graph_readback(
    vault_path: str,
    expected_note_count: int,
    expected_edges: dict[str, list[str]] | None = None,
) -> bool:
    """Oracle: note count + link edges match the expected graph after edit/rename.

    KILL-PROOF: rename a note but leave a stale link → FAILS (edge mismatch).

    Args:
        vault_path: Path to the vault directory.
        expected_note_count: Expected number of notes in the vault.
        expected_edges: Optional dict mapping note_name → sorted list of forward
                        link targets. If provided, each note's forward links
                        must match exactly.

    Returns:
        True if the graph matches expectations.

    Raises:
        AssertionError: If note count or edges don't match.
        NotesVaultUnavailableError: If the vault path is missing.
    """
    graph = parse_vault(vault_path)

    # Check note count
    if graph.note_count != expected_note_count:
        actual_names = sorted(graph.notes.keys())
        raise AssertionError(
            f"graph_readback FAILED: note count mismatch.\n"
            f"  Expected: {expected_note_count}\n"
            f"  Got:      {graph.note_count}\n"
            f"  Notes: {actual_names}"
        )

    # Check edges if provided
    if expected_edges is not None:
        for note_name, expected_targets in expected_edges.items():
            if note_name not in graph.notes:
                raise AssertionError(
                    f"graph_readback FAILED: expected note '{note_name}' not found in vault.\n"
                    f"  Available: {sorted(graph.notes.keys())}"
                )
            actual_targets = sorted(graph.notes[note_name].forward_links)
            expected_sorted = sorted(expected_targets)
            if actual_targets != expected_sorted:
                raise AssertionError(
                    f"graph_readback FAILED: forward links for '{note_name}' mismatch.\n"
                    f"  Expected: {expected_sorted}\n"
                    f"  Got:      {actual_targets}"
                )

    return True
