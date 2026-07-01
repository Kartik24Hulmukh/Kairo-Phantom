"""Tests for SopsManager module."""

import sys
import os
import subprocess
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sidecar.sops_manager import SopsManager


def test_sops_manager_fallback_without_sops(tmp_path):
    with patch("shutil.which", return_value=None):
        manager = SopsManager()
        secrets = manager.decrypt_file(str(tmp_path / "nonexistent.yaml"))
        assert (
            secrets["DATABASE_URL"] == "postgresql://mock_user:mock_pass@localhost:5432/mock_kairo"
        )
        assert secrets["LLM_API_KEY"] == "sk-mock-kairo-phantom-api-key-for-testing"


def test_sops_manager_fallback_on_decryption_failure(tmp_path):
    dummy_file = tmp_path / "secrets.yaml"
    dummy_file.write_text("dummy content")

    with (
        patch("shutil.which", return_value="/usr/bin/sops"),
        patch("subprocess.run", side_effect=subprocess.SubprocessError("decryption failed")),
    ):
        manager = SopsManager(key_path="/fake/key.txt")
        secrets = manager.decrypt_file(str(dummy_file))
        assert (
            secrets["DATABASE_URL"] == "postgresql://mock_user:mock_pass@localhost:5432/mock_kairo"
        )


def test_sops_manager_successful_decryption(tmp_path):
    secrets_file = tmp_path / "secrets.yaml"
    secrets_file.write_text("encrypted content")

    decrypted_yaml = """
DATABASE_URL: "postgresql://real_user:real_pass@localhost:5432/real_kairo"
LLM_API_KEY: "sk-real-api-key"
"""

    mock_run = MagicMock()
    mock_run.return_value.stdout = decrypted_yaml
    mock_run.return_value.returncode = 0

    with (
        patch("shutil.which", return_value="/usr/bin/sops"),
        patch("subprocess.run", mock_run) as mock_subprocess,
    ):
        manager = SopsManager(key_path="/fake/key.txt")
        secrets = manager.decrypt_file(str(secrets_file))

        mock_subprocess.assert_called_once()
        args, kwargs = mock_subprocess.call_args
        cmd = args[0]
        assert cmd[0] == "/usr/bin/sops"
        assert cmd[1] == "-d"
        assert cmd[2] == str(secrets_file)
        assert kwargs["env"]["SOPS_AGE_KEY_FILE"] == "/fake/key.txt"

        assert (
            secrets["DATABASE_URL"] == "postgresql://real_user:real_pass@localhost:5432/real_kairo"
        )
        assert secrets["LLM_API_KEY"] == "sk-real-api-key"
