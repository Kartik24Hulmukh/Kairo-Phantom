"""
Phase A1: Verify @track decorator on 8 remaining domain masters.

For each master: call extract_context (or query for MemMachine) →
assert JSONL trace is non-empty with correct domain + trace_id.
Fails if trace is empty or faked.
"""

import sys
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from sidecar.observability.opik_tracer import OpikTracer, set_global_tracer


@pytest.fixture
def temp_tracer(tmp_path):
    """Create a tracer with a temporary trace file."""
    trace_path = tmp_path / "opik_traces.jsonl"
    tracer = OpikTracer(trace_path=trace_path)
    set_global_tracer(tracer)
    yield tracer
    set_global_tracer(None)


class TestTrackOnRemainingMasters:
    """Each remaining domain master must emit a real trace when called."""

    def test_code_master_trace(self, temp_tracer):
        """CodeMaster.extract_context emits a trace with domain='code'."""
        from sidecar.masters.other_masters import CodeMaster

        master = CodeMaster()
        # Create a temp Python file for context extraction
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def hello():\n    print('world')\n")
            f.flush()
            master.extract_context(f.name, 1)
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted — @track is NOT working"
        assert traces[0]["domain"] == "code", f"Wrong domain: {traces[0]['domain']}"
        assert traces[0]["trace_id"] != "", "trace_id is EMPTY — trace is FAKE"

    def test_browser_master_trace(self, temp_tracer):
        """BrowserMaster.extract_context emits a trace with domain='browser'."""
        from sidecar.masters.other_masters import BrowserMaster

        master = BrowserMaster()
        master.extract_context("https://example.com", None)
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted"
        assert traces[0]["domain"] == "browser"
        assert traces[0]["trace_id"] != ""

    def test_terminal_master_trace(self, temp_tracer):
        """TerminalMaster.extract_context emits a trace with domain='terminal'."""
        from sidecar.masters.other_masters import TerminalMaster

        master = TerminalMaster()
        master.extract_context(None, None)
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted"
        assert traces[0]["domain"] == "terminal"
        assert traces[0]["trace_id"] != ""

    def test_email_master_trace(self, temp_tracer):
        """EmailMaster.extract_context emits a trace with domain='email'."""
        from sidecar.masters.other_masters import EmailMaster

        master = EmailMaster()
        master.extract_context(None, None)
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted"
        assert traces[0]["domain"] == "email"
        assert traces[0]["trace_id"] != ""

    def test_notes_master_trace(self, temp_tracer):
        """NotesMaster.extract_context emits a trace with domain='notes'."""
        from sidecar.masters.other_masters import NotesMaster

        master = NotesMaster()
        master.extract_context("notes.md", None)
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted"
        assert traces[0]["domain"] == "notes"
        assert traces[0]["trace_id"] != ""

    def test_media_master_trace(self, temp_tracer):
        """MediaMaster.extract_context emits a trace with domain='media'."""
        from sidecar.masters.other_masters import MediaMaster

        master = MediaMaster()
        master.extract_context(None, None)
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted"
        assert traces[0]["domain"] == "media"
        assert traces[0]["trace_id"] != ""

    def test_data_master_trace(self, temp_tracer):
        """DataMaster.extract_context emits a trace with domain='data'."""
        from sidecar.masters.other_masters import DataMaster

        master = DataMaster()
        master.extract_context(None, None)
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted"
        assert traces[0]["domain"] == "data"
        assert traces[0]["trace_id"] != ""

    def test_memory_recall_trace(self, temp_tracer, tmp_path):
        """MemMachineClient.query emits a trace with domain='memory'."""
        from sidecar.mem_machine import MemMachineClient

        db_path = str(tmp_path / "test_mem.db")
        client = MemMachineClient(db_path=db_path)
        client.record_interaction(
            domain="word", task_type="writing", user_prompt="test", style_notes="test style"
        )
        client.query(domain="word")
        traces = temp_tracer.read_traces()
        assert len(traces) >= 1, "No trace emitted"
        # Find the memory trace (query might also trigger other traces)
        mem_traces = [t for t in traces if t["domain"] == "memory"]
        assert len(mem_traces) >= 1, "No memory domain trace found"
        assert mem_traces[0]["trace_id"] != "", "trace_id is EMPTY"
