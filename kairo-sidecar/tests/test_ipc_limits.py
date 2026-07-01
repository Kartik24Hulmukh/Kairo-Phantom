import asyncio
import pytest
import json
from sidecar.ipc import NamedPipeProtocol, MAX_MESSAGE_BYTES, MAX_CONCURRENT_REQUESTS


class MockTransport:
    def __init__(self):
        self.written = []
        self.closed = False

    def write(self, data):
        self.written.append(data)

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_ipc_buffer_overflow():
    async def mock_handler(req):
        return {"ok": True}

    protocol = NamedPipeProtocol(mock_handler)
    transport = MockTransport()
    protocol.connection_made(transport)

    # Send data exceeding MAX_MESSAGE_BYTES
    large_data = b"a" * (MAX_MESSAGE_BYTES + 10)
    protocol.data_received(large_data)

    assert transport.closed
    assert protocol.buffer == b""


@pytest.mark.asyncio
async def test_ipc_concurrency_semaphore():
    started_requests = 0
    completed_requests = 0
    blocked_event = asyncio.Event()

    async def mock_handler(req):
        nonlocal started_requests, completed_requests
        started_requests += 1
        await blocked_event.wait()
        completed_requests += 1
        return {"ok": True}

    protocol = NamedPipeProtocol(mock_handler)
    transport = MockTransport()
    protocol.connection_made(transport)

    # Send MAX_CONCURRENT_REQUESTS + 5 requests
    for i in range(MAX_CONCURRENT_REQUESTS + 5):
        payload = json.dumps({"req": i}).encode("utf-8") + b"\n"
        protocol.data_received(payload)

    # Let the event loop run to schedule tasks
    await asyncio.sleep(0.1)

    # Only MAX_CONCURRENT_REQUESTS should have started
    assert started_requests == MAX_CONCURRENT_REQUESTS

    # Let them complete
    blocked_event.set()
    await protocol.drain()

    assert completed_requests == MAX_CONCURRENT_REQUESTS + 5
