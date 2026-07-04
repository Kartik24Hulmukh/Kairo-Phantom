# PROVENANCE: original | clean-room CLI tests for the Legal-redline wedge
"""Tests for the kairo.cli module — redline + verify happy path + tamper kill-proof.

All tests run fully offline (KAIRO_NO_NET=1). No mocks on production paths.
The CLI calls the REAL redline_contract pipeline on the REAL demo fixture.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Fixture paths
_DEMO_DIR = os.path.join(_REPO_ROOT, "fixtures", "demo")
_CONTRACT = os.path.join(_DEMO_DIR, "sample_nda.docx")
_PLAYBOOK = os.path.join(_DEMO_DIR, "nda_playbook.json")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the CLI as a subprocess and return the result."""
    cmd = [sys.executable, "-m", "kairo.cli", *args]
    env = os.environ.copy()
    env["KAIRO_NO_NET"] = "1"
    env["KAIRO_OFFLINE"] = "1"
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=env,
        timeout=60,
    )


# ======================== REDLINE COMMAND ========================


class TestRedlineCommand:
    """The `redline` command runs the real pipeline and writes artifacts."""

    def test_redline_happy_path(self, tmp_path):
        """Redline on the demo NDA produces all expected artifacts."""
        out = str(tmp_path / "output")
        result = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out)

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "LEGAL REDLINE COMPLETE" in result.stdout
        assert "Edits applied:  5" in result.stdout
        assert "Clauses flagged: 0" in result.stdout
        assert "Audit log verified: ✅" in result.stdout
        assert "Zero-egress report verified: ✅" in result.stdout

        # Check artifacts exist
        assert os.path.exists(os.path.join(out, "redlined.docx"))
        assert os.path.exists(os.path.join(out, "audit_log.json"))
        assert os.path.exists(os.path.join(out, "zero_egress_report.json"))
        assert os.path.exists(os.path.join(out, "public_key.pem"))

    def test_redline_sealed_mode(self, tmp_path):
        """Redline with --sealed produces airgap egress report + 0 outbound."""
        out = str(tmp_path / "sealed_output")
        result = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--sealed", "--out", out)

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "SEALED mode" in result.stdout
        assert "Air-gap: 0 outbound packets ✅" in result.stdout
        assert os.path.exists(os.path.join(out, "airgap_egress_report.json"))

        # Verify the airgap report shows 0 egress
        with open(os.path.join(out, "airgap_egress_report.json")) as f:
            airgap = json.load(f)
        assert airgap["total_egress_attempts"] == 0
        assert airgap["total_dns_lookups"] == 0
        assert airgap["zero_egress"] is True
        assert airgap["sealed_mode_active"] is True

    def test_redline_missing_contract(self, tmp_path):
        """CLI returns error code for missing contract."""
        out = str(tmp_path / "output")
        result = _run_cli("redline", "nonexistent.docx", _PLAYBOOK, "--out", out)
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_redline_missing_playbook(self, tmp_path):
        """CLI returns error code for missing playbook."""
        out = str(tmp_path / "output")
        result = _run_cli("redline", _CONTRACT, "nonexistent.json", "--out", out)
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_redline_keypair_reuse(self, tmp_path):
        """Running redline twice reuses the same keypair (same public key)."""
        out1 = str(tmp_path / "output1")
        out2 = str(tmp_path / "output2")

        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out1)
        assert r1.returncode == 0

        # Copy keys from out1 to out2's key dir to simulate reuse
        import shutil

        key_src = os.path.join(out1, ".keys")
        key_dst = os.path.join(out2, ".keys")
        os.makedirs(key_dst, exist_ok=True)
        shutil.copy(os.path.join(key_src, "private_key.pem"), key_dst)
        shutil.copy(os.path.join(key_src, "public_key.pem"), key_dst)

        r2 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out2)
        assert r2.returncode == 0

        # Public keys should match
        with open(os.path.join(out1, "public_key.pem"), "rb") as f:
            pub1 = f.read()
        with open(os.path.join(out2, "public_key.pem"), "rb") as f:
            pub2 = f.read()
        assert pub1 == pub2, "Keypair was not reused"


# ======================== VERIFY COMMAND ========================


class TestVerifyCommand:
    """The `verify` command independently re-verifies artifacts."""

    def test_verify_happy_path(self, tmp_path):
        """Verify on a fresh redline output passes all checks."""
        out = str(tmp_path / "output")
        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out)
        assert r1.returncode == 0

        r2 = _run_cli("verify", out, os.path.join(out, "public_key.pem"))
        assert r2.returncode == 0, f"Verify failed: {r2.stderr}"
        assert "ALL PASS ✅" in r2.stdout
        assert "Audit log chain" in r2.stdout
        assert "PASS ✅" in r2.stdout

    def test_verify_sealed_output(self, tmp_path):
        """Verify on sealed output also checks airgap egress report."""
        out = str(tmp_path / "sealed_output")
        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--sealed", "--out", out)
        assert r1.returncode == 0

        r2 = _run_cli("verify", out, os.path.join(out, "public_key.pem"))
        assert r2.returncode == 0
        assert "Air-gap egress report: PASS ✅" in r2.stdout
        assert "Egress attempts: 0" in r2.stdout

    def test_verify_missing_dir(self, tmp_path):
        """Verify returns error for missing directory."""
        result = _run_cli("verify", str(tmp_path / "nonexistent"), "key.pem")
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_verify_missing_key(self, tmp_path):
        """Verify returns error for missing public key."""
        out = str(tmp_path / "output")
        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out)
        assert r1.returncode == 0

        result = _run_cli("verify", out, "nonexistent_key.pem")
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()


# ======================== KILL-PROOF: TAMPER DETECTION ========================


class TestVerifyTamperKillProof:
    """Kill-proof: tampering with the audit log MUST make verify fail."""

    def test_verify_fails_on_tampered_audit_log(self, tmp_path):
        """Tampering with an audit entry's action field MUST fail verification."""
        out = str(tmp_path / "output")
        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out)
        assert r1.returncode == 0

        # Tamper with the audit log
        audit_path = os.path.join(out, "audit_log.json")
        with open(audit_path) as f:
            data = json.load(f)
        # Modify an entry's action — this breaks the Ed25519 signature
        data["entries"][1]["action"] = "tampered_action"
        with open(audit_path, "w") as f:
            json.dump(data, f, indent=2)

        r2 = _run_cli("verify", out, os.path.join(out, "public_key.pem"))
        assert r2.returncode == 1, "Verify should FAIL on tampered audit log"
        assert "FAIL ❌" in r2.stdout
        assert "ALL PASS" not in r2.stdout

    def test_verify_fails_on_tampered_egress_report(self, tmp_path):
        """Tampering with the zero-egress report MUST fail verification."""
        out = str(tmp_path / "output")
        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out)
        assert r1.returncode == 0

        # Tamper with the egress report
        egress_path = os.path.join(out, "zero_egress_report.json")
        with open(egress_path) as f:
            data = json.load(f)
        data["total_edits"] = 999  # Changed — signature won't match
        with open(egress_path, "w") as f:
            json.dump(data, f, indent=2)

        r2 = _run_cli("verify", out, os.path.join(out, "public_key.pem"))
        assert r2.returncode == 1, "Verify should FAIL on tampered egress report"
        assert "FAIL ❌" in r2.stdout

    def test_verify_fails_on_wrong_public_key(self, tmp_path):
        """Verify with a wrong public key MUST fail."""
        out = str(tmp_path / "output")
        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out)
        assert r1.returncode == 0

        # Generate a different keypair
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog

        wrong_priv, wrong_pub = Ed25519AuditLog.generate_keypair()
        wrong_pub_pem = Ed25519AuditLog.public_key_to_pem(wrong_pub)
        wrong_key_path = os.path.join(str(tmp_path), "wrong_key.pem")
        with open(wrong_key_path, "wb") as f:
            f.write(wrong_pub_pem)

        r2 = _run_cli("verify", out, wrong_key_path)
        assert r2.returncode == 1, "Verify should FAIL with wrong public key"
        assert "FAIL ❌" in r2.stdout

    def test_verify_fails_on_broken_chain(self, tmp_path):
        """Removing an entry from the middle of the chain MUST fail verification."""
        out = str(tmp_path / "output")
        r1 = _run_cli("redline", _CONTRACT, _PLAYBOOK, "--out", out)
        assert r1.returncode == 0

        # Remove an entry from the middle of the chain
        audit_path = os.path.join(out, "audit_log.json")
        with open(audit_path) as f:
            data = json.load(f)
        # Remove entry at index 2 (an edit_applied entry)
        del data["entries"][2]
        with open(audit_path, "w") as f:
            json.dump(data, f, indent=2)

        r2 = _run_cli("verify", out, os.path.join(out, "public_key.pem"))
        assert r2.returncode == 1, "Verify should FAIL on broken chain"
        assert "FAIL ❌" in r2.stdout
