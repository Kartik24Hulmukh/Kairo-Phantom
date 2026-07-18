"""Tests for DSSE/in-toto envelope wrapping of legal-v3 evidence bundles."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from kairo.legal_v3.dsse_envelope import (
    PAYLOAD_TYPE,
    PREDICATE_TYPE,
    STATEMENT_TYPE,
    create_envelope,
    create_statement,
    verify_envelope,
    wrap_bundle,
)
from kairo.legal_v3.transaction import (
    approve,
    execute,
    generate_keypair,
    propose,
)


def _build_bundle(work: Path) -> Path:
    """Build a valid evidence bundle and return its path."""
    repo = Path(__file__).resolve().parents[1]
    shutil.copy2(repo / "fixtures/demo/sample_nda.docx", work / "nda.docx")
    shutil.copy2(
        repo / "fixtures/demo/nda_playbook.json", work / "playbook.json"
    )
    prod = generate_keypair("producer")
    app = generate_keypair("approver")
    obs = generate_keypair("observer")
    proposal = propose(str(work), "nda.docx", "playbook.json", "out.docx", prod)
    approval = approve(proposal, app)
    keys = {
        prod["key_id"]: prod["public"],
        app["key_id"]: app["public"],
    }
    bundle_path = work / "bundle"
    execute(str(work), proposal, approval, keys, obs, str(bundle_path))
    return bundle_path


class DSSEEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Path(tempfile.mkdtemp())
        self.bundle_path = _build_bundle(self.t)
        self.bundle = json.loads(
            (self.bundle_path / "bundle.json").read_text()
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.t, ignore_errors=True)

    def test_create_statement(self) -> None:
        """Statement has correct in-toto v1 structure."""
        stmt = create_statement(self.bundle)
        self.assertEqual(stmt["_type"], STATEMENT_TYPE)
        self.assertEqual(stmt["predicateType"], PREDICATE_TYPE)
        self.assertIsInstance(stmt["subject"], list)
        self.assertGreaterEqual(len(stmt["subject"]), 1)
        # Subject should have sha256 digest
        for subj in stmt["subject"]:
            self.assertIn("sha256", subj["digest"])
        # Predicate is the full bundle
        self.assertEqual(stmt["predicate"], self.bundle)

    def test_create_envelope(self) -> None:
        """Envelope has correct DSSE structure."""
        sigs = [{"sig": "test-sig", "keyid": "test-key"}]
        env = create_envelope(self.bundle, sigs)
        self.assertEqual(env["payloadType"], PAYLOAD_TYPE)
        self.assertIn("payload", env)
        self.assertIn("signatures", env)
        self.assertEqual(len(env["signatures"]), 1)
        self.assertEqual(env["signatures"][0]["keyid"], "test-key")

    def test_verify_envelope_structure(self) -> None:
        """Structural verification of a valid envelope passes."""
        sigs = [{"sig": "test-sig", "keyid": "test-key"}]
        env = create_envelope(self.bundle, sigs)
        stmt = verify_envelope(env)
        self.assertEqual(stmt["_type"], STATEMENT_TYPE)
        self.assertEqual(stmt["predicateType"], PREDICATE_TYPE)

    def test_verify_envelope_wrong_payload_type(self) -> None:
        """Wrong payloadType is rejected."""
        sigs = [{"sig": "test-sig", "keyid": "test-key"}]
        env = create_envelope(self.bundle, sigs)
        env["payloadType"] = "wrong-type"
        with self.assertRaises(ValueError):
            verify_envelope(env)

    def test_verify_envelope_missing_payload(self) -> None:
        """Missing payload field is rejected."""
        env = {"payloadType": PAYLOAD_TYPE, "signatures": []}
        with self.assertRaises(ValueError):
            verify_envelope(env)

    def test_verify_envelope_missing_signatures(self) -> None:
        """Missing signatures field is rejected."""
        env = {"payload": "abc", "payloadType": PAYLOAD_TYPE}
        with self.assertRaises(ValueError):
            verify_envelope(env)

    def test_verify_envelope_with_callback(self) -> None:
        """Signature verification callback is called correctly."""
        sigs = [{"sig": "valid-sig", "keyid": "test-key"}]
        env = create_envelope(self.bundle, sigs)

        def verify_fn(payload_bytes, sig_b64, key_id):
            return sig_b64 == "valid-sig" and key_id == "test-key"

        stmt = verify_envelope(env, verify_signature_fn=verify_fn)
        self.assertEqual(stmt["predicateType"], PREDICATE_TYPE)

    def test_verify_envelope_callback_rejects(self) -> None:
        """Failing signature callback raises ValueError."""
        sigs = [{"sig": "bad-sig", "keyid": "test-key"}]
        env = create_envelope(self.bundle, sigs)

        def verify_fn(payload_bytes, sig_b64, key_id):
            return False

        with self.assertRaises(ValueError):
            verify_envelope(env, verify_signature_fn=verify_fn)

    def test_wrap_bundle_to_disk(self) -> None:
        """wrap_bundle writes a DSSE envelope file to disk."""
        output = wrap_bundle(str(self.bundle_path))
        env = json.loads(Path(output).read_text())
        self.assertEqual(env["payloadType"], PAYLOAD_TYPE)
        self.assertIn("payload", env)
        self.assertIn("signatures", env)

    def test_wrap_bundle_custom_output(self) -> None:
        """wrap_bundle writes to a custom output path."""
        custom = str(self.t / "custom.dsse.json")
        output = wrap_bundle(str(self.bundle_path), output_path=custom)
        self.assertEqual(output, custom)
        env = json.loads(Path(custom).read_text())
        self.assertEqual(env["payloadType"], PAYLOAD_TYPE)

    def test_roundtrip_preserves_bundle(self) -> None:
        """Envelope -> verify -> statement preserves the original bundle."""
        sigs = [{"sig": "test", "keyid": "k"}]
        env = create_envelope(self.bundle, sigs)
        stmt = verify_envelope(env)
        self.assertEqual(stmt["predicate"], self.bundle)
        # Verify the bundle inside is still valid
        self.assertEqual(stmt["predicate"]["profile"], "kairo-legal-v3")
        self.assertEqual(len(stmt["predicate"]["events"]), 8)


if __name__ == "__main__":
    unittest.main()
