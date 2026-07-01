"""
sidecar/cua/driver_service.py

Thin wrapper around the cua-driver binary (NOT the trycua VM sandbox).

cua-driver is the low-level cross-platform driver from trycua that provides:
    - screenshot: capture screen or region
    - click: mouse click at coordinates
    - type: type text string
    - move: move mouse to coordinates
    - scroll: scroll at position

It requires NO admin privileges and NO Developer Mode.
It is used as a FALLBACK when UIA fails.

Install:
    irm https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1 | iex

Usage:
    svc = CuaDriverService()
    if svc.available:
        screenshot_bytes = svc.screenshot()
        svc.click(100, 200)
        svc.type_text("Hello World")
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("kairo-sidecar.cua.driver_service")


class CuaDriverService:
    """
    Wraps the cua-driver binary for screenshot and action primitives.

    This is the FALLBACK backend when UIA fails and enigo is not available.
    Prefers the cua-driver over raw Win32 for cross-platform consistency.
    """

    # Candidate paths where cua-driver might be installed
    CANDIDATE_PATHS = [
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Cua"
        / "cua-driver"
        / "bin"
        / "cua-driver.exe",
        Path.home() / ".cua" / "bin" / "cua-driver.exe",
        Path("C:/Program Files/cua-driver/cua-driver.exe"),
        Path("C:/ProgramData/cua-driver/cua-driver.exe"),
        Path.home() / ".local" / "bin" / "cua-driver.exe",
    ]

    def __init__(self):
        self.driver_path = self._find_cua_driver()
        self._available = self.driver_path is not None

        if self._available:
            log.info(f"[CuaDriver] Found cua-driver at: {self.driver_path}")
        else:
            log.warning(
                "[CuaDriver] cua-driver not found. "
                "Install with: irm https://raw.githubusercontent.com/trycua/cua/"
                "main/libs/cua-driver/scripts/install.ps1 | iex"
            )

    @property
    def available(self) -> bool:
        """Whether the cua-driver binary is available."""
        return self._available

    # ── Screenshot ─────────────────────────────────────────────────────────────

    def screenshot(self, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[bytes]:
        """
        Capture a screenshot.

        Args:
            region: (x, y, width, height) or None for full screen

        Returns:
            PNG bytes on success, None on failure
        """
        if not self._available:
            return None

        args = [str(self.driver_path), "screenshot"]
        if region:
            args += ["--region", f"{region[0]},{region[1]},{region[2]},{region[3]}"]

        try:
            result = subprocess.run(args, capture_output=True, timeout=3.0)
            if result.returncode == 0:
                return result.stdout  # PNG bytes
            else:
                log.warning(
                    f"[CuaDriver] screenshot failed: {result.stderr.decode('utf-8', errors='replace')}"
                )
                return None
        except subprocess.TimeoutExpired:
            log.error("[CuaDriver] screenshot timed out")
            return None
        except Exception as e:
            log.error(f"[CuaDriver] screenshot error: {e}")
            return None

    def screenshot_to_file(
        self, output_path: str, region: Optional[Tuple[int, int, int, int]] = None
    ) -> bool:
        """
        Capture screenshot to a file.

        Args:
            output_path: Where to save the PNG
            region: (x, y, width, height) or None for full screen

        Returns:
            True on success
        """
        if not self._available:
            return False

        args = [str(self.driver_path), "screenshot", "--output", output_path]
        if region:
            args += ["--region", f"{region[0]},{region[1]},{region[2]},{region[3]}"]

        try:
            result = subprocess.run(args, capture_output=True, timeout=3.0)
            return result.returncode == 0
        except Exception as e:
            log.error(f"[CuaDriver] screenshot_to_file error: {e}")
            return False

    # ── Mouse Actions ──────────────────────────────────────────────────────────

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        dpi_scale: float = 1.0,
    ) -> bool:
        """
        Click at coordinates.

        Args:
            x, y: Logical coordinates (will be scaled by dpi_scale)
            button: "left", "right", or "middle"
            dpi_scale: DPI scaling factor from GetDpiForWindow()

        Returns:
            True on success
        """
        if not self._available:
            return False

        # Scale coordinates for physical display
        scaled_x = int(x * dpi_scale)
        scaled_y = int(y * dpi_scale)

        try:
            result = subprocess.run(
                [
                    str(self.driver_path),
                    "click",
                    str(scaled_x),
                    str(scaled_y),
                    "--button",
                    button,
                ],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if result.returncode != 0:
                log.warning(f"[CuaDriver] click failed: {result.stderr}")
            return result.returncode == 0
        except Exception as e:
            log.error(f"[CuaDriver] click error: {e}")
            return False

    def double_click(self, x: int, y: int, dpi_scale: float = 1.0) -> bool:
        """Double-click at coordinates."""
        return self.click(x, y, dpi_scale=dpi_scale) and (
            time.sleep(0.05) or self.click(x, y, dpi_scale=dpi_scale)  # type: ignore
        )

    def move(self, x: int, y: int, dpi_scale: float = 1.0) -> bool:
        """Move mouse to coordinates without clicking."""
        if not self._available:
            return False

        scaled_x = int(x * dpi_scale)
        scaled_y = int(y * dpi_scale)

        try:
            result = subprocess.run(
                [str(self.driver_path), "move", str(scaled_x), str(scaled_y)],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            return result.returncode == 0
        except Exception as e:
            log.error(f"[CuaDriver] move error: {e}")
            return False

    def scroll(self, x: int, y: int, direction: str, amount: int = 3) -> bool:
        """
        Scroll at position.

        Args:
            x, y: Position to scroll at
            direction: "up", "down", "left", "right"
            amount: Number of scroll steps
        """
        if not self._available:
            return False

        try:
            result = subprocess.run(
                [
                    str(self.driver_path),
                    "scroll",
                    str(x),
                    str(y),
                    "--direction",
                    direction,
                    "--amount",
                    str(amount),
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            return result.returncode == 0
        except Exception as e:
            log.error(f"[CuaDriver] scroll error: {e}")
            return False

    # ── Keyboard Actions ──────────────────────────────────────────────────────

    def type_text(self, text: str) -> bool:
        """
        Type a text string.

        Args:
            text: Unicode text to type

        Returns:
            True on success
        """
        if not self._available:
            return False

        try:
            result = subprocess.run(
                [str(self.driver_path), "type", "--text", text],
                capture_output=True,
                text=True,
                timeout=max(5.0, len(text) * 0.1),  # 100ms per char, min 5s
            )
            if result.returncode != 0:
                log.warning(f"[CuaDriver] type_text failed: {result.stderr}")
            return result.returncode == 0
        except Exception as e:
            log.error(f"[CuaDriver] type_text error: {e}")
            return False

    def key_combo(self, *keys: str) -> bool:
        """
        Press a key combination (e.g., key_combo("ctrl", "a")).

        Args:
            keys: Key names in order (modifiers first, then main key)
        """
        if not self._available:
            return False

        try:
            result = subprocess.run(
                [str(self.driver_path), "key", "--combo", "+".join(keys)],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            return result.returncode == 0
        except Exception as e:
            log.error(f"[CuaDriver] key_combo error: {e}")
            return False

    # ── Discovery ─────────────────────────────────────────────────────────────

    def _find_cua_driver(self) -> Optional[Path]:
        """Find the installed cua-driver binary."""
        # Check hard-coded candidate paths
        for candidate in self.CANDIDATE_PATHS:
            try:
                if candidate.exists():
                    return candidate
            except (OSError, PermissionError):
                continue

        # Check PATH
        try:
            result = subprocess.run(
                ["where", "cua-driver"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if result.returncode == 0:
                first_line = result.stdout.strip().splitlines()[0].strip()
                if first_line:
                    return Path(first_line)
        except Exception:
            pass

        return None

    # ── Version ────────────────────────────────────────────────────────────────

    def version(self) -> Optional[str]:
        """Get cua-driver version string."""
        if not self._available:
            return None

        try:
            result = subprocess.run(
                [str(self.driver_path), "--version"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return None

    # ── Status ─────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Get service status dict (for health checks and debugging)."""
        return {
            "available": self._available,
            "driver_path": str(self.driver_path) if self.driver_path else None,
            "version": self.version() if self._available else None,
        }


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    parser = argparse.ArgumentParser(description="cua-driver service wrapper")
    parser.add_argument("--status", action="store_true", help="Show service status")
    parser.add_argument("--screenshot", type=str, help="Capture screenshot to file")
    parser.add_argument("--click", nargs=2, type=int, metavar=("X", "Y"), help="Click at X Y")
    args = parser.parse_args()

    svc = CuaDriverService()

    if args.status:
        print(json.dumps(svc.status(), indent=2))
    elif args.screenshot:
        success = svc.screenshot_to_file(args.screenshot)
        print(f"Screenshot: {'OK' if success else 'FAILED'}")
        sys.exit(0 if success else 1)
    elif args.click:
        x, y = args.click
        success = svc.click(x, y)
        print(f"Click ({x},{y}): {'OK' if success else 'FAILED'}")
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
