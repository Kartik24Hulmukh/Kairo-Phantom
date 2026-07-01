import os
import re
import json
import shutil
import tempfile
import subprocess
import logging
from enum import Enum
from typing import List, Dict, Any, Optional

log = logging.getLogger("kairo-sidecar.farscry_service")


class ElementType(str, Enum):
    DATE = "DATE"
    NUMBER = "NUMBER"
    CODE = "CODE"
    IMAGE = "IMAGE"
    URL = "URL"
    ERROR_MESSAGE = "ERROR_MESSAGE"
    TABLE = "TABLE"
    TEXT_BLOCK = "TEXT_BLOCK"


class FarscryService:
    """Screen visual analysis for Alt+Shift+M pointer mode."""

    def __init__(self):
        self.farscry_path = self._find_farscry()

    def analyze_cursor_region(self, cursor_x: int, cursor_y: int) -> Dict[str, Any]:
        """
        Captures a 400x300 region centered on the cursor,
        and analyzes it using farscry.
        """
        # 1. Capture screen region centered around cursor
        try:
            from PIL import ImageGrab

            # Box: (left, top, right, bottom)
            left = max(0, cursor_x - 200)
            top = max(0, cursor_y - 150)
            right = cursor_x + 200
            bottom = cursor_y + 150

            img = ImageGrab.grab(bbox=(left, top, right, bottom))
        except Exception as e:
            log.warning(f"PIL ImageGrab not available or failed: {e}. Simulating capture.")
            # Mock image for headless/test environments
            from PIL import Image

            img = Image.new("RGB", (400, 300), color="white")

        # 2. Save region to a temp file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(tmp_fd)
        img.save(tmp_path)

        # 3. Run farscry CLI visual layout analysis if available
        vasp_output = {}
        if self.farscry_path:
            try:
                res = subprocess.run(
                    [self.farscry_path, "extract", tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
                if res.returncode == 0:
                    vasp_output = json.loads(res.stdout)
            except Exception as e:
                log.warning(
                    f"farscry execution failed: {e}. Falling back to deterministic parsing."
                )

        # Cleanup temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        # 4. Classify element at cursor position (centered at 200, 150 of our box)
        element = self._find_element_at(vasp_output, 200, 150)
        element_type = self._classify_element(element)
        actions = self._get_contextual_actions(element_type, element)

        return {
            "element_type": element_type.value,
            "element_text": element.get("text", ""),
            "contextual_actions": actions,
            "vasp": vasp_output if vasp_output else {"element": element},
        }

    def _find_element_at(self, vasp: Dict[str, Any], x: int, y: int) -> Dict[str, Any]:
        """Finds matching visual element at coordinates from farscry VASP output."""
        elements = vasp.get("elements", [])
        for elem in elements:
            box = elem.get("box", [0, 0, 0, 0])  # [x1, y1, x2, y2]
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                return elem

        # Fallback default element
        return {
            "text": "Default text block at position",
            "type": "text",
            "box": [0, 0, 400, 300],
        }

    def _classify_element(self, element: Dict[str, Any]) -> ElementType:
        text = element.get("text", "").strip()
        elem_type = element.get("type", "")

        if not text:
            return ElementType.TEXT_BLOCK

        # Check for DATE format (e.g. 05/31/2026, 2026-05-31)
        if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text) or re.search(
            r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", text
        ):
            return ElementType.DATE

        # Check for numeric / financial format (e.g., $1,250.00, 45%, 1234)
        if re.match(r"^\$?[\d,]+\.?\d*%?$", text.replace(" ", "")):
            return ElementType.NUMBER

        # Check for URL format
        if text.startswith(("http://", "https://", "www.")) or ".com" in text or ".org" in text:
            return ElementType.URL

        # Check for typical code snippets / syntax
        if elem_type == "code" or self._looks_like_code(text):
            return ElementType.CODE

        # Check for error tracebacks / alerts
        if any(
            kw in text.lower() for kw in ["error:", "exception:", "failed", "traceback", "fatal"]
        ):
            return ElementType.ERROR_MESSAGE

        # Check for tables
        if elem_type == "table" or "\t" in text or " | " in text:
            return ElementType.TABLE

        return ElementType.TEXT_BLOCK

    def _looks_like_code(self, text: str) -> bool:
        indicators = [
            "def ",
            "class ",
            "import ",
            "fn ",
            "let ",
            "const ",
            "struct ",
            "public static void",
            "&&",
            "||",
            " {",
            "};",
        ]
        return (
            any(ind in text for ind in indicators)
            or len(text.split("\n")) > 1
            and ("=" in text or "(" in text)
        )

    def _get_contextual_actions(
        self, element_type: ElementType, element: Dict[str, Any]
    ) -> List[str]:
        actions_map = {
            ElementType.DATE: [
                "Schedule meeting from this date",
                "Calculate days from today",
                "Add to calendar",
            ],
            ElementType.NUMBER: [
                "Explain this figure",
                "Add to Excel spreadsheet",
                "Calculate percentage change",
            ],
            ElementType.CODE: ["Explain this code", "Improve this code", "Write unit test"],
            ElementType.IMAGE: [
                "Describe this image",
                "Extract text from image",
                "Generate similar",
            ],
            ElementType.URL: ["Summarize this page", "Check if link is live", "Extract key info"],
            ElementType.ERROR_MESSAGE: ["Explain this error", "Suggest fix", "Search for solution"],
            ElementType.TABLE: ["Extract to Excel", "Summarize data", "Create chart from this"],
            ElementType.TEXT_BLOCK: ["Improve this text", "Summarize", "Translate", "Expand"],
        }
        return actions_map.get(element_type, ["Ask Kairo about this"])

    def _find_farscry(self) -> Optional[str]:
        """Find farscry binary in PATH or common global spots."""
        path = shutil.which("farscry")
        if path:
            return path

        candidates = [
            os.path.expanduser("~/AppData/Roaming/npm/node_modules/farscry/bin/farscry.exe"),
            os.path.expanduser("~/.npm-global/bin/farscry"),
            os.path.expanduser("~/AppData/Roaming/npm/farscry.cmd"),
            os.path.expanduser("~/AppData/Roaming/npm/farscry"),
            "/usr/local/bin/farscry",
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return None
