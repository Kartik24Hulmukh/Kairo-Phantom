# PROVENANCE: original | clean-room Email/comms domain engine per DOMAIN_BUILD_TEMPLATE.md
"""Email/comms domain engine — RFC-5322 draft composition + Maildir read-back.

Implements the ``draft_readback`` and ``mailbox_structure_readback`` oracles from
specs/VERIFICATION_ORACLES.md for the Email/comms domain.

ARCHITECTURE:
  1. Pure-Python stdlib email engine (``email``, ``mailbox``, ``pathlib``).
  2. Compose RFC-5322 messages with To/Cc/From/Subject/Body/Attachments.
  3. Store drafts in a local Maildir (file-based, no network).
  4. Re-open and read back drafts for verification.
  5. Reply composition preserving In-Reply-To/References headers.

HONEST DEGRADATION:
  If the mailbox path is missing, unwritable, or corrupted, the engine FAILS LOUD:
  "email mailbox unavailable — path does not exist or is not writable"
  It NEVER claims success on an inaccessible mailbox.

  MAPI (Outlook COM) and IMAP-send are Experimental paths that FAIL LOUD when
  unavailable (no pywin32, not on Windows, no Outlook, requires network).
  They NEVER fake "sent". The local Maildir draft path is the Real, tested
  capability.

All operations are fully offline. No network calls. No LLM. No cloud.
No external dependencies (pure stdlib). No AGPL/GPL.
"""

from __future__ import annotations

import email
import email.policy
import hashlib
import logging
import mailbox
import os
from dataclasses import dataclass, field as dc_field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

log = logging.getLogger("kairo.email")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EmailMailboxUnavailableError(RuntimeError):
    """Raised when the mailbox path is missing or unwritable — honest degradation."""

    pass


class EmailError(RuntimeError):
    """Raised when an email operation fails."""

    pass


class EmailExperimentalError(RuntimeError):
    """Raised when an Experimental path (MAPI/IMAP) is requested but unavailable.

    These paths require external dependencies or network access that cannot
    be satisfied in an offline/air-gapped environment. They NEVER fake success.
    """

    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AttachmentSpec:
    """Specification for an email attachment."""

    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "octet-stream"


@dataclass
class DraftSpec:
    """Specification for composing an email draft.

    Attributes:
        to:          Recipient email address(es), comma-separated.
        from_:       Sender email address.
        subject:     Email subject line.
        body:        Plain-text body content.
        cc:          Cc recipient(s), comma-separated (optional).
        attachments: List of AttachmentSpec objects (optional).
        in_reply_to: Message-ID being replied to (optional).
        references:  List of Message-IDs for threading (optional).
    """

    to: str
    from_: str
    subject: str
    body: str
    cc: str = ""
    attachments: list[AttachmentSpec] = dc_field(default_factory=list)
    in_reply_to: str = ""
    references: list[str] = dc_field(default_factory=list)


@dataclass
class DraftReadback:
    """Result of reading back a single draft from a mailbox.

    All fields are extracted from the re-opened message for verification.
    """

    to: str
    cc: str
    from_: str
    subject: str
    body: str
    message_id: str
    in_reply_to: str
    references: list[str]
    attachment_names: list[str]
    attachment_bytes: dict[str, bytes]

    def to_dict(self) -> dict[str, Any]:
        return {
            "to": self.to,
            "cc": self.cc,
            "from": self.from_,
            "subject": self.subject,
            "body": self.body,
            "message_id": self.message_id,
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "attachment_names": self.attachment_names,
            "attachment_sha256": {
                name: hashlib.sha256(data).hexdigest()
                for name, data in self.attachment_bytes.items()
            },
        }


@dataclass
class MailboxStructure:
    """Structure of a mailbox folder after inspection."""

    folder: str
    message_count: int
    message_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "folder": self.folder,
            "message_count": self.message_count,
            "message_ids": self.message_ids,
        }


@dataclass
class EmailResult:
    """Structured result of an email pipeline run."""

    ok: bool
    drafts_created: int = 0
    readback: list[DraftReadback] = dc_field(default_factory=list)
    error: str = ""
    audit_log_json: str = ""
    egress_report_json: str = ""
    doc_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "drafts_created": self.drafts_created,
            "readback_count": len(self.readback),
            "error": self.error,
            "doc_hash": self.doc_hash,
        }


# ---------------------------------------------------------------------------
# Draft composition
# ---------------------------------------------------------------------------


def compose_draft(spec: DraftSpec) -> EmailMessage:
    """Compose an RFC-5322 email message from a DraftSpec.

    Args:
        spec: Draft specification with headers, body, and optional attachments.

    Returns:
        An EmailMessage ready to be saved to a mailbox.

    Raises:
        EmailError: If composition fails.
    """
    msg = EmailMessage()
    msg["From"] = spec.from_
    msg["To"] = spec.to
    if spec.cc:
        msg["Cc"] = spec.cc
    msg["Subject"] = spec.subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="kairo-phantom.local")

    if spec.in_reply_to:
        msg["In-Reply-To"] = spec.in_reply_to
    if spec.references:
        msg["References"] = " ".join(spec.references)

    msg.set_content(spec.body)

    for att in spec.attachments:
        msg.add_attachment(
            att.content,
            maintype=att.maintype,
            subtype=att.subtype,
            filename=att.filename,
        )

    return msg


def reply_to(
    original: EmailMessage,
    body: str,
    from_: str,
    to: str = "",
) -> EmailMessage:
    """Compose a reply to an existing email message.

    Preserves threading by setting In-Reply-To and References headers.
    Quotes the original body with ``>`` prefixes.

    Args:
        original: The original EmailMessage to reply to.
        body:     The reply body text (will be prepended to the quote).
        from_:    Sender email address for the reply.
        to:       Recipient (defaults to the original's From address).

    Returns:
        An EmailMessage reply with proper threading headers.

    Raises:
        EmailError: If the original message lacks a Message-ID.
    """
    orig_msgid = original.get("Message-ID", "")
    if not orig_msgid:
        raise EmailError("Cannot reply: original message has no Message-ID header")

    orig_from = original.get("From", "")
    orig_subject = original.get("Subject", "")
    orig_refs = original.get("References", "")
    orig_date = original.get("Date", "")

    # Build reply subject
    if orig_subject.lower().startswith("re:"):
        reply_subject = orig_subject
    else:
        reply_subject = f"Re: {orig_subject}"

    # Build References: original References + original Message-ID
    ref_list = orig_refs.split() if orig_refs else []
    ref_list.append(orig_msgid)

    # Build quoted body
    orig_body = _extract_body(original)
    quoted_lines = []
    if orig_from:
        quoted_lines.append(f"On {orig_date}, {orig_from} wrote:")
    else:
        quoted_lines.append(f"On {orig_date}, someone wrote:")
    quoted_lines.append("")
    for line in orig_body.splitlines():
        quoted_lines.append(f"> {line}")
    quoted = "\n".join(quoted_lines)

    full_body = f"{body}\n\n{quoted}"

    # Determine recipient
    reply_to_addr = to if to else orig_from

    spec = DraftSpec(
        to=reply_to_addr,
        from_=from_,
        subject=reply_subject,
        body=full_body,
        in_reply_to=orig_msgid,
        references=ref_list,
    )
    return compose_draft(spec)


def _extract_body(msg: EmailMessage) -> str:
    """Extract the plain-text body from an EmailMessage.

    Strips the trailing newline that MIME encoding adds (RFC 5322 text bodies
    are terminated with CRLF, which get_content() preserves as a trailing \\n).
    """
    body_part = msg.get_body(preferencelist=("plain",))
    if body_part is not None:
        try:
            content = body_part.get_content()
        except Exception:
            payload = body_part.get_payload(decode=True)
            if payload:
                content = payload.decode("utf-8", errors="replace")
            else:
                content = ""
        # Strip the single trailing newline added by MIME encoding
        return content.rstrip("\n")
    return ""


# ---------------------------------------------------------------------------
# Mailbox storage (Maildir)
# ---------------------------------------------------------------------------


def _open_maildir(mailbox_path: str, create: bool = False) -> mailbox.Maildir:
    """Open a Maildir at the given path.

    Args:
        mailbox_path: Path to the Maildir directory.
        create:       If True, create the Maildir if it doesn't exist.

    Returns:
        A mailbox.Maildir instance.

    Raises:
        EmailMailboxUnavailableError: If the path is missing/unwritable.
    """
    path = Path(mailbox_path).resolve()

    if not create and not path.exists():
        raise EmailMailboxUnavailableError(
            f"email mailbox unavailable — path does not exist: {path}"
        )
    if not create and not path.is_dir():
        raise EmailMailboxUnavailableError(
            f"email mailbox unavailable — path is not a directory: {path}"
        )

    # Check writability for create mode
    if create:
        try:
            path_exists = path.exists()
        except PermissionError:
            path_exists = False
        parent = path.parent if not path_exists else path
        try:
            parent_exists = parent.exists()
        except PermissionError:
            raise EmailMailboxUnavailableError(
                f"email mailbox unavailable — path is not accessible: {path}"
            ) from None
        if parent_exists and not os.access(parent, os.W_OK):
            raise EmailMailboxUnavailableError(
                f"email mailbox unavailable — path is not writable: {path}"
            )

    try:
        return mailbox.Maildir(str(path), create=create)
    except Exception as e:
        raise EmailMailboxUnavailableError(
            f"email mailbox unavailable — cannot open Maildir: {e}"
        ) from e


def _get_or_create_folder(md: mailbox.Maildir, folder: str) -> mailbox.Maildir:
    """Get an existing folder or create it if it doesn't exist.

    Args:
        md:     The root Maildir instance.
        folder: Folder name (e.g. "drafts").

    Returns:
        A Maildir instance for the folder.
    """
    try:
        return md.get_folder(folder)
    except mailbox.NoSuchMailboxError:
        return md.add_folder(folder)


def save_draft(
    mailbox_path: str,
    msg: EmailMessage,
    folder: str = "drafts",
    create: bool = True,
) -> str:
    """Save a draft email message to a Maildir folder.

    Args:
        mailbox_path: Path to the Maildir directory.
        msg:          EmailMessage to save.
        folder:       Folder name within the Maildir (default: "drafts").
        create:       If True, create the Maildir if it doesn't exist.

    Returns:
        The mailbox key for the saved message.

    Raises:
        EmailMailboxUnavailableError: If the mailbox is unavailable or unwritable.
        EmailError: If saving fails.
    """
    md = _open_maildir(mailbox_path, create=create)
    try:
        drafts = _get_or_create_folder(md, folder)
        key = drafts.add(msg.as_bytes())
        drafts.flush()
        md.close()
        return str(key)
    except EmailMailboxUnavailableError:
        raise
    except Exception as e:
        raise EmailError(f"Failed to save draft: {e}") from e


def read_drafts(
    mailbox_path: str,
    folder: str = "drafts",
) -> list[DraftReadback]:
    """Re-open a Maildir folder and read back all draft messages.

    Args:
        mailbox_path: Path to the Maildir directory.
        folder:       Folder name within the Maildir (default: "drafts").

    Returns:
        List of DraftReadback objects, one per message.

    Raises:
        EmailMailboxUnavailableError: If the mailbox or folder doesn't exist.
        EmailError: If reading fails.
    """
    md = _open_maildir(mailbox_path, create=False)
    try:
        drafts = md.get_folder(folder)
    except mailbox.NoSuchMailboxError:
        raise EmailMailboxUnavailableError(
            f"email mailbox unavailable — folder '{folder}' does not exist in: {mailbox_path}"
        ) from None

    readbacks: list[DraftReadback] = []
    try:
        for key in drafts.iterkeys():
            raw = drafts.get_bytes(key)
            if raw is None:
                continue
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            readbacks.append(_parse_readback(msg))
    except EmailMailboxUnavailableError:
        raise
    except Exception as e:
        raise EmailError(f"Failed to read drafts: {e}") from e
    finally:
        md.close()

    return readbacks


def _parse_readback(msg: EmailMessage) -> DraftReadback:
    """Parse an EmailMessage into a DraftReadback for verification."""
    to = msg.get("To", "")
    cc = msg.get("Cc", "")
    from_ = msg.get("From", "")
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")
    in_reply_to = msg.get("In-Reply-To", "")
    refs_header = msg.get("References", "")
    references = refs_header.split() if refs_header else []

    body = _extract_body(msg)

    attachment_names: list[str] = []
    attachment_bytes: dict[str, bytes] = {}

    for att in msg.iter_attachments():
        filename = att.get_filename() or "unnamed"
        content = att.get_payload(decode=True)
        if content is None:
            # Try get_content() for modern API
            try:
                content = att.get_content()
                if isinstance(content, str):
                    content = content.encode("utf-8")
            except Exception:
                content = b""
        attachment_names.append(filename)
        attachment_bytes[filename] = content

    return DraftReadback(
        to=to,
        cc=cc,
        from_=from_,
        subject=subject,
        body=body,
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references,
        attachment_names=attachment_names,
        attachment_bytes=attachment_bytes,
    )


def read_mailbox_structure(
    mailbox_path: str,
    folder: str = "drafts",
) -> MailboxStructure:
    """Inspect a Maildir folder and return its structure.

    Args:
        mailbox_path: Path to the Maildir directory.
        folder:       Folder name within the Maildir.

    Returns:
        MailboxStructure with message count and message IDs.

    Raises:
        EmailMailboxUnavailableError: If the mailbox or folder doesn't exist.
    """
    md = _open_maildir(mailbox_path, create=False)
    try:
        drafts = md.get_folder(folder)
    except mailbox.NoSuchMailboxError:
        raise EmailMailboxUnavailableError(
            f"email mailbox unavailable — folder '{folder}' does not exist in: {mailbox_path}"
        ) from None

    message_ids: list[str] = []
    try:
        for key in drafts.iterkeys():
            raw = drafts.get_bytes(key)
            if raw is None:
                continue
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            mid = msg.get("Message-ID", "")
            message_ids.append(mid)
    finally:
        md.close()

    return MailboxStructure(
        folder=folder,
        message_count=len(message_ids),
        message_ids=message_ids,
    )


# ---------------------------------------------------------------------------
# Pipeline with trust stack integration
# ---------------------------------------------------------------------------


def _compute_doc_hash(specs: list[DraftSpec]) -> str:
    """Compute a SHA-256 hash over the draft specs for audit integrity."""
    hasher = hashlib.sha256()
    for spec in specs:
        hasher.update(spec.to.encode("utf-8"))
        hasher.update(spec.from_.encode("utf-8"))
        hasher.update(spec.subject.encode("utf-8"))
        hasher.update(spec.body.encode("utf-8"))
        if spec.cc:
            hasher.update(spec.cc.encode("utf-8"))
        if spec.in_reply_to:
            hasher.update(spec.in_reply_to.encode("utf-8"))
        for ref in spec.references:
            hasher.update(ref.encode("utf-8"))
        for att in spec.attachments:
            hasher.update(att.filename.encode("utf-8"))
            hasher.update(att.content)
    return hasher.hexdigest()


def email_pipeline(
    mailbox_path: str,
    specs: list[DraftSpec],
    private_key: Any = None,
    author: str = "Kairo Email",
) -> EmailResult:
    """Run the email pipeline with trust stack integration.

    1. Compose each draft from its spec.
    2. Save each draft to the Maildir "drafts" folder.
    3. Re-open and read back all drafts for verification.
    4. Emit Ed25519 audit log + zero-egress report (if private_key provided).

    Args:
        mailbox_path: Path to the Maildir directory.
        specs:        List of DraftSpec objects to compose and save.
        private_key:  Optional Ed25519 private key for audit + egress report.
        author:       Author name for audit log.

    Returns:
        EmailResult with readback data and trust artifacts.
    """
    doc_hash = _compute_doc_hash(specs)

    try:
        # Compose and save each draft
        for spec in specs:
            msg = compose_draft(spec)
            save_draft(mailbox_path, msg, folder="drafts", create=True)

        # Read back all drafts
        readback = read_drafts(mailbox_path, folder="drafts")
        ok = len(readback) >= len(specs)
    except EmailMailboxUnavailableError as e:
        return EmailResult(ok=False, error=str(e), doc_hash=doc_hash)
    except EmailError as e:
        return EmailResult(ok=False, error=str(e), doc_hash=doc_hash)

    # Emit audit log + egress report
    audit_log_json = ""
    egress_report_json = ""
    if private_key is not None:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import generate_zero_egress_report

        audit = Ed25519AuditLog(private_key)
        audit.log_run_started(doc_hash=doc_hash, playbook_id="email_pipeline")

        for i, spec in enumerate(specs):
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=f"draft_{i}",
                clause_label=f"Draft '{spec.subject}' to {spec.to}",
                old_text="",
                new_text=f"Composed draft: subject='{spec.subject}', "
                f"to='{spec.to}', attachments={len(spec.attachments)}",
                citation="rfc5322-maildir",
                rationale="Email draft composed and saved to local Maildir",
            )

        total_edits = len(specs)
        total_flagged = 0

        audit.log_run_completed(
            doc_hash=doc_hash,
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
        )

        audit_log_json = audit.to_json()

        egress_report = generate_zero_egress_report(
            doc_hash=doc_hash,
            playbook_id="email_pipeline",
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
            audit_log_json=audit_log_json,
            private_key=private_key,
        )
        egress_report_json = egress_report.to_json()

    return EmailResult(
        ok=ok,
        drafts_created=len(specs),
        readback=readback,
        audit_log_json=audit_log_json,
        egress_report_json=egress_report_json,
        doc_hash=doc_hash,
    )


# ---------------------------------------------------------------------------
# Experimental paths — MAPI (Outlook COM) and IMAP-send
# These are clearly-labeled Experimental and FAIL LOUD when unavailable.
# They NEVER fake "sent". The local Maildir draft path is the Real capability.
# ---------------------------------------------------------------------------


def send_via_mapi(msg: EmailMessage) -> None:
    """Send an email via MAPI (Outlook COM Automation).

    EXPERIMENTAL — requires Windows + Outlook + pywin32.
    Cannot run in an offline/air-gapped environment.

    Raises:
        EmailExperimentalError: Always, unless on Windows with Outlook + pywin32.
    """
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError:
        raise EmailExperimentalError(
            "MAPI send unavailable — pywin32 not installed. "
            "This is an Experimental path; the local Maildir draft path "
            "is the Real, tested capability."
        ) from None

    try:
        win32com.client.Dispatch("Outlook.Application")
    except Exception as e:
        raise EmailExperimentalError(
            f"MAPI send unavailable — Outlook not accessible: {e}. "
            "This is an Experimental path; the local Maildir draft path "
            "is the Real, tested capability."
        ) from e

    # If we reach here, Outlook is available — but this path is still
    # Experimental and not tested in CI. It would compose and send via COM.
    # We do NOT implement the actual send here because:
    # 1. It requires network access (violates air-gap).
    # 2. It cannot be tested offline.
    # 3. The sealed build would reject any network symbols.
    raise EmailExperimentalError(
        "MAPI send is Experimental and requires network access — "
        "disabled in sealed/offline mode. The local Maildir draft path "
        "is the Real, tested capability."
    )


def send_via_imap(msg: EmailMessage, server: str, port: int = 993) -> None:
    """Send (append) an email via IMAP APPEND to a Sent folder.

    EXPERIMENTAL — requires network access to an IMAP server.
    Cannot run in an offline/air-gapped environment.

    Raises:
        EmailExperimentalError: Always, in sealed/offline mode.
    """
    raise EmailExperimentalError(
        "IMAP send is Experimental and requires network access — "
        "disabled in sealed/offline mode. IMAP APPEND to a Sent folder "
        "needs a live server connection. The local Maildir draft path "
        "is the Real, tested capability."
    )
