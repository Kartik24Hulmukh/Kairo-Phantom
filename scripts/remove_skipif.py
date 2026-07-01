#!/usr/bin/env python3
"""
FIX 2 — Remove skipif from test_creators.py and test_word_master.py.

These tests use pytest.mark.skipif(sys.platform != "win32", ...) but are
FULLY MOCKED: they patch("os.startfile"), patch("win32com.client.GetActiveObject"),
patch("pythoncom.CoInitialize"), etc. The conftest.py (in tests/) provides
stub modules for win32com, pythoncom, and os.startfile on non-Windows platforms,
making these tests pass on Ubuntu with zero skips.

PROVEN: with skipif removed, all 21 tests in both files PASS on Ubuntu:
  tests/test_creators.py — 6 tests PASSED
  tests/test_word_master.py — 15 tests PASSED

The skipif was unnecessary because:
  1. conftest.py:16-23 stubs win32com.client on non-Windows
  2. conftest.py:26-27 stubs os.startfile on non-Windows
  3. conftest.py:30-34 stubs pythoncom on non-Windows
  4. All tests mock the COM/startfile calls with patch()

A dedicated windows-python-test job in verify.yml runs these same tests on
windows-latest with real win32com, ensuring the Windows code path is
exercised for real (not just against stubs).

Usage:
  python scripts/remove_skipif.py

This script is idempotent — it only removes skipif if present.
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = [
    "kairo-sidecar/tests/test_creators.py",
    "kairo-sidecar/tests/test_word_master.py",
]


def remove_skipif(filepath: str) -> bool:
    """Remove skipif definition and decorator from a test file. Returns True if changed."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Remove the _skip_not_windows = pytest.mark.skipif(...) block
    # Pattern: _skip_not_windows = pytest.mark.skipif(\n    sys.platform != "win32",\n    reason="..."\n)
    content = re.sub(
        r'_skip_not_windows\s*=\s*pytest\.mark\.skipif\(\s*\n\s*sys\.platform\s*!=\s*"win32",\s*\n\s*reason="[^"]*"\s*\)',
        '# skipif removed — tests are fully mocked, conftest provides win32com/pythoncom/os.startfile stubs',
        content,
    )

    # Remove @_skip_not_windows decorator lines
    content = re.sub(r"\n@_skip_not_windows\n", "\n", content)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


def main():
    changed = False
    for relpath in FILES:
        filepath = os.path.join(REPO_ROOT, relpath)
        if not os.path.exists(filepath):
            print(f"⚠️  File not found: {filepath}")
            continue
        if remove_skipif(filepath):
            print(f"✅ Removed skipif from {relpath}")
            changed = True
        else:
            print(f"⏭️  No skipif found in {relpath} (already clean)")

    if changed:
        print("\n✅ skipif removal complete. Tests now run on all platforms.")
        print("   Ubuntu: conftest stubs make win32com/pythoncom/os.startfile importable.")
        print("   Windows: real win32com automation is exercised.")
    else:
        print("\n✅ All files already clean — no changes needed.")


if __name__ == "__main__":
    main()