import shutil
import tempfile
import unittest
from pathlib import Path

from kairo.legal_v3.transaction import (
    LegalV3Error,
    approve,
    execute,
    generate_keypair,
    propose,
    verify_bundle,
)


class E2E(unittest.TestCase):
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

    def tearDown(self) -> None:
        shutil.rmtree(self.t)

    def run_tx(self):
        proposal = propose(
            self.t, "nda.docx", "playbook.json", "out.docx", self.prod
        )
        approval = approve(proposal, self.app)
        keys = {
            self.prod["key_id"]: self.prod["public"],
            self.app["key_id"]: self.app["public"],
        }
        execute(
            self.t,
            proposal,
            approval,
            keys,
            self.obs,
            self.t / "bundle",
        )
        return proposal, approval

    def test_end_to_end_and_tamper(self) -> None:
        self.run_tx()
        self.assertTrue(verify_bundle(self.t / "bundle")["ok"])
        output = self.t / "bundle/output.docx"
        output.write_bytes(output.read_bytes() + b"x")
        self.assertFalse(verify_bundle(self.t / "bundle")["ok"])

    def test_source_substitution(self) -> None:
        proposal = propose(
            self.t, "nda.docx", "playbook.json", "out.docx", self.prod
        )
        approval = approve(proposal, self.app)
        (self.t / "nda.docx").write_bytes(
            (self.t / "nda.docx").read_bytes() + b"x"
        )
        keys = {
            self.prod["key_id"]: self.prod["public"],
            self.app["key_id"]: self.app["public"],
        }
        self.assertRaises(
            LegalV3Error,
            execute,
            self.t,
            proposal,
            approval,
            keys,
            self.obs,
            self.t / "bundle",
        )

    def test_wrong_approval(self) -> None:
        proposal = propose(
            self.t, "nda.docx", "playbook.json", "out.docx", self.prod
        )
        approval = approve(proposal, self.app)
        approval["intent_sha256"] = "0" * 64
        keys = {
            self.prod["key_id"]: self.prod["public"],
            self.app["key_id"]: self.app["public"],
        }
        self.assertRaises(
            LegalV3Error,
            execute,
            self.t,
            proposal,
            approval,
            keys,
            self.obs,
            self.t / "bundle",
        )


if __name__ == "__main__":
    unittest.main()
