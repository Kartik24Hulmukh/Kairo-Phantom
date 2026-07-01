"""
Domain 8: Screen Context Bridge
================================
Python sidecar module for extracting structured context from screenshots.

Handles:
- Running farscry CLI for VASP (Visual Accessibility Structured Parsing) output
- Fallback OCR via pytesseract if farscry is unavailable
- Parsing and structuring extracted content for LLM consumption
"""

import os
import json
import shutil
import subprocess
from typing import Dict, Optional


class ScreenContextBridge:
    """Extracts and structures screen content from screenshots."""

    def __init__(self):
        self._farscry_path = self._find_farscry()
        self._tesseract_path = self._find_tesseract()

    async def extract_context(
        self,
        image_path: str,
        app_context: Optional[Dict] = None,
    ) -> Dict:
        """
        Extract structured context from a screenshot image.

        Tries farscry first (VASP output), falls back to tesseract OCR,
        and finally to a basic file metadata description.

        Returns a dict with:
        - "text": extracted text content
        - "structured": structured layout data (if available)
        - "method": "farscry" | "tesseract" | "metadata"
        - "app_name": source application name
        - "success": bool
        """
        if not image_path or not os.path.exists(image_path):
            return {
                "text": "",
                "structured": {},
                "method": "none",
                "app_name": app_context.get("app_name", "Unknown") if app_context else "Unknown",
                "success": False,
                "error": f"Image not found: {image_path}",
            }

        app_name = app_context.get("app_name", "Unknown") if app_context else "Unknown"

        # Strategy 1: farscry (preferred — VASP structured output)
        if self._farscry_path:
            try:
                result = self._run_farscry(image_path)
                return {
                    "text": result.get("text", ""),
                    "structured": result,
                    "method": "farscry",
                    "app_name": app_name,
                    "success": True,
                }
            except Exception:
                pass  # Fall through to tesseract

        # Strategy 2: pytesseract (fallback OCR)
        if self._tesseract_path:
            try:
                text = self._fallback_ocr(image_path)
                return {
                    "text": text,
                    "structured": {"raw_ocr": text},
                    "method": "tesseract",
                    "app_name": app_name,
                    "success": True,
                }
            except Exception:
                pass  # Fall through to metadata

        # Strategy 3: File metadata only
        file_size = os.path.getsize(image_path)
        return {
            "text": f"[Screenshot captured: {file_size // 1024} KB, app: {app_name}]",
            "structured": {"file_size_kb": file_size // 1024, "path": image_path},
            "method": "metadata",
            "app_name": app_name,
            "success": True,
        }

    def _run_farscry(self, image_path: str) -> Dict:
        """Run farscry CLI to extract VASP output from screenshot."""
        cmd = [self._farscry_path, "extract", image_path]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"farscry failed: {result.stderr}")

        # Parse farscry output (JSON or structured text)
        output = result.stdout.strip()

        try:
            # Try JSON parse first
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                parsed.setdefault("text", output)
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Return as structured text
        return {
            "text": output,
            "format": "vasp_text",
            "lines": output.count("\n") + 1,
            "chars": len(output),
        }

    def _fallback_ocr(self, image_path: str) -> str:
        """Extract text using tesseract OCR as fallback."""
        cmd = [self._tesseract_path, image_path, "stdout", "-l", "eng"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"tesseract failed: {result.stderr}")

        return result.stdout.strip()

    def _parse_vasp_output(self, raw_output: str) -> Dict:
        """Parse VASP structured output into sections."""
        sections = []
        current_section = {"type": "text", "content": ""}

        for line in raw_output.split("\n"):
            stripped = line.strip()

            # Detect section headers (VASP uses indentation-based structure)
            indent = len(line) - len(line.lstrip())

            if not stripped:
                if current_section["content"]:
                    sections.append(current_section)
                    current_section = {"type": "text", "content": ""}
                continue

            # Detect UI elements
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = {"type": "button", "content": stripped[1:-1]}
                sections.append(current_section)
                current_section = {"type": "text", "content": ""}
            elif indent > 4:
                current_section["type"] = "nested"
                current_section["content"] += stripped + "\n"
            else:
                current_section["content"] += stripped + "\n"

        if current_section["content"]:
            sections.append(current_section)

        return {
            "sections": sections,
            "section_count": len(sections),
            "text": raw_output,
        }

    def _find_farscry(self) -> Optional[str]:
        """Find farscry binary in PATH or common locations."""
        # Check PATH
        path = shutil.which("farscry")
        if path:
            return path

        # Check common npm global locations
        candidates = [
            os.path.expanduser("~/.npm-global/bin/farscry"),
            os.path.expanduser("~/AppData/Roaming/npm/farscry.cmd"),
            os.path.expanduser("~/AppData/Roaming/npm/farscry"),
            "/usr/local/bin/farscry",
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        return None

    def _find_tesseract(self) -> Optional[str]:
        """Find tesseract binary in PATH or common locations."""
        path = shutil.which("tesseract")
        if path:
            return path

        # Windows common install location
        win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(win_path):
            return win_path

        return None
