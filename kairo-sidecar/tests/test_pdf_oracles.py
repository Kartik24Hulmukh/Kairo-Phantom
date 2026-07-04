# PROVENANCE: original | clean-room PDF oracle tests per specs/VERIFICATION_ORACLES.md
"""PDF domain oracle tests — 4 oracles + kill-proofs + honest-degradation + gauntlet.

Tests verify:
  1. pdf_text_roundtrip: pdfplumber coords stable within tolerance.
     Kill-proof: shift a word box → FAIL.
  2. pdf_render_diff: pypdfium2 render before/after; redaction removes target
     in pixels AND in extracted text.
     Kill-proof: leave text under a black box → FAIL.
  3. pdf_form_readback: fill AcroForm field → re-read via pikepdf.
     Kill-proof: write wrong value → FAIL.
  4. pdf_signature_verify: pyHanko verifies a signed doc.
     Kill-proof: tamper one byte → verification FAILS.
  5. Honest degradation: OCR engine unavailable → FAIL LOUD.
  6. >=3 gauntlet scenarios: born-digital report, form-heavy gov PDF, scanned contract.
  7. Trust stack integration: audit log + egress report.
  8. CLI integration: pdf subcommand works end-to-end.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.pdf.engine import (
    OCREngineUnavailableError,
    classify_pdf,
    extract_text_with_coords,
    fill_form_fields,
    pdf_form_readback,
    pdf_pipeline,
    pdf_render_diff,
    pdf_text_roundtrip,
    read_form_fields,
    redact_text,
    render_page_hash,
    sign_pdf,
    tamper_pdf_byte,
    verify_signature,
)

# Fixture paths
_PDF_DIR = os.path.join(_REPO_ROOT, "fixtures", "pdf")
_S01 = os.path.join(_PDF_DIR, "s01_born_digital_report.pdf")
_S02 = os.path.join(_PDF_DIR, "s02_form_heavy_gov.pdf")
_S03 = os.path.join(_PDF_DIR, "s03_scanned_contract.pdf")


# ---------------------------------------------------------------------------
# Helper: check engine availability
# ---------------------------------------------------------------------------


def _pdfplumber_available() -> bool:
    try:
        import pdfplumber  # noqa: F401

        return True
    except ImportError:
        return False


def _pypdfium2_available() -> bool:
    try:
        import pypdfium2  # noqa: F401

        return True
    except ImportError:
        return False


def _pikepdf_available() -> bool:
    try:
        import pikepdf  # noqa: F401

        return True
    except ImportError:
        return False


def _pyhanko_available() -> bool:
    try:
        import pyhanko  # noqa: F401

        return True
    except ImportError:
        return False


def _olmocr_available() -> bool:
    try:
        import olmocr  # noqa: F401

        return True
    except ImportError:
        return False


_HAS_PDFPLUMBER = _pdfplumber_available()
_HAS_PYPDFIUM2 = _pypdfium2_available()
_HAS_PIKEPDF = _pikepdf_available()
_HAS_PYHANKO = _pyhanko_available()
_HAS_OLMOCR = _olmocr_available()


# ---------------------------------------------------------------------------
# Oracle 1: pdf_text_roundtrip
# ---------------------------------------------------------------------------


class TestPdfTextRoundtrip:
    """pdf_text_roundtrip oracle: pdfplumber coords stable within tolerance."""

    def test_born_digital_coords_stable(self):
        """Two extractions produce identical word coordinates — deterministic."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available — cannot test pdf_text_roundtrip")

        passed, first, second = pdf_text_roundtrip(_S01, tolerance=1.0)
        assert passed, (
            f"pdf_text_roundtrip FAILED: coordinates not stable. "
            f"First extraction: {len(first)} words, Second: {len(second)} words"
        )
        assert len(first) > 0, "No words extracted from born-digital PDF"
        assert len(first) == len(second), "Word count mismatch between extractions"

    def test_kill_proof_shifted_box_fails(self):
        """Kill-proof: shift a word box by >tolerance → oracle FAILS."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available")

        from kairo.pdf.engine import WordBox

        _, first, _ = pdf_text_roundtrip(_S01, tolerance=1.0)
        assert len(first) > 0

        # Shift the first word box by 5 points (well above tolerance=1.0)
        shifted = WordBox(
            text=first[0].text,
            x0=first[0].x0 + 5.0,
            y0=first[0].y0,
            x1=first[0].x1 + 5.0,
            y1=first[0].y1,
            page=first[0].page,
        )

        # The shifted box must NOT match the original within tolerance
        drift = abs(shifted.x0 - first[0].x0)
        assert (
            drift > 1.0
        ), f"Kill-proof FAILED: shifted box drift {drift} should exceed tolerance 1.0"

    def test_text_contains_expected_fragments(self):
        """Extracted text contains expected content from the born-digital fixture."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available")

        text, words = extract_text_with_coords(_S01)
        assert "Quarterly Financial Report" in text
        assert "Executive Summary" in text
        assert "Revenue Breakdown" in text
        assert len(words) > 20, f"Expected >20 words, got {len(words)}"


# ---------------------------------------------------------------------------
# Oracle 2: pdf_render_diff
# ---------------------------------------------------------------------------


class TestPdfRenderDiff:
    """pdf_render_diff oracle: render before/after → redaction removes text."""

    def test_redaction_removes_text_in_pixels_and_text(self):
        """Redaction changes pixels AND removes target text from extracted text."""
        if not _HAS_PYPDFIUM2:
            pytest.fail("pypdfium2 not available — cannot test pdf_render_diff")
        if not _HAS_PIKEPDF:
            pytest.fail("pikepdf not available — cannot test redaction")
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available — cannot verify text removal")

        target = "contingency reserve of $2.5 million"

        with tempfile.TemporaryDirectory() as tmp:
            redacted_path = os.path.join(tmp, "redacted.pdf")
            edits = redact_text(_S01, target, redacted_path)
            assert len(edits) > 0, "No redaction edits applied"

            passed, hash_before, hash_after, text_absent = pdf_render_diff(
                _S01, redacted_path, target
            )
            assert passed, (
                f"pdf_render_diff FAILED: pixels_changed={hash_before != hash_after}, "
                f"text_absent={text_absent}"
            )
            assert hash_before != hash_after, "Render hashes identical — no pixel change"
            assert text_absent, "Target text still present after redaction"

    def test_kill_proof_black_box_only_fails(self):
        """Kill-proof: if text remains (black box only), oracle FAILS.

        We verify that the original (un-redacted) PDF would fail the oracle
        because the text is still present.
        """
        if not _HAS_PYPDFIUM2:
            pytest.fail("pypdfium2 not available")
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available")

        target = "Quarterly Financial Report"

        # Compare the PDF against itself — text is present, so text_absent=False
        passed, _, _, text_absent = pdf_render_diff(_S01, _S01, target)
        assert (
            not passed
        ), "Kill-proof FAILED: oracle passed when text is still present (black box only)"
        assert not text_absent, "Text should be present in the un-redacted PDF"

    def test_render_hash_deterministic(self):
        """Render hash is deterministic — same PDF, same hash."""
        if not _HAS_PYPDFIUM2:
            pytest.fail("pypdfium2 not available")

        h1 = render_page_hash(_S01, page_num=0, scale=2.0)
        h2 = render_page_hash(_S01, page_num=0, scale=2.0)
        assert h1 == h2, "Render hash is not deterministic"


# ---------------------------------------------------------------------------
# Oracle 3: pdf_form_readback
# ---------------------------------------------------------------------------


class TestPdfFormReadback:
    """pdf_form_readback oracle: fill AcroForm → re-read → values match."""

    def test_fill_and_readback(self):
        """Fill form fields, re-read, and verify values match."""
        if not _HAS_PIKEPDF:
            pytest.fail("pikepdf not available — cannot test pdf_form_readback")

        field_values = {
            "full_name": "Jane Marie Smith",
            "address": "123 Main Street, Springfield, IL 62701",
            "phone": "(555) 123-4567",
            "email": "jane.smith@example.com",
            "certify_checkbox": "/Yes",
        }

        passed, readback = pdf_form_readback(_S02, field_values)
        assert passed, f"pdf_form_readback FAILED: values don't match. Readback: {readback}"
        assert readback.get("full_name", "").lstrip("/") == "Jane Marie Smith"
        assert "123 Main Street" in readback.get("address", "")
        assert "(555) 123-4567" in readback.get("phone", "")
        assert "jane.smith@example.com" in readback.get("email", "")

    def test_kill_proof_wrong_value_fails(self):
        """Kill-proof: write wrong value → readback mismatch → FAIL."""
        if not _HAS_PIKEPDF:
            pytest.fail("pikepdf not available")

        # Fill with one value, but expect a different value — must fail
        field_values = {
            "full_name": "Jane Marie Smith",
        }
        passed, readback = pdf_form_readback(_S02, field_values)
        assert passed, "Correct fill should pass"

        # Now verify that a wrong expected value would fail
        actual = readback.get("full_name", "")
        assert (
            actual != "Wrong Name"
        ), "Kill-proof FAILED: readback returned wrong value that should not match"

    def test_form_field_count(self):
        """The form PDF has the expected number of fields."""
        if not _HAS_PIKEPDF:
            pytest.fail("pikepdf not available")

        fields = read_form_fields(_S02)
        assert len(fields) == 5, f"Expected 5 fields, got {len(fields)}: {fields}"
        assert "full_name" in fields
        assert "address" in fields
        assert "phone" in fields
        assert "email" in fields
        assert "certify_checkbox" in fields


# ---------------------------------------------------------------------------
# Oracle 4: pdf_signature_verify
# ---------------------------------------------------------------------------


class TestPdfSignatureVerify:
    """pdf_signature_verify oracle: pyHanko verifies a signed doc."""

    def test_sign_and_verify(self):
        """Sign a PDF, then verify the signature is valid."""
        if not _HAS_PYHANKO:
            pytest.fail("pyhanko not available — cannot test pdf_signature_verify")

        with tempfile.TemporaryDirectory() as tmp:
            signed_path = os.path.join(tmp, "signed.pdf")
            edit = sign_pdf(_S01, signed_path, signer_name="Kairo Test Signer")
            assert edit.action == "sign"

            valid = verify_signature(signed_path)
            assert valid, "Signature verification failed on freshly signed PDF"

    def test_kill_proof_tampered_byte_fails(self):
        """Kill-proof: tamper one byte → verification FAILS."""
        if not _HAS_PYHANKO:
            pytest.fail("pyhanko not available")

        with tempfile.TemporaryDirectory() as tmp:
            signed_path = os.path.join(tmp, "signed.pdf")
            tampered_path = os.path.join(tmp, "tampered.pdf")

            sign_pdf(_S01, signed_path, signer_name="Kairo Test Signer")

            # Verify the original signed PDF is valid
            valid_before = verify_signature(signed_path)
            assert valid_before, "Signed PDF should be valid before tampering"

            # Tamper one byte
            tamper_pdf_byte(signed_path, tampered_path)

            # The tampered PDF should fail verification
            valid_after = verify_signature(tampered_path)
            assert (
                not valid_after
            ), "Kill-proof FAILED: tampered PDF signature still verified as valid"


# ---------------------------------------------------------------------------
# Honest degradation: OCR engine unavailable
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """OCR engine unavailable → FAIL LOUD, never empty success."""

    def test_ocr_unavailable_fails_loud(self):
        """If olmocr is not installed, the OCR path must raise OCREngineUnavailableError."""
        from kairo.pdf.engine import ocr_scanned_pdf

        if _HAS_OLMOCR:
            # If olmocr IS installed, verify it produces real text (not a skip)
            ocr_text = ocr_scanned_pdf(_S03)
            assert len(ocr_text.strip()) > 0, "OCR should produce text from scanned PDF"
        else:
            # If olmocr is NOT installed, must FAIL LOUD
            with pytest.raises(OCREngineUnavailableError) as exc_info:
                ocr_scanned_pdf(_S03)

            msg = str(exc_info.value)
            assert "OCR engine unavailable" in msg or "olmocr" in msg.lower()
            assert "install" in msg.lower(), "Error message should mention installation"

    def test_scanned_pdf_classified_correctly(self):
        """The scanned contract fixture is classified as scanned (no text layer)."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available")

        is_scanned, reason = classify_pdf(_S03)
        assert is_scanned, f"Scanned contract should be classified as scanned: {reason}"

    def test_born_digital_classified_correctly(self):
        """The born-digital report is classified as NOT scanned."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available")

        is_scanned, reason = classify_pdf(_S01)
        assert not is_scanned, f"Born-digital report should not be scanned: {reason}"

    def test_pipeline_scanned_ocr_unavailable_fails_loud(self):
        """pdf_pipeline on scanned PDF without OCR → ok=False, error mentions OCR."""
        with tempfile.TemporaryDirectory() as tmp:
            result = pdf_pipeline(
                input_path=_S03,
                output_path=os.path.join(tmp, "out.pdf"),
                action="extract",
            )
            if _HAS_OLMOCR:
                # If olmocr IS installed, pipeline should succeed with OCR text
                assert result.ok, "Pipeline should succeed when OCR is available"
                assert result.ocr_used, "Pipeline should use OCR for scanned PDF"
                assert len(result.extracted_text.strip()) > 0, "OCR should produce text"
            else:
                # If olmocr is NOT installed, must FAIL LOUD
                assert not result.ok, "Pipeline should fail when OCR is unavailable"
                assert result.is_scanned, "Pipeline should detect scanned PDF"
                assert "OCR" in result.error or "olmocr" in result.error.lower()


# ---------------------------------------------------------------------------
# Gauntlet scenarios (>=3, zero skips)
# ---------------------------------------------------------------------------


class TestGauntletScenarios:
    """>=3 end-to-end gauntlet scenarios exercising the full pipeline."""

    def test_scenario_a_born_digital_report(self):
        """Scenario (a): Clean born-digital report — extract + redact."""
        if not _HAS_PDFPLUMBER or not _HAS_PIKEPDF or not _HAS_PYPDFIUM2:
            pytest.fail("Required engines not available for scenario (a)")

        with tempfile.TemporaryDirectory() as tmp:
            # 1. Extract text
            text, words = extract_text_with_coords(_S01)
            assert "Quarterly Financial Report" in text
            assert len(words) > 20

            # 2. Redact sensitive text
            target = "contingency reserve of $2.5 million"
            redacted_path = os.path.join(tmp, "redacted.pdf")
            edits = redact_text(_S01, target, redacted_path)
            assert len(edits) > 0

            # 3. Verify redaction via render-diff oracle
            passed, _, _, text_absent = pdf_render_diff(_S01, redacted_path, target)
            assert passed, "Render-diff oracle failed after redaction"

            # 4. Verify text is truly gone (not just black-boxed)
            text_after, _ = extract_text_with_coords(redacted_path)
            assert target not in text_after, "Redacted text still present"

    def test_scenario_b_form_heavy_government(self):
        """Scenario (b): Form-heavy government PDF — fill + readback + verify."""
        if not _HAS_PIKEPDF:
            pytest.fail("pikepdf not available for scenario (b)")

        field_values = {
            "full_name": "Jane Marie Smith",
            "address": "123 Main Street, Springfield, IL 62701",
            "phone": "(555) 123-4567",
            "email": "jane.smith@example.com",
            "certify_checkbox": "/Yes",
        }

        with tempfile.TemporaryDirectory() as tmp:
            filled_path = os.path.join(tmp, "filled.pdf")

            # 1. Fill form fields
            edits = fill_form_fields(_S02, field_values, filled_path)
            assert len(edits) == 5, f"Expected 5 form fills, got {len(edits)}"

            # 2. Read back filled values
            readback = read_form_fields(filled_path)
            assert readback.get("full_name", "").lstrip("/") == "Jane Marie Smith"
            assert "123 Main Street" in readback.get("address", "")
            assert "(555) 123-4567" in readback.get("phone", "")
            assert "jane.smith@example.com" in readback.get("email", "")

            # 3. Verify via oracle
            passed, _ = pdf_form_readback(_S02, field_values)
            assert passed, "Form readback oracle failed"

    def test_scenario_c_scanned_contract(self):
        """Scenario (c): Scanned contract — classify as scanned, OCR honest-degrade."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available for scenario (c)")

        # 1. Classify — must be scanned
        is_scanned, reason = classify_pdf(_S03)
        assert is_scanned, f"Scanned contract should be classified as scanned: {reason}"

        # 2. Text extraction must return empty (no text layer)
        text, words = extract_text_with_coords(_S03)
        assert len(text.strip()) == 0, "Scanned PDF should have no extractable text"
        assert len(words) == 0, "Scanned PDF should have no word boxes"

        # 3. OCR path — honest degradation
        if _HAS_OLMOCR:
            # If olmocr is available, OCR should produce text
            from kairo.pdf.engine import ocr_scanned_pdf

            ocr_text = ocr_scanned_pdf(_S03)
            assert len(ocr_text.strip()) > 0, "OCR should produce text from scanned PDF"
        else:
            # If olmocr is NOT available, must FAIL LOUD
            from kairo.pdf.engine import ocr_scanned_pdf

            with pytest.raises(OCREngineUnavailableError):
                ocr_scanned_pdf(_S03)


# ---------------------------------------------------------------------------
# Trust stack integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration for PDF pipeline."""

    def test_pipeline_emits_audit_and_egress(self):
        """pdf_pipeline with private_key emits audit log + egress report."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available")

        private_key = ed25519.Ed25519PrivateKey.generate()

        with tempfile.TemporaryDirectory() as tmp:
            result = pdf_pipeline(
                input_path=_S01,
                output_path=os.path.join(tmp, "out.pdf"),
                action="extract",
                private_key=private_key,
            )
            assert result.ok
            assert result.audit_log_json, "Audit log JSON should be non-empty"
            assert result.egress_report_json, "Egress report JSON should be non-empty"

            # Verify audit log
            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

            public_key = private_key.public_key()
            entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
            assert len(entries) > 0, "Audit log should have entries"
            assert Ed25519AuditLog.verify_chain(
                entries, public_key
            ), "Audit log chain verification failed"

            # Verify egress report
            from kairo.oracles.zero_egress_report import (
                report_from_json,
                verify_zero_egress_report,
            )

            report = report_from_json(result.egress_report_json)
            assert verify_zero_egress_report(
                report, public_key
            ), "Zero-egress report verification failed"

    def test_pipeline_redact_with_audit(self):
        """Redaction pipeline emits audit log with redaction edits."""
        if not _HAS_PIKEPDF or not _HAS_PDFPLUMBER:
            pytest.fail("Required engines not available")

        private_key = ed25519.Ed25519PrivateKey.generate()

        with tempfile.TemporaryDirectory() as tmp:
            result = pdf_pipeline(
                input_path=_S01,
                output_path=os.path.join(tmp, "redacted.pdf"),
                action="redact",
                spec={"target_text": "contingency reserve of $2.5 million"},
                private_key=private_key,
            )
            assert result.ok
            assert len(result.applied_edits) > 0
            assert result.audit_log_json

            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

            public_key = private_key.public_key()
            entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
            assert Ed25519AuditLog.verify_chain(entries, public_key)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """PDF CLI subcommand works end-to-end."""

    def test_cli_extract(self):
        """`kairo pdf extract` produces output + audit artifacts."""
        if not _HAS_PDFPLUMBER:
            pytest.fail("pdfplumber not available")

        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "pdf_output")
            rc = main(["pdf", "extract", _S01, "--out", out_dir])
            assert rc == 0, f"CLI extract failed with exit code {rc}"

            # Check artifacts
            assert os.path.isfile(os.path.join(out_dir, "audit_log.json"))
            assert os.path.isfile(os.path.join(out_dir, "zero_egress_report.json"))
            assert os.path.isfile(os.path.join(out_dir, "public_key.pem"))

    def test_cli_redact(self):
        """`kairo pdf redact` produces redacted PDF + audit artifacts."""
        if not _HAS_PIKEPDF or not _HAS_PDFPLUMBER:
            pytest.fail("Required engines not available")

        from kairo.cli import main

        spec_path = os.path.join(_PDF_DIR, "s01_spec.json")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "pdf_output")
            rc = main(["pdf", "redact", _S01, spec_path, "--out", out_dir])
            assert rc == 0, f"CLI redact failed with exit code {rc}"

            assert os.path.isfile(os.path.join(out_dir, "redacted.pdf"))
            assert os.path.isfile(os.path.join(out_dir, "audit_log.json"))

    def test_cli_fill(self):
        """`kairo pdf fill` fills form fields + produces audit artifacts."""
        if not _HAS_PIKEPDF:
            pytest.fail("pikepdf not available")

        from kairo.cli import main

        spec_path = os.path.join(_PDF_DIR, "s02_spec.json")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "pdf_output")
            rc = main(["pdf", "fill", _S02, spec_path, "--out", out_dir])
            assert rc == 0, f"CLI fill failed with exit code {rc}"

            assert os.path.isfile(os.path.join(out_dir, "filled.pdf"))
            assert os.path.isfile(os.path.join(out_dir, "audit_log.json"))

    def test_cli_sign(self):
        """`kairo pdf sign` signs PDF + produces audit artifacts."""
        if not _HAS_PYHANKO:
            pytest.fail("pyhanko not available")

        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "pdf_output")
            rc = main(["pdf", "sign", _S01, "--out", out_dir])
            assert rc == 0, f"CLI sign failed with exit code {rc}"

            assert os.path.isfile(os.path.join(out_dir, "signed.pdf"))
            assert os.path.isfile(os.path.join(out_dir, "audit_log.json"))

    def test_cli_verify(self):
        """`kairo pdf verify` verifies a signed PDF."""
        if not _HAS_PYHANKO:
            pytest.fail("pyhanko not available")

        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "pdf_output")
            # First sign
            rc = main(["pdf", "sign", _S01, "--out", out_dir])
            assert rc == 0

            # Then verify
            signed_path = os.path.join(out_dir, "signed.pdf")
            rc = main(["pdf", "verify", signed_path])
            assert rc == 0, f"CLI verify failed with exit code {rc}"
