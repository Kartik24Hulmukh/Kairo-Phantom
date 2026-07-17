import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from kairo.legal_v3.transaction import (
    LegalV3Error,
    approve,
    execute,
    generate_keypair,
    propose,
    sign,
    verify_bundle,
)


class Adversarial(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Path(tempfile.mkdtemp())
        repo = Path(__file__).resolve().parents[1]
        shutil.copy2(repo / "fixtures/demo/sample_nda.docx", self.t / "nda.docx")
        shutil.copy2(
            repo / "fixtures/demo/nda_playbook.json", self.t / "playbook.json"
        )
        self.prod = generate_keypair("producer")
        self.app = generate_keypair("approver")
        self.obs = generate_keypair("observer")
        self.keys = {
            self.prod["key_id"]: self.prod["public"],
            self.app["key_id"]: self.app["public"],
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.t)

    def tx(self):
        proposal = propose(
            self.t, "nda.docx", "playbook.json", "out.docx", self.prod
        )
        approval = approve(proposal, self.app)
        execute(
            self.t,
            proposal,
            approval,
            self.keys,
            self.obs,
            self.t / "bundle",
        )
        return proposal, approval

    def test_playbook_tamper(self) -> None:
        proposal = propose(
            self.t, "nda.docx", "playbook.json", "out.docx", self.prod
        )
        approval = approve(proposal, self.app)
        playbook = json.loads((self.t / "playbook.json").read_text())
        playbook["description"] = "tamper"
        (self.t / "playbook.json").write_text(json.dumps(playbook))
        self.assertRaises(
            LegalV3Error,
            execute,
            self.t,
            proposal,
            approval,
            self.keys,
            self.obs,
            self.t / "bundle",
        )

    def test_observer_key_tamper(self) -> None:
        self.tx()
        manifest = json.loads((self.t / "bundle/bundle.json").read_text())
        manifest["events"][0]["signature"] = "AAAA"
        (self.t / "bundle/bundle.json").write_text(json.dumps(manifest))
        self.assertFalse(verify_bundle(self.t / "bundle")["ok"])

    def test_reorder(self) -> None:
        self.tx()
        manifest = json.loads((self.t / "bundle/bundle.json").read_text())
        manifest["events"][1], manifest["events"][2] = (
            manifest["events"][2],
            manifest["events"][1],
        )
        (self.t / "bundle/bundle.json").write_text(json.dumps(manifest))
        self.assertFalse(verify_bundle(self.t / "bundle")["ok"])

    def test_missing_event(self) -> None:
        self.tx()
        manifest = json.loads((self.t / "bundle/bundle.json").read_text())
        manifest["events"].pop(3)
        (self.t / "bundle/bundle.json").write_text(json.dumps(manifest))
        self.assertFalse(verify_bundle(self.t / "bundle")["ok"])

    def test_observer_must_differ(self) -> None:
        bad = dict(self.obs)
        bad["key_id"] = self.prod["key_id"]
        proposal = propose(
            self.t, "nda.docx", "playbook.json", "out.docx", self.prod
        )
        approval = approve(proposal, self.app)
        self.assertRaises(
            LegalV3Error,
            execute,
            self.t,
            proposal,
            approval,
            self.keys,
            bad,
            self.t / "bundle",
        )

    def test_expired_approval(self) -> None:
        proposal = propose(
            self.t, "nda.docx", "playbook.json", "out.docx", self.prod
        )
        approval = approve(proposal, self.app)
        approval["expires_at"] = int(time.time()) - 1
        approval["signature"] = sign(
            {k: v for k, v in approval.items() if k != "signature"}, self.app
        )
        self.assertRaises(
            LegalV3Error,
            execute,
            self.t,
            proposal,
            approval,
            self.keys,
            self.obs,
            self.t / "bundle",
        )

    def test_path_escape(self) -> None:
        self.assertRaises(
            LegalV3Error,
            propose,
            self.t,
            "../x.docx",
            "playbook.json",
            "out.docx",
            self.prod,
        )

    def test_non_nda_clause_denied(self) -> None:
        playbook = json.loads((self.t / "playbook.json").read_text())
        playbook["clauses"][0]["clause_id"] = "payment_terms"
        (self.t / "playbook.json").write_text(json.dumps(playbook))
        self.assertRaises(
            LegalV3Error,
            propose,
            self.t,
            "nda.docx",
            "playbook.json",
            "out.docx",
            self.prod,
        )


if __name__ == "__main__":
    unittest.main()
