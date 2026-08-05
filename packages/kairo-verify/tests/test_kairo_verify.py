import base64
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kairo_verify.answer import answerability, ANSWERED, NOT_ANSWERABLE
from kairo_verify.canon import RECEIPT_FIELD_ORDER, content_hash
from kairo_verify.demo import build_demo, write_demo
from kairo_verify.integrity import verify_receipts, verify_checkpoints

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestIntegrity(unittest.TestCase):
    def test_valid_chain_no_violations(self):
        receipts, _ = build_demo(n=5)
        self.assertEqual(verify_receipts(receipts), [])

    def test_tamper_content_detected(self):
        receipts, _ = build_demo(n=5)
        receipts[2]["outcome"] = "TAMPERED_VALUE"
        v = verify_receipts(receipts)
        self.assertTrue(any("self_hash mismatch" in x for x in v), v)

    def test_chain_break_detected(self):
        receipts, _ = build_demo(n=5)
        receipts[1]["prev_hash"] = "deadbeef"
        v = verify_receipts(receipts)
        self.assertTrue(any("chain break" in x for x in v), v)

    def test_seq_gap_detected(self):
        receipts, _ = build_demo(n=5)
        receipts[2]["seq"] = 9
        v = verify_receipts(receipts)
        self.assertTrue(any("seq gap" in x for x in v), v)

    def test_bad_signature_detected(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        receipts, _ = build_demo(n=5)
        attacker = Ed25519PrivateKey.generate()
        receipts[0]["signature"] = attacker.sign(
            receipts[0]["self_hash"].encode("ascii")
        ).hex()
        v = verify_receipts(receipts)
        self.assertTrue(any("invalid Ed25519 signature" in x for x in v), v)

    def test_valid_checkpoint_no_violations(self):
        receipts, ckpts = build_demo(n=5)
        self.assertEqual(verify_checkpoints(ckpts, receipts), [])

    def test_truncation_detected(self):
        receipts, ckpts = build_demo(n=5)
        v = verify_checkpoints(ckpts, receipts[:3])
        self.assertTrue(any("TRUNCATED" in x for x in v), v)

    def test_merkle_mismatch_detected(self):
        receipts, ckpts = build_demo(n=5)
        receipts[0]["outcome"] = "TAMPERED_VALUE"
        v = verify_checkpoints(ckpts, receipts)
        self.assertTrue(any("MERKLE root mismatch" in x for x in v), v)

    def test_seq_wrong_type_reported_not_crash(self):
        receipts, _ = build_demo(n=5)
        receipts[2]["seq"] = "2"
        v = verify_receipts(receipts)
        self.assertTrue(any("seq is not an integer" in x for x in v), v)

    def test_extension_field_flagged_unsigned(self):
        receipts, _ = build_demo(n=5)
        receipts[2]["injected_unsigned_field"] = {"payload": "attacker data"}
        v = verify_receipts(receipts)
        self.assertTrue(any("unverified extension field" in x for x in v), v)

    def test_checkpoint_extension_field_flagged(self):
        receipts, ckpts = build_demo(n=5)
        ckpts[0]["injected"] = "x"
        v = verify_checkpoints(ckpts, receipts)
        self.assertTrue(any("unverified extension field" in x for x in v), v)


class TestAnswerability(unittest.TestCase):
    def test_plain_demo_all_not_answerable(self):
        receipts, _ = build_demo(n=5, typed=False)
        for d in answerability(receipts):
            self.assertEqual(d["status"], NOT_ANSWERABLE, d)
            self.assertTrue(d["missing"], d)

    def test_typed_demo_all_answered(self):
        receipts, _ = build_demo(n=5, typed=True)
        for d in answerability(receipts):
            self.assertEqual(d["status"], ANSWERED, d)
            self.assertTrue(d["evidence"], d)


class TestCli(unittest.TestCase):
    def _run(self, *argv):
        env = dict(os.environ, PYTHONPATH=W)
        return subprocess.run(
            [sys.executable, "-m", "kairo_verify", *argv],
            capture_output=True, text=True, env=env, cwd=W,
        )

    def test_end_to_end_demo_tamper_answer(self):
        with tempfile.TemporaryDirectory() as td:
            r = self._run("demo", "--out", td)
            self.assertEqual(r.returncode, 0, r.stderr)
            rp = os.path.join(td, "receipts.jsonl")
            cp = os.path.join(td, "checkpoints.jsonl")
            r = self._run("integrity", rp, "--checkpoints", cp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
            with open(rp) as fh:
                lines = fh.read().splitlines()
            rec = json.loads(lines[2])
            rec["outcome"] = "TAMPERED_VALUE"
            lines[2] = json.dumps(rec)
            with open(rp, "w") as fh:
                fh.write("\n".join(lines) + "\n")
            r = self._run("integrity", rp)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("self_hash mismatch", r.stdout)
            r = self._run("answer", rp, "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            report = json.loads(r.stdout)
            self.assertEqual(len(report["determinations"]), 4)
            self.assertTrue(all(
                d["status"] == NOT_ANSWERABLE for d in report["determinations"]
            ))

    def test_import_isolation(self):
        code = (
            "import importlib, sys\n"
            "before = set(sys.modules)\n"
            "importlib.import_module('kairo_verify.cli')\n"
            "heavy = {m for m in set(sys.modules) - before if m.split('.')[0] in "
            "{'torch','transformers','sentence_transformers','numpy','requests',"
            "'httpx','urllib3','kairo','scipy','pandas'}}\n"
            "print('HEAVY:' + ','.join(sorted(heavy)) if heavy else 'CLEAN')\n"
        )
        env = dict(os.environ, PYTHONPATH=W)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertIn("CLEAN", r.stdout, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
