import json
from unittest.mock import patch
from pydantic import BaseModel

from sidecar.prompt_builder import (
    build_word_prompt,
    build_excel_prompt,
    build_powerpoint_prompt,
    build_code_prompt,
    build_pdf_prompt,
    build_browser_prompt,
    build_terminal_prompt,
    build_email_prompt,
    build_notes_prompt,
    build_design_prompt,
    build_media_prompt,
    build_data_prompt,
)
from sidecar.llm_caller import call_with_schema


class MockHTTPResponse:
    def __init__(self, data: bytes):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class SimpleSchema(BaseModel):
    status: str


def test_prompt_builders_ordering_and_reminder():
    builders = [
        ("word", build_word_prompt),
        ("excel", build_excel_prompt),
        ("powerpoint", build_powerpoint_prompt),
        ("code", build_code_prompt),
        ("pdf", build_pdf_prompt),
        ("browser", build_browser_prompt),
        ("terminal", build_terminal_prompt),
        ("email", build_email_prompt),
        ("notes", build_notes_prompt),
        ("design", build_design_prompt),
        ("media", build_media_prompt),
        ("data", build_data_prompt),
    ]

    doc_context = {
        "styles": {"paragraph": ["Normal"]},
        "paragraphs": [{"text": "Hello world"}],
        "tables": [],
        "theme_fonts": {},
        "list_sequences": [],
        "document_purpose": "business_memo",
        "cursor_paragraph_index": 0,
        "total_paragraphs": 1,
        "file_path": "test.txt",
        "slide_index": 0,
        "total_slides": 5,
        "layout_name": "Title and Content",
        "major_font": "Segoe UI Light",
        "minor_font": "Segoe UI",
        "shapes_json": "[]",
        "deck_purpose": "sales_deck",
        "language": "python",
        "cursor_line": 10,
        "indent_style": "spaces",
        "indent_size": 4,
        "line_endings": "LF",
        "enclosing_function_signature": "None",
        "enclosing_class_name": "None",
        "existing_imports": [],
        "surrounding_code": "print('hello')",
        "extraction_tier": "PyMuPDF",
        "document_type": "PDF",
        "page_count": 2,
        "extracted_content": "Extracted text",
        "page_url": "https://google.com",
        "page_title": "Google",
        "active_element_type": "body",
        "platform": "Chrome",
        "page_content_truncated": "truncated",
        "shell_type": "bash",
        "os_type": "Linux",
        "current_directory": "/home",
        "terminal_content": "",
        "git_info": "",
        "email_client": "Outlook",
        "compose_mode": "new",
        "thread_context": "",
        "preferred_signoff": "Best regards,",
        "user_name": "User",
        "notes_app": "Obsidian",
        "current_heading": "None",
        "surrounding_content": "",
        "existing_tags": [],
        "backlinks": [],
        "design_tool": "Figma",
        "active_frame_name": "Frame 1",
        "canvas_dimensions": [1920, 1080],
        "color_tokens": {},
        "type_tokens": {},
        "layers_json": "[]",
        "auto_layout_active": False,
        "active_app": "Canva",
        "timeline_scrubber_seconds": 0,
        "notebook_cell_count": 5,
        "kernel_active": True,
        "imports": [],
        "sql_dialect": "generic",
        "data_libraries": [],
    }

    user_prompt = "Generate the next section."
    mem_context = "Always be professional."
    classification = {"task_type": "document_generation"}

    json_reminder_str = (
        "REMINDER: Your entire response must be a single JSON object. "
        "First character must be {. Last character must be }."
    )

    for name, builder_func in builders:
        prompt = builder_func(user_prompt, doc_context, mem_context, classification)

        idx_app = prompt.find("=== APP CONTEXT ===")
        idx_doc = prompt.find("=== DOCUMENT CONTEXT ===")
        idx_mem = prompt.find("=== MEMORY CONTEXT ===")
        idx_intent = prompt.find("=== INTENT CLASSIFICATION ===")
        idx_reminder = prompt.find(json_reminder_str)
        idx_instruction = prompt.find("USER INSTRUCTION:")

        # Assert variable presence
        assert idx_app != -1, f"{name}: APP CONTEXT not found"
        assert idx_doc != -1, f"{name}: DOCUMENT CONTEXT not found"
        assert idx_mem != -1, f"{name}: MEMORY CONTEXT not found"
        assert idx_intent != -1, f"{name}: INTENT CLASSIFICATION not found"
        assert idx_reminder != -1, f"{name}: JSON reminder not found"
        assert idx_instruction != -1, f"{name}: USER INSTRUCTION not found"

        # Assert correct ordering: App Context -> Document Context -> Memory Context -> Intent Classification -> JSON reminder -> User Instruction
        assert idx_app < idx_doc, f"{name}: APP CONTEXT must precede DOCUMENT CONTEXT"
        assert idx_doc < idx_mem, f"{name}: DOCUMENT CONTEXT must precede MEMORY CONTEXT"
        assert idx_mem < idx_intent, f"{name}: MEMORY CONTEXT must precede INTENT CLASSIFICATION"
        assert (
            idx_intent < idx_reminder
        ), f"{name}: INTENT CLASSIFICATION must precede JSON reminder"
        assert (
            idx_reminder < idx_instruction
        ), f"{name}: JSON reminder must precede USER INSTRUCTION"

        # Assert that the JSON reminder immediately precedes the User Instruction
        between_reminder_and_instruction = prompt[
            idx_reminder + len(json_reminder_str) : idx_instruction
        ]
        assert (
            "===" not in between_reminder_and_instruction
        ), f"{name}: The JSON reminder must immediately precede the USER INSTRUCTION without other blocks in between"


def test_llm_caller_json_decode_retry():
    requests_captured = []

    def mock_urlopen(req, timeout=None):
        payload = json.loads(req.data.decode("utf-8"))
        requests_captured.append(payload)

        if len(requests_captured) == 1:
            # First attempt: Return invalid JSON in choice message content
            response_payload = {
                "choices": [{"message": {"content": "{invalid json structure here"}}]
            }
        else:
            # Second attempt: Return valid JSON matching SimpleSchema
            response_payload = {"choices": [{"message": {"content": '{"status": "ok"}'}}]}

        return MockHTTPResponse(json.dumps(response_payload).encode("utf-8"))

    # Patch urllib.request.urlopen
    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = call_with_schema("initial prompt", SimpleSchema)

    # Assertions
    # 1. The call was retried and eventually succeeded
    assert isinstance(result, SimpleSchema)
    assert result.status == "ok"

    # 2. There were exactly 2 calls made
    assert len(requests_captured) == 2

    # 3. First attempt payload checks
    first_payload = requests_captured[0]
    assert first_payload["model"] == "ollama/qwen2.5:7b"
    assert first_payload["temperature"] == 0.0
    assert first_payload["response_format"] == {"type": "json_object"}
    assert first_payload["messages"] == [{"role": "user", "content": "initial prompt"}]

    # 4. Second attempt payload checks
    second_payload = requests_captured[1]
    assert second_payload["model"] == "ollama/qwen2.5:7b"
    assert second_payload["temperature"] == 0.0
    assert second_payload["response_format"] == {"type": "json_object"}

    expected_retry_prompt = (
        "initial prompt\n\n"
        "Your previous response was not valid JSON. Output ONLY the JSON object, nothing else."
    )
    assert second_payload["messages"] == [{"role": "user", "content": expected_retry_prompt}]
