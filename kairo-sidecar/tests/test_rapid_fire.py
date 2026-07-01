import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.router import SwarmOrchestrator, KairoResponse


@pytest.mark.asyncio
async def test_rapid_fire_requests():
    orchestrator = SwarmOrchestrator()

    # Mock routing/LLM execution to avoid hitting actual ollama / files
    mock_response = KairoResponse(
        type="write", domain="word", confidence=1.0, context_summary="Test success"
    )

    # We patch DomainMasterRouter.route to return our mock response instantly
    with patch.object(orchestrator._router, "route", return_value=mock_response):
        tasks = []
        for i in range(10):
            # Send 10 requests in a tight loop
            tasks.append(
                asyncio.to_thread(
                    orchestrator.route,
                    user_prompt=f"Rapid fire instruction {i}",
                    domain="word",
                    file_path="",
                )
            )

        results = await asyncio.gather(*tasks)

        # Verify 10 results were returned with zero exceptions/crashes
        assert len(results) == 10
        for r in results:
            assert r.confidence == 1.0
