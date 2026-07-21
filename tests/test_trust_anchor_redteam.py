"""Regression test for Gate D: trust-anchor red team attack.

Attack scenario:
  1. Run a clean redline (generates keypair in --out dir)
  2. Generate a NEW attacker Ed25519 keypair
  3. Tamper redlined.docx
  4. Re-sign output_manifest.json with the attacker key
  5. Replace public_key.pem with the attacker public key
  6. Run verify — MUST FAIL because:
     a) Without --pubkey or --fingerprint: verify refuses to run
     b) With attacker key as external --pubkey: audit log signatures
        were signed by the original key, so chain verification fails
     c) With --fingerprint of the original key: fingerprint mismatch
        on the replaced public_key.pem
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

WEDGE = REPO / "fixtures" / "wedge_gauntlet"
DEMO = REPO / "fixtures" / "demo"

if (WEDGE / "s01_nda_standard.docx").exists():
    GOOD_DOCX = WEDGE / "s01_nda_standard.docx"
    GOOD_PB = WEDGE / "s01_playbook.json"
else:
    GOOD_DOCX = DEMO / "sample_nda.docx"
    GOOD_PB = DEMO / "nda_playbook.json"


def _run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    full_env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, "-m", "kairo"] + args,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
    )


class TrustAnchorRedTeamTests(unittest.TestCase):
    """Gate D: verify must not trust co-located public_key.pem."""

    def setUp(self) -> None:
        self.t = Path(tempfile.mkdtemp(prefix="gate-d-"))
        self.out_dir = str(self.t / "out")

        # Step 1: Clean run
        result = _run_cli([
            "redline", "--out", self.out_dir,
            str(GOOD_DOCX), str(GOOD_PB),
        ])
        self.assertEqual(result.returncode, 0,
                         f"Clean redline failed: {result.stderr}")

        # Save original public key fingerprint
        orig_pub = (Path(self.out_dir) / "public_key.pem").read_bytes()
        self.orig_fingerprint = hashlib.sha256(orig_pub).hexdigest()

    def tearDown(self) -> None:
        shutil.rmtree(self.t, ignore_errors=True)

    def _generate_attacker_key(self) -> tuple[bytes, bytes]:
        """Generate an attacker Ed25519 keypair, return (pub_pem, priv_pem)."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        from cryptography.hazmat.primitives import serialization

        attacker_priv = Ed25519PrivateKey.generate()
        attacker_pub = attacker_priv.public_key()

        pub_pem = attacker_pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        priv_pem = attacker_priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return pub_pem, priv_pem

    def _tamper_and_resign(self, attacker_pub_pem: bytes,
                           attacker_priv_pem: bytes) -> None:
        """Tamper redlined.docx, re-sign manifest, replace public key."""
        from cryptography.hazmat.primitives import serialization

        # Tamper redlined.docx
        docx_path = Path(self.out_dir) / "redlined.docx"
        data = bytearray(docx_path.read_bytes())
        data[100] ^= 0xFF
        docx_path.write_bytes(bytes(data))

        # Re-sign output_manifest.json with attacker key
        attacker_priv = serialization.load_pem_private_key(
            attacker_priv_pem, password=None
        )
        manifest = json.loads(
            (Path(self.out_dir) / "output_manifest.json").read_text()
        )

        def hash_file(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        manifest["redlined_docx_sha256"] = hash_file(docx_path)
        manifest["audit_log_sha256"] = hash_file(
            Path(self.out_dir) / "audit_log.json"
        )
        manifest["zero_egress_report_sha256"] = hash_file(
            Path(self.out_dir) / "zero_egress_report.json"
        )

        payload = {k: v for k, v in manifest.items() if k != "signature"}
        content = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        manifest["signature"] = attacker_priv.sign(content).hex()

        (Path(self.out_dir) / "output_manifest.json").write_text(
            json.dumps(manifest, indent=2)
        )

        # Replace public_key.pem with attacker's
        (Path(self.out_dir) / "public_key.pem").write_bytes(attacker_pub_pem)

    def test_verify_without_key_fails_closed(self) -> None:
        """Verify with no --pubkey and no --fingerprint must fail."""
        result = _run_cli(["verify", self.out_dir])
        self.assertNotEqual(result.returncode, 0,
                            "verify must fail when no trusted key is supplied")
        combined = result.stdout + result.stderr
        self.assertIn("trusted public key", combined.lower())

    def test_attacker_key_swap_detected_by_fingerprint(self) -> None:
        """Attacker replaces public_key.pem; fingerprint check catches it."""
        attacker_pub, attacker_priv = self._generate_attacker_key()
        self._tamper_and_resign(attacker_pub, attacker_priv)

        # Verify with original fingerprint — must fail (key was swapped)
        result = _run_cli([
            "verify", self.out_dir,
            "--fingerprint", self.orig_fingerprint,
        ])
        self.assertNotEqual(result.returncode, 0,
                            "verify must fail when fingerprint doesn't match")
        combined = result.stdout + result.stderr
        self.assertIn("fingerprint mismatch", combined.lower())

    def test_attacker_key_as_external_fails_on_audit_log(self) -> None:
        """Attacker supplies their key as external --pubkey; audit log
        signatures were signed by the original key, so verification fails."""
        attacker_pub, attacker_priv = self._generate_attacker_key()
        self._tamper_and_resign(attacker_pub, attacker_priv)

        # Save attacker key externally
        ext_key = self.t / "attacker_key.pem"
        ext_key.write_bytes(attacker_pub)

        # Verify with attacker's key as external key
        result = _run_cli(["verify", self.out_dir, str(ext_key)])
        self.assertNotEqual(result.returncode, 0,
                            "verify must fail: audit log signed by original key, "
                            "not attacker key")

    def test_clean_run_passes_with_external_key(self) -> None:
        """Clean run (no tampering) passes with externally supplied key."""
        # Use the original public key from the output dir as external key
        ext_key = self.t / "trusted_key.pem"
        shutil.copy2(Path(self.out_dir) / "public_key.pem", ext_key)

        result = _run_cli(["verify", self.out_dir, str(ext_key)])
        self.assertEqual(result.returncode, 0,
                         f"Clean run should pass with external key: "
                         f"{result.stdout} {result.stderr}")

    def test_clean_run_passes_with_fingerprint(self) -> None:
        """Clean run passes with correct fingerprint."""
        result = _run_cli([
            "verify", self.out_dir,
            "--fingerprint", self.orig_fingerprint,
        ])
        self.assertEqual(result.returncode, 0,
                         f"Clean run should pass with correct fingerprint: "
                         f"{result.stdout} {result.stderr}")


if __name__ == "__main__":
    unittest.main()
