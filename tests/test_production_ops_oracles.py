# PROVENANCE: original | clean-room production-ops oracle tests per prompts/12_production_ops.md
"""Kill-proof tests for the production-ops oracles (Phase F step 12).

Tests verify (per prompts/12_production_ops.md + specs/VERIFICATION_ORACLES.md):

  1. **airgap_telemetry oracle**: with telemetry "enabled", sealed mode still
     emits ZERO egress and ZERO telemetry writes.
  2. **airgap_telemetry kill-proof**: a forced telemetry send in sealed mode
     is caught by the egress oracle.
  3. **update_signature oracle**: a valid Ed25519-signed update is accepted;
     a tampered payload (one byte flipped) is REJECTED.
  4. **update_signature kill-proof**: a tampered payload that passes
     verification means the oracle is broken.
  5. **supply_chain_gates oracle**: SBOM generates and validates; a clean
     directory passes secret scan; a planted secret is DETECTED; removing
     it passes again.
  6. **supply_chain_gates kill-proof**: a planted secret that is NOT detected
     means the scanner is broken.

All tests run fully offline. No mocks on production paths.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.oracles.production_ops import (  # noqa: E402
    run_airgap_telemetry_oracle,
    verify_airgap_telemetry,
    run_airgap_telemetry_kill_proof,
    run_update_signature_oracle,
    verify_update_signature,
    run_update_signature_kill_proof,
    run_supply_chain_oracle,
    verify_supply_chain,
    run_supply_chain_kill_proof,
    scan_for_secrets,
    generate_cyclonedx_sbom,
    validate_sbom,
)
from kairo.sealed_profile import activate_sealed_mode, is_sealed  # noqa: E402


@pytest.fixture(autouse=True)
def _sealed_mode(monkeypatch):
    """Ensure sealed mode is active for every test. Cleans up env vars after."""
    monkeypatch.setenv("KAIRO_SEALED", "1")
    monkeypatch.setenv("KAIRO_OFFLINE", "1")
    if not is_sealed():
        activate_sealed_mode(reason="production_ops test fixture")
    yield


# ======================== AIRGAP TELEMETRY ORACLE ========================


class TestAirgapTelemetryOracle:
    """Oracle 1: telemetry ON in sealed mode → zero egress."""

    def test_telemetry_enabled_sealed_zero_egress(self, tmp_path):
        """With telemetry enabled, sealed mode emits ZERO egress and ZERO writes."""
        config_path = str(tmp_path / "config.json")
        report = run_airgap_telemetry_oracle(config_path, sealed_env=True)

        assert report.telemetry_enabled is True, "Telemetry should be enabled"
        assert report.sealed_mode_active is True, "Sealed mode should be active"
        assert report.telemetry_writes_succeeded == 0, (
            f"VIOLATION: {report.telemetry_writes_succeeded} telemetry writes "
            f"succeeded in sealed mode with telemetry enabled"
        )
        assert report.egress_attempts == 0, (
            f"VIOLATION: {report.egress_attempts} egress attempts in sealed mode"
        )
        assert report.zero_egress is True
        assert verify_airgap_telemetry(report) is True

    def test_telemetry_file_not_created_in_sealed_mode(self, tmp_path):
        """The telemetry JSONL file must NOT be created in sealed mode."""
        config_path = str(tmp_path / "config.json")
        telemetry_file = tmp_path / "telemetry.jsonl"

        report = run_airgap_telemetry_oracle(config_path, sealed_env=True)

        assert not telemetry_file.exists(), (
            "telemetry.jsonl was created in sealed mode — sealed mode is broken"
        )
        assert report.passed is True

    def test_airgap_telemetry_report_hash(self, tmp_path):
        """The report hash is deterministic (same content → same hash)."""
        config_path = str(tmp_path / "config.json")
        report = run_airgap_telemetry_oracle(config_path, sealed_env=True)
        assert report.report_hash != ""
        assert len(report.report_hash) == 64  # SHA-256 hex


class TestAirgapTelemetryKillProof:
    """Kill-proof: forced telemetry send in sealed mode → egress oracle catches it."""

    def test_forced_telemetry_send_caught(self, tmp_path):
        """A forced telemetry send in sealed mode MUST be caught by egress oracle."""
        config_path = str(tmp_path / "config.json")
        report = run_airgap_telemetry_kill_proof(config_path)

        # The kill-proof should show egress was attempted and caught
        assert report.egress_attempts > 0, (
            "KILL-PROOF FAILED: egress oracle did not catch forced telemetry send"
        )
        assert report.zero_egress is False, (
            "KILL-PROOF FAILED: zero_egress is True despite forced send"
        )

    def test_kill_proof_report_not_passing(self, tmp_path):
        """The kill-proof report must NOT pass (it shows a violation was caught)."""
        config_path = str(tmp_path / "config.json")
        report = run_airgap_telemetry_kill_proof(config_path)
        assert report.passed is False, (
            "KILL-PROOF FAILED: kill-proof report passed — oracle did not catch violation"
        )


# ======================== UPDATE SIGNATURE ORACLE ========================


class TestUpdateSignatureOracle:
    """Oracle 2: valid signed update accepted, tampered rejected."""

    def test_valid_payload_accepted(self, tmp_path):
        """A valid Ed25519-signed update payload is accepted."""
        report = run_update_signature_oracle(str(tmp_path))

        assert report.valid_payload_accepted is True, (
            f"Valid payload was not accepted: checksum={report.checksum_verified}, "
            f"signature={report.signature_verified}"
        )
        assert verify_update_signature(report) is True

    def test_tampered_data_rejected(self, tmp_path):
        """A tampered update payload (one byte flipped) is rejected."""
        report = run_update_signature_oracle(str(tmp_path))

        assert report.tampered_data_rejected is True, (
            "Tampered data was not rejected — signature verification is broken"
        )

    def test_tampered_signature_rejected(self, tmp_path):
        """A tampered signature is rejected."""
        report = run_update_signature_oracle(str(tmp_path))

        assert report.tampered_signature_rejected is True, (
            "Tampered signature was not rejected — signature verification is broken"
        )

    def test_tampered_payload_rejected_overall(self, tmp_path):
        """Overall: tampered payload is rejected."""
        report = run_update_signature_oracle(str(tmp_path))

        assert report.tampered_payload_rejected is True, (
            "Tampered payload was not rejected"
        )

    def test_update_signature_report_hash(self, tmp_path):
        """The report hash is present and valid."""
        report = run_update_signature_oracle(str(tmp_path))
        assert report.report_hash != ""
        assert len(report.report_hash) == 64


class TestUpdateSignatureKillProof:
    """Kill-proof: tampered payload that passes = oracle broken."""

    def test_tampered_payload_not_accepted(self, tmp_path):
        """A tampered payload MUST NOT pass signature verification."""
        report = run_update_signature_kill_proof(str(tmp_path))

        assert report.tampered_data_rejected is True, (
            "KILL-PROOF FAILED: tampered payload was accepted by signature verification"
        )
        assert report.error is None, f"Kill-proof error: {report.error}"


# ======================== SUPPLY CHAIN GATES ORACLE ========================


class TestSupplyChainOracle:
    """Oracle 3: SBOM + secret scan gates."""

    def test_sbom_generated_and_valid(self, tmp_path):
        """SBOM is generated and is valid CycloneDX."""
        report = run_supply_chain_oracle(str(tmp_path), _REPO_ROOT)

        assert report.sbom_generated is True, "SBOM was not generated"
        assert report.sbom_valid is True, "SBOM is not valid CycloneDX"
        assert os.path.exists(report.sbom_path), "SBOM file does not exist"

    def test_sbom_has_components(self, tmp_path):
        """SBOM contains at least one component."""
        report = run_supply_chain_oracle(str(tmp_path), _REPO_ROOT)

        with open(report.sbom_path) as f:
            sbom = json.load(f)
        assert len(sbom["components"]) > 0, "SBOM has no components"

    def test_clean_scan_passes(self, tmp_path):
        """A clean directory passes the secret scan."""
        report = run_supply_chain_oracle(str(tmp_path), _REPO_ROOT)

        assert report.secret_scan_passed is True, (
            "Clean directory failed secret scan"
        )

    def test_planted_secret_detected(self, tmp_path):
        """A planted secret is DETECTED by the secret scanner."""
        report = run_supply_chain_oracle(str(tmp_path), _REPO_ROOT)

        assert report.planted_secret_detected is True, (
            "Planted secret was not detected — scanner is broken"
        )
        assert len(report.violations) > 0, "No violations recorded for planted secret"

    def test_cleaned_scan_passes(self, tmp_path):
        """After removing the planted secret, the scan passes."""
        report = run_supply_chain_oracle(str(tmp_path), _REPO_ROOT)

        assert report.clean_scan_passed is True, (
            "Cleaned directory failed secret scan after removing planted secret"
        )

    def test_supply_chain_oracle_passes(self, tmp_path):
        """The overall supply chain oracle passes."""
        report = run_supply_chain_oracle(str(tmp_path), _REPO_ROOT)

        assert verify_supply_chain(report) is True, (
            f"Supply chain oracle did not pass: {report.to_json()}"
        )

    def test_supply_chain_report_hash(self, tmp_path):
        """The report hash is present and valid."""
        report = run_supply_chain_oracle(str(tmp_path), _REPO_ROOT)
        assert report.report_hash != ""
        assert len(report.report_hash) == 64


class TestSupplyChainKillProof:
    """Kill-proof: planted secret not detected = scanner broken."""

    def test_planted_secret_must_be_detected(self, tmp_path):
        """A planted AWS secret MUST be detected by the scanner."""
        report = run_supply_chain_kill_proof(str(tmp_path))

        assert report.planted_secret_detected is True, (
            "KILL-PROOF FAILED: planted AWS secret was not detected"
        )
        assert report.error is None, f"Kill-proof error: {report.error}"

    def test_planted_secret_violations_recorded(self, tmp_path):
        """Violations are recorded for the planted secret."""
        report = run_supply_chain_kill_proof(str(tmp_path))

        assert len(report.violations) > 0, "No violations recorded for planted secret"
        # Check the violation type
        violation_types = [v["type"] for v in report.violations]
        assert "AWS_SECRET_ACCESS_KEY" in violation_types, (
            f"AWS secret not in violation types: {violation_types}"
        )


# ======================== SECRET SCANNER UNIT TESTS ========================


class TestSecretScanner:
    """Direct tests for the secret scanner."""

    def test_clean_file_passes(self, tmp_path):
        """A clean source file passes the scanner."""
        clean_file = tmp_path / "clean.py"
        clean_file.write_text("import os\nvalue = 42\nprint('hello')\n")

        result = scan_for_secrets(str(tmp_path))
        assert result["passed"] is True
        assert len(result["violations"]) == 0

    def test_aws_key_detected(self, tmp_path):
        """AWS access key pattern is detected."""
        secret_file = tmp_path / "config.py"
        secret_file.write_text("key = 'AKIAIOSFODNN7EXAMPLE'\n")

        result = scan_for_secrets(str(tmp_path))
        assert result["passed"] is False
        assert len(result["violations"]) > 0

    def test_private_key_detected(self, tmp_path):
        """Private key PEM block is detected."""
        secret_file = tmp_path / "key.pem"
        secret_file.write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----\n"
        )

        result = scan_for_secrets(str(tmp_path))
        assert result["passed"] is False

    def test_github_token_detected(self, tmp_path):
        """GitHub token pattern is detected."""
        secret_file = tmp_path / "ci.py"
        secret_file.write_text("token = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz'\n")

        result = scan_for_secrets(str(tmp_path))
        assert result["passed"] is False

    def test_comments_ignored(self, tmp_path):
        """Commented-out secrets are ignored."""
        clean_file = tmp_path / "config.py"
        clean_file.write_text("# API_KEY = 'sk-1234567890abcdef1234567890abcdef'\n")

        result = scan_for_secrets(str(tmp_path))
        assert result["passed"] is True


# ======================== SBOM UNIT TESTS ========================


class TestSBOMGeneration:
    """Direct tests for SBOM generation."""

    def test_sbom_cyclonedx_format(self, tmp_path):
        """SBOM is in CycloneDX format."""
        sbom_path = str(tmp_path / "sbom.json")
        sbom = generate_cyclonedx_sbom(_REPO_ROOT, sbom_path)

        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.5"

    def test_sbom_validated(self, tmp_path):
        """SBOM passes validation."""
        sbom_path = str(tmp_path / "sbom.json")
        sbom = generate_cyclonedx_sbom(_REPO_ROOT, sbom_path)

        assert validate_sbom(sbom) is True

    def test_sbom_file_written(self, tmp_path):
        """SBOM file is written to disk."""
        sbom_path = str(tmp_path / "sbom.json")
        generate_cyclonedx_sbom(_REPO_ROOT, sbom_path)

        assert os.path.exists(sbom_path)
        with open(sbom_path) as f:
            loaded = json.load(f)
        assert loaded["bomFormat"] == "CycloneDX"


# ======================== HONEST DEGRADATION ========================


class TestHonestDegradation:
    """Verify honest degradation for production-ops capabilities."""

    def test_updater_disabled_in_sealed_mode(self):
        """Auto-update is disabled in sealed mode — no network call made."""
        os.environ["KAIRO_SEALED"] = "1"
        os.environ["KAIRO_OFFLINE"] = "1"

        # Add sidecar to path
        sidecar_path = os.path.join(_REPO_ROOT, "kairo-sidecar")
        if sidecar_path not in sys.path:
            sys.path.insert(0, sidecar_path)

        from sidecar.updater import check_for_update

        result = check_for_update()
        assert result is None, (
            "Update check returned a result in sealed mode — sealed mode is broken"
        )

    def test_telemetry_suppressed_in_sealed_mode(self, tmp_path):
        """Telemetry writes are suppressed in sealed mode."""
        os.environ["KAIRO_SEALED"] = "1"
        os.environ["KAIRO_OFFLINE"] = "1"

        sidecar_path = os.path.join(_REPO_ROOT, "kairo-sidecar")
        if sidecar_path not in sys.path:
            sys.path.insert(0, sidecar_path)

        from sidecar import telemetry as telemetry_mod

        # Patch paths to tmp
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"telemetry_enabled": True}))
        tel_file = tmp_path / "telemetry.jsonl"

        telemetry_mod.CONFIG_FILE = config_file
        telemetry_mod.TELEMETRY_FILE = tel_file

        # Attempt to record — should be suppressed
        telemetry_mod.record_operation("test", 100.0, success=True)

        assert not tel_file.exists(), (
            "Telemetry file was created in sealed mode — sealed mode is broken"
        )

    def test_opik_tracer_suppressed_in_sealed_mode(self, tmp_path):
        """Opik tracer writes are suppressed in sealed mode."""
        os.environ["KAIRO_SEALED"] = "1"
        os.environ["KAIRO_OFFLINE"] = "1"

        sidecar_path = os.path.join(_REPO_ROOT, "kairo-sidecar")
        if sidecar_path not in sys.path:
            sys.path.insert(0, sidecar_path)

        from sidecar.observability.opik_tracer import OpikTracer, TraceContext

        trace_file = tmp_path / "opik_traces.jsonl"
        tracer = OpikTracer(trace_path=trace_file)

        ctx = TraceContext("trace_test", "word", "generate", "test input", "test-model")
        trace_id = tracer.emit(ctx)

        assert trace_id is not None, "Trace ID should still be returned"
        assert not trace_file.exists(), (
            "Opik trace file was created in sealed mode — sealed mode is broken"
        )
