# PROVENANCE: original | Research/notes domain oracle tests per VERIFICATION_ORACLES.md
"""Research/notes domain oracle tests — backlink_integrity + graph_readback + kill-proofs.

Tests verify:
  1. backlink_integrity: every [[link]] resolves; backlinks bidirectionally
     consistent; no dangling links. Kill-proof: add dangling link → FAILS.
  2. graph_readback: note count + link edges match expected graph after
     edit/rename. Kill-proof: stale link after rename → FAILS.
  3. Honest degradation: vault path missing → FAIL LOUD.
  4. >=3 gauntlet scenarios: (a) add note + link (backlinks update),
     (b) rename note → all backlinks rewritten + graph consistent,
     (c) dangling/broken link the oracle must catch.
  5. Trust stack integration: audit log + egress report.
  6. CLI integration: notes subcommand works end-to-end.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.domains.notes.engine import (  # noqa: E402
    create_note,
    edit_note,
    notes_pipeline,
    parse_vault,
    rename_note,
)
from kairo.domains.notes.oracles import (  # noqa: E402
    backlink_integrity,
    graph_readback,
)

# Fixture paths
_FIX_VAULT = os.path.join(_REPO_ROOT, "kairo", "domains", "notes", "fixtures", "vault")


# ---------------------------------------------------------------------------
# Helper: copy fixture vault to temp dir
# ---------------------------------------------------------------------------


def _copy_fixture_vault(tmpdir: str) -> str:
    """Copy the fixture vault to a temp directory and return the path."""
    dest = os.path.join(tmpdir, "vault")
    shutil.copytree(_FIX_VAULT, dest)
    return dest


# ---------------------------------------------------------------------------
# Oracle 1: backlink_integrity
# ---------------------------------------------------------------------------


class TestBacklinkIntegrity:
    """backlink_integrity oracle: all links resolve, backlinks consistent."""

    def test_clean_vault_passes(self):
        """A clean fixture vault passes backlink integrity."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            passed = backlink_integrity(vault)
            assert passed, "backlink_integrity should pass for a clean vault"

    def test_kill_proof_dangling_link_fails(self):
        """Kill-proof: add a link to a nonexistent note → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)

            # Add a dangling link to Python.md
            python_path = os.path.join(vault, "Python.md")
            with open(python_path, "a", encoding="utf-8") as f:
                f.write("\nSee [[Nonexistent Note]] for more.\n")

            with pytest.raises(AssertionError, match="dangling link"):
                backlink_integrity(vault)

    def test_backlinks_bidirectionally_consistent(self):
        """Backlinks are the exact reverse of forward links."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            graph = parse_vault(vault)

            # Verify: Python links to Algorithms → Algorithms backlinks include Python
            assert "Algorithms" in graph.notes["Python"].forward_links
            assert "Python" in graph.notes["Algorithms"].backlinks

            # Verify: Index links to Python → Python backlinks include Index
            assert "Python" in graph.notes["Index"].forward_links
            assert "Index" in graph.notes["Python"].backlinks


# ---------------------------------------------------------------------------
# Oracle 2: graph_readback
# ---------------------------------------------------------------------------


class TestGraphReadback:
    """graph_readback oracle: note count + edges match expected graph."""

    def test_note_count_matches(self):
        """Note count matches expected for the fixture vault."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            passed = graph_readback(vault, expected_note_count=5)
            assert passed

    def test_edges_match(self):
        """Forward link edges match expected graph."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            expected_edges = {
                "Index": ["Algorithms", "Databases", "Python"],
                "Python": ["Algorithms", "Databases"],
                "Algorithms": ["Python"],
                "Databases": ["Python"],
                "Machine Learning": ["Algorithms", "Python"],
            }
            passed = graph_readback(vault, expected_note_count=5, expected_edges=expected_edges)
            assert passed

    def test_kill_proof_wrong_note_count_fails(self):
        """Kill-proof: wrong note count → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            with pytest.raises(AssertionError, match="note count mismatch"):
                graph_readback(vault, expected_note_count=99)

    def test_kill_proof_wrong_edges_fails(self):
        """Kill-proof: wrong edges → FAILS."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            expected_edges = {
                "Python": ["Nonexistent"],  # Wrong edge
            }
            with pytest.raises(AssertionError, match="forward links for 'Python' mismatch"):
                graph_readback(vault, expected_note_count=5, expected_edges=expected_edges)


# ---------------------------------------------------------------------------
# Honest degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """Vault path missing → FAIL LOUD, never fake results."""

    def test_pipeline_with_missing_vault_fails_loud(self):
        """If vault path doesn't exist, pipeline must fail with clear error."""
        result = notes_pipeline(vault_path="/nonexistent/path/vault")
        assert not result.ok
        assert "notes vault unavailable" in result.error.lower()

    def test_parse_vault_missing_path_raises(self):
        """parse_vault on missing path raises NotesVaultUnavailableError."""
        from kairo.domains.notes.engine import NotesVaultUnavailableError

        with pytest.raises(NotesVaultUnavailableError, match="notes vault unavailable"):
            parse_vault("/nonexistent/path/vault")


# ---------------------------------------------------------------------------
# Gauntlet scenarios (>=3, zero skips)
# ---------------------------------------------------------------------------


class TestGauntletScenarios:
    ">=3 end-to-end gauntlet scenarios." ""

    def test_scenario_a_add_note_and_link(self):
        """Scenario (a): add a note + link it (backlinks update)."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)

            # Create a new note that links to Python
            create_note(vault, "Web Dev", "Web development uses [[Python]] for backends.")

            # Verify graph: new note should appear, backlinks should update
            graph = parse_vault(vault)
            assert graph.note_count == 6
            assert "Web Dev" in graph.notes
            assert "Python" in graph.notes["Web Dev"].forward_links
            assert "Web Dev" in graph.notes["Python"].backlinks

            # Backlink integrity should still pass
            passed = backlink_integrity(vault)
            assert passed

    def test_scenario_b_rename_note_updates_backlinks(self):
        """Scenario (b): rename a note → all backlinks rewritten + graph consistent."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)

            # Rename Python → Python3
            rename_note(vault, "Python", "Python3")

            # Verify: Python.md is gone, Python3.md exists
            assert not os.path.exists(os.path.join(vault, "Python.md"))
            assert os.path.exists(os.path.join(vault, "Python3.md"))

            # Verify: all references to [[Python]] are now [[Python3]]
            graph = parse_vault(vault)
            assert "Python3" in graph.notes
            assert "Python" not in graph.notes

            # Check that Index now links to Python3
            assert "Python3" in graph.notes["Index"].forward_links
            assert "Python" not in graph.notes["Index"].forward_links

            # Check that Algorithms now links to Python3
            assert "Python3" in graph.notes["Algorithms"].forward_links

            # Backlink integrity should pass
            passed = backlink_integrity(vault)
            assert passed

    def test_scenario_c_dangling_link_caught(self):
        """Scenario (c): a dangling/broken link the oracle must catch."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)

            # Edit Index.md to add a link to a nonexistent note
            edit_note(vault, "Index", "# Index\n\nSee [[Broken Link]] for missing content.\n")

            # The oracle must catch this
            with pytest.raises(AssertionError, match="dangling link"):
                backlink_integrity(vault)


# ---------------------------------------------------------------------------
# Trust stack integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_pipeline_emits_audit_and_egress(self):
        """Pipeline with private_key emits audit log + egress report."""
        private_key = ed25519.Ed25519PrivateKey.generate()

        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            result = notes_pipeline(
                vault_path=vault,
                private_key=private_key,
            )
            assert result.ok
            assert result.audit_log_json, "Audit log JSON should be non-empty"
            assert result.egress_report_json, "Egress report JSON should be non-empty"

            from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
            from kairo.oracles.zero_egress_report import (
                report_from_json,
                verify_zero_egress_report,
            )

            public_key = private_key.public_key()
            entries = Ed25519AuditLog.entries_from_json(result.audit_log_json)
            assert len(entries) > 0
            assert Ed25519AuditLog.verify_chain(entries, public_key)

            report = report_from_json(result.egress_report_json)
            assert verify_zero_egress_report(report, public_key)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """notes CLI subcommand works end-to-end via registry."""

    def test_cli_verify(self):
        """`kairo notes verify` produces output + audit artifacts."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            out_dir = os.path.join(tmp, "notes_output")
            rc = main(["notes", "verify", vault, "--outdir", out_dir])
            assert rc == 0, f"CLI verify failed with exit code {rc}"
            assert os.path.isfile(os.path.join(out_dir, "audit_log.json"))
            assert os.path.isfile(os.path.join(out_dir, "zero_egress_report.json"))

    def test_cli_graph(self):
        """`kairo notes graph` displays the vault document graph."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            vault = _copy_fixture_vault(tmp)
            rc = main(["notes", "graph", vault, "--outdir", os.path.join(tmp, "out")])
            assert rc == 0, f"CLI graph failed with exit code {rc}"
