# PROVENANCE: original | clean-room Research/notes domain engine per DOMAIN_BUILD_TEMPLATE.md
"""Research/notes domain engine — real markdown vault with [[wikilinks]] + backlinks.

Implements the ``backlink_integrity`` and ``graph_readback`` oracles from
specs/VERIFICATION_ORACLES.md for the Research/notes domain.

ARCHITECTURE:
  1. Pure-Python markdown vault engine (stdlib only — re, pathlib, dataclasses).
  2. Parses [[wikilinks]] from .md files, builds a document graph.
  3. Backlinks are computed as the reverse edge of forward links.
  4. Create/edit/rename notes and update all referencing links.

HONEST DEGRADATION:
  If the vault path is missing or unreadable, the engine FAILS LOUD:
  "notes vault unavailable — path does not exist or is not a directory"
  It NEVER claims success on an unparsed vault.

All operations are fully offline. No network calls. No LLM. No cloud.
No external dependencies (pure stdlib). No AGPL/GPL.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

log = logging.getLogger("kairo.notes")

# Regex for [[wikilinks]] — captures the note name (optionally with alias)
# Supports [[Note Name]] and [[Note Name|Display Text]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NotesVaultUnavailableError(RuntimeError):
    """Raised when the vault path is missing or unreadable — honest degradation."""

    pass


class NotesError(RuntimeError):
    """Raised when a notes operation fails."""

    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class NoteInfo:
    """Information about a single note in the vault."""

    name: str  # note name without .md extension
    file_path: str
    forward_links: list[str]  # note names this note links TO
    backlinks: list[str]  # note names that link TO this note
    content: str = ""


@dataclass
class VaultGraph:
    """Full document graph of a markdown vault."""

    notes: dict[str, NoteInfo] = dc_field(default_factory=dict)

    @property
    def note_count(self) -> int:
        return len(self.notes)

    @property
    def edge_count(self) -> int:
        return sum(len(n.forward_links) for n in self.notes.values())

    def get_dangling_links(self) -> list[tuple[str, str]]:
        """Return (source_note, target_note) pairs where target doesn't exist."""
        dangling = []
        for name, note in self.notes.items():
            for link in note.forward_links:
                if link not in self.notes:
                    dangling.append((name, link))
        return dangling


@dataclass
class NotesResult:
    """Structured result of a notes pipeline run."""

    ok: bool
    vault_graph: VaultGraph | None = None
    error: str = ""
    audit_log_json: str = ""
    egress_report_json: str = ""
    doc_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "note_count": self.vault_graph.note_count if self.vault_graph else 0,
            "edge_count": self.vault_graph.edge_count if self.vault_graph else 0,
            "dangling_links": len(self.vault_graph.get_dangling_links()) if self.vault_graph else 0,
            "error": self.error,
            "doc_hash": self.doc_hash,
        }


# ---------------------------------------------------------------------------
# Vault parsing
# ---------------------------------------------------------------------------


def parse_vault(vault_path: str) -> VaultGraph:
    """Parse a markdown vault and build the document graph.

    Args:
        vault_path: Path to the vault directory containing .md files.

    Returns:
        VaultGraph with all notes, forward links, and backlinks.

    Raises:
        NotesVaultUnavailableError: If the vault path doesn't exist.
        NotesError: If parsing fails.
    """
    vault = Path(vault_path).resolve()

    if not vault.exists():
        raise NotesVaultUnavailableError(
            f"notes vault unavailable — path does not exist: {vault}"
        )
    if not vault.is_dir():
        raise NotesVaultUnavailableError(
            f"notes vault unavailable — path is not a directory: {vault}"
        )

    # Collect all .md files
    md_files = sorted(vault.rglob("*.md"))
    notes: dict[str, NoteInfo] = {}

    for md_file in md_files:
        # Note name is the filename without .md extension
        note_name = md_file.stem

        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            raise NotesError(f"Failed to read {md_file}: {e}") from e

        # Extract forward links via [[wikilinks]]
        forward_links = _extract_wikilinks(content)

        notes[note_name] = NoteInfo(
            name=note_name,
            file_path=str(md_file),
            forward_links=forward_links,
            backlinks=[],  # computed below
            content=content,
        )

    # Compute backlinks (reverse edges)
    for source_name, source_note in notes.items():
        for target_name in source_note.forward_links:
            if target_name in notes:
                notes[target_name].backlinks.append(source_name)

    # Sort backlinks for determinism
    for note in notes.values():
        note.backlinks.sort()

    return VaultGraph(notes=notes)


def _extract_wikilinks(content: str) -> list[str]:
    """Extract [[wikilink]] targets from markdown content.

    Returns a sorted list of unique note names (without .md extension).
    Links to nonexistent notes are included (for dangling-link detection).
    """
    matches = _WIKILINK_RE.findall(content)
    # Deduplicate and sort
    unique = sorted(set(m.strip() for m in matches))
    return unique


# ---------------------------------------------------------------------------
# Vault mutation
# ---------------------------------------------------------------------------


def create_note(vault_path: str, note_name: str, content: str) -> str:
    """Create a new note in the vault.

    Args:
        vault_path: Path to the vault directory.
        note_name: Name for the new note (without .md).
        content: Markdown content of the note.

    Returns:
        The absolute path of the created note.

    Raises:
        NotesError: If the note already exists or creation fails.
    """
    vault = Path(vault_path).resolve()
    note_path = vault / f"{note_name}.md"

    if note_path.exists():
        raise NotesError(f"Note already exists: {note_name}")

    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")
    return str(note_path)


def edit_note(vault_path: str, note_name: str, content: str) -> str:
    """Edit (overwrite) an existing note in the vault.

    Args:
        vault_path: Path to the vault directory.
        note_name: Name of the note to edit (without .md).
        content: New markdown content.

    Returns:
        The absolute path of the edited note.

    Raises:
        NotesError: If the note doesn't exist.
    """
    vault = Path(vault_path).resolve()
    note_path = vault / f"{note_name}.md"

    if not note_path.exists():
        raise NotesError(f"Note not found: {note_name}")

    note_path.write_text(content, encoding="utf-8")
    return str(note_path)


def rename_note(vault_path: str, old_name: str, new_name: str) -> str:
    """Rename a note and update all [[wikilinks]] that reference it.

    Args:
        vault_path: Path to the vault directory.
        old_name: Current note name (without .md).
        new_name: New note name (without .md).

    Returns:
        The absolute path of the renamed note.

    Raises:
        NotesError: If the note doesn't exist or new name is taken.
    """
    vault = Path(vault_path).resolve()
    old_path = vault / f"{old_name}.md"
    new_path = vault / f"{new_name}.md"

    if not old_path.exists():
        raise NotesError(f"Note not found: {old_name}")
    if new_path.exists():
        raise NotesError(f"Note already exists: {new_name}")

    # Rename the file
    old_path.rename(new_path)

    # Update all [[wikilinks]] in all .md files that reference old_name
    old_link_pattern = f"[[{old_name}]]"
    new_link_pattern = f"[[{new_name}]]"
    # Also handle alias syntax: [[Old Name|Display]] → [[New Name|Display]]
    old_alias_pattern = re.compile(rf"\[\[{re.escape(old_name)}\|([^\]]+)\]\]")
    new_alias_replacement = rf"[[{new_name}|\1]]"

    for md_file in vault.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        original = content

        # Replace plain wikilinks
        content = content.replace(old_link_pattern, new_link_pattern)

        # Replace aliased wikilinks
        content = old_alias_pattern.sub(new_alias_replacement, content)

        if content != original:
            md_file.write_text(content, encoding="utf-8")

    return str(new_path)


# ---------------------------------------------------------------------------
# Pipeline with trust stack integration
# ---------------------------------------------------------------------------


def notes_pipeline(
    vault_path: str,
    private_key: Any = None,
    author: str = "Kairo Notes",
) -> NotesResult:
    """Run the notes pipeline with trust stack integration.

    1. Parse the vault and build the document graph.
    2. Check for dangling links.
    3. Emit Ed25519 audit log + zero-egress report (if private_key provided).

    Args:
        vault_path: Path to the vault directory.
        private_key: Optional Ed25519 private key for audit + egress report.
        author: Author name for audit log.

    Returns:
        NotesResult with vault graph and trust artifacts.
    """
    vault = Path(vault_path).resolve()

    # Compute doc hash from vault files
    hasher = hashlib.sha256()
    if vault.exists() and vault.is_dir():
        for md_file in sorted(vault.rglob("*.md")):
            hasher.update(md_file.read_bytes())
    doc_hash = hasher.hexdigest()

    try:
        graph = parse_vault(str(vault))
    except NotesVaultUnavailableError as e:
        return NotesResult(ok=False, error=str(e), doc_hash=doc_hash)
    except NotesError as e:
        return NotesResult(ok=False, error=str(e), doc_hash=doc_hash)

    # Check for dangling links
    dangling = graph.get_dangling_links()
    ok = len(dangling) == 0

    # Emit audit log + egress report
    audit_log_json = ""
    egress_report_json = ""
    if private_key is not None:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import generate_zero_egress_report

        audit = Ed25519AuditLog(private_key)
        audit.log_run_started(doc_hash=doc_hash, playbook_id="notes_pipeline")

        for name, note in sorted(graph.notes.items()):
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=f"note_{name}",
                clause_label=f"Note '{name}': {len(note.forward_links)} links, {len(note.backlinks)} backlinks",
                old_text="",
                new_text=f"Note '{name}': {len(note.forward_links)} forward links, "
                f"{len(note.backlinks)} backlinks",
                citation="markdown-vault",
                rationale="Note parsed from markdown vault with wikilink graph",
            )

        if dangling:
            for source, target in dangling:
                audit.log_edit(
                    doc_hash=doc_hash,
                    clause_id=f"dangling_{source}_{target}",
                    clause_label=f"Dangling link: {source} → {target}",
                    old_text="",
                    new_text=f"Dangling link: [[{target}]] in '{source}' does not resolve",
                    citation="markdown-vault",
                    rationale="Dangling wikilink detected — target note does not exist",
                )

        total_edits = len(graph.notes) + len(dangling)
        total_flagged = len(dangling)

        audit.log_run_completed(
            doc_hash=doc_hash,
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
        )

        audit_log_json = audit.to_json()

        egress_report = generate_zero_egress_report(
            doc_hash=doc_hash,
            playbook_id="notes_pipeline",
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
            audit_log_json=audit_log_json,
            private_key=private_key,
        )
        egress_report_json = egress_report.to_json()

    return NotesResult(
        ok=ok,
        vault_graph=graph,
        audit_log_json=audit_log_json,
        egress_report_json=egress_report_json,
        doc_hash=doc_hash,
    )
