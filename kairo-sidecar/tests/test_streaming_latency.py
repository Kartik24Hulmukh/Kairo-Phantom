import sys
import time
import asyncio
import pytest
from pathlib import Path

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.humanized_injector import HumanizedInjector


@pytest.mark.asyncio
async def test_streaming_latency_first_token():
    injector = HumanizedInjector()

    async def mock_token_generator():
        yield "FirstToken"
        await asyncio.sleep(0.1)
        yield "SecondToken"

    t0 = time.perf_counter()
    first_token_time = None

    async for token in injector.stream_inject(mock_token_generator(), wpm=120):
        if first_token_time is None:
            first_token_time = time.perf_counter() - t0

    assert first_token_time is not None
    # Assert first token appears within 2000ms (should be way under 100ms in practice)
    assert (
        first_token_time < 2.0
    ), f"First token latency was {first_token_time}s, exceeding 2s limit."
