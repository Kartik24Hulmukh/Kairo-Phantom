from sidecar.masters.other_masters import BrowserMaster
from sidecar.schemas.domain_schemas import BrowserResponse, BrowserSafetyCheck


def test_browser_master_extract_context():
    master = BrowserMaster()

    # Clean URL
    ctx1 = master.extract_context("https://example.com/blog/1", None)
    assert ctx1["page_url"] == "https://example.com/blog/1"
    assert ctx1["is_collaborative_editor"] is False

    # Notion URL
    ctx2 = master.extract_context("https://www.notion.so/workspace/doc123", None)
    assert ctx2["page_url"] == "https://www.notion.so/workspace/doc123"
    assert ctx2["is_collaborative_editor"] is True

    # Google Docs URL
    ctx3 = master.extract_context("https://docs.google.com/document/d/xyz/edit", None)
    assert ctx3["is_collaborative_editor"] is True


def test_browser_master_build_prompt():
    master = BrowserMaster()
    context = {
        "page_url": "https://example.com/news",
        "page_title": "Daily News",
        "active_element_type": "div",
        "platform": "Firefox",
        "page_content_truncated": "Breaking news content...",
    }

    # Without memory context
    prompt = master.build_prompt("summarize this article", context, mem_context="")
    assert "SYSTEM:" in prompt
    assert "https://example.com/news" in prompt
    assert "Daily News" in prompt
    assert "Firefox" in prompt
    assert "Breaking news content..." in prompt
    assert "summarize this article" in prompt
    assert "USER WRITING PREFERENCES" not in prompt

    # With memory context
    prompt_with_mem = master.build_prompt(
        "summarize this article", context, mem_context="Use casual tone."
    )
    assert "USER WRITING PREFERENCES (from memory):" in prompt_with_mem
    assert "Use casual tone." in prompt_with_mem


def test_browser_master_validate_operations_safety_flags():
    master = BrowserMaster()
    context = {
        "page_url": "https://example.com/news",
        "page_title": "Daily News",
        "active_element_type": "div",
    }

    # Clean response
    resp = BrowserResponse(
        injection_method="clipboard",
        content="Clean content",
        platform_formatted=True,
        is_collaborative_editor=False,
        safety_check=BrowserSafetyCheck(
            is_password_field=False, is_payment_field=False, is_auto_submit=False
        ),
        confidence=0.9,
        reasoning="All looks safe",
    )
    ops = master.validate_operations(resp, context)
    assert len(ops) == 1
    assert ops[0]["content"] == "Clean content"
    assert ops[0]["injection_method"] == "clipboard"

    # Password field flagged
    resp_pw = BrowserResponse(
        injection_method="clipboard",
        content="Unsafe content",
        platform_formatted=True,
        is_collaborative_editor=False,
        safety_check=BrowserSafetyCheck(
            is_password_field=True, is_payment_field=False, is_auto_submit=False
        ),
        confidence=0.9,
        reasoning="Password safety flag",
    )
    assert master.validate_operations(resp_pw, context) == []

    # Payment field flagged
    resp_pay = BrowserResponse(
        injection_method="clipboard",
        content="Unsafe payment content",
        platform_formatted=True,
        is_collaborative_editor=False,
        safety_check=BrowserSafetyCheck(
            is_password_field=False, is_payment_field=True, is_auto_submit=False
        ),
        confidence=0.9,
        reasoning="Payment safety flag",
    )
    assert master.validate_operations(resp_pay, context) == []

    # Auto submit flagged
    resp_submit = BrowserResponse(
        injection_method="clipboard",
        content="Unsafe auto-submit content",
        platform_formatted=True,
        is_collaborative_editor=False,
        safety_check=BrowserSafetyCheck(
            is_password_field=False, is_payment_field=False, is_auto_submit=True
        ),
        confidence=0.9,
        reasoning="Auto submit safety flag",
    )
    assert master.validate_operations(resp_submit, context) == []


def test_browser_master_validate_operations_runtime_guardrails():
    master = BrowserMaster()

    resp = BrowserResponse(
        injection_method="clipboard",
        content="Testing input",
        platform_formatted=True,
        is_collaborative_editor=False,
        safety_check=BrowserSafetyCheck(
            is_password_field=False, is_payment_field=False, is_auto_submit=False
        ),
        confidence=0.9,
        reasoning="No flags",
    )

    # Active element type contains password
    context_pw_el = {
        "page_url": "https://example.com",
        "page_title": "Login",
        "active_element_type": "input-password-field",
    }
    assert master.validate_operations(resp, context_pw_el) == []

    # URL contains 2fa keyword
    context_2fa_url = {
        "page_url": "https://example.com/2fa/verify",
        "page_title": "Security check",
        "active_element_type": "input",
    }
    assert master.validate_operations(resp, context_2fa_url) == []

    # Title contains otp
    context_otp_title = {
        "page_url": "https://example.com/login",
        "page_title": "Enter OTP",
        "active_element_type": "input",
    }
    assert master.validate_operations(resp, context_otp_title) == []


def test_browser_master_validate_operations_crdt_override():
    master = BrowserMaster()

    # User / LLM thinks it's clipboard/regular editor
    resp = BrowserResponse(
        injection_method="clipboard",
        content="Collaborative edit content",
        platform_formatted=True,
        is_collaborative_editor=False,
        safety_check=BrowserSafetyCheck(
            is_password_field=False, is_payment_field=False, is_auto_submit=False
        ),
        confidence=0.9,
        reasoning="No flags",
    )

    # Notion URL detected -> should coerce injection_method to crdt_yjs and is_collaborative_editor to True
    context_notion = {
        "page_url": "https://notion.so/document/123",
        "page_title": "My Notion Page",
        "active_element_type": "editor",
    }
    ops = master.validate_operations(resp, context_notion)
    assert len(ops) == 1
    assert ops[0]["injection_method"] == "crdt_yjs"
    assert ops[0]["is_collaborative_editor"] is True
