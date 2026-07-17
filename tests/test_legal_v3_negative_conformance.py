"""Negative conformance vectors for the legal-v3 verifier.

Each test tampers with a valid evidence bundle in a specific way and
confirms that verify_bundle rejects it. These complement the adversarial
suite by testing the pure verifier (verify_bundle) against corrupted
bundles rather than corrupted transaction inputs.
"""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from kairo.legal_v3.transaction import (
    approve,
    execute,
    generate_keypair,
    propose,
    verify_bundle,
)


def _build_bundle(work: Path) -> Path:
    """Build a valid evidence bundle and return its path."""
    shutil.copy2(
        Path(__file__).resolve().parents[1] / "fixtures/demo/sample_nda.docx",
        work / "nda.docx",
    )
    shutil.copy2(
        Path(__file__).resolve().parents[1] / "fixtures/demo/nda_playbook.json",
        work / "playbook.json",
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


def _load_bundle(bundle_path: Path) -> dict:
    return json.loads((bundle_path / "bundle.json").read_text())


def _save_bundle(bundle_path: Path, manifest: dict) -> None:
    (bundle_path / "bundle.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


class NegativeConformance(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Path(tempfile.mkdtemp())
        self.bundle_path = _build_bundle(self.t)
        self.manifest = _load_bundle(self.bundle_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.t, ignore_errors=True)

    def _expect_fail(self, label: str) -> None:
        _save_bundle(self.bundle_path, self.manifest)
        result = verify_bundle(str(self.bundle_path))
        self.assertFalse(
            result["ok"], f"{label}: verifier accepted tampered bundle"
        )

    def test_tamper_source_hash(self) -> None:
        """Corrupted source hash must fail."""
        self.manifest["proposal"]["source_sha256"] = "0" * 64
        self._expect_fail("tampered source hash")

    def test_tamper_playbook_hash(self) -> None:
        """Corrupted playbook hash must fail."""
        self.manifest["proposal"]["playbook_sha256"] = "0" * 64
        self._expect_fail("tampered playbook hash")

    def test_tamper_proposal_digest(self) -> None:
        """Corrupted proposal intent digest must fail."""
        self.manifest["proposal"]["intent_sha256"] = "0" * 64
        self._expect_fail("tampered proposal digest")

    def test_tamper_proposal_signature(self) -> None:
        """Corrupted proposal signature must fail."""
        sig = self.manifest["proposal"]["signature"]
        self.manifest["proposal"]["signature"] = "AAAA" + sig[4:]
        self._expect_fail("tampered proposal signature")

    def test_tamper_approval_signature(self) -> None:
        """Corrupted approval signature must fail."""
        sig = self.manifest["approval"]["signature"]
        self.manifest["approval"]["signature"] = "AAAA" + sig[4:]
        self._expect_fail("tampered approval signature")

    def test_delete_event(self) -> None:
        """Missing event must fail."""
        self.manifest["events"] = self.manifest["events"][:7]
        self._expect_fail("deleted event")

    def test_reorder_events(self) -> None:
        """Reordered events must fail (parent chain breaks)."""
        events = self.manifest["events"]
        self.manifest["events"] = [events[1], events[0]] + events[2:]
        self._expect_fail("reordered events")

    def test_tamper_event_digest(self) -> None:
        """Corrupted event digest must fail."""
        self.manifest["events"][3]["event_sha256"] = "0" * 64
        self._expect_fail("tampered event digest")

    def test_tamper_event_signature(self) -> None:
        """Corrupted event signature must fail."""
        sig = self.manifest["events"][3]["signature"]
        self.manifest["events"][3]["signature"] = "AAAA" + sig[4:]
        self._expect_fail("tampered event signature")

    def test_wrong_event_type_sequence(self) -> None:
        """Wrong event type order must fail."""
        self.manifest["events"][0]["event_type"] = "RUN_CLOSED"
        self._expect_fail("wrong event type sequence")

    def test_tamper_public_key(self) -> None:
        """Corrupted public key must fail (signature verification breaks)."""
        keys = self.manifest["public_keys"]
        first_key = list(keys.keys())[0]
        keys[first_key] = "AAAA" + keys[first_key][4:]
        self._expect_fail("tampered public key")

    def test_replay_event_chain(self) -> None:
        """Duplicated event (replay) must fail — sequence breaks."""
        events = self.manifest["events"]
        self.manifest["events"] = events + [copy.deepcopy(events[-1])]
        self._expect_fail("replayed event")

    def test_observer_collision(self) -> None:
        """Observer key collision (same key for producer and observer) must fail."""
        prod_key_id = self.manifest["proposal"]["producer_key_id"]
        obs_key_id = self.manifest["observer_key_id"]
        if prod_key_id != obs_key_id:
            self.manifest["public_keys"][obs_key_id] = self.manifest["public_keys"][prod_key_id]
        self._expect_fail("observer key collision")


if __name__ == "__main__":
    unittest.main()
