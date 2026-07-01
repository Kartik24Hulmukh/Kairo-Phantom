"""
Auto-update checker for Kairo Phantom.
Checks GitHub releases API on startup (non-blocking).
Never downloads automatically — only prompts user.
"""

import json
import threading
import logging
import os
import sys
import subprocess
import shutil
import zipfile
import hashlib
from typing import Optional, Tuple
from urllib import request, error

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

log = logging.getLogger("kairo.updater")

CURRENT_VERSION = "3.9.0"
GITHUB_RELEASES_API = "https://api.github.com/repos/KairoPhantom/Kairo-Phantom/releases/latest"

# Default fallback/embedded public key for updates (mocked/testing key representation)
DEFAULT_PUBLIC_KEY = "3b7b25ad75753065b706f9479b18360d8a5db39d73d6de5a6873bc076b32df5a"


def check_for_update() -> Optional[Tuple[str, str]]:
    """
    Check GitHub releases for a newer version.
    Returns (latest_version, download_url) if newer available, else None.
    Times out in 5 seconds.
    """
    if os.environ.get("KAIRO_OFFLINE") == "1":
        log.info("[Updater] Offline mode active; skipping update check.")
        return None

    try:
        req = request.Request(
            GITHUB_RELEASES_API,
            headers={"User-Agent": f"KairoPhantom/{CURRENT_VERSION}"},
        )
        with request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        latest = data.get("tag_name", "").lstrip("v")
        download_url = data.get("html_url", "")
        if latest and latest != CURRENT_VERSION and _is_newer(latest, CURRENT_VERSION):
            log.info(f"[Updater] New version available: {latest}")
            return (latest, download_url)
        return None
    except (error.URLError, json.JSONDecodeError, Exception) as e:
        log.debug(f"[Updater] Update check failed (offline or error): {e}")
        return None


def _is_newer(a: str, b: str) -> bool:
    """Return True if version a > version b."""
    try:
        return tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
    except ValueError:
        return False


def check_for_update_async(callback) -> None:
    """Run update check in background thread, call callback with result."""

    def _run():
        result = check_for_update()
        if result:
            callback(result)

    threading.Thread(target=_run, daemon=True, name="kairo-updater").start()


def verify_checksum(file_path: str, expected_sha256: str) -> bool:
    """Verify SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest().lower() == expected_sha256.strip().lower()
    except Exception as e:
        log.error(f"[Updater] Checksum verification failed: {e}")
        return False


def verify_signature(file_path: str, signature_hex: str, public_key_hex: str) -> bool:
    """Verify Ed25519 signature of a file."""
    if not HAS_CRYPTOGRAPHY:
        log.error("[Updater] Cryptography package missing, cannot verify signature")
        return False
    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        with open(file_path, "rb") as f:
            data = f.read()
        sig_bytes = bytes.fromhex(signature_hex)
        public_key.verify(sig_bytes, data)
        return True
    except Exception as e:
        log.error(f"[Updater] Signature verification failed: {e}")
        return False


def verify_installer_signature(file_path: str) -> bool:
    """
    Verify that the Windows installer has a valid Authenticode signature.
    Uses PowerShell's Get-AuthenticodeSignature on Windows.
    Returns True on non-Windows/mocked setups.
    """
    if sys.platform != "win32":
        return True

    if not os.path.exists(file_path):
        log.error(f"[Updater] Installer file not found: {file_path}")
        return False

    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"(Get-AuthenticodeSignature -LiteralPath '{file_path}').Status",
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        status = result.stdout.strip()
        if status == "Valid":
            log.info(f"[Updater] Installer signature is valid: {file_path}")
            return True
        else:
            log.error(f"[Updater] Installer signature is invalid ({status}): {file_path}")
            return False
    except subprocess.SubprocessError as e:
        log.error(f"[Updater] Failed to run Get-AuthenticodeSignature: {e}")
        return False
    except Exception as e:
        log.error(f"[Updater] Unexpected error during signature verification: {e}")
        return False


def run_health_check() -> bool:
    """Startup health check simulation."""
    # A real health check tries to load sidecar submodules
    try:
        return True
    except Exception as e:
        log.error(f"[Updater] Health check failed: {e}")
        return False


def apply_update(
    archive_path: str,
    signature_hex: str,
    expected_sha256: str,
    public_key_hex: str = DEFAULT_PUBLIC_KEY,
    target_dir: Optional[str] = None,
) -> bool:
    """
    Verifies signature and checksum, backs up target directory, extracts update archive,
    runs health check, and rolls back if the health check fails.
    """
    if not verify_checksum(archive_path, expected_sha256):
        log.error("[Updater] Update failed: Checksum mismatch")
        return False

    if not verify_signature(archive_path, signature_hex, public_key_hex):
        log.error("[Updater] Update failed: Signature invalid")
        return False

    if not target_dir:
        target_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    backup_dir = target_dir + "_backup"

    # 1. Take backup
    try:
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        shutil.copytree(
            target_dir,
            backup_dir,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp"),
        )
    except Exception as e:
        log.error(f"[Updater] Failed to create backup: {e}")
        return False

    # 2. Extract ZIP
    try:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(target_dir)
    except Exception as e:
        log.error(f"[Updater] Extraction failed: {e}. Initiating rollback...")
        _rollback(backup_dir, target_dir)
        return False

    # 3. Health check
    if not run_health_check():
        log.error("[Updater] Update failed health check. Initiating rollback...")
        _rollback(backup_dir, target_dir)
        return False

    # Clean up backup on success
    try:
        shutil.rmtree(backup_dir)
    except Exception:
        pass

    log.info("[Updater] Update applied successfully")
    return True


def _rollback(backup_dir: str, target_dir: str):
    """Restore from backup directory."""
    try:
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(backup_dir, target_dir, symlinks=True)
        shutil.rmtree(backup_dir)
        log.info("[Updater] Rollback completed successfully")
    except Exception as e:
        log.critical(f"[Updater] Rollback failed: {e}. System may be in inconsistent state!")
