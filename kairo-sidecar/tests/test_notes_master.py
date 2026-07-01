from sidecar.masters.other_masters import NotesMaster
from sidecar.schemas.domain_schemas import NotesResponse


def test_notes_master_extract_context():
    master = NotesMaster()

    # Org file -> Logseq
    ctx_org = master.extract_context("journal.org", 5)
    assert ctx_org["notes_app"] == "Logseq"
    assert ctx_org["cursor_line"] == 5

    # Txt file -> Plain .md
    ctx_txt = master.extract_context("todo.txt", "10")
    assert ctx_txt["notes_app"] == "Plain .md"
    assert ctx_txt["cursor_line"] == 10

    # Markdown/Default -> Obsidian
    ctx_md = master.extract_context("notes.md", None)
    assert ctx_md["notes_app"] == "Obsidian"
    assert ctx_md["cursor_line"] == 1


def test_notes_master_build_prompt():
    master = NotesMaster()
    context = {
        "notes_app": "Obsidian",
        "file_path": "work.md",
        "current_heading": "## Overview",
        "cursor_line": 20,
        "surrounding_content": "Old notes",
        "existing_tags": ["work", "active"],
        "backlinks": ["Index", "TODO"],
    }

    prompt = master.build_prompt("expand outline", context, mem_context="")
    assert "SYSTEM:" in prompt
    assert "App: Obsidian" in prompt
    assert "File: work.md" in prompt
    assert "Current section heading: ## Overview" in prompt
    assert "Cursor line: 20" in prompt
    assert "Surrounding content:\nOld notes" in prompt
    assert "Existing tags: ['work', 'active']" in prompt
    assert "Linked notes (backlinks): ['Index', 'TODO']" in prompt
    assert "expand outline" in prompt


def test_notes_master_validate_operations():
    master = NotesMaster()

    resp = NotesResponse(
        injection_method="file_write",
        insert_at_line=5,
        content="Expanded content",
        new_tags=["update"],
        new_links=["Link1"],
        frontmatter_update={"status": "done"},
        confidence=0.95,
    )

    ops = master.validate_operations(resp, {"notes_app": "Obsidian"})
    assert len(ops) == 1
    assert ops[0]["injection_method"] == "file_write"
    assert ops[0]["insert_at_line"] == 5
    assert ops[0]["content"] == "Expanded content"
    assert ops[0]["new_tags"] == ["update"]
    assert ops[0]["new_links"] == ["Link1"]
    assert ops[0]["frontmatter_update"] == {"status": "done"}
