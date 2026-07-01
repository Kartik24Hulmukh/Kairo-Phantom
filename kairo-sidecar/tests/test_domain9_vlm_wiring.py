import asyncio
import json
from sidecar.cua.vlm_config import build_vlm_config, VLM_7B_Q4
from sidecar.cua.vlm_grounding import VlmGroundingEngine, GROUNDING_PROMPT


def test_client_read_timeout_is_generous():
    eng = VlmGroundingEngine()
    assert eng._get_client().timeout.read >= 180


def test_gpu7b_tier_selects_7b():
    cfg = build_vlm_config(force_tier="gpu-7b")
    assert cfg.selected_model is VLM_7B_Q4
    assert cfg.selected_model.min_vram_gb <= 8.0


def test_grounding_prompt_formats_and_parses():
    prompt = GROUNDING_PROMPT.format(description="green Submit button")
    assert "Submit button" in prompt
    eng = VlmGroundingEngine()
    parsed = eng._parse_json_response(json.dumps(dict(found=True, x=182, y=326)))
    assert parsed.get("found") is True
    assert parsed.get("x") == 182


def test_keep_alive_is_sent_top_level():
    eng = VlmGroundingEngine()
    captured = dict()

    class _FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return dict(message=dict(content=json.dumps(dict(found=False, x=0))))

    class _FakeClient:
        is_closed = False

        async def post(self, url, json=None):
            captured.update(payload=json)
            return _FakeResp()

    eng._client = _FakeClient()

    async def run():
        await eng._ollama_chat("hi", list(), model_name="qwen2.5vl:7b")

    asyncio.run(run())
    assert "keep_alive" in captured.get("payload")
