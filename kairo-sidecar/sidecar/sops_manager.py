"""
SOPS secrets manager for Kairo Phantom.
Handles transparent decryption of encrypted yaml/json secret files for local and CI environments.
Falls back to mock secrets if the sops CLI or key material is unavailable.
"""

import os
import subprocess
import shutil
import json
import logging
from typing import Dict, Any, Optional

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

log = logging.getLogger("kairo.sops")


class SopsManager:
    """Manages SOPS secret file decryption and retrieval."""

    def __init__(self, key_path: Optional[str] = None):
        self.key_path = key_path or os.environ.get("SOPS_AGE_KEY_FILE")
        self.sops_bin = shutil.which("sops")

    def decrypt_file(self, file_path: str) -> Dict[str, Any]:
        """
        Decrypt a SOPS encrypted file.
        If sops is installed and configured, decrypts via subprocess.
        Otherwise, falls back to mock secrets.
        """
        if not os.path.exists(file_path):
            log.warning(f"[SOPS] File not found: {file_path}. Returning mock secrets.")
            return self._get_mock_secrets()

        # Check if sops is available
        if self.sops_bin:
            try:
                env = os.environ.copy()
                if self.key_path:
                    env["SOPS_AGE_KEY_FILE"] = self.key_path

                # Call sops decryption
                cmd = [self.sops_bin, "-d", file_path]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)

                # Parse output
                if file_path.endswith(".json"):
                    return json.loads(res.stdout)
                elif file_path.endswith((".yaml", ".yml")):
                    if HAS_YAML:
                        return yaml.safe_load(res.stdout) or {}
                    else:
                        log.warning(
                            "[SOPS] PyYAML not installed; parsing simple key-value YAML manually."
                        )
                        return self._parse_simple_yaml(res.stdout)
                else:
                    # Generic format or env format
                    return self._parse_env_output(res.stdout)
            except Exception as e:
                log.error(f"[SOPS] Decryption failed: {e}. Falling back to mock secrets.")
                return self._get_mock_secrets()
        else:
            log.info(
                "[SOPS] sops CLI not found on PATH. Using mock secrets for local verification."
            )
            return self._get_mock_secrets()

    def _get_mock_secrets(self) -> Dict[str, Any]:
        """Return a dictionary of safe, mock secrets for local/CI test runs."""
        return {
            "DATABASE_URL": "postgresql://mock_user:mock_pass@localhost:5432/mock_kairo",
            "LLM_API_KEY": "sk-mock-kairo-phantom-api-key-for-testing",
            "TELEMETRY_ENDPOINT": "http://127.0.0.1:4317/v1/traces",
            "CRASH_REPORT_URL": "http://127.0.0.1:8000/crash-report",
            "SIGNING_PRIVATE_KEY": "c0ffeec0ffeec0ffeec0ffeec0ffeec0ffeec0ffeec0ffeec0ffeec0ffeec0ffee",
        }

    def _parse_simple_yaml(self, content: str) -> Dict[str, Any]:
        """Simple manual yaml parser for key-value pairs in case pyyaml is missing."""
        secrets = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            secrets[k.strip()] = v.strip().strip('"').strip("'")
        return secrets

    def _parse_env_output(self, content: str) -> Dict[str, Any]:
        """Parse env/dotenv output format into a dict."""
        secrets = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            secrets[k.strip()] = v.strip().strip('"').strip("'")
        return secrets
