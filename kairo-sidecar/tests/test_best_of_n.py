"""
tests/test_best_of_n.py — Unit tests for Best-of-N and Adaptive Compute.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from pydantic import BaseModel

from sidecar.adaptive_compute import estimate_difficulty, get_compute_budget
from sidecar.best_of_n import run_best_of_n


class DummySchema(BaseModel):
    ok: bool
    val: str


def test_estimate_difficulty():
    # Simple prompt
    assert estimate_difficulty("hi", "word") == "simple"

    # Medium prompt
    assert estimate_difficulty("Please write a summary of the topic", "word") == "medium"

    # Complex prompt (high-stakes keyword)
    assert (
        estimate_difficulty("review this NDA contract and add a liability cap", "word") == "complex"
    )

    # Complex prompt (waza agent)
    assert estimate_difficulty("write notes", "word", waza_agent="legal_reviewer") == "complex"


def test_get_compute_budget():
    simple_budget = get_compute_budget("simple")
    assert simple_budget["use_best_of_n"] is False
    assert simple_budget["N"] == 1

    complex_budget = get_compute_budget("complex")
    assert complex_budget["use_best_of_n"] is True
    assert complex_budget["N"] == 3


def test_run_best_of_n_fallback(tmpdir):
    file_path = os.path.join(str(tmpdir), "test.docx")
    with open(file_path, "w") as f:
        f.write("dummy")

    # Test N <= 1 fallback
    with patch("sidecar.best_of_n.call_with_schema") as mock_call:
        mock_call.return_value = DummySchema(ok=True, val="hello")
        res = run_best_of_n("prompt", DummySchema, "model", "word", file_path, None, None, N=1)
        assert res.val == "hello"
        mock_call.assert_called_once()


def test_estimate_difficulty_doc_length_and_page():
    # Simple prompt but large document (length > 10000)
    assert estimate_difficulty("hi", "word", document_length=15000) == "complex"
    # Simple prompt but page count > 5
    assert estimate_difficulty("hi", "word", document_page_count=6) == "complex"
    # Normal medium case
    assert estimate_difficulty("hi", "word", document_length=500, document_page_count=1) == "simple"


def test_run_best_of_n_pdf_scoring(tmpdir):
    file_path = os.path.join(str(tmpdir), "test.pdf")
    with open(file_path, "w") as f:
        f.write("dummy pdf")

    # Mock call_with_schema to return 3 different candidates
    candidate_1 = DummySchema(ok=True, val="candidate 1 text")
    candidate_2 = DummySchema(ok=True, val="candidate 2 text")
    candidate_3 = DummySchema(ok=True, val="candidate 3 text")

    # Mock master and doc_context
    mock_master = MagicMock()
    mock_master.validate_operations.side_effect = lambda cand, ctx: [cand.val]

    # We mock verify_pdf to fail for candidate_1 and candidate_2, but pass for candidate_3.
    def mock_verify_pdf(path, expected_substrings=None):
        if expected_substrings and "candidate 3 text" in expected_substrings[0]:
            return True
        raise AssertionError("mismatch")

    with (
        patch(
            "sidecar.best_of_n.call_with_schema",
            side_effect=[candidate_1, candidate_2, candidate_3, candidate_1],
        ),
        patch("sidecar.best_of_n.verify_pdf", side_effect=mock_verify_pdf),
    ):
        res = run_best_of_n(
            "prompt", DummySchema, "model", "pdf", file_path, mock_master, MagicMock(), N=3
        )
        assert res.val == "candidate 3 text"
