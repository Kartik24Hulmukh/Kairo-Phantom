"""ComfyUI Bridge for Kairo Domain 5.

Bridges to local ComfyUI instance on port 8188.

HONEST DEGRADATION:
  If ComfyUI is not available (offline mode or server unreachable), this bridge
  RAISES EngineUnavailableError — it NEVER generates a mock/placeholder image
  and claims success. The caller must handle the absence explicitly.
"""

import os
import json
import socket
import urllib.request
import logging
import tempfile
from typing import Any, Dict, Optional

from sidecar.bridge_health import EngineUnavailableError

log = logging.getLogger("kairo-sidecar.comfyui_bridge")


class ComfyUIBridge:
    """Bridges Kairo to ComfyUI for local AI asset generation."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8188, offline_mode: bool = True):
        self.host = host
        self.port = port
        self.offline_mode = offline_mode
        self.server_address = f"http://{host}:{port}"

    def is_available(self) -> bool:
        """Check if the ComfyUI server is reachable on port 8188."""
        if self.offline_mode:
            return False
        try:
            with socket.create_connection((self.host, self.port), timeout=1.0):
                return True
        except Exception:
            return False

    def generate_asset(
        self, prompt: str, style: str = "default", output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Trigger a local ComfyUI generation.

        Raises:
            EngineUnavailableError: If ComfyUI is not available.
                NEVER generates a mock image.
        """
        log.info(f"ComfyUI generate_asset request: prompt='{prompt}', style='{style}'")

        if not self.is_available():
            raise EngineUnavailableError(
                engine_name="comfyui",
                message="ComfyUI server is not reachable. Cannot generate image assets.",
                install_hint="Start ComfyUI on localhost:8188 or disable offline_mode.",
            )

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".png", prefix="kairo_asset_")
            os.close(fd)

        try:
            return self._generate_online(prompt, style, output_path)
        except Exception as e:
            raise EngineUnavailableError(
                engine_name="comfyui",
                message=f"ComfyUI online generation failed: {e}",
                install_hint="Check ComfyUI server status and model availability.",
            ) from e

    def _has_pil(self) -> bool:
        """Check if PIL/Pillow is importable."""
        try:
            from PIL import Image, ImageDraw  # noqa: F401

            return True
        except ImportError:
            return False

    def _generate_online(self, prompt: str, style: str, output_path: str) -> Dict[str, Any]:
        """Connect to ComfyUI, queue prompt, poll, and download the resulting image."""
        # Standard ComfyUI basic txt2img workflow API format
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 8,
                    "denoise": 1,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "noise_seed": 42,
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "steps": 20,
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"batch_size": 1, "height": 512, "width": 512},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": f"{prompt}, {style} style, ultra premium, modern UI asset",
                },
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": "blurry, low quality, distorted, bad text"},
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "KairoDesignAsset", "images": ["8", 0]},
            },
        }

        # Queue the job
        data = json.dumps({"prompt": workflow}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.server_address}/prompt", data=data, headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=5.0) as f:
            response = json.loads(f.read().decode("utf-8"))
            prompt_id = response["prompt_id"]

        # Simple polling logic
        import time

        max_attempts = 10
        image_name = None
        for _ in range(max_attempts):
            time.sleep(1.0)
            status_req = urllib.request.urlopen(
                f"{self.server_address}/history/{prompt_id}", timeout=2.0
            )
            history = json.loads(status_req.read().decode("utf-8"))
            if prompt_id in history:
                outputs = history[prompt_id]["outputs"]
                for node_id in outputs:
                    if "images" in outputs[node_id]:
                        image_name = outputs[node_id]["images"][0]["filename"]
                        break
                if image_name:
                    break

        if not image_name:
            raise RuntimeError("ComfyUI generation timed out or had no output image.")

        # Download the file
        view_url = f"{self.server_address}/view?filename={image_name}"
        urllib.request.urlretrieve(view_url, output_path)

        return {"ok": True, "prompt_id": prompt_id, "image_path": output_path, "offline": False}
