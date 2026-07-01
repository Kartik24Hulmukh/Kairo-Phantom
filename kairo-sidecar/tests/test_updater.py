"""Tests for auto-update module."""

import sys
import os
import json
import threading
from unittest.mock import patch, MagicMock
from urllib import error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sidecar.updater import (
    check_for_update,
    _is_newer,
    check_for_update_async,
    CURRENT_VERSION,
    verify_checksum,
    verify_signature,
    apply_update,
    verify_installer_signature,
)


def test_is_newer_true():
    assert _is_newer("4.0.0", "3.9.0") is True


def test_is_newer_false_equal():
    assert _is_newer("3.9.0", "3.9.0") is False


def test_is_newer_false_older():
    assert _is_newer("3.8.0", "3.9.0") is False


def test_is_newer_patch():
    assert _is_newer("3.9.1", "3.9.0") is True


def _make_mock_response(tag_name: str, html_url: str = "https://github.com/test/release"):
    """Create a mock urllib response."""
    data = json.dumps({"tag_name": tag_name, "html_url": html_url}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_check_for_update_newer_available():
    """Returns (version, url) when a newer version exists."""
    with patch("sidecar.updater.request.urlopen", return_value=_make_mock_response("v4.0.0")):
        result = check_for_update()
    assert result is not None
    assert result[0] == "4.0.0"
    assert "github.com" in result[1]


def test_check_for_update_same_version():
    """Returns None when latest == current."""
    with patch(
        "sidecar.updater.request.urlopen", return_value=_make_mock_response(f"v{CURRENT_VERSION}")
    ):
        result = check_for_update()
    assert result is None


def test_check_for_update_older_version():
    """Returns None when latest < current."""
    with patch("sidecar.updater.request.urlopen", return_value=_make_mock_response("v1.0.0")):
        result = check_for_update()
    assert result is None


def test_check_for_update_network_error():
    """Returns None when network is unavailable."""
    with patch(
        "sidecar.updater.request.urlopen", side_effect=error.URLError("Network unreachable")
    ):
        result = check_for_update()
    assert result is None


def test_check_for_update_malformed_response():
    """Returns None when response JSON is malformed."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"not json"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("sidecar.updater.request.urlopen", return_value=mock_resp):
        result = check_for_update()
    assert result is None


def test_check_for_update_async():
    """Async variant calls callback when update is available."""
    results = []
    done = threading.Event()

    def cb(r):
        results.append(r)
        done.set()

    with patch("sidecar.updater.request.urlopen", return_value=_make_mock_response("v4.0.0")):
        check_for_update_async(cb)
        done.wait(timeout=5)

    assert len(results) == 1
    assert results[0][0] == "4.0.0"


def test_verify_checksum(tmpdir):
    test_file = os.path.join(str(tmpdir), "test.bin")
    with open(test_file, "wb") as f:
        f.write(b"hello world")

    # Expected SHA-256 of "hello world"
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert verify_checksum(test_file, expected) is True
    assert verify_checksum(test_file, "wrong_checksum") is False


def test_verify_signature(tmpdir):
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    test_file = os.path.join(str(tmpdir), "test.bin")
    with open(test_file, "wb") as f:
        f.write(b"hello world")

    signature = private_key.sign(b"hello world")
    sig_hex = signature.hex()
    pub_hex = public_key.public_bytes_raw().hex()

    assert verify_signature(test_file, sig_hex, pub_hex) is True
    assert verify_signature(test_file, sig_hex, "00" * 32) is False


def test_apply_update_success(tmpdir):
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_hex = public_key.public_bytes_raw().hex()

    # Create dummy update zip
    update_zip = os.path.join(str(tmpdir), "update.zip")
    dummy_file = os.path.join(str(tmpdir), "dummy.txt")
    with open(dummy_file, "wb") as f:
        f.write(b"new version contents")

    import zipfile

    with zipfile.ZipFile(update_zip, "w") as zf:
        zf.write(dummy_file, "dummy.txt")

    # Calculate checksum and signature
    import hashlib

    sha = hashlib.sha256()
    with open(update_zip, "rb") as f:
        data = f.read()
    sha.update(data)
    checksum = sha.hexdigest()

    signature = private_key.sign(data).hex()

    # Target directory to update
    target_dir = os.path.join(str(tmpdir), "target")
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "original.txt"), "w") as f:
        f.write("old version")

    # Mock run_health_check to pass
    with patch("sidecar.updater.run_health_check", return_value=True):
        ok = apply_update(update_zip, signature, checksum, pub_hex, target_dir)

    assert ok is True
    assert os.path.exists(os.path.join(target_dir, "dummy.txt"))
    assert not os.path.exists(target_dir + "_backup")


def test_apply_update_failed_health_check_rollback(tmpdir):
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_hex = public_key.public_bytes_raw().hex()

    update_zip = os.path.join(str(tmpdir), "update.zip")
    dummy_file = os.path.join(str(tmpdir), "dummy.txt")
    with open(dummy_file, "wb") as f:
        f.write(b"corrupted contents")

    import zipfile

    with zipfile.ZipFile(update_zip, "w") as zf:
        zf.write(dummy_file, "dummy.txt")

    # Calculate checksum and signature
    import hashlib

    sha = hashlib.sha256()
    with open(update_zip, "rb") as f:
        data = f.read()
    sha.update(data)
    checksum = sha.hexdigest()

    signature = private_key.sign(data).hex()

    # Target directory to update
    target_dir = os.path.join(str(tmpdir), "target")
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "original.txt"), "w") as f:
        f.write("old version")

    # Mock run_health_check to fail
    with patch("sidecar.updater.run_health_check", return_value=False):
        ok = apply_update(update_zip, signature, checksum, pub_hex, target_dir)

    assert ok is False
    # Verify rollback
    assert os.path.exists(os.path.join(target_dir, "original.txt"))
    assert not os.path.exists(os.path.join(target_dir, "dummy.txt"))
    assert not os.path.exists(target_dir + "_backup")


def test_verify_installer_signature_non_windows():
    """On non-Windows platforms, verify_installer_signature returns True."""
    with patch("sidecar.updater.sys.platform", "linux"):
        assert verify_installer_signature("any_file.exe") is True


def test_verify_installer_signature_missing_file():
    """If the installer file does not exist, return False."""
    with patch("sidecar.updater.sys.platform", "win32"):
        assert verify_installer_signature("nonexistent_file.exe") is False


def test_verify_installer_signature_valid():
    """If the signature check returns Valid, return True."""
    mock_run = MagicMock()
    mock_run.return_value.stdout = "Valid\n"

    with (
        patch("sidecar.updater.sys.platform", "win32"),
        patch("os.path.exists", return_value=True),
        patch("sidecar.updater.subprocess.run", mock_run),
    ):
        assert verify_installer_signature("dummy_installer.exe") is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "Get-AuthenticodeSignature" in cmd[-1]


def test_verify_installer_signature_invalid():
    """If the signature check returns a non-Valid status, return False."""
    mock_run = MagicMock()
    mock_run.return_value.stdout = "NotSigned\n"

    with (
        patch("sidecar.updater.sys.platform", "win32"),
        patch("os.path.exists", return_value=True),
        patch("sidecar.updater.subprocess.run", mock_run),
    ):
        assert verify_installer_signature("dummy_installer.exe") is False


def test_verify_installer_signature_command_failure():
    """If subprocess.run raises an error, return False."""
    import subprocess

    mock_run = MagicMock(side_effect=subprocess.SubprocessError("PowerShell failed"))

    with (
        patch("sidecar.updater.sys.platform", "win32"),
        patch("os.path.exists", return_value=True),
        patch("sidecar.updater.subprocess.run", mock_run),
    ):
        assert verify_installer_signature("dummy_installer.exe") is False


import pytest


@pytest.fixture(autouse=True)
def _clear_offline_env(monkeypatch):
    # CI sets KAIRO_OFFLINE=1 globally, suppressing telemetry/updater writes & network.
    # These tests exercise the opted-in / online paths, so clear it per-test.
    # Tests that need offline behavior set KAIRO_OFFLINE themselves via patch.dict.
    monkeypatch.delenv("KAIRO_OFFLINE", raising=False)
