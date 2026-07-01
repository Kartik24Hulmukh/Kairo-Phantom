"""FigMirror Bridge for Kairo Domain 3 (PowerPoint).

FigMirror generates publication-quality charts and figures in the style of
scientific papers. This bridge provides a real HTTP client to communicate
with a running FigMirror service.

If FigMirror is not running, this bridge FAILS LOUDLY with a
ConnectionError — it NEVER silently mocks or returns fake data.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

log = logging.getLogger("kairo-sidecar.figmirror_bridge")

DEFAULT_URL = "http://localhost:8766"


class FigMirrorBridge:
    """Real HTTP client for FigMirror chart generation service."""

    def __init__(self, base_url: str = DEFAULT_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health_check(self) -> Dict[str, Any]:
        """Check if FigMirror service is reachable.

        Returns: {"ok": True, "status": "healthy"} if reachable.
        Raises: ConnectionError if service is down.
        """
        try:
            req = urllib.request.Request(
                f"{self.base_url}/health",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"ok": True, "status": "healthy", "data": data}
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"FigMirror service not reachable at {self.base_url}. "
                f"Start it via: git clone https://github.com/VILA-Lab/FigMirror.git && "
                f"cd FigMirror && python -m figmirror.server --port 8766. "
                f"Error: {e}"
            )
        except Exception as e:
            raise ConnectionError(
                f"FigMirror health check failed: {e}. "
                f"Ensure FigMirror is running at {self.base_url}."
            )

    def generate_chart(
        self,
        data: List[Dict[str, Any]],
        chart_type: str = "bar",
        style: str = "scientific",
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a publication-quality chart via FigMirror.

        Args:
            data: List of data points (e.g., [{"x": "A", "y": 10}, ...])
            chart_type: Chart type (bar, line, scatter, pie, heatmap)
            style: Visual style (scientific, minimal, dark, light)
            title: Optional chart title
            x_label: Optional x-axis label
            y_label: Optional y-axis label

        Returns: {"ok": True, "image_path": "...", "image_base64": "..."}
        Raises: ConnectionError if service is down.
        """
        payload = {
            "data": data,
            "chart_type": chart_type,
            "style": style,
        }
        if title:
            payload["title"] = title
        if x_label:
            payload["x_label"] = x_label
        if y_label:
            payload["y_label"] = y_label

        try:
            req = urllib.request.Request(
                f"{self.base_url}/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"ok": True, **data}
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"FigMirror generate_chart failed — service not reachable at {self.base_url}. "
                f"Start it via: python -m figmirror.server --port 8766. Error: {e}"
            )
        except Exception as e:
            raise ConnectionError(
                f"FigMirror generate_chart failed: {e}. "
                f"Ensure FigMirror is running at {self.base_url}."
            )

    def is_available(self) -> bool:
        """Check if FigMirror is available (non-raising version)."""
        try:
            self.health_check()
            return True
        except ConnectionError:
            return False
