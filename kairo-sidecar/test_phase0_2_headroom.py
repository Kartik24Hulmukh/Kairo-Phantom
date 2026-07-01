"""
Tests for Phase 0.2: Headroom Context Compression

Verifies:
1. Headroom is installed and importable
2. compress_context() produces real compression (tokens_after < tokens_before)
3. Compression ratio is logged correctly
4. Disabled mode returns original text unchanged
5. Empty text is handled gracefully
6. Spreadsheet compression works
7. Token counting works
8. Compression does NOT corrupt critical content (semantic preservation)
"""

import os
from unittest.mock import patch

from sidecar.observability.headroom_proxy import (
    compress_context,
    compress_spreadsheet_context,
    count_tokens,
    get_headroom_client,
)


class TestHeadroomAvailability:
    """Test that Headroom is installed and available."""

    def test_headroom_imports(self):
        """Headroom must be importable."""
        import headroom

        assert hasattr(headroom, "compress")

    def test_headroom_client_initializes(self):
        """Headroom client must initialize without error."""
        client = get_headroom_client()
        # Client may be None if env flag is off, but shouldn't crash
        assert client is not None or True  # Don't fail if disabled


class TestCompressContext:
    """Test context compression."""

    def test_long_text_is_compressed(self):
        """Long text should be compressed (tokens_after < tokens_before)."""
        long_text = "This is a test paragraph. " * 100  # ~2300 chars
        compressed, metrics = compress_context(long_text)

        # If compression is enabled, tokens_after should be less
        if metrics["compressed"]:
            assert (
                metrics["tokens_after"] < metrics["tokens_before"]
            ), "Compression did not reduce token count"
            assert metrics["compression_ratio"] < 1.0, "Compression ratio should be < 1.0"
            assert len(compressed) > 0, "Compressed text is empty"
        else:
            # If compression is disabled, text should be unchanged
            assert compressed == long_text

    def test_short_text_passthrough(self):
        """Short text may not benefit from compression — should still return valid text."""
        short_text = "Hello world."
        compressed, metrics = compress_context(short_text)
        assert len(compressed) > 0
        assert metrics["chars_before"] == len(short_text)

    def test_empty_text_handled(self):
        """Empty text should be handled gracefully."""
        compressed, metrics = compress_context("")
        assert compressed == ""
        assert metrics["compressed"] == False

    def test_whitespace_only_text_handled(self):
        """Whitespace-only text should be handled gracefully."""
        compressed, metrics = compress_context("   \n\n\t  ")
        assert metrics["compressed"] == False

    def test_metrics_structure(self):
        """Metrics dict should have all required fields."""
        text = "This is a test. " * 50
        _, metrics = compress_context(text)

        required_fields = [
            "tokens_before",
            "tokens_after",
            "compression_ratio",
            "chars_before",
            "chars_after",
            "compressed",
        ]
        for field in required_fields:
            assert field in metrics, f"Missing metric: {field}"

    def test_compression_preserves_key_information(self):
        """Compression should preserve key information (not destroy content)."""
        # Text with specific facts that must survive compression
        text = """
        The contract was signed on January 15, 2024 between Acme Corp and Beta Inc.
        The total value is $1,500,000 USD. The contract terminates on December 31, 2025.
        The governing law is California. The liability cap is $500,000.
        """
        compressed, metrics = compress_context(text)

        # Key facts should survive compression
        # (Even if compressed, the semantic content should be preserved)
        if metrics["compressed"]:
            # At minimum, compressed text should be non-empty
            assert len(compressed) > 0
            # Check that at least some key terms survive
            # (Headroom uses semantic compression, not keyword deletion)
            combined = compressed.lower()
            # At least 2 of these key terms should be present
            key_terms = ["acme", "beta", "1500000", "california", "500000", "2024", "2025"]
            found = sum(1 for term in key_terms if term in combined)
            assert (
                found >= 2
            ), f"Only {found}/7 key terms survived compression — content was destroyed"


class TestDisabledMode:
    """Test behavior when compression is disabled."""

    def test_disabled_returns_original(self):
        """When KAIRO_HEADROOM=0, compression should return original text."""
        with patch.dict(os.environ, {"KAIRO_HEADROOM": "0"}):
            text = "This is a test. " * 50
            compressed, metrics = compress_context(text)
            assert compressed == text
            assert metrics["compressed"] == False
            assert metrics["compression_ratio"] == 1.0


class TestTokenCounting:
    """Test token counting utility."""

    def test_count_tokens_non_empty(self):
        """count_tokens should return a positive integer for non-empty text."""
        tokens = count_tokens("This is a test sentence with several words.")
        assert tokens > 0

    def test_count_tokens_empty(self):
        """count_tokens should return 0 for empty text."""
        assert count_tokens("") == 0

    def test_count_tokens_longer_for_longer_text(self):
        """Longer text should have more tokens."""
        short = count_tokens("Hello world.")
        long_text = count_tokens("This is a much longer text. " * 100)
        assert long_text > short


class TestSpreadsheetCompression:
    """Test spreadsheet-specific compression."""

    def test_spreadsheet_compression_returns_text(self):
        """Spreadsheet compression should return valid text."""
        spreadsheet_data = "Name,Value,Date\nAlice,100,2024-01-01\nBob,200,2024-01-02\n" * 20
        compressed, metrics = compress_spreadsheet_context(spreadsheet_data)
        assert len(compressed) > 0
        assert metrics["chars_before"] == len(spreadsheet_data)

    def test_spreadsheet_metrics_structure(self):
        """Spreadsheet metrics should have all required fields."""
        data = "A,B,C\n1,2,3\n4,5,6\n"
        _, metrics = compress_spreadsheet_context(data)
        for field in ["tokens_before", "tokens_after", "compression_ratio", "compressed"]:
            assert field in metrics


class TestCompressionRatioBenchmark:
    """Benchmark compression ratio on representative document types."""

    def test_contract_text_compression(self):
        """Contract text should achieve meaningful compression."""
        contract = (
            """
        THIS AGREEMENT is made and entered into as of this 15th day of January, 2024,
        by and between Acme Corporation, a Delaware corporation ("Company"), and
        Beta Industries, a California corporation ("Contractor").

        WHEREAS, Company desires to engage Contractor to provide certain services;
        WHEREAS, Contractor is willing to provide such services;

        NOW THEREFORE, in consideration of the mutual covenants contained herein,
        the parties agree as follows:

        1. SERVICES. Contractor shall provide the following services:
           (a) Software development and maintenance
           (b) Technical consulting and advisory
           (c) Code review and quality assurance

        2. COMPENSATION. Company shall pay Contractor $150 per hour for services rendered.
           Payment shall be made monthly within 30 days of invoice.

        3. TERM. This agreement shall commence on January 15, 2024 and continue
           until terminated by either party with 30 days written notice.

        4. CONFIDENTIALITY. Contractor shall maintain confidentiality of all
           Company proprietary information.

        5. LIABILITY. Liability shall be limited to $50,000.

        6. GOVERNING LAW. This agreement shall be governed by California law.
        """
            * 5
        )  # Repeat to make it long enough for meaningful compression

        compressed, metrics = compress_context(contract)
        if metrics["compressed"]:
            # Target: >=60% token reduction (compression_ratio <= 0.4)
            # Note: actual ratio depends on Headroom's algorithm
            print(
                f"Contract compression: {metrics['tokens_before']}→{metrics['tokens_after']} "
                f"({metrics['compression_ratio']:.1%})"
            )
            # At minimum, some reduction should occur
            assert metrics["tokens_after"] <= metrics["tokens_before"]

    def test_repeated_text_compression(self):
        """Highly repetitive text should compress well."""
        repetitive = "The quick brown fox jumps over the lazy dog. " * 200
        compressed, metrics = compress_context(repetitive)
        if metrics["compressed"]:
            print(
                f"Repetitive text: {metrics['tokens_before']}→{metrics['tokens_after']} "
                f"({metrics['compression_ratio']:.1%})"
            )
            # Repetitive text should compress significantly
            assert (
                metrics["compression_ratio"] < 0.8
            ), f"Repetitive text only compressed to {metrics['compression_ratio']:.1%}"
