"""
Phase A3: Expose 12 domain tools through kairo-mcp.

Test: Start the MCP server as a subprocess, send JSON-RPC requests,
verify all 12 domain tools are registered and callable.
"""

import json
import subprocess
import time
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_BINARY = REPO_ROOT / "target" / "debug" / "kairo-mcp"


def start_mcp_server():
    """Start the MCP server as a subprocess."""
    proc = subprocess.Popen(
        [str(MCP_BINARY)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc


def send_request(proc, method, params=None, req_id=1):
    """Send a JSON-RPC request and get the response."""
    request = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params:
        request["params"] = params

    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()

    # Read response line
    response_line = proc.stdout.readline()
    if response_line:
        return json.loads(response_line.strip())
    return None


@pytest.fixture
def mcp_server():
    """Start and stop the MCP server for each test."""
    if not MCP_BINARY.exists():
        pytest.skip(f"MCP binary not found at {MCP_BINARY}. Run: cargo build -p kairo-mcp")

    proc = start_mcp_server()
    time.sleep(0.5)  # Give server time to start

    # Send initialize request
    init_response = send_request(proc, "initialize", req_id=0)
    assert init_response is not None, "No response to initialize"
    assert "result" in init_response

    yield proc

    proc.terminate()
    proc.wait(timeout=5)


class TestMCPToolRegistration:
    """Test that all 12 domain tools are registered in the MCP server."""

    def test_tools_list_contains_12_domain_tools(self, mcp_server):
        """The tools/list response must contain all 12 domain tools."""
        response = send_request(mcp_server, "tools/list", req_id=1)
        assert response is not None
        assert "result" in response
        assert "tools" in response["result"]

        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        expected_domain_tools = [
            "kairo_word_process",
            "kairo_excel_process",
            "kairo_pptx_process",
            "kairo_pdf_process",
            "kairo_legal_process",
            "kairo_design_process",
            "kairo_code_process",
            "kairo_media_process",
            "kairo_browser_process",
            "kairo_terminal_process",
            "kairo_email_process",
            "kairo_notes_process",
        ]

        for tool_name in expected_domain_tools:
            assert tool_name in tool_names, f"Tool '{tool_name}' not found in tools/list"

        # Verify each tool has required fields
        for tool_name in expected_domain_tools:
            tool = next(t for t in tools if t["name"] == tool_name)
            assert "description" in tool, f"Tool '{tool_name}' missing description"
            assert "inputSchema" in tool, f"Tool '{tool_name}' missing inputSchema"
            assert (
                tool["inputSchema"]["type"] == "object"
            ), f"Tool '{tool_name}' schema not object type"

    def test_each_domain_tool_is_callable(self, mcp_server):
        """Each of the 12 domain tools must be callable via tools/call."""
        domain_tools = [
            ("kairo_word_process", {"instruction": "draft a memo"}),
            ("kairo_excel_process", {"instruction": "create a sum formula"}),
            ("kairo_pptx_process", {"instruction": "create a title slide"}),
            ("kairo_pdf_process", {"file_path": "/tmp/test.pdf", "instruction": "extract text"}),
            ("kairo_legal_process", {"instruction": "extract clauses"}),
            ("kairo_design_process", {"instruction": "create a wireframe"}),
            ("kairo_code_process", {"instruction": "add a docstring"}),
            ("kairo_media_process", {"instruction": "resize image"}),
            ("kairo_browser_process", {"instruction": "summarize page"}),
            ("kairo_terminal_process", {"instruction": "list files"}),
            ("kairo_email_process", {"instruction": "draft a reply"}),
            ("kairo_notes_process", {"instruction": "create a todo note"}),
        ]

        for i, (tool_name, args) in enumerate(domain_tools):
            response = send_request(
                mcp_server,
                "tools/call",
                params={"name": tool_name, "arguments": args},
                req_id=i + 10,
            )
            assert response is not None, f"No response for tool '{tool_name}'"
            assert (
                "result" in response
            ), f"Tool '{tool_name}' returned error: {response.get('error')}"
            assert "content" in response["result"], f"Tool '{tool_name}' missing content in result"

            # The tool should return text content (even if sidecar is not running)
            content = response["result"]["content"]
            assert len(content) > 0, f"Tool '{tool_name}' returned empty content"
            assert content[0]["type"] == "text", f"Tool '{tool_name}' content type not text"
            assert len(content[0]["text"]) > 0, f"Tool '{tool_name}' returned empty text"

    def test_unknown_tool_returns_error(self, mcp_server):
        """Calling an unknown tool should return an error."""
        response = send_request(
            mcp_server,
            "tools/call",
            params={"name": "nonexistent_tool", "arguments": {}},
            req_id=99,
        )
        assert response is not None
        # The MCP server should return either an error or an isError result
        assert "error" in response or (
            "result" in response and response["result"].get("isError", False)
        ), "Unknown tool should return an error"
