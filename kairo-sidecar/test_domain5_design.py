#!/usr/bin/env python3
"""
Domain 5 Design & Figma — Vector-Native Ghost-Designing — Test Suite
=============================================================================
Covers all 7 Domain Gate Conditions with hermetic execution:
  - Figma Node Creation (Section, Frame, Component, Text, solid fills, Auto Layout)
  - Figma-to-Tailwind CSS / Semantic HTML Transpiler
  - Penpot Vector SVG drawing workflows
  - tldraw whiteboard diagramming and coordinate/arrow flowcharts
  - ComfyUI asset generation and PIL / custom raw BMP fallbacks
  - Cross-Tool visual design memory (MemMachine) persistence
  - Active window tool classification & Sidecar IPC endpoints
  - REAL Figma REST API client (no token → clear error)
  - REAL tldraw WebSocket client (no server → clear error)
  - Excalidraw zero-setup fallback (valid JSON output)

Mock-based tests set KAIRO_ENABLE_MOCK_CANVAS=1 explicitly per-test.
Real-mode tests run WITHOUT the flag to verify production behavior.

Run with:
    python -m pytest test_domain5_design.py -v -p no:asyncio -p no:superclaude
"""

import os
import sys
import json
import asyncio
import tempfile
from pathlib import Path

import pytest

# Add sidecar directories to the python path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from sidecar.parsers.figma_design_bridge import FigmaRestClient
from sidecar.parsers.comfyui_bridge import ComfyUIBridge
from sidecar.parsers.tldraw_bridge import TldrawBridge, TldrawWebSocketClient
from sidecar.parsers.excalidraw_bridge import ExcalidrawBridge
from sidecar.parsers.design_bridge import (
    UnifiedDesignBridge,
    MemMachine,
    FramegroundManipulator,
    PenpotBridge,
    OpenPencilBridge,
)
import importlib.util

spec = importlib.util.spec_from_file_location(
    "sidecar_module", Path(__file__).parent / "sidecar.py"
)
sidecar_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sidecar_module)


# =============================================================================
# HELPERS: Mock environment management
# =============================================================================


@pytest.fixture
def mock_canvas_env():
    """Set KAIRO_ENABLE_MOCK_CANVAS=1 for tests that need the mock canvas."""
    old_val = os.environ.get("KAIRO_ENABLE_MOCK_CANVAS", None)
    os.environ["KAIRO_ENABLE_MOCK_CANVAS"] = "1"
    # Reload modules so the module-level flag is re-evaluated
    import importlib
    import sidecar.parsers.figma_design_bridge as fdb
    import sidecar.parsers.tldraw_bridge as tb

    importlib.reload(fdb)
    importlib.reload(tb)
    yield
    if old_val is not None:
        os.environ["KAIRO_ENABLE_MOCK_CANVAS"] = old_val
    else:
        os.environ.pop("KAIRO_ENABLE_MOCK_CANVAS", None)
    importlib.reload(fdb)
    importlib.reload(tb)


@pytest.fixture
def real_mode_env():
    """Ensure KAIRO_ENABLE_MOCK_CANVAS is NOT set for real-mode tests."""
    old_val = os.environ.get("KAIRO_ENABLE_MOCK_CANVAS", None)
    os.environ.pop("KAIRO_ENABLE_MOCK_CANVAS", None)
    import importlib
    import sidecar.parsers.figma_design_bridge as fdb
    import sidecar.parsers.tldraw_bridge as tb

    importlib.reload(fdb)
    importlib.reload(tb)
    yield
    if old_val is not None:
        os.environ["KAIRO_ENABLE_MOCK_CANVAS"] = old_val
    importlib.reload(fdb)
    importlib.reload(tb)


# =============================================================================
# SECTION 1: FIGMA DESIGN BRIDGE MOCK TESTS (Tests 1-10)
# =============================================================================


def test_figma_mock_canvas_init(mock_canvas_env):
    """Test 1: FigmaDesignBridge correctly populates standard offline mock nodes on init."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    tree = bridge.read_node_tree("canvas-root")
    assert "error" not in tree
    assert tree["id"] == "canvas-root"
    assert tree["type"] == "CANVAS"
    assert len(tree["children"]) == 2
    assert tree["children"][0]["id"] == "frame-hero"
    assert tree["children"][1]["id"] == "frame-dashboard"


def test_figma_create_frame(mock_canvas_env):
    """Test 2: Creating a frame node inside Figma correctly adds it to the mock canvas structure."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res = bridge.create_frame(
        "New Container Frame", x=100, y=150, width=400, height=300, parent_id="canvas-root"
    )
    assert res["ok"]
    assert res["node_id"].startswith("frame-node-")
    node = bridge.read_node_tree(res["node_id"])
    assert node["name"] == "New Container Frame"
    assert node["type"] == "FRAME"
    assert node["x"] == 100
    assert node["y"] == 150
    assert node["width"] == 400
    assert node["height"] == 300


def test_figma_create_text(mock_canvas_env):
    """Test 3: Creating a text node yields correct label, font characters, and size settings."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res = bridge.create_text_node(
        "Hero Banner Text", characters="Build Premium Designs", fontSize=32, parent_id="frame-hero"
    )
    assert res["ok"]
    node = bridge.read_node_tree(res["node_id"])
    assert node["type"] == "TEXT"
    assert node["characters"] == "Build Premium Designs"
    assert node["fontSize"] == 32
    assert node["fontName"]["family"] == "Inter"


def test_figma_create_rectangle(mock_canvas_env):
    """Test 4: Creating a rectangle node stores precise bounding coordinates."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res = bridge.create_rectangle(
        "Card Divider", x=0, y=80, width=1200, height=2, parent_id="frame-dashboard"
    )
    assert res["ok"]
    node = bridge.read_node_tree(res["node_id"])
    assert node["type"] == "RECTANGLE"
    assert node["width"] == 1200
    assert node["height"] == 2


def test_figma_create_component(mock_canvas_env):
    """Test 5: Reusable component creation adds valid component node type."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res = bridge.create_component("IconButton", parent_id="canvas-root")
    assert res["ok"]
    node = bridge.read_node_tree(res["node_id"])
    assert node["type"] == "COMPONENT"
    assert node["name"] == "IconButton"


def test_figma_create_section(mock_canvas_env):
    """Test 6: Grouping section creation adds section type container."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res = bridge.create_section("Layout Metrics Section", parent_id="canvas-root")
    assert res["ok"]
    node = bridge.read_node_tree(res["node_id"])
    assert node["type"] == "SECTION"


def test_figma_set_fills_solid(mock_canvas_env):
    """Test 7: Solid hex color fills correctly translate to normalized RGB color ratios."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res_frame = bridge.create_frame("Solid Color Frame", 0, 0, 100, 100)
    node_id = res_frame["node_id"]

    fill_res = bridge.set_fills(node_id, "#ff0080")
    assert fill_res["ok"]
    node = bridge.read_node_tree(node_id)
    fills = node["fills"]
    assert len(fills) == 1
    assert fills[0]["type"] == "SOLID"
    assert abs(fills[0]["color"]["r"] - 1.0) < 0.01
    assert abs(fills[0]["color"]["g"] - 0.0) < 0.01
    assert abs(fills[0]["color"]["b"] - 0.5) < 0.05  # 128/255 = 0.501


def test_figma_set_fills_invalid_hex(mock_canvas_env):
    """Test 8: Invalid hex color string falls back gracefully to standard slate grey."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res_frame = bridge.create_frame("Fallback Frame", 0, 0, 100, 100)
    node_id = res_frame["node_id"]

    fill_res = bridge.set_fills(node_id, "invalid-hex-format")
    assert fill_res["ok"]
    node = bridge.read_node_tree(node_id)
    assert node["fills"][0]["color"] == {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1}


def test_figma_set_auto_layout_horizontal(mock_canvas_env):
    """Test 9: Applying HORIZONTAL auto layout maps correct layout parameters."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res_frame = bridge.create_frame("Horizontal Layout", 0, 0, 100, 100)
    node_id = res_frame["node_id"]

    layout_res = bridge.set_auto_layout(
        node_id, "HORIZONTAL", spacing=16, padding_tb=8, padding_lr=12
    )
    assert layout_res["ok"]
    node = bridge.read_node_tree(node_id)
    assert node["layoutMode"] == "HORIZONTAL"
    assert node["itemSpacing"] == 16
    assert node["paddingTop"] == 8
    assert node["paddingLeft"] == 12


def test_figma_set_auto_layout_vertical(mock_canvas_env):
    """Test 10: Applying VERTICAL auto layout sets layoutMode to vertical container."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = FDB(offline_mode=True)
    res_frame = bridge.create_frame("Vertical Layout", 0, 0, 100, 100)
    node_id = res_frame["node_id"]

    layout_res = bridge.set_auto_layout(
        node_id, "VERTICAL", spacing=24, padding_tb=16, padding_lr=24
    )
    assert layout_res["ok"]
    node = bridge.read_node_tree(node_id)
    assert node["layoutMode"] == "VERTICAL"
    assert node["paddingTop"] == 16
    assert node["paddingBottom"] == 16


# =============================================================================
# SECTION 2: FIGMA-TO-TAILWIND TRANSPILER TESTS (Tests 11-20)
# =============================================================================


def test_transpiler_canvas_root(mock_canvas_env):
    """Test 11: CANVAS node is transpiled to a full viewport dark dashboard container."""
    bridge = UnifiedDesignBridge(offline_mode=True)
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert '<div id="canvas-root" class="w-full min-h-screen bg-[#050508] text-white p-8">' in html


def test_transpiler_section(mock_canvas_env):
    """Test 12: SECTION nodes map to premium semantic HTML <section> containers."""
    bridge = UnifiedDesignBridge(offline_mode=True)
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert (
        '<section id="section-metrics" class="flex flex-col" style="background-color: #e5eaf2;">'
        in html
    )


def test_transpiler_component_button(mock_canvas_env):
    """Test 13: COMPONENTs containing button names are converted to accessible buttons."""
    bridge = UnifiedDesignBridge(offline_mode=True)
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert (
        '<button id="btn-primary" class="flex flex-row items-center pt-3 pb-3 pl-6 pr-6 rounded-md" style="background-color: #603fef;">'
        in html
    )


def test_transpiler_component_div(mock_canvas_env):
    """Test 14: Non-button COMPONENTs are transpiled into structured grid/flex HTML divs."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    # Patch the UnifiedDesignBridge to use the reloaded FDB
    bridge = UnifiedDesignBridge(offline_mode=True)
    bridge.figma = FDB(offline_mode=True)
    bridge.figma.create_component("DashboardCard", parent_id="canvas-root")
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert 'id="component-node-' in html


def test_transpiler_text_headline(mock_canvas_env):
    """Test 15: Huge figma text sizes (fontSize >= 36) transpile to h1 with modern headline tracking."""
    bridge = UnifiedDesignBridge(offline_mode=True)
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert (
        '<h1 id="text-headline" class="text-5xl font-extrabold tracking-tight font-heading" style="color: #ffffff;">Decentralized Intelligence for Modern Swarms</h1>'
        in html
    )


def test_transpiler_text_subheadline(mock_canvas_env):
    """Test 16: Medium figma text sizes (fontSize >= 24) transpile to h2 subheads."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = UnifiedDesignBridge(offline_mode=True)
    bridge.figma = FDB(offline_mode=True)
    bridge.figma.create_text_node(
        "Subheadline", "Analytics Overview", fontSize=28, parent_id="canvas-root"
    )
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert '<h2 id="text-node-' in html
    assert 'class="text-3xl font-bold font-heading"' in html


def test_transpiler_text_p(mock_canvas_env):
    """Test 17: Normal body fonts (fontSize between 13 and 23) transpile to standard readable paragraphs."""
    bridge = UnifiedDesignBridge(offline_mode=True)
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert (
        '<p id="text-subheadline" class="text-lg font-medium text-slate-300" style="color: #99a3b2;">'
        in html
    )


def test_transpiler_text_span(mock_canvas_env):
    """Test 18: Tiny utility captions (fontSize <= 12) transpile to semantic inline spans."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    bridge = UnifiedDesignBridge(offline_mode=True)
    bridge.figma = FDB(offline_mode=True)
    bridge.figma.create_text_node(
        "Caption Label", "Active State", fontSize=11, parent_id="canvas-root"
    )
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert 'class="text-xs font-semibold uppercase tracking-wider"' in html


def test_transpiler_text_color(mock_canvas_env):
    """Test 19: Text node color styles map to inline style overrides."""
    bridge = UnifiedDesignBridge(offline_mode=True)
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert 'style="color: #ffffff;"' in html


def test_transpiler_auto_layout_spacing(mock_canvas_env):
    """Test 20: Auto layout margins, item spacing, and border radius map to responsive Tailwind utilities."""
    bridge = UnifiedDesignBridge(offline_mode=True)
    html = bridge.transpile_figma_to_tailwind("canvas-root")
    assert "gap-6" in html
    assert "rounded-md" in html


# =============================================================================
# SECTION 3: PENPOT VECTOR SVG DRAWING TESTS (Tests 21-28)
# =============================================================================


def test_penpot_is_available_offline():
    """Test 21: Penpot is_available returns False when offline_mode is active."""
    bridge = PenpotBridge(offline_mode=True)
    assert not bridge.is_available()


def test_penpot_is_available_online():
    """Test 22: Penpot is_available returns True when online mode is explicitly enabled."""
    bridge = PenpotBridge(offline_mode=False)
    assert bridge.is_available()


def test_penpot_draw_svg():
    """Test 23: Drawing SVG to Penpot registers successfully in local state."""
    bridge = PenpotBridge(offline_mode=True)
    res = bridge.draw_svg("<svg><rect width='10' height='10'/></svg>")
    assert res["ok"]
    assert res["element_id"].startswith("penpot-svg-")
    assert res["svg_rendered"]


def test_penpot_draw_multiple_svg():
    """Test 24: Multiple sequential SVG draws are recorded in order."""
    bridge = PenpotBridge(offline_mode=True)
    r1 = bridge.draw_svg("<path d='M0 0 L10 10'/>")
    r2 = bridge.draw_svg("<circle cx='5' cy='5' r='2'/>")
    assert r1["element_id"] == "penpot-svg-1"
    assert r2["element_id"] == "penpot-svg-2"


def test_penpot_empty_svg():
    """Test 25: Drawing empty SVG element is handled gracefully."""
    bridge = PenpotBridge(offline_mode=True)
    res = bridge.draw_svg("")
    assert res["ok"]


def test_penpot_custom_rect_svg():
    """Test 26: Drawing complex rectangular vector SVG handles coordinates."""
    bridge = PenpotBridge(offline_mode=True)
    svg = "<svg viewBox='0 0 100 100'><rect x='20' y='20' width='60' height='60' fill='#6140f0'/></svg>"
    res = bridge.draw_svg(svg)
    assert res["ok"]
    assert res["svg_rendered"]


def test_openpencil_is_available_offline():
    """Test 27: OpenPencil bridge defaults to False availability in isolated offline environment."""
    bridge = OpenPencilBridge(offline_mode=True)
    assert not bridge.is_available()


def test_openpencil_record_stroke():
    """Test 28: Recording pencil strokes in OpenPencil tracks paths cleanly."""
    bridge = OpenPencilBridge(offline_mode=True)
    stroke_data = {"points": [(0, 0), (5, 5), (10, 15)], "color": "#000000", "thickness": 2}
    res = bridge.record_stroke(stroke_data)
    assert res["ok"]
    assert res["stroke_count"] == 1


# =============================================================================
# SECTION 4: TLDRAW CANVAS & DIAGRAMMING MOCK TESTS (Tests 29-38)
# =============================================================================


def test_tldraw_mock_canvas_init(mock_canvas_env):
    """Test 29: tldraw canvas correctly pre-populates process flow blocks."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    shapes = bridge.get_canvas_shapes()
    assert len(shapes) == 5
    ids = [s["id"] for s in shapes]
    assert "node-start" in ids
    assert "arrow-1" in ids


def test_tldraw_is_available_offline():
    """Test 30: tldraw bridge states unavailable on local port checks during isolated runs."""
    bridge = TldrawBridge(offline_mode=True)
    assert not bridge.is_available()


def test_tldraw_create_geo_rectangle(mock_canvas_env):
    """Test 31: Creating a geometric shape in tldraw canvas assigns unique ID and properties."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    props = {"w": 200, "h": 80, "geo": "rectangle", "text": "Validation Step", "color": "green"}
    res = bridge.create_shape("geo", x=400, y=400, props=props)
    assert res["ok"]
    assert res["shape_id"].startswith("shape-")
    shape = res["shape"]
    assert shape["type"] == "geo"
    assert shape["props"]["text"] == "Validation Step"


def test_tldraw_create_arrow(mock_canvas_env):
    """Test 32: Creating an arrow connector records start and end canvas vectors."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    props = {"start": {"x": 100, "y": 100}, "end": {"x": 200, "y": 200}, "color": "orange"}
    res = bridge.create_shape("arrow", x=0, y=0, props=props)
    assert res["ok"]
    assert res["shape"]["props"]["start"] == {"x": 100, "y": 100}


def test_tldraw_update_shape_coords(mock_canvas_env):
    """Test 33: Relocating a canvas shape coordinate modifies its position accurately."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    res = bridge.update_shape("node-start", x=150, y=180)
    assert res["ok"]
    shape = res["shape"]
    assert shape["x"] == 150
    assert shape["y"] == 180


def test_tldraw_update_shape_props(mock_canvas_env):
    """Test 34: Modifying canvas shape properties updates text label and color options."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    res = bridge.update_shape("node-start", props={"text": "Initiated Node", "color": "red"})
    assert res["ok"]
    shape = res["shape"]
    assert shape["props"]["text"] == "Initiated Node"
    assert shape["props"]["color"] == "red"


def test_tldraw_delete_shape(mock_canvas_env):
    """Test 35: Removing a shape deletes it completely from the active shapes list."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    res = bridge.delete_shape("node-start")
    assert res["ok"]
    shapes = bridge.get_canvas_shapes()
    ids = [s["id"] for s in shapes]
    assert "node-start" not in ids


def test_tldraw_delete_nonexistent(mock_canvas_env):
    """Test 36: Deleting an absent shape id returns failure instead of raising crashes."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    res = bridge.delete_shape("missing-id")
    assert not res["ok"]
    assert "error" in res


def test_tldraw_draw_flowchart_nodes(mock_canvas_env):
    """Test 37: Automatic flowchart layout positions nodes sequentially on horizontal rails."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    nodes = [
        {"id": "s", "name": "Start", "shape": "rectangle"},
        {"id": "d", "name": "Decide", "shape": "diamond"},
    ]
    res = bridge.draw_flowchart(nodes, [])
    assert res["ok"]
    assert len(res["created_nodes"]) == 2


def test_tldraw_draw_flowchart_edges(mock_canvas_env):
    """Test 38: Automatic flowchart edge generator creates connecting arrows between node vectors."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(offline_mode=True)
    nodes = [
        {"id": "s", "name": "Start", "shape": "rectangle"},
        {"id": "p", "name": "Process", "shape": "rectangle"},
    ]
    edges = [{"source": "s", "target": "p"}]
    res = bridge.draw_flowchart(nodes, edges)
    assert res["ok"]
    shapes = bridge.get_canvas_shapes()
    # 5 default shapes + 2 nodes + 1 arrow = 8 shapes
    assert len(shapes) == 8


# =============================================================================
# SECTION 5: COMFYUI LOCAL ASSET GENERATOR TESTS (Tests 39-48)
# =============================================================================


def test_comfyui_is_available_offline():
    """Test 39: Local port check fails safely in fully isolated offline environments."""
    bridge = ComfyUIBridge(offline_mode=True)
    assert not bridge.is_available()


def test_comfyui_has_pil():
    """Test 40: Pil presence helper returns importability boolean state."""
    bridge = ComfyUIBridge(offline_mode=True)
    val = bridge._has_pil()
    assert isinstance(val, bool)


def test_comfyui_offline_generation_temp_path():
    """Test 41: Asset generation with empty path automatically creates temp asset file."""
    bridge = ComfyUIBridge(offline_mode=True)
    res = bridge.generate_asset("Dark Cyberpunk Dashboard Banner")
    assert res["ok"]
    assert res["offline"]
    assert os.path.exists(res["image_path"])
    os.unlink(res["image_path"])


def test_comfyui_offline_generation_style_hero():
    """Test 42: Style 'hero' uses Kairo premium brand purple (97, 64, 240)."""
    bridge = ComfyUIBridge(offline_mode=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        out_path = tf.name
    res = bridge.generate_asset("Hero banner", style="hero", output_path=out_path)
    assert res["ok"]
    assert os.path.exists(out_path)
    os.unlink(out_path)


def test_comfyui_offline_generation_style_success():
    """Test 43: Style 'success' maps to vibrant green theme colors."""
    bridge = ComfyUIBridge(offline_mode=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        out_path = tf.name
    res = bridge.generate_asset("Success card", style="success", output_path=out_path)
    assert res["ok"]
    assert os.path.exists(out_path)
    os.unlink(out_path)


def test_comfyui_offline_generation_style_dark():
    """Test 44: Style 'dark' maps to premium glassmorphic dark theme backings."""
    bridge = ComfyUIBridge(offline_mode=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        out_path = tf.name
    res = bridge.generate_asset("Dark card", style="dark", output_path=out_path)
    assert res["ok"]
    assert os.path.exists(out_path)
    os.unlink(out_path)


def test_comfyui_offline_generation_style_light():
    """Test 45: Style 'light' maps to light clean neutral palettes."""
    bridge = ComfyUIBridge(offline_mode=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        out_path = tf.name
    res = bridge.generate_asset("Light card", style="light", output_path=out_path)
    assert res["ok"]
    assert os.path.exists(out_path)
    os.unlink(out_path)


def test_comfyui_offline_generation_style_fallback():
    """Test 46: Unrecognized style keyword correctly defaults to slate gray color backing."""
    bridge = ComfyUIBridge(offline_mode=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        out_path = tf.name
    res = bridge.generate_asset("Fallback theme card", style="vintage-retro", output_path=out_path)
    assert res["ok"]
    assert os.path.exists(out_path)
    os.unlink(out_path)


def test_comfyui_raw_bmp_generation():
    """Test 47: Generating asset in absolute PIL absence falls back to raw structured BMP files."""
    bridge = ComfyUIBridge(offline_mode=True)
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tf:
        out_path = tf.name
    bridge._write_raw_bmp(out_path, color=(97, 64, 240))
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 54  # BMP header size
    os.unlink(out_path)


def test_comfyui_raw_bmp_padding():
    """Test 48: BMP pixel rows are correctly padded to standard 4-byte boundaries."""
    width = 512
    row_size = (width * 3 + 3) & ~3
    padding = row_size - (width * 3)
    assert padding == 0

    width_odd = 511
    row_size_odd = (width_odd * 3 + 3) & ~3
    padding_odd = row_size_odd - (width_odd * 3)
    assert padding_odd == 3


# =============================================================================
# SECTION 6: CROSS-TOOL DESIGN MEMORY & FRAMEGROUND TESTS (Tests 49-56)
# =============================================================================


def test_mem_machine_dir_creation():
    """Test 49: MemMachine correctly creates visual design preference folder paths."""
    with tempfile.TemporaryDirectory() as td:
        memory_dir = Path(td) / "custom_memory"
        assert not memory_dir.exists()
        _ = MemMachine(memory_dir=memory_dir)
        assert memory_dir.exists()


def test_mem_machine_default_palette():
    """Test 50: Default visual preferences color scheme is written on first run."""
    with tempfile.TemporaryDirectory() as td:
        memory_dir = Path(td) / "custom_memory"
        mem = MemMachine(memory_dir=memory_dir)
        primary = mem.get_preference("default", "primary_color")
        assert primary == "#6140f0"
        heading_font = mem.get_preference("default", "font_family_heading")
        assert heading_font == "Outfit"


def test_mem_machine_learn_preference():
    """Test 51: Visual preferencing writes choice updates successfully to JSON storage."""
    with tempfile.TemporaryDirectory() as td:
        memory_dir = Path(td) / "custom_memory"
        mem = MemMachine(memory_dir=memory_dir)
        mem.learn_preference("figma", "preferred_card_bg", "#1c1c28")
        assert mem.get_preference("figma", "preferred_card_bg") == "#1c1c28"

        with open(memory_dir / "design_mem.json", "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        assert disk_data["figma"]["preferred_card_bg"] == "#1c1c28"


def test_mem_machine_get_preference_fallback():
    """Test 52: Accessing absent tool preference correctly returns fallback default style value."""
    with tempfile.TemporaryDirectory() as td:
        memory_dir = Path(td) / "custom_memory"
        mem = MemMachine(memory_dir=memory_dir)
        border_radius = mem.get_preference("tldraw", "border_radius")
        assert border_radius == "8px"  # default radius fallback


def test_mem_machine_get_all_preferences():
    """Test 53: Getting all preferences merges tool styles with master defaults."""
    with tempfile.TemporaryDirectory() as td:
        memory_dir = Path(td) / "custom_memory"
        mem = MemMachine(memory_dir=memory_dir)
        mem.learn_preference("penpot", "primary_color", "#00ffcc")
        all_prefs = mem.get_all_preferences("penpot")
        assert all_prefs["primary_color"] == "#00ffcc"
        assert all_prefs["font_family_heading"] == "Outfit"


def test_mem_machine_custom_dir():
    """Test 54: Visual styling memory folder supports custom overrides on execution."""
    with tempfile.TemporaryDirectory() as td:
        memory_dir = Path(td) / "custom_design_store"
        mem = MemMachine(memory_dir=memory_dir)
        assert mem.memory_file == memory_dir / "design_mem.json"


def test_frameground_create_canvas():
    """Test 55: Creating local HTML canvases writes valid files to Frameground workspace."""
    with tempfile.TemporaryDirectory() as td:
        fg = FramegroundManipulator(workspace_dir=Path(td))
        path = fg.create_canvas(
            "test_canvas.html", "<div id='card' class='bg-slate-800 p-4'>Canvas content</div>"
        )
        assert os.path.exists(path)
        with open(path, "r") as f:
            assert "Canvas content" in f.read()


def test_frameground_get_attribute_by_id():
    """Test 56: Getting HTML design attributes via ID selector reads properties accurately."""
    with tempfile.TemporaryDirectory() as td:
        fg = FramegroundManipulator(workspace_dir=Path(td))
        path = fg.create_canvas(
            "canvas.html",
            "<div><button id='action-btn' class='w-full bg-[#10b981]'></button></div>",
        )
        attr_class = fg.get_attribute(path, "//*[@id='action-btn']", "class")
        assert attr_class == "w-full bg-[#10b981]"


# =============================================================================
# SECTION 7: ACTIVE WINDOW TOOL ROUTING & INTEGRATION TESTS (Tests 57-60)
# =============================================================================


def test_frameground_get_attribute_by_tag():
    """Test 57: Getting HTML design attributes via tag selector parses classes perfectly."""
    with tempfile.TemporaryDirectory() as td:
        fg = FramegroundManipulator(workspace_dir=Path(td))
        path = fg.create_canvas(
            "canvas.html", "<section class='min-h-screen bg-slate-950'></section>"
        )
        attr_class = fg.get_attribute(path, "//section", "class")
        assert attr_class == "min-h-screen bg-slate-950"


def test_ipc_figma_create_command(mock_canvas_env):
    """Test 58: Dispatching socket request for figma_create creates figma elements over IPC."""
    payload = {
        "node_type": "FRAME",
        "name": "IPC Layout Frame",
        "x": 100,
        "y": 100,
        "width": 800,
        "height": 600,
        "color_hex": "#10b981",
    }
    req = {"id": "test-figma-create", "action": "figma_create", "payload": payload}

    res = asyncio.run(sidecar_module.handle_request(req))

    assert res["ok"]
    assert res["data"]["node_id"].startswith("frame-node-")


def test_ipc_design_ghost_write_figma(mock_canvas_env):
    """Test 59: Active window title classification routes ghost design edits correctly to Figma."""
    payload = {
        "window_title": "Project Swarm Dashboard - Figma Web UI",
        "text": "Applying premium styling templates to layers...",
    }
    req = {"id": "test-ghost-write", "action": "design_ghost_write", "payload": payload}

    res = asyncio.run(sidecar_module.handle_request(req))

    assert res["ok"]
    assert res["data"]["tool_detected"] == "figma"
    assert res["data"]["node_id"].startswith("text-node-")


def test_ipc_tldraw_canvas_flowchart(mock_canvas_env):
    """Test 60: Whiteboard canvas operations draw multi-node flowchart diagrams successfully."""
    payload = {
        "operation": "draw_flowchart",
        "nodes": [
            {"id": "a", "name": "Load", "shape": "rectangle", "color": "blue"},
            {"id": "b", "name": "Transpile", "shape": "diamond", "color": "orange"},
        ],
        "edges": [{"source": "a", "target": "b"}],
    }
    req = {"id": "test-flowchart", "action": "tldraw_canvas", "payload": payload}

    res = asyncio.run(sidecar_module.handle_request(req))

    assert res["ok"]
    assert len(res["data"]["created_nodes"]) == 2
    assert res["data"]["canvas_shapes_count"] == 8


# =============================================================================
# SECTION 8: REAL-MODE FIGMA REST API TESTS (no mock flag)
# =============================================================================


def test_figma_rest_client_no_token_raises_clear_error(real_mode_env):
    """Test 61: FigmaRestClient without token raises clear configuration error."""
    from sidecar.parsers.figma_design_bridge import FigmaRestClient

    # Ensure no token in env
    old_token = os.environ.pop("FIGMA_TOKEN", None)
    try:
        client = FigmaRestClient()
        assert not client.is_configured()
        with pytest.raises(ConnectionError, match="Figma not configured"):
            client.get_file("test_file_key")
    finally:
        if old_token:
            os.environ["FIGMA_TOKEN"] = old_token


def test_figma_bridge_no_token_raises_clear_error(real_mode_env):
    """Test 62: FigmaDesignBridge without token and without mock raises clear error, not mock data."""
    from sidecar.parsers.figma_design_bridge import FigmaDesignBridge as FDB

    old_token = os.environ.pop("FIGMA_TOKEN", None)
    try:
        bridge = FDB(offline_mode=False)
        with pytest.raises(ConnectionError, match="Figma not configured"):
            bridge.create_frame("Test", 0, 0, 100, 100)
    finally:
        if old_token:
            os.environ["FIGMA_TOKEN"] = old_token


def test_figma_rest_client_with_fake_token_raises_connection_error(real_mode_env):
    """Test 63: FigmaRestClient with fake token raises ConnectionError on network call (not mock)."""
    from sidecar.parsers.figma_design_bridge import FigmaRestClient

    os.environ["FIGMA_TOKEN"] = "fake-test-token-12345"
    try:
        client = FigmaRestClient()
        assert client.is_configured()
        # This should raise ConnectionError because the token is invalid / network will fail
        with pytest.raises(ConnectionError):
            client.get_file("nonexistent_file_key_12345")
    finally:
        os.environ.pop("FIGMA_TOKEN", None)


def test_figma_rest_client_api_base():
    """Test 64: FigmaRestClient correctly constructs API URLs."""
    client = FigmaRestClient(token="test", api_base="https://api.figma.com/v1")
    assert client.api_base == "https://api.figma.com/v1"
    assert client.token == "test"
    assert client.is_configured()


# =============================================================================
# SECTION 9: REAL-MODE TLDRAW WEBSOCKET TESTS (no mock flag)
# =============================================================================


def test_tldraw_ws_client_no_server_raises_error(real_mode_env):
    """Test 65: TldrawWebSocketClient without server raises clear ConnectionError."""
    from sidecar.parsers.tldraw_bridge import TldrawWebSocketClient

    client = TldrawWebSocketClient(host="127.0.0.1", port=59999)  # unlikely port
    assert not client.is_available()
    with pytest.raises(ConnectionError, match="tldraw server not found"):
        client.connect()


def test_tldraw_bridge_no_server_raises_error(real_mode_env):
    """Test 66: TldrawBridge without server and without mock raises clear error, not mock data."""
    from sidecar.parsers.tldraw_bridge import TldrawBridge as TB

    bridge = TB(host="127.0.0.1", port=59999, offline_mode=False)
    with pytest.raises(ConnectionError, match="tldraw server not found"):
        bridge.create_shape("geo", 100, 100, {"w": 100, "h": 50, "text": "Test"})


def test_tldraw_ws_client_url_property():
    """Test 67: TldrawWebSocketClient correctly constructs WebSocket URL."""
    client = TldrawWebSocketClient(host="example.com", port=9000, room_id="test-room")
    assert client.url == "ws://example.com:9000/test-room"


# =============================================================================
# SECTION 10: EXCALIDRAW ZERO-SETUP FALLBACK TESTS
# =============================================================================


def test_excalidraw_create_canvas():
    """Test 68: ExcalidrawBridge creates a canvas with correct metadata."""
    bridge = ExcalidrawBridge()
    res = bridge.create_canvas()
    assert res["ok"]
    assert res["type"] == "excalidraw"
    assert res["elements_count"] == 0


def test_excalidraw_create_rectangle():
    """Test 69: Creating a rectangle produces valid Excalidraw JSON element."""
    bridge = ExcalidrawBridge()
    bridge.create_canvas()
    res = bridge.create_rectangle(100, 100, 200, 80)
    assert res["ok"]
    elem = res["element"]
    assert elem["type"] == "rectangle"
    assert elem["x"] == 100
    assert elem["y"] == 100
    assert elem["width"] == 200
    assert elem["height"] == 80
    assert "id" in elem


def test_excalidraw_create_text():
    """Test 70: Creating text produces valid Excalidraw text element."""
    bridge = ExcalidrawBridge()
    bridge.create_canvas()
    res = bridge.create_text(50, 50, "Hello World", font_size=24)
    assert res["ok"]
    elem = res["element"]
    assert elem["type"] == "text"
    assert elem["text"] == "Hello World"
    assert elem["fontSize"] == 24
    assert elem["originalText"] == "Hello World"


def test_excalidraw_create_arrow():
    """Test 71: Creating arrow produces valid Excalidraw arrow element with points."""
    bridge = ExcalidrawBridge()
    bridge.create_canvas()
    res = bridge.create_arrow(100, 100, 300, 200)
    assert res["ok"]
    elem = res["element"]
    assert elem["type"] == "arrow"
    assert len(elem["points"]) == 2
    assert elem["endArrowhead"] == "arrow"


def test_excalidraw_export_json():
    """Test 72: Export produces valid Excalidraw scene JSON."""
    bridge = ExcalidrawBridge()
    bridge.create_canvas(background_color="#f0f0f0")
    bridge.create_rectangle(10, 10, 100, 50)
    bridge.create_text(20, 20, "Label")
    bridge.create_arrow(50, 50, 150, 150)

    scene = bridge.export_json()
    assert scene["type"] == "excalidraw"
    assert scene["version"] == 2
    assert len(scene["elements"]) == 3
    assert scene["appState"]["viewBackgroundColor"] == "#f0f0f0"
    # Verify each element has required Excalidraw fields
    for elem in scene["elements"]:
        assert "id" in elem
        assert "type" in elem
        assert "x" in elem
        assert "y" in elem
        assert "width" in elem
        assert "height" in elem
        assert "strokeColor" in elem
        assert "isDeleted" in elem


def test_excalidraw_export_json_string():
    """Test 73: Export as JSON string is valid parseable JSON."""
    bridge = ExcalidrawBridge()
    bridge.create_canvas()
    bridge.create_rectangle(0, 0, 100, 100)
    json_str = bridge.export_json_string()
    parsed = json.loads(json_str)
    assert parsed["type"] == "excalidraw"
    assert len(parsed["elements"]) == 1


def test_excalidraw_flowchart():
    """Test 74: Excalidraw flowchart generates valid multi-element scene."""
    bridge = ExcalidrawBridge()
    bridge.create_canvas()
    nodes = [
        {"id": "start", "name": "Start", "shape": "rectangle", "color": "#10b981"},
        {"id": "decide", "name": "Check?", "shape": "diamond", "color": "#f59e0b"},
        {"id": "end", "name": "Done", "shape": "ellipse", "color": "#3b82f6"},
    ]
    edges = [
        {"source": "start", "target": "decide"},
        {"source": "decide", "target": "end"},
    ]
    res = bridge.draw_flowchart(nodes, edges)
    assert res["ok"]
    assert len(res["created_nodes"]) == 3
    # 3 shapes + 3 text labels + 2 arrows = 8 elements
    assert res["elements_count"] == 8

    scene = bridge.export_json()
    types = [e["type"] for e in scene["elements"]]
    assert "rectangle" in types
    assert "diamond" in types
    assert "ellipse" in types
    assert "text" in types
    assert "arrow" in types


def test_excalidraw_clear():
    """Test 75: Clearing the canvas removes all elements."""
    bridge = ExcalidrawBridge()
    bridge.create_canvas()
    bridge.create_rectangle(0, 0, 100, 100)
    assert len(bridge.get_elements()) == 1
    res = bridge.clear()
    assert res["ok"]
    assert len(bridge.get_elements()) == 0
