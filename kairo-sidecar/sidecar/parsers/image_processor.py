"""
Domain 9: CPU-Based Image Processing
=====================================

CPU-based image preprocessing using PIL/Pillow (no GPU needed).
All operations are REAL — no mocking.

Usage:
    proc = ImageProcessor()
    img = proc.resize('/path/to/image.png', 256, 256)
    arr = proc.normalize('/path/to/image.png')
    quality = proc.histogram_quality_score('/path/to/image.png')
    # → {brightness, contrast, is_screenshot, is_photo, is_diagram}
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List

import numpy as np
from PIL import Image

log = logging.getLogger("kairo.image_processor")


class ImageProcessor:
    """
    CPU-based image processor using PIL/Pillow.

    All operations are real — no GPU required, no mocking.
    """

    def __init__(self) -> None:
        pass

    def resize(self, image_path: str, width: int, height: int) -> Image.Image:
        """
        Resize an image to the given width and height.

        Returns a PIL Image object.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        img = Image.open(image_path)
        img = img.convert("RGB")
        return img.resize((width, height), Image.LANCZOS)

    def center_crop(self, image_path: str, size: int) -> Image.Image:
        """
        Center-crop an image to a square of the given size.

        Returns a PIL Image object.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        img = Image.open(image_path)
        img = img.convert("RGB")
        w, h = img.size
        # If image is smaller than crop size, upscale first
        if w < size or h < size:
            scale = max(size / w, size / h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            w, h = img.size
        left = (w - size) // 2
        top = (h - size) // 2
        right = left + size
        bottom = top + size
        return img.crop((left, top, right, bottom))

    def normalize(self, image_path: str) -> np.ndarray:
        """
        Load an image and normalize pixel values to [0, 1].

        Returns a numpy array of shape (H, W, C) with float32 values in [0, 1].
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        img = Image.open(image_path)
        img = img.convert("RGB")
        arr = np.array(img, dtype=np.float32)
        arr = arr / 255.0
        return arr

    def histogram_quality_score(self, image_path: str) -> Dict:
        """
        Analyze image quality and classify image type using histogram analysis.

        Returns:
            {
                "brightness": float,       # mean brightness [0, 255]
                "contrast": float,         # std dev of pixel values
                "is_screenshot": bool,     # sharp edges, high contrast, limited palette
                "is_photo": bool,          # smooth gradients, wide color range
                "is_diagram": bool,        # geometric shapes, limited colors
            }
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        img = Image.open(image_path)
        img = img.convert("RGB")
        arr = np.array(img, dtype=np.float32)

        # Brightness: mean of luminance
        luminance = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        brightness = float(np.mean(luminance))
        contrast = float(np.std(luminance))

        # Convert to grayscale for histogram
        gray = np.array(img.convert("L"))
        hist: np.ndarray = np.histogram(gray, bins=256, range=(0, 256))[0]
        hist = hist.astype(np.float32)

        # Number of unique colors (downsampled for speed)
        small = img.resize((64, 64), Image.LANCZOS)
        pixels = np.array(small).reshape(-1, 3)
        unique_colors = len(np.unique(pixels, axis=0))

        # Edge density via simple gradient
        gray_small = np.array(small.convert("L"), dtype=np.float32)
        if gray_small.shape[0] > 1 and gray_small.shape[1] > 1:
            grad_x = np.abs(np.diff(gray_small, axis=1))
            grad_y = np.abs(np.diff(gray_small, axis=0))
            edge_density = float((np.mean(grad_x) + np.mean(grad_y)) / 2.0)
        else:
            edge_density = 0.0

        # Smoothness: low edge density → smooth gradients (photo-like)
        # High edge density + limited palette → screenshot
        # Medium edge density + very limited palette → diagram

        total_pixels_64 = 64 * 64  # 4096
        color_ratio = unique_colors / total_pixels_64

        # Classification heuristics (based on real histogram/edge analysis):
        # Screenshot: high edge density, limited color palette, high contrast
        is_screenshot = edge_density > 10.0 and color_ratio < 0.15 and contrast > 50.0

        # Photo: smooth gradients, wide color range, moderate-to-high unique colors
        is_photo = edge_density < 10.0 and color_ratio > 0.20

        # Diagram: very limited palette, moderate edges, geometric
        is_diagram = color_ratio < 0.08 and edge_density > 5.0 and not is_screenshot

        return {
            "brightness": brightness,
            "contrast": contrast,
            "is_screenshot": is_screenshot,
            "is_photo": is_photo,
            "is_diagram": is_diagram,
        }

    def batch_process(
        self,
        image_paths: List[str],
        operation: str,
    ) -> List[Dict]:
        """
        Process multiple images with the given operation.

        Supported operations:
            - "resize": requires width, height in kwargs (not supported here,
              use default 256x256)
            - "normalize": returns {path, shape, min, max}
            - "histogram": returns histogram_quality_score dict + path
            - "center_crop": returns {path, size}

        Returns a list of result dicts, one per image.
        """
        results: List[Dict] = []
        for path in image_paths:
            try:
                if operation == "resize":
                    img = self.resize(path, 256, 256)
                    results.append(
                        {
                            "path": path,
                            "operation": "resize",
                            "size": img.size,
                            "status": "ok",
                        }
                    )
                elif operation == "normalize":
                    arr = self.normalize(path)
                    results.append(
                        {
                            "path": path,
                            "operation": "normalize",
                            "shape": arr.shape,
                            "min": float(np.min(arr)),
                            "max": float(np.max(arr)),
                            "status": "ok",
                        }
                    )
                elif operation == "histogram":
                    score = self.histogram_quality_score(path)
                    score["path"] = path
                    score["operation"] = "histogram"
                    score["status"] = "ok"
                    results.append(score)
                elif operation == "center_crop":
                    img = self.center_crop(path, 224)
                    results.append(
                        {
                            "path": path,
                            "operation": "center_crop",
                            "size": img.size,
                            "status": "ok",
                        }
                    )
                else:
                    results.append(
                        {
                            "path": path,
                            "operation": operation,
                            "status": "error",
                            "error": f"Unknown operation: {operation}",
                        }
                    )
            except Exception as exc:
                results.append(
                    {
                        "path": path,
                        "operation": operation,
                        "status": "error",
                        "error": str(exc),
                    }
                )
        return results
