import sys
import os
import types
import pytest

# Setup pathing
_conftest_dir = os.path.dirname(os.path.abspath(__file__))
_sidecar_root = os.path.dirname(_conftest_dir)
if _sidecar_root not in sys.path:
    sys.path.insert(0, _sidecar_root)
if os.path.join(_sidecar_root, "sidecar") not in sys.path:
    sys.path.insert(0, os.path.join(_sidecar_root, "sidecar"))

# Cross-platform: stub win32com on non-Windows so patch("win32com.client...") works.
# The tests already mock all win32com interactions — this just makes the module importable.
if sys.platform != "win32" and "win32com" not in sys.modules:
    _win32com = types.ModuleType("win32com")
    _win32com_client = types.ModuleType("win32com.client")
    _win32com_client.GetActiveObject = lambda *a, **kw: None
    _win32com_client.GetObject = lambda *a, **kw: None
    _win32com.client = _win32com_client
    sys.modules["win32com"] = _win32com
    sys.modules["win32com.client"] = _win32com_client

# Cross-platform: stub os.startfile on non-Windows so patch("os.startfile") works.
if sys.platform != "win32" and not hasattr(os, "startfile"):
    os.startfile = lambda *a, **kw: None

# Cross-platform: stub pythoncom on non-Windows so patch("pythoncom.CoInitialize") works.
if sys.platform != "win32" and "pythoncom" not in sys.modules:
    _pythoncom = types.ModuleType("pythoncom")
    _pythoncom.CoInitialize = lambda *a, **kw: None
    _pythoncom.CoUninitialize = lambda *a, **kw: None
    sys.modules["pythoncom"] = _pythoncom


def pytest_runtest_setup(item):
    # Enforce no skipped or xfailed tests at runtime via markers
    if item.get_closest_marker("skip"):
        pytest.fail("Skipped tests are strictly forbidden!", pytrace=False)
    if item.get_closest_marker("skipif"):
        pytest.fail("Conditional skipped tests (skipif) are strictly forbidden!", pytrace=False)
    if item.get_closest_marker("xfail"):
        pytest.fail("Xfailed tests are strictly forbidden!", pytrace=False)


def pytest_runtest_logreport(report):
    # Enforce no dynamic runtime skips or xfails
    if report.outcome == "skipped":
        raise pytest.UsageError(f"Skipped tests are strictly forbidden at runtime: {report.nodeid}")
    if hasattr(report, "wasxfail"):
        raise pytest.UsageError(f"Xfailed tests are strictly forbidden at runtime: {report.nodeid}")


@pytest.fixture
def anyio_backend():
    return "asyncio"
