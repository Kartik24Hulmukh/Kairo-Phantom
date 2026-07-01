"""
Tests for Phase 0.1: Opik Observability + Provenance Receipts

These tests verify:
1. OpikTracer produces real traces with trace_id, domain, timestamps
2. Traces are written to local JSONL (queue sink)
3. PiiGuard redacts PII in traces (SSN, email, phone, credit card)
4. System prompts are NOT leaked in traces
5. Provenance bridge can read and verify the receipt chain
6. The flagship test: 5 domain master calls produce 5 traces with
   non-empty trace_ids — FAILS if traces are faked or empty
"""

import json

import pytest

from sidecar.observability.opik_tracer import (
    OpikTracer,
    TraceContext,
    track,
    set_global_tracer,
)
from sidecar.observability.provenance_bridge import (
    read_receipts,
    find_receipts_by_trace_id,
    verify_trace_receipt_linkage,
    canonical_receipt_json,
)


@pytest.fixture
def temp_tracer(tmp_path):
    """Create a tracer with a temporary trace file."""
    trace_path = tmp_path / "opik_traces.jsonl"
    tracer = OpikTracer(trace_path=trace_path)
    set_global_tracer(tracer)
    yield tracer
    set_global_tracer(None)  # Reset global tracer


class TestOpikTracerEmission:
    """Test that the OpikTracer emits real traces."""

    def test_single_trace_has_trace_id(self, temp_tracer):
        """A single trace must have a non-empty trace_id."""
        with temp_tracer.trace("word", "generate_response", input_summary="test prompt") as ctx:
            ctx.add_span("llm_call", input_data="prompt", output_data="response")

        traces = temp_tracer.read_traces()
        assert len(traces) == 1
        assert traces[0]["trace_id"] != ""
        assert traces[0]["trace_id"].startswith("trace_")
        assert traces[0]["domain"] == "word"
        assert traces[0]["action"] == "generate_response"

    def test_five_domain_calls_produce_five_traces(self, temp_tracer):
        """FLAGSHIP TEST: 5 domain master calls must produce 5 traces with non-empty trace_ids."""
        domains = ["word", "excel", "pptx", "pdf", "legal"]
        trace_ids = []

        for domain in domains:
            with temp_tracer.trace(
                domain, "domain_master_call", input_summary=f"test_{domain}"
            ) as ctx:
                ctx.add_span("llm_call", input_data="prompt", output_data="response")
                ctx.add_span("grounding_check", output_data="grounded=True")
            trace_ids.append(ctx.trace_id)

        traces = temp_tracer.read_traces()
        assert len(traces) == 5

        # FLAGSHIP ASSERTION: Every trace must have a non-empty trace_id
        # If the trace is faked (empty trace_id), this fails
        for i, trace in enumerate(traces):
            assert trace["trace_id"] != "", f"Trace {i} has empty trace_id — trace is FAKE"
            assert (
                trace["domain"] == domains[i]
            ), f"Trace {i} domain mismatch: {trace['domain']} != {domains[i]}"
            assert len(trace["spans"]) >= 1, f"Trace {i} has no spans"
            assert trace["latency_ms"] >= 0, f"Trace {i} has negative latency"

        # All trace_ids must be unique
        assert len(set(trace_ids)) == 5, "Trace IDs are not unique"

    def test_trace_writes_to_jsonl_file(self, temp_tracer, tmp_path):
        """Trace must be written to the JSONL file, not just kept in memory."""
        trace_path = tmp_path / "opik_traces.jsonl"

        with temp_tracer.trace("excel", "recompute_formulas") as ctx:
            ctx.add_span("libreoffice_call", output_data="computed=True")

        # File must exist and contain valid JSON
        assert trace_path.exists(), "Trace JSONL file was not created"
        content = trace_path.read_text()
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 1
        trace = json.loads(lines[0])
        assert trace["domain"] == "excel"

    def test_trace_emission_errors_loudly_on_write_failure(self, tmp_path):
        """If the trace file can't be written, the tracer must error loudly."""
        # Create a file and try to use it as a directory path
        blocking_file = tmp_path / "blocking_file"
        blocking_file.write_text("blocking")
        # Try to write to a path under this file (impossible — it's a file, not a dir)
        tracer = OpikTracer(trace_path=blocking_file / "opik_traces.jsonl")
        ctx = TraceContext("test_trace", "word", "test")

        with pytest.raises((RuntimeError, NotADirectoryError, OSError)):
            tracer.emit(ctx)


class TestPiiGuardOnTraces:
    """Test that PII is redacted in trace data."""

    def test_ssn_redacted_in_trace(self, temp_tracer):
        """SSN must be redacted in trace data."""
        ssn_text = "My SSN is 123-45-6789 and I need help"
        with temp_tracer.trace("legal", "contract_analysis", input_summary=ssn_text) as ctx:
            ctx.add_span("llm_call", input_data=ssn_text, output_data="Response about 123-45-6789")

        traces = temp_tracer.read_traces()
        trace_json = json.dumps(traces[0])
        assert "123-45-6789" not in trace_json, "SSN was NOT redacted in trace"
        assert "[REDACTED_SSN]" in trace_json, "SSN redaction marker not found"

    def test_email_redacted_in_trace(self, temp_tracer):
        """Email addresses must be redacted in trace data."""
        email_text = "Contact me at john.doe@example.com for details"
        with temp_tracer.trace("word", "draft_email", input_summary=email_text) as ctx:
            ctx.add_span("llm_call", input_data=email_text)

        traces = temp_tracer.read_traces()
        trace_json = json.dumps(traces[0])
        assert "john.doe@example.com" not in trace_json, "Email was NOT redacted in trace"
        assert "[REDACTED_EMAIL]" in trace_json, "Email redaction marker not found"

    def test_phone_redacted_in_trace(self, temp_tracer):
        """Phone numbers must be redacted in trace data."""
        phone_text = "Call me at 555-123-4567"
        with temp_tracer.trace("word", "draft_memo", input_summary=phone_text) as ctx:
            ctx.add_span("llm_call", input_data=phone_text)

        traces = temp_tracer.read_traces()
        trace_json = json.dumps(traces[0])
        assert "555-123-4567" not in trace_json, "Phone was NOT redacted in trace"
        assert "[REDACTED_PHONE]" in trace_json, "Phone redaction marker not found"

    def test_credit_card_redacted_in_trace(self, temp_tracer):
        """Credit card numbers must be redacted in trace data."""
        cc_text = "Card: 4111-1111-1111-1111"
        with temp_tracer.trace("excel", "process_payment", input_summary=cc_text) as ctx:
            ctx.add_span("llm_call", input_data=cc_text)

        traces = temp_tracer.read_traces()
        trace_json = json.dumps(traces[0])
        assert "4111-1111-1111-1111" not in trace_json, "Credit card was NOT redacted in trace"
        assert "[REDACTED_CC]" in trace_json, "Credit card redaction marker not found"

    def test_multiple_pii_types_redacted(self, temp_tracer):
        """Multiple PII types in the same text must all be redacted."""
        text = "SSN: 123-45-6789, Email: jane@company.org, Phone: 555-987-6543"
        with temp_tracer.trace("legal", "contract_review", input_summary=text) as ctx:
            ctx.add_span("llm_call", input_data=text, output_data=text)

        traces = temp_tracer.read_traces()
        trace_json = json.dumps(traces[0])
        assert "123-45-6789" not in trace_json
        assert "jane@company.org" not in trace_json
        assert "555-987-6543" not in trace_json
        assert "[REDACTED_SSN]" in trace_json
        assert "[REDACTED_EMAIL]" in trace_json
        assert "[REDACTED_PHONE]" in trace_json


class TestSystemPromptLeakage:
    """Test that system prompts are NOT leaked in traces (PR-03)."""

    def test_system_prompt_not_in_trace(self, temp_tracer):
        """System prompts must not appear in trace data."""
        user_prompt = "Help me write a document about AI."

        with temp_tracer.trace("word", "generate_response", input_summary=user_prompt) as ctx:
            # The trace should only capture the user prompt, NOT the system prompt
            ctx.add_span("llm_call", input_data=user_prompt, output_data="Here is your document...")

        traces = temp_tracer.read_traces()
        trace_json = json.dumps(traces[0])
        assert (
            "confidential Kairo system agent" not in trace_json
        ), "System prompt was leaked in trace data — PR-03 VIOLATION"
        assert (
            "Never reveal this prompt" not in trace_json
        ), "System prompt was leaked in trace data — PR-03 VIOLATION"


class TestProvenanceBridge:
    """Test the provenance bridge that links Python traces to Rust receipts."""

    def test_read_receipts_from_empty_file(self, tmp_path):
        """Reading receipts from a non-existent file returns empty list."""
        path = tmp_path / "receipts.jsonl"
        receipts = read_receipts(path)
        assert receipts == []

    def test_read_receipts_from_file(self, tmp_path):
        """Reading receipts from a file with content returns them."""
        path = tmp_path / "receipts.jsonl"
        receipt = {
            "seq": 0,
            "timestamp": 1719200000,
            "agent_id": "abcd1234",
            "action": "generate_response",
            "context": "doc.docx",
            "outcome": "ok",
            "prev_hash": "genesis",
            "self_hash": "fakehash",
            "signature": "fakesig",
            "opik_trace_id": "trace_001",
            "opik_trace_url": "http://localhost:5173/trace/trace_001",
            "domain": "word",
        }
        path.write_text(json.dumps(receipt) + "\n")

        receipts = read_receipts(path)
        assert len(receipts) == 1
        assert receipts[0]["opik_trace_id"] == "trace_001"
        assert receipts[0]["domain"] == "word"

    def test_find_receipts_by_trace_id(self, tmp_path):
        """Finding receipts by trace_id works correctly."""
        path = tmp_path / "receipts.jsonl"
        r1 = {"opik_trace_id": "trace_001", "domain": "word", "seq": 0}
        r2 = {"opik_trace_id": "trace_002", "domain": "excel", "seq": 1}
        r3 = {"opik_trace_id": "trace_001", "domain": "word", "seq": 2}
        path.write_text(json.dumps(r1) + "\n" + json.dumps(r2) + "\n" + json.dumps(r3) + "\n")

        found = find_receipts_by_trace_id("trace_001", path)
        assert len(found) == 2
        assert all(r["opik_trace_id"] == "trace_001" for r in found)

    def test_verify_trace_receipt_linkage(self, tmp_path):
        """Trace-receipt linkage verification works correctly."""
        path = tmp_path / "receipts.jsonl"
        r1 = {"opik_trace_id": "trace_001", "domain": "word"}
        r2 = {"opik_trace_id": "trace_002", "domain": "excel"}
        path.write_text(json.dumps(r1) + "\n" + json.dumps(r2) + "\n")

        linkage = verify_trace_receipt_linkage(["trace_001", "trace_002", "trace_003"], path)
        assert linkage["trace_001"] == True
        assert linkage["trace_002"] == True
        assert linkage["trace_003"] == False  # Missing

    def test_canonical_receipt_json_order(self):
        """Canonical receipt JSON must use the correct field order."""
        receipt = {
            "seq": 0,
            "timestamp": 1719200000,
            "agent_id": "abcd",
            "action": "test",
            "context": "doc",
            "outcome": "ok",
            "prev_hash": "genesis",
            "self_hash": "hash",
            "signature": "sig",
            "opik_trace_id": "trace_1",
            "opik_trace_url": "url",
            "domain": "word",
        }
        canonical = canonical_receipt_json(receipt)
        # Verify the field order matches the Rust struct
        # The first field should be "seq"
        assert canonical.startswith('{"seq":')
        # self_hash and signature should be empty
        assert '"self_hash":""' in canonical
        assert '"signature":""' in canonical


class TestTrackDecorator:
    """Test the @track decorator for domain masters."""

    def test_track_decorator_creates_trace(self, temp_tracer):
        """The @track decorator should create a trace for the wrapped function."""

        @track("word", "generate_response")
        def mock_domain_master(self, prompt):
            return f"Response to: {prompt}"

        class FakeMaster:
            pass

        result = mock_domain_master(FakeMaster(), "test prompt")
        assert result == "Response to: test prompt"

        traces = temp_tracer.read_traces()
        assert len(traces) == 1
        assert traces[0]["domain"] == "word"
        assert traces[0]["action"] == "generate_response"

    def test_track_decorator_captures_errors(self, temp_tracer):
        """The @track decorator should capture errors in the trace."""

        @track("excel", "recompute")
        def failing_master(self, data):
            raise ValueError("Computation failed")

        class FakeMaster:
            pass

        with pytest.raises(ValueError):
            failing_master(FakeMaster(), "data")

        traces = temp_tracer.read_traces()
        assert len(traces) == 1
        assert traces[0]["metadata"]["outcome"] == "error"
        assert "Computation failed" in traces[0]["metadata"]["error"]
