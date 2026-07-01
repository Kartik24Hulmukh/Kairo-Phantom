import asyncio
import json
from sidecar.cua.vlm_config import build_vlm_config, VLM_7B_Q4, VLM_3B_Q4
from sidecar.cua.vlm_grounding import VlmGroundingEngine
from sidecar.cua.vlm_download_manager import VlmDownloadManager


def test_pull_tags_are_native_multimodal():
    assert VLM_7B_Q4.ollama_pull_tag.startswith("qwen2.5vl")
    assert VLM_3B_Q4.ollama_pull_tag.startswith("qwen2.5vl")


def test_manager_target_tag_is_native():
    cfg = build_vlm_config(force_tier="gpu-7b")
    mgr = VlmDownloadManager(cfg)
    assert mgr.target_model_tag.startswith("qwen2.5vl")


def test_manager_pulls_not_bare_gguf():
    assert hasattr(VlmDownloadManager, "_pull_model")
    assert not hasattr(VlmDownloadManager, "_download_model")


def test_engine_sends_native_multimodal_tag():
    cfg = build_vlm_config(force_tier="gpu-7b")
    eng = VlmGroundingEngine(cfg)
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
        await eng._ollama_chat("hi", list(), model_name=None)

    asyncio.run(run())
    assert captured.get("payload").get("model").startswith("qwen2.5vl")
