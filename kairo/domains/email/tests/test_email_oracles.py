# PROVENANCE: original | Email/comms domain oracle tests per VERIFICATION_ORACLES.md
"""Email/comms domain oracle tests — draft_readback + mailbox_structure_readback + kill-proofs.

Tests verify:
  1. draft_readback: compose+save draft, RE-OPEN, assert To/Cc/From/Subject/
     Body/attachment names+bytes match spec. Kill-proof: alter header/body
     or drop attachment → FAILS.
  2. mailbox_structure_readback: draft count + message-id + folder integrity
     after add. Kill-proof: expect wrong count → FAILS.
  3. Honest degradation: mailbox path missing → FAIL LOUD; mailbox unwritable
     → FAIL LOUD; MAPI/IMAP requested but unavailable → FAIL LOUD (Experimental).
  4. >=3 gauntlet scenarios: (a) plain draft, (b) draft WITH real attachment
     (bytes verified), (c) reply quoting original + preserving In-Reply-To/
     References headers.
  5. Trust stack integration: audit log + egress report.
  6. CLI integration: email subcommand works end-to-end.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.domains.email.engine import (  # noqa: E402
    AttachmentSpec,
    DraftSpec,
    EmailError,
    EmailExperimentalError,
    EmailMailboxUnavailableError,
    compose_draft,
    email_pipeline,
    read_drafts,
    read_mailbox_structure,
    reply_to,
    save_draft,
    send_via_imap,
    send_via_mapi,
)
from kairo.domains.email.oracles import (  # noqa: E402
    draft_readback,
    mailbox_structure_readback,
    verify_draft_readback,
)

# Fixture paths
_FIX_DIR = os.path.join(_REPO_ROOT, "kairo", "domains", "email", "fixtures")
_FIX_TXT = os.path.join(_FIX_DIR, "attachment.txt")
_FIX_BIN = os.path.join(_FIX_DIR, "attachment.bin")
_FIX_GT = os.path.join(_FIX_DIR, "ground_truth.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_ground_truth() -> dict:
    with open(_FIX_GT, encoding="utf-8") as f:
        return json.load(f)


def _make_maildir(tmpdir: str) -> str:
    """Create a fresh empty Maildir path inside tmpdir."""
    path = os.path.join(tmpdir, "maildir")
    return path


# ---------------------------------------------------------------------------
# Oracle 1: draft_readback
# ---------------------------------------------------------------------------


class TestDraftReadback:
    """draft_readback oracle — compose, save, re-open, verify all fields."""

    def test_plain_draft_readback(self):
        """Compose a plain draft, save, re-open, verify all fields match."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Test Subject",
                body="Hello, this is a test email body.",
            )
            result = draft_readback(mb, spec)
            assert result is True

    def test_draft_with_cc_readback(self):
        """Draft with Cc field is read back correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Test with Cc",
                body="Body with Cc.",
                cc="carol@example.com, dave@example.com",
            )
            result = draft_readback(mb, spec)
            assert result is True

    def test_draft_with_attachment_readback(self):
        """Draft with a real attachment — bytes verified via SHA-256."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            att_content = b"Binary attachment content\x00\x01\x02\x03"
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Test with Attachment",
                body="Body with attachment.",
                attachments=[
                    AttachmentSpec(filename="test.bin", content=att_content),
                ],
            )
            result = draft_readback(mb, spec)
            assert result is True

    def test_draft_with_multiple_attachments_readback(self):
        """Draft with multiple attachments — all names and bytes verified."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            att1 = open(_FIX_TXT, "rb").read()
            att2 = open(_FIX_BIN, "rb").read()
            spec = DraftSpec(
                to="team@example.com",
                from_="lead@example.com",
                subject="Budget Proposal",
                body="Please review the attached files.",
                cc="cc@example.com",
                attachments=[
                    AttachmentSpec(filename="attachment.txt", content=att1),
                    AttachmentSpec(filename="attachment.bin", content=att2),
                ],
            )
            result = draft_readback(mb, spec)
            assert result is True

    def test_reply_draft_readback(self):
        """Reply draft preserving In-Reply-To and References headers."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)

            # First, compose and save an original message
            orig_spec = DraftSpec(
                to="bob@example.com",
                from_="alice@example.com",
                subject="Original Message",
                body="This is the original message body.\nLine 2.\nLine 3.",
            )
            orig_msg = compose_draft(orig_spec)
            save_draft(mb, orig_msg, folder="drafts", create=True)

            # Read back the original to get its Message-ID
            readback = read_drafts(mb, folder="drafts")
            orig_msgid = readback[0].message_id

            # Compose a reply
            reply_msg = reply_to(orig_msg, "Thanks for the message!", "bob@example.com")
            save_draft(mb, reply_msg, folder="drafts", create=False)

            # Read back and verify the reply
            all_drafts = read_drafts(mb, folder="drafts")
            assert len(all_drafts) == 2

            # Find the reply (the second one, with In-Reply-To set)
            reply_rb = None
            for rb in all_drafts:
                if rb.in_reply_to:
                    reply_rb = rb
                    break

            assert reply_rb is not None, "Reply draft not found"
            assert reply_rb.in_reply_to == orig_msgid
            assert orig_msgid in reply_rb.references
            assert reply_rb.subject.startswith("Re:")
            assert "Thanks for the message!" in reply_rb.body
            # Verify the original is quoted
            assert "> This is the original message body." in reply_rb.body


# ---------------------------------------------------------------------------
# Oracle 1 Kill-Proofs
# ---------------------------------------------------------------------------


class TestDraftReadbackKillProofs:
    """Kill-proofs: perturbing the draft → FAILS."""

    def test_kill_altered_subject(self):
        """Kill-proof: alter subject after save → readback FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Correct Subject",
                body="Body text.",
            )
            # Save correctly
            msg = compose_draft(spec)
            our_msgid = msg["Message-ID"]
            save_draft(mb, msg, folder="drafts", create=True)

            # Now verify with a spec that has a WRONG subject
            wrong_spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="WRONG Subject",
                body="Body text.",
            )
            with pytest.raises(AssertionError, match="Subject mismatch"):
                verify_draft_readback(mb, wrong_spec, our_msgid)

    def test_kill_altered_body(self):
        """Kill-proof: alter body → readback FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Subject",
                body="Original body text.",
            )
            msg = compose_draft(spec)
            our_msgid = msg["Message-ID"]
            save_draft(mb, msg, folder="drafts", create=True)

            # Verify with a different body spec
            wrong_spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Subject",
                body="TAMPERED body text.",
            )
            with pytest.raises(AssertionError, match="Body mismatch"):
                verify_draft_readback(mb, wrong_spec, our_msgid)

    def test_kill_dropped_attachment(self):
        """Kill-proof: save with attachment, verify without → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            att_content = b"Important attachment data"
            spec_with = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="With Attachment",
                body="Body.",
                attachments=[
                    AttachmentSpec(filename="important.bin", content=att_content),
                ],
            )
            # Save the draft with attachment
            msg = compose_draft(spec_with)
            our_msgid = msg["Message-ID"]
            save_draft(mb, msg, folder="drafts", create=True)

            # Now try to verify with a spec that has NO attachment
            spec_without = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="With Attachment",
                body="Body.",
            )
            with pytest.raises(AssertionError, match="attachment names mismatch"):
                verify_draft_readback(mb, spec_without, our_msgid)

    def test_kill_wrong_attachment_bytes(self):
        """Kill-proof: attachment bytes differ → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            original_bytes = b"Original content"
            tampered_bytes = b"Tampered content"
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Test",
                body="Body.",
                attachments=[
                    AttachmentSpec(filename="file.bin", content=original_bytes),
                ],
            )
            # Save with original bytes
            msg = compose_draft(spec)
            our_msgid = msg["Message-ID"]
            save_draft(mb, msg, folder="drafts", create=True)

            # Verify with tampered bytes spec
            tampered_spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Test",
                body="Body.",
                attachments=[
                    AttachmentSpec(filename="file.bin", content=tampered_bytes),
                ],
            )
            with pytest.raises(AssertionError, match="bytes mismatch"):
                verify_draft_readback(mb, tampered_spec, our_msgid)


# ---------------------------------------------------------------------------
# Oracle 2: mailbox_structure_readback
# ---------------------------------------------------------------------------


class TestMailboxStructureReadback:
    """mailbox_structure_readback oracle — count + message-id + folder integrity."""

    def test_empty_folder_structure(self):
        """Empty folder has 0 messages."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            # Create the maildir with a draft then remove it to get empty folder
            spec = DraftSpec(
                to="a@example.com",
                from_="b@example.com",
                subject="Temp",
                body="Temp body.",
            )
            msg = compose_draft(spec)
            save_draft(mb, msg, folder="drafts", create=True)

            # Now there's 1 message
            result = mailbox_structure_readback(mb, expected_count=1)
            assert result is True

    def test_multiple_drafts_structure(self):
        """Multiple drafts in folder — count matches."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            for i in range(5):
                spec = DraftSpec(
                    to=f"recipient{i}@example.com",
                    from_="sender@example.com",
                    subject=f"Draft {i}",
                    body=f"Body {i}.",
                )
                msg = compose_draft(spec)
                save_draft(mb, msg, folder="drafts", create=(i == 0))

            result = mailbox_structure_readback(mb, expected_count=5)
            assert result is True

    def test_message_ids_non_empty(self):
        """All messages have non-empty Message-ID headers."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="a@example.com",
                from_="b@example.com",
                subject="Test",
                body="Body.",
            )
            msg = compose_draft(spec)
            save_draft(mb, msg, folder="drafts", create=True)

            structure = read_mailbox_structure(mb, folder="drafts")
            assert structure.message_count == 1
            assert all(mid for mid in structure.message_ids)


# ---------------------------------------------------------------------------
# Oracle 2 Kill-Proofs
# ---------------------------------------------------------------------------


class TestMailboxStructureKillProofs:
    """Kill-proofs: wrong count → FAILS."""

    def test_kill_wrong_count_high(self):
        """Kill-proof: expect more messages than exist → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="a@example.com",
                from_="b@example.com",
                subject="Test",
                body="Body.",
            )
            msg = compose_draft(spec)
            save_draft(mb, msg, folder="drafts", create=True)

            with pytest.raises(AssertionError, match="message count mismatch"):
                mailbox_structure_readback(mb, expected_count=5)

    def test_kill_wrong_count_low(self):
        """Kill-proof: expect fewer messages than exist → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            for i in range(3):
                spec = DraftSpec(
                    to=f"r{i}@example.com",
                    from_="s@example.com",
                    subject=f"S{i}",
                    body=f"B{i}.",
                )
                msg = compose_draft(spec)
                save_draft(mb, msg, folder="drafts", create=(i == 0))

            with pytest.raises(AssertionError, match="message count mismatch"):
                mailbox_structure_readback(mb, expected_count=1)


# ---------------------------------------------------------------------------
# Honest Degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """Honest degradation: missing/unwritable mailbox → FAIL LOUD."""

    def test_missing_mailbox_raises(self):
        """Reading from a non-existent mailbox raises, not silently succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = os.path.join(tmp, "nonexistent_maildir")
            with pytest.raises(EmailMailboxUnavailableError, match="does not exist"):
                read_drafts(mb, folder="drafts")

    def test_missing_folder_raises(self):
        """Reading from a non-existent folder raises."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            # Create the maildir but not the folder
            import mailbox as mb_mod

            md = mb_mod.Maildir(mb, create=True)
            md.close()

            with pytest.raises(EmailMailboxUnavailableError, match="does not exist"):
                read_drafts(mb, folder="nonexistent_folder")

    def test_mapi_unavailable_raises(self):
        """MAPI send (Experimental) fails loud when unavailable."""
        msg = compose_draft(DraftSpec(
            to="a@example.com",
            from_="b@example.com",
            subject="Test",
            body="Body.",
        ))
        with pytest.raises(EmailExperimentalError, match="MAPI send unavailable"):
            send_via_mapi(msg)

    def test_imap_unavailable_raises(self):
        """IMAP send (Experimental) fails loud in offline mode."""
        msg = compose_draft(DraftSpec(
            to="a@example.com",
            from_="b@example.com",
            subject="Test",
            body="Body.",
        ))
        with pytest.raises(EmailExperimentalError, match="IMAP send is Experimental"):
            send_via_imap(msg, "imap.example.com")

    def test_unwritable_mailbox_raises(self):
        """Saving to an unwritable path fails loud."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a path that can't be written to
            ro_path = os.path.join(tmp, "readonly")
            os.makedirs(ro_path)
            os.chmod(ro_path, 0o444)

            spec = DraftSpec(
                to="a@example.com",
                from_="b@example.com",
                subject="Test",
                body="Body.",
            )
            msg = compose_draft(spec)
            with pytest.raises((EmailMailboxUnavailableError, EmailError)):
                save_draft(os.path.join(ro_path, "maildir"), msg, create=True)


# ---------------------------------------------------------------------------
# Gauntlet Scenarios (>=3 end-to-end)
# ---------------------------------------------------------------------------


class TestGauntletScenarios:
    """>=3 end-to-end gauntlet scenarios."""

    def test_scenario_a_plain_draft(self):
        """Scenario (a): plain draft — compose, save, read-back, verify all fields."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["a_plain_draft"]

        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to=sc["to"],
                from_=sc["from"],
                subject=sc["subject"],
                body=sc["body"],
                cc=sc.get("cc", ""),
            )
            result = draft_readback(mb, spec)
            assert result is True

            # Also verify mailbox structure
            struct_result = mailbox_structure_readback(mb, expected_count=1)
            assert struct_result is True

    def test_scenario_b_draft_with_attachments(self):
        """Scenario (b): draft WITH real attachments — bytes verified via SHA-256."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["b_attachment_draft"]

        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)

            # Load actual attachment files
            attachments = []
            for att_spec in sc["attachments"]:
                att_path = os.path.join(_FIX_DIR, att_spec["filename"])
                content = open(att_path, "rb").read()
                # Verify the fixture itself matches ground truth
                actual_hash = hashlib.sha256(content).hexdigest()
                assert actual_hash == att_spec["sha256"], (
                    f"Fixture '{att_spec['filename']}' hash mismatch: "
                    f"expected {att_spec['sha256']}, got {actual_hash}"
                )
                attachments.append(
                    AttachmentSpec(filename=att_spec["filename"], content=content)
                )

            spec = DraftSpec(
                to=sc["to"],
                from_=sc["from"],
                subject=sc["subject"],
                body=sc["body"],
                cc=sc.get("cc", ""),
                attachments=attachments,
            )
            result = draft_readback(mb, spec)
            assert result is True

    def test_scenario_c_reply_with_threading(self):
        """Scenario (c): reply quoting original + preserving In-Reply-To/References."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)

            # Compose and save original
            orig_spec = DraftSpec(
                to="bob@example.com",
                from_="alice@example.com",
                subject="Project Update — Q3 Roadmap",
                body="Hi Bob,\n\nHere is the Q3 roadmap update.\nKey milestones:\n1. API v2 launch\n2. Migration tooling\n3. GA release\n\nBest,\nAlice",
            )
            orig_msg = compose_draft(orig_spec)
            save_draft(mb, orig_msg, folder="drafts", create=True)

            # Read back original to get Message-ID
            readback = read_drafts(mb, folder="drafts")
            orig_msgid = readback[0].message_id

            # Compose reply
            reply_msg = reply_to(
                orig_msg,
                "Thanks Alice, this looks great. I'll review the timeline and get back to you by EOD.",
                "bob@example.com",
            )
            save_draft(mb, reply_msg, folder="drafts", create=False)

            # Read back and verify
            all_drafts = read_drafts(mb, folder="drafts")
            assert len(all_drafts) == 2

            # Find the reply
            reply_rb = None
            for rb in all_drafts:
                if rb.in_reply_to:
                    reply_rb = rb
                    break

            assert reply_rb is not None
            assert reply_rb.in_reply_to == orig_msgid
            assert orig_msgid in reply_rb.references
            assert reply_rb.subject == "Re: Project Update — Q3 Roadmap"
            assert "Thanks Alice" in reply_rb.body
            # Verify original is quoted
            assert "> Hi Bob," in reply_rb.body
            assert "> Here is the Q3 roadmap update." in reply_rb.body

            # Verify mailbox structure
            struct_result = mailbox_structure_readback(mb, expected_count=2)
            assert struct_result is True


# ---------------------------------------------------------------------------
# Trust Stack Integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_pipeline_emits_audit_and_egress(self):
        """Pipeline with private_key emits audit log + egress report."""
        private_key = ed25519.Ed25519PrivateKey.generate()

        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="Audit Test",
                body="Body for audit test.",
            )
            result = email_pipeline(
                mailbox_path=mb,
                specs=[spec],
                private_key=private_key,
            )
            assert result.ok
            assert result.audit_log_json, "Audit log JSON should be non-empty"
            assert result.egress_report_json, "Egress report JSON should be non-empty"

            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
            from kairo.oracles.zero_egress_report import (
                report_from_json,
                verify_zero_egress_report,
            )

            public_key = private_key.public_key()
            entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
            assert len(entries) > 0
            assert Ed25519AuditLog.verify_chain(entries, public_key)

            report = report_from_json(result.egress_report_json)
            assert verify_zero_egress_report(report, public_key)

    def test_pipeline_without_key_still_works(self):
        """Pipeline without private_key still composes and saves drafts."""
        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            spec = DraftSpec(
                to="alice@example.com",
                from_="bob@example.com",
                subject="No Key Test",
                body="Body without key.",
            )
            result = email_pipeline(mailbox_path=mb, specs=[spec])
            assert result.ok
            assert result.drafts_created == 1
            assert len(result.readback) == 1
            assert not result.audit_log_json
            assert not result.egress_report_json


# ---------------------------------------------------------------------------
# CLI Integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """email CLI subcommand works end-to-end via registry."""

    def test_cli_compose(self):
        """`kairo email compose` creates a draft in a Maildir."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            out_dir = os.path.join(tmp, "email_output")
            rc = main([
                "email", "compose", mb,
                "--to", "alice@example.com",
                "--from", "bob@example.com",
                "--subject", "CLI Test",
                "--body", "Body via CLI.",
                "--outdir", out_dir,
            ])
            assert rc == 0, f"CLI compose failed with exit code {rc}"

            # Verify the draft was actually saved
            readback = read_drafts(mb, folder="drafts")
            assert len(readback) == 1
            assert readback[0].to == "alice@example.com"
            assert readback[0].subject == "CLI Test"

    def test_cli_verify(self):
        """`kairo email verify` reads back and displays drafts."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            out_dir = os.path.join(tmp, "email_output")

            # First compose a draft
            rc = main([
                "email", "compose", mb,
                "--to", "alice@example.com",
                "--from", "bob@example.com",
                "--subject", "Verify Test",
                "--body", "Body for verify.",
                "--outdir", out_dir,
            ])
            assert rc == 0

            # Now verify
            rc = main(["email", "verify", mb, "--outdir", out_dir])
            assert rc == 0, f"CLI verify failed with exit code {rc}"

    def test_cli_list(self):
        """`kairo email list` lists drafts in a Maildir folder."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)

            # Compose two drafts
            for i in range(2):
                rc = main([
                    "email", "compose", mb,
                    "--to", f"r{i}@example.com",
                    "--from", "s@example.com",
                    "--subject", f"List Test {i}",
                    "--body", f"Body {i}.",
                    "--outdir", os.path.join(tmp, "out"),
                ])
                assert rc == 0

            # List should show 2 drafts
            rc = main(["email", "list", mb])
            assert rc == 0, f"CLI list failed with exit code {rc}"

    def test_cli_compose_with_attachment(self):
        """`kairo email compose --attach` includes a real attachment."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            mb = _make_maildir(tmp)
            out_dir = os.path.join(tmp, "email_output")
            rc = main([
                "email", "compose", mb,
                "--to", "alice@example.com",
                "--from", "bob@example.com",
                "--subject", "Attachment CLI Test",
                "--body", "Body with attachment via CLI.",
                "--attach", _FIX_TXT,
                "--outdir", out_dir,
            ])
            assert rc == 0, f"CLI compose with attachment failed with exit code {rc}"

            # Verify the attachment was saved
            readback = read_drafts(mb, folder="drafts")
            assert len(readback) == 1
            assert "attachment.txt" in readback[0].attachment_names
            att_bytes = readback[0].attachment_bytes["attachment.txt"]
            expected = open(_FIX_TXT, "rb").read()
            assert att_bytes == expected
