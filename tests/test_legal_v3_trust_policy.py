"""Tests for the configurable trust-policy input for the legal-v3 verifier."""
import json
import tempfile
import unittest
from pathlib import Path

from kairo.legal_v3.trust_policy import (
    DEFAULT_POLICY,
    TrustPolicyError,
    check_approval_ttl,
    check_clause,
    check_key_trust,
    check_observer_collision,
    check_source_size,
    load_policy,
    write_default_policy,
)


class TrustPolicyTests(unittest.TestCase):
    def test_default_policy(self) -> None:
        """Default policy matches hardcoded allowlist."""
        policy = load_policy(None)
        self.assertEqual(policy["profile"], "kairo-legal-v3")
        self.assertIn("governing_law", policy["allowed_clauses"])
        self.assertIn("liability_cap", policy["allowed_clauses"])
        self.assertIsNone(policy["trusted_key_ids"])

    def test_load_from_file(self) -> None:
        """Can load a custom policy from a JSON file."""
        custom = {
            "profile": "kairo-legal-v3",
            "allowed_clauses": ["governing_law", "liability_cap"],
            "trusted_key_ids": ["key-abc", "key-def"],
            "approval_ttl_seconds": 300,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(custom, f)
            f.flush()
            policy = load_policy(f.name)

        self.assertEqual(policy["allowed_clauses"], ["governing_law", "liability_cap"])
        self.assertEqual(policy["trusted_key_ids"], ["key-abc", "key-def"])
        self.assertEqual(policy["approval_ttl_seconds"], 300)
        # Defaults filled in
        self.assertTrue(policy["reject_observer_collision"])

    def test_invalid_profile_rejected(self) -> None:
        """Wrong profile name is rejected."""
        bad = {"profile": "wrong-profile", "allowed_clauses": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(bad, f)
            f.flush()
            with self.assertRaises(TrustPolicyError):
                load_policy(f.name)

    def test_missing_clauses_rejected(self) -> None:
        """Missing allowed_clauses field is rejected."""
        bad = {"profile": "kairo-legal-v3"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(bad, f)
            f.flush()
            with self.assertRaises(TrustPolicyError):
                load_policy(f.name)

    def test_nonexistent_file_rejected(self) -> None:
        """Nonexistent policy file is rejected."""
        with self.assertRaises(TrustPolicyError):
            load_policy("/nonexistent/policy.json")

    def test_check_clause_allowed(self) -> None:
        """Allowed clause passes check."""
        policy = load_policy(None)
        self.assertTrue(check_clause(policy, "governing_law"))
        self.assertTrue(check_clause(policy, "liability_cap"))

    def test_check_clause_denied(self) -> None:
        """Non-allowlisted clause is denied."""
        policy = load_policy(None)
        self.assertFalse(check_clause(policy, "nonexistent_clause"))
        self.assertFalse(check_clause(policy, "payment_terms"))

    def test_check_key_trust_default(self) -> None:
        """Default policy accepts any key."""
        policy = load_policy(None)
        self.assertTrue(check_key_trust(policy, "any-key-id"))

    def test_check_key_trust_restricted(self) -> None:
        """Restricted policy only accepts trusted keys."""
        policy = {
            "trusted_key_ids": ["trusted-1", "trusted-2"],
            "allowed_clauses": [],
        }
        self.assertTrue(check_key_trust(policy, "trusted-1"))
        self.assertFalse(check_key_trust(policy, "untrusted"))

    def test_check_approval_ttl_within(self) -> None:
        """Approval within TTL passes."""
        policy = load_policy(None)
        self.assertTrue(check_approval_ttl(policy, 1000, 1100))

    def test_check_approval_ttl_expired(self) -> None:
        """Approval beyond TTL fails."""
        policy = {"approval_ttl_seconds": 60, "allowed_clauses": []}
        self.assertFalse(check_approval_ttl(policy, 1000, 2000))

    def test_check_observer_collision_pass(self) -> None:
        """Distinct observer key passes."""
        policy = {"reject_observer_collision": True, "allowed_clauses": []}
        self.assertTrue(
            check_observer_collision(policy, "obs-key", ["prod-key", "app-key"])
        )

    def test_check_observer_collision_fail(self) -> None:
        """Observer key matching producer key fails."""
        policy = {"reject_observer_collision": True, "allowed_clauses": []}
        self.assertFalse(
            check_observer_collision(policy, "same-key", ["same-key", "app-key"])
        )

    def test_check_observer_collision_allowed(self) -> None:
        """Policy that allows collisions passes even with collision."""
        policy = {"reject_observer_collision": False, "allowed_clauses": []}
        self.assertTrue(
            check_observer_collision(policy, "same-key", ["same-key", "app-key"])
        )

    def test_check_source_size_within(self) -> None:
        """Source within size limit passes."""
        policy = load_policy(None)
        self.assertTrue(check_source_size(policy, 1024))

    def test_check_source_size_exceeds(self) -> None:
        """Source exceeding size limit fails."""
        policy = {"max_source_bytes": 100, "allowed_clauses": []}
        self.assertFalse(check_source_size(policy, 200))

    def test_write_default_policy(self) -> None:
        """write_default_policy produces a valid policy file."""
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "policy.json")
            write_default_policy(path)
            policy = load_policy(path)
            self.assertEqual(policy["profile"], "kairo-legal-v3")
            self.assertEqual(
                policy["allowed_clauses"], DEFAULT_POLICY["allowed_clauses"]
            )


if __name__ == "__main__":
    unittest.main()
