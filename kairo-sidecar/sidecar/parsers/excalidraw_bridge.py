"""Excalidraw Bridge for Kairo Domain 5.

Zero-setup design canvas using Excalidraw's simple JSON format.
No API key, no server needed — all operations generate valid Excalidraw
JSON elements that can be imported into any Excalidraw instance.

This provides a zero-configuration fallback for users who don't have
Figma or tldraw set up.
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

log = logging.getLogger("kairo-sidecar.excalidraw_bridge")


class ExcalidrawBridge:
    """Zero-setup Excalidraw JSON canvas bridge.

    All methods produce valid Excalidraw scene JSON.  No network calls,
    no API keys, no server required.
    """

    def __init__(self):
        self._elements: List[Dict[str, Any]] = []
        self._app_state: Dict[str, Any] = {
            "viewBackgroundColor": "#ffffff",
            "gridSize": None,
        }
        self._version = 2

    def _new_id(self) -> str:
        """Generate a unique element ID."""
        return str(uuid.uuid4())

    def _base_element(
        self, element_type: str, x: float, y: float, width: float, height: float
    ) -> Dict[str, Any]:
        """Create a base Excalidraw element with common properties."""
        return {
            "id": self._new_id(),
            "type": element_type,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "angle": 0,
            "strokeColor": "#1e1e1e",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": None,
            "seed": int(time.time() * 1000) % 1000000,
            "version": 1,
            "versionNonce": int(time.time() * 1000) % 1000000,
            "isDeleted": False,
            "boundElements": [],
            "updated": int(time.time() * 1000),
            "link": None,
            "locked": False,
        }

    def create_canvas(self, background_color: str = "#ffffff") -> Dict[str, Any]:
        """Initialize a new Excalidraw canvas (scene).

        Returns the scene metadata.  Elements are added via the other
        create_* methods.
        """
        self._elements = []
        self._app_state["viewBackgroundColor"] = background_color
        return {
            "ok": True,
            "type": "excalidraw",
            "background": background_color,
            "elements_count": 0,
        }

    def create_rectangle(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        stroke_color: str = "#1e1e1e",
        background_color: str = "transparent",
        fill_style: str = "solid",
        stroke_width: int = 2,
        roundness: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a rectangle element in Excalidraw format."""
        elem = self._base_element("rectangle", x, y, width, height)
        elem["strokeColor"] = stroke_color
        elem["backgroundColor"] = background_color
        elem["fillStyle"] = fill_style
        elem["strokeWidth"] = stroke_width
        if roundness is not None:
            elem["roundness"] = roundness
        self._elements.append(elem)
        log.info(f"Excalidraw rectangle created: {elem['id']} at ({x},{y}) {width}x{height}")
        return {"ok": True, "element_id": elem["id"], "element": elem}

    def create_text(
        self,
        x: float,
        y: float,
        text: str,
        font_size: int = 20,
        font_family: int = 1,
        stroke_color: str = "#1e1e1e",
        text_align: str = "left",
        width: Optional[float] = None,
        height: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create a text element in Excalidraw format.

        font_family: 1=Virgil (hand-drawn), 2=Helvetica, 3=Cascadia
        """
        # Auto-size if not provided
        if width is None:
            width = max(len(text) * font_size * 0.6, 50)
        if height is None:
            height = font_size * 1.5

        elem = self._base_element("text", x, y, width, height)
        elem["strokeColor"] = stroke_color
        elem["backgroundColor"] = "transparent"
        elem["fontSize"] = font_size
        elem["fontFamily"] = font_family
        elem["text"] = text
        elem["textAlign"] = text_align
        elem["verticalAlign"] = "top"
        elem["containerId"] = None
        elem["originalText"] = text
        elem["lineHeight"] = 1.25
        self._elements.append(elem)
        log.info(f"Excalidraw text created: {elem['id']} -> '{text[:30]}'")
        return {"ok": True, "element_id": elem["id"], "element": elem}

    def create_arrow(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        stroke_color: str = "#1e1e1e",
        stroke_width: int = 2,
        start_arrowhead: Optional[str] = None,
        end_arrowhead: str = "arrow",
    ) -> Dict[str, Any]:
        """Create an arrow element in Excalidraw format.

        start_arrowhead/end_arrowhead: None, "arrow", "bar", "dot", "triangle"
        """
        width = abs(end_x - start_x)
        height = abs(end_y - start_y)
        x = min(start_x, end_x)
        y = min(start_y, end_y)

        elem = self._base_element("arrow", x, y, width, height)
        elem["strokeColor"] = stroke_color
        elem["strokeWidth"] = stroke_width
        elem["backgroundColor"] = "transparent"
        elem["points"] = [[start_x - x, start_y - y], [end_x - x, end_y - y]]
        elem["startArrowhead"] = start_arrowhead
        elem["endArrowhead"] = end_arrowhead
        elem["startBinding"] = None
        elem["endBinding"] = None
        elem["lastCommittedPoint"] = None
        self._elements.append(elem)
        log.info(f"Excalidraw arrow created: {elem['id']} ({start_x},{start_y})->({end_x},{end_y})")
        return {"ok": True, "element_id": elem["id"], "element": elem}

    def create_ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        stroke_color: str = "#1e1e1e",
        background_color: str = "transparent",
        fill_style: str = "solid",
        stroke_width: int = 2,
    ) -> Dict[str, Any]:
        """Create an ellipse element in Excalidraw format."""
        elem = self._base_element("ellipse", x, y, width, height)
        elem["strokeColor"] = stroke_color
        elem["backgroundColor"] = background_color
        elem["fillStyle"] = fill_style
        elem["strokeWidth"] = stroke_width
        self._elements.append(elem)
        log.info(f"Excalidraw ellipse created: {elem['id']} at ({x},{y}) {width}x{height}")
        return {"ok": True, "element_id": elem["id"], "element": elem}

    def create_diamond(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        stroke_color: str = "#1e1e1e",
        background_color: str = "transparent",
        fill_style: str = "solid",
        stroke_width: int = 2,
    ) -> Dict[str, Any]:
        """Create a diamond element in Excalidraw format."""
        elem = self._base_element("diamond", x, y, width, height)
        elem["strokeColor"] = stroke_color
        elem["backgroundColor"] = background_color
        elem["fillStyle"] = fill_style
        elem["strokeWidth"] = stroke_width
        self._elements.append(elem)
        log.info(f"Excalidraw diamond created: {elem['id']} at ({x},{y}) {width}x{height}")
        return {"ok": True, "element_id": elem["id"], "element": elem}

    def draw_flowchart(
        self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Draw a flowchart using Excalidraw elements.

        nodes: list of {"id", "name", "shape" ("rectangle"/"diamond"/"ellipse"), "color"}
        edges: list of {"source", "target"}
        """
        created_ids = {}
        start_x = 100.0
        start_y = 100.0
        spacing_x = 250.0

        for idx, n in enumerate(nodes):
            name = n.get("name", f"Step {idx}")
            shape = n.get("shape", "rectangle")
            color = n.get("color", "#6140f0")

            x_pos = start_x + (idx * spacing_x)
            y_pos = start_y
            w = 160.0
            h = 70.0
            if shape == "diamond":
                w = 120.0
                h = 100.0
                y_pos -= 15.0

            if shape == "diamond":
                res = self.create_diamond(
                    x_pos, y_pos, w, h, background_color=color, fill_style="solid"
                )
            elif shape == "ellipse":
                res = self.create_ellipse(
                    x_pos, y_pos, w, h, background_color=color, fill_style="solid"
                )
            else:
                res = self.create_rectangle(
                    x_pos, y_pos, w, h, background_color=color, fill_style="solid"
                )

            # Add text label
            self.create_text(
                x_pos + 10,
                y_pos + h / 2 - 10,
                name,
                font_size=16,
                stroke_color="#ffffff" if color != "transparent" else "#1e1e1e",
            )

            created_ids[n.get("id", str(idx))] = {
                "element_id": res["element_id"],
                "x": x_pos,
                "y": y_pos,
                "w": w,
                "h": h,
            }

        # Draw arrows
        for edge in edges:
            source_key = edge.get("source")
            target_key = edge.get("target")
            if source_key in created_ids and target_key in created_ids:
                s = created_ids[source_key]
                t = created_ids[target_key]
                self.create_arrow(
                    s["x"] + s["w"],
                    s["y"] + s["h"] / 2.0,
                    t["x"],
                    t["y"] + t["h"] / 2.0,
                )

        return {
            "ok": True,
            "created_nodes": [v["element_id"] for v in created_ids.values()],
            "elements_count": len(self._elements),
        }

    def export_json(self) -> Dict[str, Any]:
        """Export the full Excalidraw scene as valid JSON.

        Returns a dict with type="excalidraw", elements, appState, and version.
        This is the standard Excalidraw file format.
        """
        scene = {
            "type": "excalidraw",
            "version": self._version,
            "source": "https://excalidraw.com",
            "elements": self._elements,
            "appState": self._app_state,
            "files": {},
        }
        return scene

    def export_json_string(self) -> str:
        """Export the Excalidraw scene as a JSON string."""
        return json.dumps(self.export_json(), indent=2)

    def get_elements(self) -> List[Dict[str, Any]]:
        """Return all elements in the current scene."""
        return list(self._elements)

    def clear(self) -> Dict[str, Any]:
        """Clear all elements from the canvas."""
        self._elements = []
        return {"ok": True, "elements_count": 0}
