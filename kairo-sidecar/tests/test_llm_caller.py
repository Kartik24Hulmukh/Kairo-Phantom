import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.llm_caller import call_with_schema
from pydantic import BaseModel


class DummySchema(BaseModel):
    value: str


@patch("urllib.request.urlopen")
def test_call_with_schema_timeout_env(mock_urlopen):
    # Setup mock response
    mock_resp = MagicMock()
    mock_resp.read.return_value = (
        b'{"choices": [{"message": {"content": "{\\"value\\": \\"ok\\"}"}}]}'
    )
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    with patch.dict(os.environ, {"KAIRO_LLM_TIMEOUT": "25.0"}):
        res = call_with_schema("hello", DummySchema)
        assert res.value == "ok"
        # Assert urlopen was called with timeout=25.0
        args, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 25.0


@patch("urllib.request.urlopen")
def test_call_with_schema_timeout_override(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = (
        b'{"choices": [{"message": {"content": "{\\"value\\": \\"ok\\"}"}}]}'
    )
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    res = call_with_schema("hello", DummySchema, timeout=42.0)
    assert res.value == "ok"
    args, kwargs = mock_urlopen.call_args
    assert kwargs.get("timeout") == 42.0


@patch("urllib.request.urlopen")
def test_call_with_schema_timeout_length_short(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = (
        b'{"choices": [{"message": {"content": "{\\"value\\": \\"ok\\"}"}}]}'
    )
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    # Short prompt (< 500 chars) -> default 15s timeout
    call_with_schema("hello", DummySchema)
    args, kwargs = mock_urlopen.call_args
    assert kwargs.get("timeout") == 15.0


@patch("urllib.request.urlopen")
def test_call_with_schema_timeout_length_long(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = (
        b'{"choices": [{"message": {"content": "{\\"value\\": \\"ok\\"}"}}]}'
    )
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    # Long prompt (> 4000 chars) -> default 120s timeout
    long_prompt = "hello " * 1000
    call_with_schema(long_prompt, DummySchema)
    args, kwargs = mock_urlopen.call_args
    assert kwargs.get("timeout") == 120.0
