# PROVENANCE: original | clean-room Email/comms domain oracles per VERIFICATION_ORACLES.md
"""Email/comms domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``draft_readback`` — compose+save a draft to a local Maildir, RE-OPEN,
     assert To/Cc/From/Subject/Body/attachment names+bytes match spec.
     KILL-PROOF: alter a header/body or drop an attachment → FAILS.

  2. ``mailbox_structure_readback`` — draft count + message-id + folder
     integrity after add. KILL-PROOF: expect wrong count → FAILS.

Both oracles are KILL-PROVEN: perturbing the draft (altered header, dropped
attachment, wrong count) causes a hard failure.

HONEST DEGRADATION:
  If the mailbox path is missing or unreadable, the oracles raise
  ``EmailMailboxUnavailableError`` — they never claim success on an
  inaccessible mailbox.

All operations are fully offline. No network calls. No LLM. No cloud.
No external dependencies (pure stdlib). No AGPL/GPL.
"""

from __future__ import annotations

import hashlib

from kairo.domains.email.engine import (
    DraftSpec,
    compose_draft,
    read_drafts,
    read_mailbox_structure,
    save_draft,
)


# ---------------------------------------------------------------------------
# Oracle 1: draft_readback
# ---------------------------------------------------------------------------


def draft_readback(
    mailbox_path: str,
    spec: DraftSpec,
    folder: str = "drafts",
) -> bool:
    """Oracle: compose+save a draft, RE-OPEN, assert all fields match spec.

    KILL-PROOF: alter a header/body or drop an attachment → FAILS.

    Args:
        mailbox_path: Path to the Maildir directory.
        spec:         DraftSpec to compose, save, and verify.
        folder:       Maildir folder name (default: "drafts").

    Returns:
        True if the re-opened draft matches the spec exactly.

    Raises:
        AssertionError: If any field doesn't match.
        EmailMailboxUnavailableError: If the mailbox is missing.
    """
    # Compose and save
    msg = compose_draft(spec)
    our_msgid = msg["Message-ID"]
    save_draft(mailbox_path, msg, folder=folder, create=True)

    # Re-open and verify by Message-ID
    return verify_draft_readback(mailbox_path, spec, our_msgid, folder=folder)


def verify_draft_readback(
    mailbox_path: str,
    spec: DraftSpec,
    message_id: str,
    folder: str = "drafts",
) -> bool:
    """Oracle: RE-OPEN mailbox, find draft by Message-ID, assert all fields match.

    This is the read-back-only portion of draft_readback. It does NOT compose
    or save — it only reads and verifies. Used by kill-proofs that tamper with
    the mailbox after saving.

    KILL-PROOF: alter a header/body or drop an attachment → FAILS.

    Args:
        mailbox_path: Path to the Maildir directory.
        spec:         DraftSpec to verify against.
        message_id:   Message-ID of the draft to find and verify.
        folder:       Maildir folder name (default: "drafts").

    Returns:
        True if the re-opened draft matches the spec exactly.

    Raises:
        AssertionError: If any field doesn't match.
        EmailMailboxUnavailableError: If the mailbox is missing.
    """
    # Re-open and read back
    readback = read_drafts(mailbox_path, folder=folder)

    # Find our draft by Message-ID
    found = None
    for rb in readback:
        if rb.message_id == message_id:
            found = rb
            break

    if found is None:
        raise AssertionError(
            f"draft_readback FAILED: saved draft with Message-ID '{message_id}' "
            f"not found in readback. Got {len(readback)} message(s)."
        )

    # Check To
    if found.to != spec.to:
        raise AssertionError(
            f"draft_readback FAILED: To mismatch.\n"
            f"  Expected: {spec.to}\n"
            f"  Got:      {found.to}"
        )

    # Check From
    if found.from_ != spec.from_:
        raise AssertionError(
            f"draft_readback FAILED: From mismatch.\n"
            f"  Expected: {spec.from_}\n"
            f"  Got:      {found.from_}"
        )

    # Check Subject
    if found.subject != spec.subject:
        raise AssertionError(
            f"draft_readback FAILED: Subject mismatch.\n"
            f"  Expected: {spec.subject}\n"
            f"  Got:      {found.subject}"
        )

    # Check Cc
    expected_cc = spec.cc if spec.cc else ""
    if found.cc != expected_cc:
        raise AssertionError(
            f"draft_readback FAILED: Cc mismatch.\n"
            f"  Expected: {expected_cc}\n"
            f"  Got:      {found.cc}"
        )

    # Check Body
    if found.body != spec.body:
        raise AssertionError(
            f"draft_readback FAILED: Body mismatch.\n"
            f"  Expected: {spec.body!r}\n"
            f"  Got:      {found.body!r}"
        )

    # Check In-Reply-To
    expected_irt = spec.in_reply_to if spec.in_reply_to else ""
    if found.in_reply_to != expected_irt:
        raise AssertionError(
            f"draft_readback FAILED: In-Reply-To mismatch.\n"
            f"  Expected: {expected_irt}\n"
            f"  Got:      {found.in_reply_to}"
        )

    # Check References
    if found.references != spec.references:
        raise AssertionError(
            f"draft_readback FAILED: References mismatch.\n"
            f"  Expected: {spec.references}\n"
            f"  Got:      {found.references}"
        )

    # Check attachment names
    expected_names = [a.filename for a in spec.attachments]
    if sorted(found.attachment_names) != sorted(expected_names):
        raise AssertionError(
            f"draft_readback FAILED: attachment names mismatch.\n"
            f"  Expected: {sorted(expected_names)}\n"
            f"  Got:      {sorted(found.attachment_names)}"
        )

    # Check attachment bytes
    for att in spec.attachments:
        if att.filename not in found.attachment_bytes:
            raise AssertionError(
                f"draft_readback FAILED: attachment '{att.filename}' "
                f"missing from readback."
            )
        actual = found.attachment_bytes[att.filename]
        actual_hash = hashlib.sha256(actual).hexdigest()
        expected_hash = hashlib.sha256(att.content).hexdigest()
        if actual_hash != expected_hash:
            raise AssertionError(
                f"draft_readback FAILED: attachment '{att.filename}' "
                f"bytes mismatch.\n"
                f"  Expected SHA-256: {expected_hash}\n"
                f"  Got SHA-256:      {actual_hash}"
            )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: mailbox_structure_readback
# ---------------------------------------------------------------------------


def mailbox_structure_readback(
    mailbox_path: str,
    expected_count: int,
    folder: str = "drafts",
) -> bool:
    """Oracle: draft count + message-id + folder integrity after add.

    KILL-PROOF: expect wrong count → FAILS.

    Args:
        mailbox_path:    Path to the Maildir directory.
        expected_count:  Expected number of messages in the folder.
        folder:          Maildir folder name (default: "drafts").

    Returns:
        True if the folder structure matches expectations.

    Raises:
        AssertionError: If message count doesn't match or folder is missing.
        EmailMailboxUnavailableError: If the mailbox is missing.
    """
    structure = read_mailbox_structure(mailbox_path, folder=folder)

    if structure.message_count != expected_count:
        raise AssertionError(
            f"mailbox_structure_readback FAILED: message count mismatch.\n"
            f"  Expected: {expected_count}\n"
            f"  Got:      {structure.message_count}\n"
            f"  Message IDs: {structure.message_ids}"
        )

    # Check that all message IDs are non-empty
    for mid in structure.message_ids:
        if not mid:
            raise AssertionError(
                "mailbox_structure_readback FAILED: found a message with "
                "empty Message-ID header."
            )

    # Check folder name matches
    if structure.folder != folder:
        raise AssertionError(
            f"mailbox_structure_readback FAILED: folder name mismatch.\n"
            f"  Expected: {folder}\n"
            f"  Got:      {structure.folder}"
        )

    return True
