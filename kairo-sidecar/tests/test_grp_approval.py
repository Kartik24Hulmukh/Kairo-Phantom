import sys
import asyncio
import pytest
from pathlib import Path

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.humanized_injector import HumanizedInjector, InjectionSession


@pytest.mark.asyncio
async def test_grp_approval_esc_cancellation():
    injector = HumanizedInjector()

    # Create a mock session
    session = InjectionSession(session_id="test_esc", file_path="")

    async def mock_token_gen():
        yield "Hello"
        yield " "
        # Simulate user pressing Esc causing asyncio.CancelledError before "World" is yielded
        raise asyncio.CancelledError()
        yield "World"

    tokens = []
    with pytest.raises(asyncio.CancelledError):
        async for token in injector.stream_inject(mock_token_gen(), wpm=120, session=session):
            tokens.append(token)

    # Verify that the session is marked incomplete
    assert session.completed is False
    assert len(tokens) == 2  # Cancelled before "World"
