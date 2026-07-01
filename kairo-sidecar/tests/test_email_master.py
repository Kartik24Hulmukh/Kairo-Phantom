from sidecar.masters.other_masters import EmailMaster
from sidecar.schemas.domain_schemas import EmailResponse


def test_email_master_extract_context():
    master = EmailMaster()
    ctx = master.extract_context(None, None)

    assert ctx["email_client"] == "Outlook"
    assert ctx["compose_mode"] == "new"
    assert ctx["thread_context"] == ""
    assert ctx["preferred_signoff"] == "Best regards,"
    assert ctx["user_name"] == "User"


def test_email_master_build_prompt():
    master = EmailMaster()
    context = {
        "email_client": "Gmail",
        "compose_mode": "reply",
        "thread_context": "Hi Alice, let's meet tomorrow. - Bob",
        "preferred_signoff": "Thanks,",
        "user_name": "Alice",
    }

    prompt = master.build_prompt("draft a reply", context, mem_context="Keep it concise.")
    assert "SYSTEM:" in prompt
    assert "Gmail" in prompt
    assert "reply" in prompt
    assert "Hi Alice, let's meet tomorrow." in prompt
    assert "Thanks," in prompt
    assert "Alice" in prompt
    assert "draft a reply" in prompt


def test_email_master_validate_operations_subject_rules():
    master = EmailMaster()

    # 1. Truncate, remove exclamation, convert ALL CAPS to Title Case
    resp = EmailResponse(
        injection_method="clipboard",
        subject="URGENT OUTAGE REPORT FOR CRITICAL SYSTEMS!!!",
        body="Dear team, we have an issue.",
        emotional_flag=False,
        word_count=6,
        confidence=0.9,
    )
    ops = master.validate_operations(resp, {})
    assert len(ops) == 1
    assert "!" not in ops[0]["subject"]
    assert ops[0]["subject"].istitle()
    assert len(ops[0]["subject"]) <= 50


def test_email_master_validate_operations_block_send():
    master = EmailMaster()

    resp = EmailResponse(
        injection_method="clipboard",
        subject="Report",
        body="Here is the report. Please send this email.",
        emotional_flag=False,
        suggested_revision="Please send this email",
        word_count=8,
        confidence=0.9,
    )
    ops = master.validate_operations(resp, {})
    assert len(ops) == 1
    assert "send this email" not in ops[0]["body"].lower()
    assert ops[0]["suggested_revision"] == ""


def test_email_master_validate_operations_emotion_detection():
    master = EmailMaster()

    # Frustrated emotion keyword in body
    resp = EmailResponse(
        injection_method="clipboard",
        subject="Outage",
        body="I am extremely frustrated with this terrible software! It is completely unacceptable.",
        emotional_flag=False,  # LLM forgot to set it
        word_count=11,
        confidence=0.9,
    )
    ops = master.validate_operations(resp, {})
    assert len(ops) == 1
    assert ops[0]["emotional_flag"] is True
    assert ops[0]["suggested_revision"] is not None
    assert "frustrated" not in ops[0]["suggested_revision"].lower()
    assert "terrible" not in ops[0]["suggested_revision"].lower()
    assert "unacceptable" not in ops[0]["suggested_revision"].lower()


def test_email_master_validate_operations_pii_redaction():
    master = EmailMaster()

    context = {"thread_context": "The user's SSN is 123-45-6789 and Card is 1111-2222-3333-4444"}
    resp = EmailResponse(
        injection_method="clipboard",
        subject="Secure Info",
        body="We found SSN 123-45-6789 and Card 1111-2222-3333-4444",
        emotional_flag=False,
        pii_redacted=False,
        word_count=9,
        confidence=0.9,
    )
    ops = master.validate_operations(resp, context)
    assert len(ops) == 1
    assert ops[0]["pii_redacted"] is True
    assert "123-45-6789" not in ops[0]["body"]
    assert "1111-2222-3333-4444" not in ops[0]["body"]
    assert "[SSN REDACTED]" in ops[0]["body"]
    assert "[CARD REDACTED]" in ops[0]["body"]
