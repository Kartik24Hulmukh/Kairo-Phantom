import os
import platform
from sidecar.masters.other_masters import TerminalMaster
from sidecar.schemas.domain_schemas import TerminalResponse


def test_terminal_master_extract_context():
    master = TerminalMaster()
    ctx = master.extract_context(None, None)

    assert ctx["os_type"] == platform.system()
    assert ctx["shell_type"] in ["powershell", "bash"]
    assert ctx["current_directory"] == os.getcwd()


def test_terminal_master_build_prompt():
    master = TerminalMaster()
    context = {
        "shell_type": "bash",
        "os_type": "Linux",
        "current_directory": "/home/user",
        "terminal_content": "bash-4.2$",
        "git_info": "Git repository detected",
    }

    prompt = master.build_prompt("list files", context, mem_context="")
    assert "SYSTEM:" in prompt
    assert "CRITICAL SAFETY RULE:" in prompt
    assert "bash" in prompt
    assert "Linux" in prompt
    assert "/home/user" in prompt
    assert "Git repository detected" in prompt
    assert "list files" in prompt


def test_terminal_master_validate_operations():
    master = TerminalMaster()

    # 1. Safe command
    resp_safe = TerminalResponse(
        command="git status",
        explanation="shows git status",
        danger_level="safe",
        confidence=0.9,
        reasoning="Simple read-only command",
    )
    ops = master.validate_operations(resp_safe, {"shell_type": "bash"})
    assert len(ops) == 1
    assert ops[0]["injection_method"] == "show_only"
    assert ops[0]["command"] == "git status"
    assert ops[0]["danger_level"] == "safe"

    # 2. Caution command - bash (should get review warning and comment)
    resp_caution = TerminalResponse(
        command="rm file.txt",
        explanation="deletes a file",
        danger_level="safe",  # LLM incorrectly marked safe
        confidence=0.9,
        reasoning="Should be caution",
    )
    ops = master.validate_operations(resp_caution, {"shell_type": "bash"})
    assert len(ops) == 1
    assert ops[0]["danger_level"] == "caution"
    assert "Review before running" in ops[0]["warning"]
    assert ops[0]["command"] == "rm file.txt # Review before running"

    # 3. Caution command - cmd (should get & rem Review before running)
    ops_cmd = master.validate_operations(resp_caution, {"shell_type": "cmd"})
    assert len(ops_cmd) == 1
    assert ops_cmd[0]["command"] == "rm file.txt & rem Review before running"

    # 4. Dangerous command (should force warning and dangerous danger_level)
    resp_dangerous = TerminalResponse(
        command="rm -rf /",
        explanation="deletes everything",
        danger_level="safe",  # LLM hallucinated safety
        confidence=0.9,
        reasoning="Highly dangerous",
    )
    ops_dangerous = master.validate_operations(resp_dangerous, {"shell_type": "bash"})
    assert len(ops_dangerous) == 1
    assert ops_dangerous[0]["danger_level"] == "dangerous"
    assert "⚠️" in ops_dangerous[0]["warning"]
