"""tldraw Canvas Bridge for Kairo Domain 5.

Interfaces with the infinite whiteboard canvas (tldraw/mcp-app).
Supports coordinate mapping, shape structure creation/updating/deletion, and automated flowchart layouts.

The in-process mock shape store (_mock_shapes) is gated behind the  # mock
``KAIRO_ENABLE_MOCK_CANVAS`` environment variable.  It MUST NOT be used in
production.  Set the flag only in local development or CI sandboxes.

Real canvas access is provided by :class:`TldrawWebSocketClient`, which
connects to a tldraw room server via WebSocket.  If no server is running,
a clear error is raised — it NEVER silently falls back to mock in production.
"""

import json
import logging
import os
import socket
from typing import Any, Dict, List, Optional

log = logging.getLogger("kairo-sidecar.tldraw_bridge")

# Feature flag — must be explicit opt-in; never enabled in production.
_MOCK_CANVAS_ENABLED = os.getenv("KAIRO_ENABLE_MOCK_CANVAS", "0") == "1"


class TldrawWebSocketClient:
    """Real tldraw WebSocket client.

    Connects to a tldraw room server via WebSocket.  If the server is not
    running, a clear ConnectionError is raised.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8082, room_id: Optional[str] = None):
        self.host = host
        self.port = port
        self.room_id = room_id or "kairo-default"
        self._ws = None

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}/{self.room_id}"

    def is_available(self, timeout: float = 1.0) -> bool:
        """Check if the tldraw server is reachable via TCP."""
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout):
                return True
        except (OSError, socket.timeout):
            return False

    def connect(self):
        """Establish a WebSocket connection to the tldraw room server."""
        if not self.is_available():
            raise ConnectionError(
                f"tldraw server not found at {self.host}:{self.port}. "
                "Start one via: docker run -p 8082:8082 tldraw/tldraw"
            )
        try:
            import websockets  # type: ignore
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._ws = loop.run_until_complete(websockets.connect(self.url))
        except ImportError:
            raise ConnectionError(
                "websockets library not installed. Install via: pip install websockets"
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to tldraw server at {self.url}: {e}")

    def send_shapes(self, shapes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Send a list of shape definitions to the tldraw room server."""
        if self._ws is None:
            self.connect()
        import asyncio

        payload = {"type": "create_shapes", "shapes": shapes}
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._send_payload(payload))
                    return future.result()
            else:
                return loop.run_until_complete(self._send_payload(payload))
        except Exception as e:
            raise ConnectionError(f"tldraw WebSocket send failed: {e}")

    async def _send_payload(self, payload: dict) -> dict:
        """Send a payload over WebSocket and receive response."""
        if self._ws is None:
            await self._async_connect()
        await self._ws.send(json.dumps(payload))
        resp = await self._ws.recv()
        return json.loads(resp)

    async def _async_connect(self):
        """Async connect to the tldraw server."""
        if not self.is_available():
            raise ConnectionError(
                f"tldraw server not found at {self.host}:{self.port}. "
                "Start one via: docker run -p 8082:8082 tldraw/tldraw"
            )
        try:
            import websockets  # type: ignore

            self._ws = await websockets.connect(self.url)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to tldraw server at {self.url}: {e}")

    def close(self):
        """Close the WebSocket connection."""
        if self._ws is not None:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(self._ws.close())
            except Exception:
                pass
            self._ws = None


class TldrawBridge:
    """Bridges Kairo to tldraw infinite whiteboard canvas.

    When ``KAIRO_ENABLE_MOCK_CANVAS=1`` the bridge uses an in-memory mock
    shape store.  Otherwise it attempts to use the real
    :class:`TldrawWebSocketClient`.  If no server is running, a clear
    ConnectionError is raised.
    """

    def _is_mock_enabled(self) -> bool:
        global _MOCK_CANVAS_ENABLED
        return _MOCK_CANVAS_ENABLED or (os.getenv("KAIRO_ENABLE_MOCK_CANVAS", "0") == "1")

    def _handle_fallback(self, method_name: str):
        if self._is_mock_enabled():
            log.warning("LOUD WARNING: Figma/tldraw mock canvas is active!")
        else:
            raise ConnectionError(
                f"tldraw service is offline and mock canvas is disabled (method: {method_name})."
            )

    def __init__(self, host: str = "127.0.0.1", port: int = 8082, offline_mode: bool = False):
        self.host = host
        self.port = port
        # offline_mode can be overridden per-instance; production callers leave it False.
        self.offline_mode = offline_mode
        self._next_id = 1

        # Real WebSocket client — created lazily.
        self._ws_client: Optional[TldrawWebSocketClient] = None

        if self._is_mock_enabled():
            log.warning("LOUD WARNING: Figma/tldraw mock canvas is active!")
            self._mock_shapes: Dict[str, Dict[str, Any]] = {}  # mock
            self._reset_mock_canvas()  # mock
        else:
            self._mock_shapes = {}  # empty — never written in production  # mock

    def _get_ws_client(self) -> TldrawWebSocketClient:
        """Return a connected TldrawWebSocketClient or raise a clear error."""
        if self._ws_client is not None:
            return self._ws_client
        client = TldrawWebSocketClient(host=self.host, port=self.port)
        if not client.is_available():
            raise ConnectionError(
                f"tldraw server not found at {self.host}:{self.port}. "
                "Start one via: docker run -p 8082:8082 tldraw/tldraw"
            )
        self._ws_client = client
        return self._ws_client

    def _reset_mock_canvas(self):  # mock
        """Pre-populate flowchart blocks in local mock state."""
        self._mock_shapes = {  # mock
            "node-start": {
                "id": "node-start",
                "type": "geo",
                "x": 100,
                "y": 100,
                "props": {
                    "w": 120,
                    "h": 60,
                    "geo": "rectangle",
                    "text": "Start Process",
                    "fill": "semi",
                    "color": "blue",
                },
            },
            "node-step1": {
                "id": "node-step1",
                "type": "geo",
                "x": 300,
                "y": 100,
                "props": {
                    "w": 150,
                    "h": 60,
                    "geo": "rectangle",
                    "text": "Retrieve Design Tokens",
                    "fill": "semi",
                    "color": "violet",
                },
            },
            "node-decide": {
                "id": "node-decide",
                "type": "geo",
                "x": 550,
                "y": 80,
                "props": {
                    "w": 100,
                    "h": 100,
                    "geo": "diamond",
                    "text": "Is Valid?",
                    "fill": "semi",
                    "color": "yellow",
                },
            },
            "arrow-1": {
                "id": "arrow-1",
                "type": "arrow",
                "x": 0,
                "y": 0,
                "props": {
                    "start": {"x": 220, "y": 130},
                    "end": {"x": 300, "y": 130},
                    "color": "grey",
                },
            },
            "arrow-2": {
                "id": "arrow-2",
                "type": "arrow",
                "x": 0,
                "y": 0,
                "props": {
                    "start": {"x": 450, "y": 130},
                    "end": {"x": 550, "y": 130},
                    "color": "grey",
                },
            },
        }

    def is_available(self) -> bool:
        """Check if the tldraw MCP server is available."""
        if self.offline_mode:
            return False
        if self._is_mock_enabled():
            return True
        # Real mode: check if server is reachable
        try:
            client = self._get_ws_client()
            return client.is_available()
        except ConnectionError:
            return False

    async def _send_websocket_req(self, payload: dict) -> dict:
        import websockets

        ws_url = f"ws://{self.host}:{self.port}"
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps(payload))
            resp = await ws.recv()
            return json.loads(resp)

    def _call_websocket_sync(self, payload: dict) -> dict:
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self._send_websocket_req(payload))
                return future.result()
        else:
            return loop.run_until_complete(self._send_websocket_req(payload))

    def _call_online_tool(self, tool_name: str, args: dict) -> dict:
        """Call the tldraw MCP tool via WebSocket or standard stdio if WS fails."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
            "id": 1,
        }

        # 1. Try WebSocket
        try:
            res = self._call_websocket_sync(payload)
            if "error" not in res:
                return {"ok": True, "result": res.get("result", {})}
        except Exception as e:
            log.warning(f"tldraw WebSocket call failed: {e}. Trying stdio fallback.")

        # 2. Try stdio npx fallback
        import subprocess

        try:
            result = subprocess.run(
                ["npx", "-y", "@tldraw/mcp-app", "call", tool_name, json.dumps(args)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return {"ok": True, "result": json.loads(result.stdout)}
        except Exception as e:
            log.error(f"tldraw stdio MCP call failed: {e}")
            return {"ok": False, "error": str(e)}

    def create_shape(
        self, shape_type: str, x: float, y: float, props: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new shape (e.g. geo, arrow, text) on the canvas."""
        is_mock_enabled = self._is_mock_enabled()
        if not is_mock_enabled and not self.offline_mode:
            # Real path: try WebSocket client
            try:
                client = self._get_ws_client()
                result = client.send_shapes([{"type": shape_type, "x": x, "y": y, "props": props}])
                shape_id = result.get("shape_ids", [f"shape-{self._next_id}"])[0]
                self._next_id += 1
                shape = {"id": shape_id, "type": shape_type, "x": x, "y": y, "props": props}
                return {"ok": True, "shape_id": shape_id, "shape": shape}
            except ConnectionError:
                raise

        self._handle_fallback("create_shape")

        shape_id = f"shape-{self._next_id}"
        self._next_id += 1

        shape = {"id": shape_id, "type": shape_type, "x": x, "y": y, "props": props}

        self._mock_shapes[shape_id] = shape  # mock
        log.info(
            f"tldraw Shape created: {shape_id} of type '{shape_type}' at ({x}, {y}) [mock={'ON' if is_mock_enabled else 'OFF'}]"
        )
        return {"ok": True, "shape_id": shape_id, "shape": shape}

    def update_shape(
        self,
        shape_id: str,
        x: Optional[float] = None,
        y: Optional[float] = None,
        props: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update properties or coordinates of an existing shape."""
        if not self._is_mock_enabled():
            if self.offline_mode:
                raise ConnectionError(
                    "update_shape: mock canvas is disabled (method: update_shape)."
                )
            return {
                "ok": False,
                "error": "update_shape unavailable: mock canvas is disabled. Set KAIRO_ENABLE_MOCK_CANVAS=1 for offline testing.",
            }
        is_mock_enabled = self._is_mock_enabled()
        if not is_mock_enabled and not self.offline_mode:
            try:
                self._get_ws_client()
                raise ConnectionError(
                    "tldraw server is reachable but update_shape requires a running "
                    "tldraw MCP server. Start one via: docker run -p 8082:8082 tldraw/tldraw"
                )
            except ConnectionError:
                raise

        if not is_mock_enabled:
            self._handle_fallback("update_shape")

        if shape_id not in self._mock_shapes:  # mock
            return {"ok": False, "error": f"Shape not found: {shape_id}"}

        shape = self._mock_shapes[shape_id]  # mock
        if x is not None:
            shape["x"] = x
        if y is not None:
            shape["y"] = y
        if props is not None:
            shape.setdefault("props", {}).update(props)

        log.info(f"tldraw Shape updated: {shape_id}")
        return {"ok": True, "shape_id": shape_id, "shape": shape}

    def delete_shape(self, shape_id: str) -> Dict[str, Any]:
        """Remove a shape from the canvas."""
        if not self._is_mock_enabled():
            if self.offline_mode:
                raise ConnectionError(
                    "delete_shape: mock canvas is disabled (method: delete_shape)."
                )
            return {
                "ok": False,
                "error": "delete_shape unavailable: mock canvas is disabled. Set KAIRO_ENABLE_MOCK_CANVAS=1 for offline testing.",
            }
        is_mock_enabled = self._is_mock_enabled()
        if not is_mock_enabled and not self.offline_mode:
            try:
                self._get_ws_client()
                raise ConnectionError(
                    "tldraw server is reachable but delete_shape requires a running "
                    "tldraw MCP server. Start one via: docker run -p 8082:8082 tldraw/tldraw"
                )
            except ConnectionError:
                raise

        if not is_mock_enabled:
            self._handle_fallback("delete_shape")

        if shape_id not in self._mock_shapes:  # mock
            return {"ok": False, "error": f"Shape not found: {shape_id}"}

        del self._mock_shapes[shape_id]  # mock
        log.info(f"tldraw Shape deleted: {shape_id}")
        return {"ok": True, "shape_id": shape_id}

    def get_canvas_shapes(self) -> List[Dict[str, Any]]:
        """Retrieve all active shapes from the canvas."""
        is_mock_enabled = self._is_mock_enabled()
        if not is_mock_enabled:
            return []
        return list(self._mock_shapes.values())  # mock

    def draw_flowchart(
        self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Position a list of nodes and draw connecting arrows programmatically."""
        log.info(f"tldraw drawing flowchart with {len(nodes)} nodes and {len(edges)} edges.")

        created_node_ids = {}
        # Simple vertical grid layout
        start_x = 100.0
        start_y = 100.0
        spacing_x = 250.0

        # 1. Create Nodes
        for idx, n in enumerate(nodes):
            name = n.get("name", f"Step {idx}")
            geo_type = n.get("shape", "rectangle")  # rectangle, ellipse, diamond
            color = n.get("color", "blue")

            x_pos = start_x + (idx * spacing_x)
            y_pos = start_y

            w = 140.0
            h = 70.0
            if geo_type == "diamond":
                w = 100.0
                h = 100.0
                y_pos -= 15.0  # Center align diamonds slightly

            props = {"w": w, "h": h, "geo": geo_type, "text": name, "fill": "semi", "color": color}

            res = self.create_shape("geo", x_pos, y_pos, props)
            created_node_ids[n.get("id", str(idx))] = {
                "id": res["shape_id"],
                "x": x_pos,
                "y": y_pos,
                "w": w,
                "h": h,
            }

        # 2. Draw connecting arrows
        for edge in edges:
            source_key = edge.get("source")
            target_key = edge.get("target")

            if source_key in created_node_ids and target_key in created_node_ids:
                s_info = created_node_ids[source_key]
                t_info = created_node_ids[target_key]

                # Start from right edge of source, end at left edge of target
                start_pt = {"x": s_info["x"] + s_info["w"], "y": s_info["y"] + (s_info["h"] / 2.0)}
                end_pt = {"x": t_info["x"], "y": t_info["y"] + (t_info["h"] / 2.0)}

                props = {"start": start_pt, "end": end_pt, "color": "grey"}

                self.create_shape("arrow", 0, 0, props)

        return {
            "ok": True,
            "created_nodes": [val["id"] for val in created_node_ids.values()],
            "canvas_shapes_count": len(self._mock_shapes),  # mock
        }
