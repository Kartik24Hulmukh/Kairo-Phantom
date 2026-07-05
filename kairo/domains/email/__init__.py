# PROVENANCE: original | Email/comms domain descriptor for plugin registry
"""Email/comms domain — RFC-5322 draft composition + Maildir read-back (offline).

Registers the ``email`` CLI subcommand with sub-actions:
  - compose: compose a draft and save to a local Maildir
  - reply:   compose a reply to an existing draft (preserves threading)
  - verify:  re-open Maildir, read back drafts, verify integrity
  - list:    list drafts in a Maildir folder

The local Maildir/mbox DRAFT path is the Real, tested capability.
MAPI (Outlook COM) and IMAP-send are Experimental paths that fail loud
when unavailable — they never fake "sent".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kairo.domains.registry import Domain, register


def _register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "email",
        help="Compose email drafts (Maildir, RFC-5322, attachments, replies) — offline",
    )
    email_sub = parser.add_subparsers(dest="action", help="Email action")

    # email compose
    ec = email_sub.add_parser("compose", help="Compose a draft and save to Maildir")
    ec.add_argument("mailbox", help="Path to the Maildir directory")
    ec.add_argument("--to", required=True, help="Recipient email address(es)")
    ec.add_argument("--from", dest="from_", required=True, help="Sender email address")
    ec.add_argument("--subject", required=True, help="Email subject")
    ec.add_argument("--body", required=True, help="Email body (plain text)")
    ec.add_argument("--cc", default="", help="Cc recipient(s)")
    ec.add_argument("--attach", action="append", default=[], help="Attachment file path(s)")
    ec.add_argument("--outdir", default="email_output", help="Output directory for artifacts")

    # email reply
    er = email_sub.add_parser("reply", help="Compose a reply to an existing draft")
    er.add_argument("mailbox", help="Path to the Maildir directory")
    er.add_argument("--key", required=True, help="Mailbox key of the original message")
    er.add_argument("--from", dest="from_", required=True, help="Sender email address")
    er.add_argument("--body", required=True, help="Reply body (plain text)")
    er.add_argument("--to", default="", help="Recipient (defaults to original From)")
    er.add_argument("--outdir", default="email_output", help="Output directory for artifacts")

    # email verify
    ev = email_sub.add_parser("verify", help="Re-open Maildir and verify draft integrity")
    ev.add_argument("mailbox", help="Path to the Maildir directory")
    ev.add_argument("--folder", default="drafts", help="Maildir folder to verify")
    ev.add_argument("--outdir", default="email_output", help="Output directory for artifacts")

    # email list
    el = email_sub.add_parser("list", help="List drafts in a Maildir folder")
    el.add_argument("mailbox", help="Path to the Maildir directory")
    el.add_argument("--folder", default="drafts", help="Maildir folder to list")


def _run(args: argparse.Namespace) -> int:
    """Execute the email CLI command."""
    if args.action is None:
        print("Usage: kairo email <action> [options]", file=sys.stderr)
        return 1

    if args.action == "compose":
        return _run_compose(args)
    elif args.action == "reply":
        return _run_reply(args)
    elif args.action == "verify":
        return _run_verify(args)
    elif args.action == "list":
        return _run_list(args)
    else:
        print(f"Unknown email action: {args.action}", file=sys.stderr)
        return 1


def _run_compose(args: argparse.Namespace) -> int:
    """Compose a draft and save to Maildir."""
    from kairo.domains.email.engine import (
        AttachmentSpec,
        DraftSpec,
        compose_draft,
        save_draft,
    )

    mailbox_path = str(Path(args.mailbox).resolve())
    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load attachments
    attachments = []
    for att_path in args.attach:
        p = Path(att_path).resolve()
        if not p.exists():
            print(f"ERROR: Attachment not found: {p}", file=sys.stderr)
            return 1
        attachments.append(
            AttachmentSpec(
                filename=p.name,
                content=p.read_bytes(),
            )
        )

    spec = DraftSpec(
        to=args.to,
        from_=args.from_,
        subject=args.subject,
        body=args.body,
        cc=args.cc,
        attachments=attachments,
    )

    try:
        msg = compose_draft(spec)
        key = save_draft(mailbox_path, msg, folder="drafts", create=True)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — EMAIL DRAFT COMPOSED")
    print("=" * 60)
    print(f"  Maildir:  {mailbox_path}")
    print("  Folder:   drafts")
    print(f"  Key:      {key}")
    print(f"  To:       {spec.to}")
    print(f"  From:     {spec.from_}")
    print(f"  Subject:  {spec.subject}")
    if spec.cc:
        print(f"  Cc:       {spec.cc}")
    if attachments:
        print(f"  Attachments: {len(attachments)}")
        for att in attachments:
            print(f"    • {att.filename} ({len(att.content)} bytes)")
    print(f"  Message-ID: {msg['Message-ID']}")
    print("=" * 60)
    return 0


def _run_reply(args: argparse.Namespace) -> int:
    """Compose a reply to an existing draft."""
    import email as email_mod
    import mailbox as mailbox_mod

    from kairo.domains.email.engine import (
        reply_to,
        save_draft,
    )

    mailbox_path = str(Path(args.mailbox).resolve())
    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        md = mailbox_mod.Maildir(mailbox_path, create=False)
        drafts = md.get_folder("drafts")
        raw = drafts.get_bytes(args.key)
        if raw is None:
            print(f"ERROR: Message with key '{args.key}' not found", file=sys.stderr)
            return 1
        original = email_mod.message_from_bytes(raw, policy=email_mod.policy.default)
        md.close()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    try:
        reply_msg = reply_to(original, args.body, args.from_, args.to)
        key = save_draft(mailbox_path, reply_msg, folder="drafts", create=True)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — EMAIL REPLY COMPOSED")
    print("=" * 60)
    print(f"  Maildir:  {mailbox_path}")
    print("  Folder:   drafts")
    print(f"  Key:      {key}")
    print(f"  To:       {reply_msg['To']}")
    print(f"  From:     {args.from_}")
    print(f"  Subject:  {reply_msg['Subject']}")
    print(f"  In-Reply-To: {reply_msg.get('In-Reply-To', 'N/A')}")
    print(f"  References:  {reply_msg.get('References', 'N/A')}")
    print("=" * 60)
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    """Re-open Maildir and verify draft integrity."""
    from kairo.domains.email.engine import (
        EmailMailboxUnavailableError,
        read_drafts,
        read_mailbox_structure,
    )

    mailbox_path = str(Path(args.mailbox).resolve())
    out_dir = Path(args.outdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        readback = read_drafts(mailbox_path, folder=args.folder)
        structure = read_mailbox_structure(mailbox_path, folder=args.folder)
    except EmailMailboxUnavailableError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print("  KAIRO PHANTOM — EMAIL DRAFT VERIFICATION")
    print("=" * 60)
    print(f"  Maildir:  {mailbox_path}")
    print(f"  Folder:   {args.folder}")
    print(f"  Messages: {structure.message_count}")
    print()

    all_ok = True
    for i, rb in enumerate(readback):
        print(f"  Draft {i + 1}:")
        print(f"    Message-ID: {rb.message_id}")
        print(f"    To:         {rb.to}")
        print(f"    From:       {rb.from_}")
        print(f"    Subject:    {rb.subject}")
        if rb.cc:
            print(f"    Cc:         {rb.cc}")
        if rb.in_reply_to:
            print(f"    In-Reply-To: {rb.in_reply_to}")
        if rb.references:
            print(f"    References:  {rb.references}")
        if rb.attachment_names:
            print(f"    Attachments: {rb.attachment_names}")
        print(f"    Body:       {rb.body[:80]}{'...' if len(rb.body) > 80 else ''}")
        print()

    print(f"  Folder integrity: {'✅' if structure.message_count == len(readback) else '❌'}")
    print("=" * 60)
    return 0 if all_ok else 1


def _run_list(args: argparse.Namespace) -> int:
    """List drafts in a Maildir folder."""
    from kairo.domains.email.engine import (
        EmailMailboxUnavailableError,
        read_drafts,
    )

    mailbox_path = str(Path(args.mailbox).resolve())

    try:
        readback = read_drafts(mailbox_path, folder=args.folder)
    except EmailMailboxUnavailableError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print(f"  KAIRO PHANTOM — EMAIL DRAFTS ({args.folder})")
    print("=" * 60)
    print(f"  Maildir: {mailbox_path}")
    print(f"  Count:   {len(readback)}")
    print()

    for i, rb in enumerate(readback):
        print(f"  [{i + 1}] {rb.subject}")
        print(f"      To: {rb.to}  From: {rb.from_}")
        print(f"      Message-ID: {rb.message_id}")
        if rb.attachment_names:
            print(f"      Attachments: {rb.attachment_names}")
        print()

    print("=" * 60)
    return 0


DOMAIN = Domain(
    name="email",
    cli_name="email",
    status="Real",
    summary=(
        "draft_readback + mailbox_structure_readback — RFC-5322 email draft "
        "composition with Maildir storage, attachments, replies (In-Reply-To/"
        "References threading), kill-proven read-back, honest-degradation; "
        "MAPI/IMAP Experimental (fail-loud offline)"
    ),
    register_cli=_register_cli,
    run=_run,
    requirements=[
        "# pure-stdlib — no external dependencies required",
    ],
)

register(DOMAIN)
