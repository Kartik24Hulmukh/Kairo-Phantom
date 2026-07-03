# PROVENANCE: original | clean-room implementation of oracle `docx_tracked_changes_readback`
"""Deterministic tracked-changes read-back oracle for the Legal-redline wedge.

Implements the `docx_tracked_changes_readback` oracle required by
prompts/domains/08a_legal_redline.md and listed in specs/VERIFICATION_ORACLES.md.

It re-opens a produced ``.docx`` with python-docx and asserts, on the raw OOXML
revision markup (``w:ins`` / ``w:del``):

  (a) every INTENDED change is present as a REAL tracked revision carrying an
      author and a timestamp,
  (b) there are NO UNINTENDED edits (no unexpected revisions), and
  (c) the ORIGINAL text is recoverable by rejecting the changes, and the FINAL
      text is what you get by accepting them.

The oracle is deterministic (same input => same verdict) and ships with kill-proof
fixtures in tests/test_docx_tracked_changes_oracle.py (drop a revision, strip an
author, or tamper the recovered text => the oracle FAILS). No mocks: it runs on
real ``.docx`` files produced by the real tracked-changes engine.

Dependency: python-docx (BSD-3-Clause, BUNDLE lane per specs/TECH_MANIFEST.md).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

import docx  # python-docx, BSD-3-Clause

# OOXML wordprocessingml namespace.
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(tag: str) -> str:
    """Return the Clark-notation qualified name for a wordprocessingml tag."""
    return f"{{{_W}}}{tag}"


def _local(tag: Any) -> str:
    """Local name of an lxml element tag (namespace stripped)."""
    if not isinstance(tag, str):
        tag = str(tag)
    return tag.split("}", 1)[1] if "}" in tag else tag


def _norm(text: Any) -> str:
    """NFC-normalize and fold whitespace so comparisons are layout-insensitive."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


@dataclass(frozen=True)
class Revision:
    """A single tracked revision extracted from the document.

    kind:    "ins" (w:ins insertion) or "del" (w:del deletion).
    text:    the inserted (w:t) or deleted (w:delText) text of the revision.
    author:  value of the w:author attribute, or None if absent.
    date:    value of the w:date attribute, or None if absent.
    """

    kind: str
    text: str
    author: Optional[str]
    date: Optional[str]


def extract_revisions(path: str) -> list[Revision]:
    """Extract every w:ins / w:del revision from a .docx in document order."""
    doc = docx.Document(path)
    body = doc.element.body
    revs: list[Revision] = []
    for elem in body.iter():
        name = _local(elem.tag)
        if name == "ins":
            text = "".join(t.text or "" for t in elem.iter(_q("t")))
            revs.append(
                Revision("ins", text, elem.get(_q("author")), elem.get(_q("date")))
            )
        elif name == "del":
            text = "".join(t.text or "" for t in elem.iter(_q("delText")))
            revs.append(
                Revision("del", text, elem.get(_q("author")), elem.get(_q("date")))
            )
    return revs


def _walk(elem: Any, in_ins: bool, in_del: bool, orig: list[str], fin: list[str]) -> None:
    """Recursively collect original (reject) and final (accept) text streams.

    * A normal run's text (w:t not under a revision) belongs to BOTH streams.
    * Inserted text (w:t under w:ins) belongs to the FINAL stream only.
    * Deleted text (w:delText under w:del) belongs to the ORIGINAL stream only.
    """
    for child in elem:
        name = _local(child.tag)
        if name == "ins":
            _walk(child, True, in_del, orig, fin)
        elif name == "del":
            _walk(child, in_ins, True, orig, fin)
        elif name == "t":
            txt = child.text or ""
            if not in_del:
                fin.append(txt)
            if not in_ins and not in_del:
                orig.append(txt)
        elif name == "delText":
            # Deleted content: restored when the change is rejected.
            orig.append(child.text or "")
        else:
            _walk(child, in_ins, in_del, orig, fin)


def reconstruct_original_and_final(path: str) -> tuple[str, str]:
    """Return (original_text, final_text) reconstructed from the revision markup.

    original_text = document with all tracked changes REJECTED.
    final_text    = document with all tracked changes ACCEPTED.
    Paragraphs are joined with newlines; text is NFC/whitespace-normalized.
    """
    doc = docx.Document(path)
    orig_paras: list[str] = []
    fin_paras: list[str] = []
    for p in doc.element.body.iter(_q("p")):
        o: list[str] = []
        f: list[str] = []
        _walk(p, False, False, o, f)
        orig_paras.append("".join(o))
        fin_paras.append("".join(f))
    return _norm("\n".join(orig_paras)), _norm("\n".join(fin_paras))


def verify_docx_tracked_changes(
    path: str,
    expected_changes: list[dict],
    *,
    require_author: bool = True,
    require_date: bool = True,
    forbid_extra_revisions: bool = True,
    original_text: Optional[str] = None,
    final_text: Optional[str] = None,
) -> bool:
    """Assert a produced .docx contains exactly the intended tracked changes.

    expected_changes: list of ``{"old": str, "new": str, "author": <opt>}``.
      * ``old`` non-empty  -> expect a w:del revision whose text == old.
      * ``new`` non-empty  -> expect a w:ins revision whose text == new.
      * A change may be a pure insertion (old == "") or pure deletion (new == "").

    Raises AssertionError on any failure; returns True only when every check holds.
    Deterministic and kill-proof (see module docstring / tests).
    """
    if not isinstance(expected_changes, list) or not expected_changes:
        raise AssertionError("expected_changes must be a non-empty list of changes")

    revs = extract_revisions(path)
    # Working pools we consume as we match, so extras can be detected afterward.
    ins_pool = [r for r in revs if r.kind == "ins"]
    del_pool = [r for r in revs if r.kind == "del"]

    def _match(pool: list[Revision], want: str, kind: str, author: Optional[str]) -> None:
        want_n = _norm(want)
        for i, r in enumerate(pool):
            if _norm(r.text) != want_n:
                continue
            if require_author and not (r.author and r.author.strip()):
                raise AssertionError(
                    f"{kind} revision for {want!r} is missing a w:author attribute"
                )
            if author is not None and _norm(r.author) != _norm(author):
                continue  # author-specific match requested; keep searching
            if require_date and not (r.date and r.date.strip()):
                raise AssertionError(
                    f"{kind} revision for {want!r} is missing a w:date attribute"
                )
            pool.pop(i)
            return
        raise AssertionError(
            f"expected {kind} tracked revision with text {want!r} "
            f"(author={author!r}) not found in {path}"
        )

    for ch in expected_changes:
        old = ch.get("old", "") or ""
        new = ch.get("new", "") or ""
        author = ch.get("author")
        if not old and not new:
            raise AssertionError(f"change {ch!r} specifies neither 'old' nor 'new'")
        if old:
            _match(del_pool, old, "w:del", author)
        if new:
            _match(ins_pool, new, "w:ins", author)

    if forbid_extra_revisions and (ins_pool or del_pool):
        extra = [(r.kind, r.text) for r in (*ins_pool, *del_pool)]
        raise AssertionError(f"unintended tracked revisions present: {extra}")

    if original_text is not None or final_text is not None:
        recovered_original, recovered_final = reconstruct_original_and_final(path)
        if original_text is not None and recovered_original != _norm(original_text):
            raise AssertionError(
                "rejecting changes did not recover the original text:\n"
                f"  expected: {_norm(original_text)!r}\n"
                f"  got:      {recovered_original!r}"
            )
        if final_text is not None and recovered_final != _norm(final_text):
            raise AssertionError(
                "accepting changes did not produce the expected final text:\n"
                f"  expected: {_norm(final_text)!r}\n"
                f"  got:      {recovered_final!r}"
            )

    return True
