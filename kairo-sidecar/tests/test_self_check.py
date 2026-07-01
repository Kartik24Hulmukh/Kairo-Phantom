import sys
from pathlib import Path

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.main import handle_request, check_llm_available


def test_check_llm_available():
    # It should run without raising exceptions
    res = check_llm_available()
    assert isinstance(res, bool)


def test_handle_request_self_check():
    req = {"id": "test-self-check", "action": "self_check", "path": "", "payload": {}}
    import asyncio

    res = asyncio.run(handle_request(req))
    assert res["ok"] is True
    assert "data" in res
    data = res["data"]
    assert "version" in data
    assert "domain_1_word" in data
    assert "domain_2_excel" in data
    assert "domain_3_pptx" in data
    assert "domain_4_pdf" in data
    assert "llm_available" in data
    assert "offline_mode" in data
