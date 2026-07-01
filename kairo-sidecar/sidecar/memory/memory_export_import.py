"""
MemoryExportImport — Cross-machine memory migration (Domain 10)

Exports memories to encrypted JSON files with optional PII scrubbing.
Supports .kairo-memory format with metadata for cross-machine portability.

Encryption: Simple key-derivation using hashlib (SHA-256) + XOR cipher.
This is NOT military-grade — it's a transport-layer obfuscation to prevent
casual inspection of memory files in transit. For true encryption, use
the Rust-side AES-GCM via phantom-core.
"""

from __future__ import annotations

import json
import os
import hashlib
import logging
import time
from typing import Dict, List, Optional

from sidecar.safety.pii_guard import PiiGuard
from sidecar.safety.prompt_shield import PromptShield

log = logging.getLogger("kairo-sidecar.memory_export_import")


def _derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte key from a passphrase using SHA-256."""
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def _xor_encrypt(data: bytes, key: bytes) -> bytes:
    """XOR cipher — simple transport obfuscation."""
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _xor_decrypt(data: bytes, key: bytes) -> bytes:
    """XOR decrypt (same operation as encrypt)."""
    return _xor_encrypt(data, key)


class MemoryExportImport:
    """
    Memory export/import for cross-machine migration.

    - export_to_file: Export memories to encrypted JSON
    - import_from_file: Import memories from encrypted JSON
    - export_to_kairo_memory: Export to .kairo-memory format with metadata
    """

    def __init__(self, passphrase: Optional[str] = None):
        self.pii_guard = PiiGuard()
        self.prompt_shield = PromptShield()
        # Default passphrase from env or deterministic fallback
        self.passphrase = passphrase or os.environ.get(
            "KAIRO_MEMORY_PASSPHRASE", "kairo-phantom-default-key"
        )

    def _get_default_passphrase(self) -> str:
        return self.passphrase

    def export_to_file(
        self,
        memories: List[Dict],
        output_path: str,
        include_pii: bool = False,
    ) -> str:
        """
        Export memories to an encrypted JSON file.

        Args:
            memories: List of memory dicts to export
            output_path: Path to write the export file
            include_pii: If False, PiiGuard scrubs PII from export

        Returns:
            Path to the written file.
        """
        export_data = {
            "version": 1,
            "exported_at": time.time(),
            "memory_count": len(memories),
            "memories": [],
        }

        for mem in memories:
            entry = dict(mem)  # shallow copy
            if not include_pii:
                # Scrub PII from all string fields
                for key, value in entry.items():
                    if isinstance(value, str):
                        entry[key] = self.pii_guard.redact(value)
            export_data["memories"].append(entry)

        # Serialize and encrypt
        json_bytes = json.dumps(export_data, ensure_ascii=False).encode("utf-8")
        key = _derive_key(self.passphrase)
        encrypted = _xor_encrypt(json_bytes, key)

        # Write with header for identification
        with open(output_path, "wb") as f:
            f.write(b"KAIRO_MEM\x00")  # 9-byte magic header
            f.write(encrypted)

        log.info(f"Exported {len(memories)} memories to {output_path} (include_pii={include_pii})")
        return output_path

    def import_from_file(self, file_path: str) -> List[Dict]:
        """
        Import memories from an encrypted JSON file.

        Args:
            file_path: Path to the export file

        Returns:
            List of imported memory dicts.
        """
        with open(file_path, "rb") as f:
            raw = f.read()

        # Verify and strip magic header
        if raw.startswith(b"KAIRO_MEM\x00"):
            raw = raw[len(b"KAIRO_MEM\x00") :]
        else:
            # Try loading as plain JSON (backward compat)
            try:
                data = json.loads(raw.decode("utf-8"))
                return data.get("memories", [])
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # Decrypt
        key = _derive_key(self.passphrase)
        decrypted = _xor_decrypt(raw, key)

        try:
            data = json.loads(decrypted.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to decrypt/parse memory file: {e}")

        memories = data.get("memories", [])
        log.info(f"Imported {len(memories)} memories from {file_path}")
        return memories

    def export_to_kairo_memory(
        self,
        memories: List[Dict],
        output_path: str,
        user_id: str = "local",
        include_pii: bool = False,
    ) -> str:
        """
        Export to .kairo-memory format (JSON with metadata).

        The .kairo-memory format is a structured JSON with:
        - format: "kairo-memory"
        - version: 1
        - metadata: user_id, export timestamp, memory count, PII status
        - memories: list of memory entries

        The file is encrypted with the same XOR cipher as export_to_file.
        """
        export_data = {
            "format": "kairo-memory",
            "version": 1,
            "metadata": {
                "user_id": user_id,
                "exported_at": time.time(),
                "memory_count": len(memories),
                "pii_included": include_pii,
                "export_tool": "kairo-sidecar Domain 10",
            },
            "memories": [],
        }

        for mem in memories:
            entry = dict(mem)
            if not include_pii:
                for key, value in entry.items():
                    if isinstance(value, str):
                        entry[key] = self.pii_guard.redact(value)
            export_data["memories"].append(entry)

        # Serialize and encrypt
        json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
        key = _derive_key(self.passphrase)
        encrypted = _xor_encrypt(json_bytes, key)

        with open(output_path, "wb") as f:
            f.write(b"KAIRO_MEM\x00")
            f.write(encrypted)

        log.info(f"Exported {len(memories)} memories to .kairo-memory format at {output_path}")
        return output_path
