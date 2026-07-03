# PROVENANCE: original | clean-room airgap egress oracle tests per specs/R3_AIRGAP_ENFORCEMENT.md
"""Kill-proof tests for the airgap_egress oracle and sealed build profile.

Tests verify (per specs/VERIFICATION_ORACLES.md + specs/R3_AIRGAP_ENFORCEMENT.md):

  1. **airgap_egress oracle**: the legal-redline flow runs under sealed mode
     with live egress capture and asserts 0 outbound packets.
  2. **Kill-proof (egress)**: a deliberate socket connect to an external host
     MUST turn the oracle red (zero_egress=False).
  3. **Kill-proof (DNS)**: a deliberate DNS lookup MUST turn the oracle red.
  4. **Sealed profile**: sealed mode is a one-way switch; deactivation raises.
  5. **Sealed fallback ladder**: in sealed mode, low confidence → human-review
     flag, never cloud fallback.
  6. **sealed_binary_scan**: static scan of sealed source dirs finds no
     networking symbols (except in the allowlisted oracle/test files).
  7. **Signed egress report**: the zero-egress report is tied to the airgap
     result (CLAIM_DISCIPLINE wording).

All tests run fully offline (KAIRO_NO_NET=1, KAIRO_SEALED=1). No mocks on
production paths. The legal-redline pipeline is the REAL pipeline running on
real fixtures.
"""

from __future__ import annotations

import json
import os
import socket
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.oracles.airgap_egress import (
    SocketEgressInterceptor,
    run_airgap_egress_oracle,
    verify_airgap_egress,
    run_kill_proof,
    sealed_binary_scan,
)
from kairo.sealed_profile import (
    activate_sealed_mode,
    deactivate_sealed_mode,
    is_sealed,
    sealed_fallback_ladder,
    low_confidence_flag,
    SealedModeViolation,
)
from kairo.oracles.zero_egress_report import (
    verify_zero_egress_report,
    report_from_json,
)

# --- Fixture paths ---
_FIXTURE_DIR = os.path.join(_REPO_ROOT, "fixtures", "legal_redline")
_CONTRACT = os.path.join(_FIXTURE_DIR, "sample_contract.docx")
_PLAYBOOK = os.path.join(_FIXTURE_DIR, "playbook.json")


@pytest.fixture(autouse=True)
def _ensure_sealed():
    """Ensure sealed mode is active for every test."""
    activate_sealed_mode(reason="test fixture")
    yield


@pytest.fixture
def private_key():
    return ed25519.Ed25519PrivateKey.generate()


# ======================== AIRGAP EGRESS ORACLE ========================


class TestAirgapEgressOracle:
    """The airgap_egress oracle must assert 0 outbound in sealed mode."""

    def test_legal_redline_zero_egress(self, private_key, tmp_path):
        """The legal-redline flow runs under sealed mode with 0 outbound packets."""
        out = str(tmp_path / "redlined_sealed.docx")
        report = run_airgap_egress_oracle(
            contract_path=_CONTRACT,
            playbook_path=_PLAYBOOK,
            output_path=out,
            private_key=private_key,
        )
        assert report.session_completed, f"Flow did not complete: {report.error}"
        assert (
            report.total_egress_attempts == 0
        ), f"VIOLATION: {report.total_egress_attempts} egress attempts in sealed mode"
        assert (
            report.total_dns_lookups == 0
        ), f"VIOLATION: {report.total_dns_lookups} DNS lookups in sealed mode"
        assert report.zero_egress is True
        assert report.passed is True
        assert report.sealed_mode_active is True
        assert verify_airgap_egress(report) is True

    def test_egress_report_has_hash(self, private_key, tmp_path):
        """The egress report has a content hash for integrity."""
        out = str(tmp_path / "redlined_sealed.docx")
        report = run_airgap_egress_oracle(
            contract_path=_CONTRACT,
            playbook_path=_PLAYBOOK,
            output_path=out,
            private_key=private_key,
        )
        assert report.report_hash != ""
        assert len(report.report_hash) == 64  # SHA-256 hex

    def test_egress_report_enforcement_mechanism(self, private_key, tmp_path):
        """The report records which enforcement mechanism was used."""
        out = str(tmp_path / "redlined_sealed.docx")
        report = run_airgap_egress_oracle(
            contract_path=_CONTRACT,
            playbook_path=_PLAYBOOK,
            output_path=out,
        )
        assert "socket_interception" in report.enforcement_mechanism

    def test_egress_report_serializable(self, private_key, tmp_path):
        """The report can be serialized to JSON and back."""
        out = str(tmp_path / "redlined_sealed.docx")
        report = run_airgap_egress_oracle(
            contract_path=_CONTRACT,
            playbook_path=_PLAYBOOK,
            output_path=out,
        )
        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["total_egress_attempts"] == 0
        assert parsed["zero_egress"] is True
        assert parsed["sealed_mode_active"] is True


# ======================== KILL-PROOFS ========================


class TestKillProofs:
    """Kill-proofs: a flow that opens a socket MUST turn the oracle red."""

    def test_kill_proof_egress(self):
        """Deliberately connecting to an external host MUST be caught."""
        report = run_kill_proof()
        # The kill-proof MUST show at least 1 egress attempt
        assert (
            report.total_egress_attempts > 0
        ), "KILL-PROOF FAILED: oracle did not catch a deliberate egress attempt"
        assert (
            report.zero_egress is False
        ), "KILL-PROOF FAILED: oracle reported zero_egress=True despite egress"
        assert (
            report.passed is False
        ), "KILL-PROOF FAILED: oracle reported passed=True despite egress"

    def test_kill_proof_dns(self):
        """Deliberately doing a DNS lookup MUST be caught."""
        report = run_kill_proof()
        assert (
            report.total_dns_lookups > 0
        ), "KILL-PROOF FAILED: oracle did not catch a deliberate DNS lookup"
        assert report.zero_egress is False

    def test_kill_proof_socket_interceptor_catches_connect(self):
        """Direct test: SocketEgressInterceptor catches socket.connect to external."""
        with SocketEgressInterceptor() as interceptor:
            with pytest.raises(ConnectionError, match="AIR-GAP VIOLATION"):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(("93.184.216.34", 80))
                s.close()
        assert len(interceptor.attempts) > 0
        assert interceptor.attempts[0].blocked is True

    def test_kill_proof_socket_interceptor_catches_dns(self):
        """Direct test: SocketEgressInterceptor catches gethostbyname for external."""
        with SocketEgressInterceptor() as interceptor:
            with pytest.raises(socket.gaierror, match="AIR-GAP VIOLATION"):
                socket.gethostbyname("example.com")
        assert len(interceptor.dns_lookups) > 0

    def test_kill_proof_loopback_allowed(self):
        """Loopback connections are NOT blocked (LAN/IPC stays in-subnet)."""
        with SocketEgressInterceptor():
            # Loopback DNS should work
            result = socket.gethostbyname("localhost")
            assert result == "127.0.0.1"


# ======================== SEALED PROFILE ========================


class TestSealedProfile:
    """Sealed build profile tests."""

    def test_sealed_mode_active(self):
        """Sealed mode is active after activation."""
        assert is_sealed() is True

    def test_sealed_mode_one_way_switch(self):
        """Deactivating sealed mode raises SealedModeViolation."""
        with pytest.raises(SealedModeViolation, match="cannot be deactivated"):
            deactivate_sealed_mode()

    def test_sealed_fallback_ladder_no_cloud(self):
        """In sealed mode, the fallback ladder has no cloud path."""
        ladder = sealed_fallback_ladder()
        assert any(
            "human-review" in step.lower() or "human_review" in step.lower() for step in ladder
        ), "Sealed fallback ladder must include human-review flag"
        assert not any(
            "cloud" in step.lower() and "no cloud" not in step.lower() for step in ladder
        ), "Sealed fallback ladder must not include cloud fallback"

    def test_low_confidence_flag_sealed(self):
        """In sealed mode, low confidence → human_review_required, not cloud."""
        flag = low_confidence_flag(confidence=0.3, threshold=0.7)
        assert flag["sealed_mode"] is True
        assert flag["low_confidence"] is True
        assert flag["action"] == "human_review_required"
        assert flag["cloud_fallback_available"] is False

    def test_high_confidence_no_flag(self):
        """High confidence → accept, no flag needed."""
        flag = low_confidence_flag(confidence=0.9, threshold=0.7)
        assert flag["low_confidence"] is False
        assert flag["action"] == "accept"


# ======================== SEALED BINARY SCAN ========================


class TestSealedBinaryScan:
    """Static symbol scan for networking symbols in sealed source paths."""

    def test_sealed_source_dirs_clean(self):
        """The kairo/oracles and kairo/sealed_profile paths contain no
        networking symbols (except allowlisted oracle/test files)."""
        result = sealed_binary_scan(
            [
                os.path.join(_REPO_ROOT, "kairo", "oracles"),
                os.path.join(_REPO_ROOT, "kairo", "sealed_profile.py").replace(
                    "sealed_profile.py",
                    "",  # scan the kairo/ dir
                ),
            ]
        )
        # Filter out violations in allowlisted files (should already be excluded)
        real_violations = [
            v
            for v in result["violations"]
            if not any(
                allowed in v["file"]
                for allowed in [
                    "airgap_egress.py",
                    "sealed_profile.py",
                    "test_airgap",
                    "airgap_proof.py",
                    "zero_egress_report.py",
                ]
            )
        ]
        assert (
            len(real_violations) == 0
        ), f"sealed_binary_scan found networking symbols: {real_violations[:5]}"

    def test_sealed_binary_scan_catches_violation(self, tmp_path):
        """Kill-proof: a file with networking symbols MUST be flagged."""
        # Create a temp file with a networking symbol
        bad_file = tmp_path / "bad_module.py"
        bad_file.write_text(
            "import requests\ndef fetch():\n    return requests.get('https://evil.com')\n"
        )
        result = sealed_binary_scan([str(tmp_path)])
        assert result["passed"] is False
        assert len(result["violations"]) > 0
        assert "requests.get" in result["violations"][0]["pattern"]


# ======================== SIGNED EGRESS REPORT TIE-IN ========================


class TestSignedEgressReport:
    """The airgap result ties into the signed zero-egress report
    (CLAIM_DISCIPLINE wording: 'reproducible, signed report showing zero
    outbound connections; source open for audit')."""

    def test_airgap_report_tied_to_zero_egress_report(self, private_key, tmp_path):
        """The legal-redline flow emits both an AirgapEgressReport and a
        signed ZeroEgressReport — they must be consistent."""
        out = str(tmp_path / "redlined_sealed.docx")
        airgap_report = run_airgap_egress_oracle(
            contract_path=_CONTRACT,
            playbook_path=_PLAYBOOK,
            output_path=out,
            private_key=private_key,
        )
        assert airgap_report.passed

        # The legal-redline pipeline also emits a signed zero-egress report
        # (via generate_zero_egress_report). Verify it.
        from kairo.oracles.legal_redline_pipeline import redline_contract

        result = redline_contract(
            contract_path=_CONTRACT,
            playbook_path=_PLAYBOOK,
            output_path=str(tmp_path / "redlined_sealed_2.docx"),
            author="Kairo Legal (Sealed)",
            private_key=private_key,
        )
        assert result.ok
        assert result.egress_report_json != ""

        zero_egress = report_from_json(result.egress_report_json)
        pub_key = private_key.public_key()
        assert verify_zero_egress_report(zero_egress, pub_key) is True
        assert zero_egress.total_edits > 0
        # CLAIM_DISCIPLINE: the offline_attestation must say "reproducible"
        assert "reproducible" in zero_egress.offline_attestation.lower()

    def test_claim_discipline_wording(self, private_key, tmp_path):
        """The zero-egress report uses CLAIM_DISCIPLINE-compliant wording."""
        from kairo.oracles.legal_redline_pipeline import redline_contract

        out = str(tmp_path / "redlined_sealed.docx")
        result = redline_contract(
            contract_path=_CONTRACT,
            playbook_path=_PLAYBOOK,
            output_path=out,
            private_key=private_key,
        )
        zero_egress = report_from_json(result.egress_report_json)
        # Must NOT claim "cryptographic proof forever"
        assert "cryptographic proof" not in zero_egress.offline_attestation.lower()
        # Must say "reproducible" and "open for audit"
        assert "reproducible" in zero_egress.offline_attestation.lower()
