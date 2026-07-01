import os
import sys
import pytest
import logging
from pathlib import Path
from unittest.mock import patch

# Add sidecar package to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from sidecar.parsers.figma_design_bridge import FigmaDesignBridge
from sidecar.parsers.tldraw_bridge import TldrawBridge
from sidecar.parsers.slide_image_gen import SlideImageGenerator
from sidecar.writers.writing_intelligence import WritingIntelligenceOrchestrator, MemorizationError


def test_figma_design_bridge_gating_disabled(caplog):
    """Verify FigmaDesignBridge raises ConnectionError when mock is disabled and service is offline."""
    # Ensure flag is OFF (0)
    with patch.dict(os.environ, {"KAIRO_ENABLE_MOCK_CANVAS": "0"}):
        bridge = FigmaDesignBridge(offline_mode=True)

        # Test creation/modification methods
        with pytest.raises(ConnectionError) as excinfo:
            bridge.create_frame("Frame 1", 0, 0, 100, 100)
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.create_text_node("Text 1", "Hello")
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.create_rectangle("Rect 1", 0, 0, 100, 100)
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.create_component("Comp 1")
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.create_section("Sect 1")
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.set_fills("some-node-id", "#ffffff")
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.set_auto_layout("some-node-id", "vertical")
        assert "mock canvas is disabled" in str(excinfo.value)

        # Query method should return error dict rather than raise
        tree = bridge.read_node_tree()
        assert "error" in tree
        assert "Mock canvas disabled" in tree["error"]


def test_figma_design_bridge_gating_enabled(caplog):
    """Verify FigmaDesignBridge logs warning and permits mocks when flag is ON."""
    with patch.dict(os.environ, {"KAIRO_ENABLE_MOCK_CANVAS": "1"}):
        with caplog.at_level(logging.WARNING):
            bridge = FigmaDesignBridge(offline_mode=True)
            # Warning logged in __init__
            assert any(
                "LOUD WARNING: Figma/tldraw mock canvas is active!" in rec.message
                for rec in caplog.records
            )
            caplog.clear()

            # Test fallback on service offline
            res = bridge.create_frame("Frame 1", 0, 0, 100, 100)
            assert res.get("ok") is True
            # Warning logged during fallback
            assert any(
                "LOUD WARNING: Figma/tldraw mock canvas is active!" in rec.message
                for rec in caplog.records
            )

            node_id = res["node_id"]

            # Fills & auto layout should succeed
            res_fills = bridge.set_fills(node_id, "#ff0000")
            assert res_fills.get("ok") is True

            res_layout = bridge.set_auto_layout(node_id, "vertical")
            assert res_layout.get("ok") is True


def test_tldraw_bridge_gating_disabled():
    """Verify TldrawBridge raises ConnectionError when mock is disabled and service is offline."""
    with patch.dict(os.environ, {"KAIRO_ENABLE_MOCK_CANVAS": "0"}):
        bridge = TldrawBridge(offline_mode=True)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.create_shape("geo", 0, 0, {"w": 100, "h": 100})
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.update_shape("some-shape", x=10)
        assert "mock canvas is disabled" in str(excinfo.value)

        with pytest.raises(ConnectionError) as excinfo:
            bridge.delete_shape("some-shape")
        assert "mock canvas is disabled" in str(excinfo.value)

        assert bridge.get_canvas_shapes() == []


def test_tldraw_bridge_gating_enabled(caplog):
    """Verify TldrawBridge logs warning and permits mocks when flag is ON."""
    with patch.dict(os.environ, {"KAIRO_ENABLE_MOCK_CANVAS": "1"}):
        with caplog.at_level(logging.WARNING):
            bridge = TldrawBridge(offline_mode=True)
            # Warning logged in __init__
            assert any(
                "LOUD WARNING: Figma/tldraw mock canvas is active!" in rec.message
                for rec in caplog.records
            )
            caplog.clear()

            res = bridge.create_shape("geo", 0, 0, {"w": 100, "h": 100})
            assert res.get("ok") is True
            assert any(
                "LOUD WARNING: Figma/tldraw mock canvas is active!" in rec.message
                for rec in caplog.records
            )


def test_slide_image_gen_disabled():
    """Verify SlideImageGenerator raises ConnectionError when mock is disabled and services offline."""
    with patch.dict(os.environ, {"KAIRO_SLIDE_IMAGE_MOCK": "0"}):
        gen = SlideImageGenerator(offline_mode=True)

        with (
            patch.object(gen, "_comfyui_available", return_value=False),
            patch.object(gen, "_gpt_image2_available", return_value=False),
            patch.object(gen, "_nano_banana_available", return_value=False),
        ):
            with pytest.raises(ConnectionError) as excinfo:
                gen.generate_slide_image({"title": "Test Slide", "topic": "Testing"})
            assert "KAIRO_SLIDE_IMAGE_MOCK is disabled" in str(excinfo.value)


def test_slide_image_gen_enabled(caplog):
    """Verify SlideImageGenerator logs warning and returns mock path when mock is ON."""
    with patch.dict(os.environ, {"KAIRO_SLIDE_IMAGE_MOCK": "1"}):
        with caplog.at_level(logging.WARNING):
            gen = SlideImageGenerator(offline_mode=True)
            # __init__ logs warning
            assert any(
                "LOUD WARNING: Slide image mock is active!" in rec.message for rec in caplog.records
            )
            caplog.clear()

            with (
                patch.object(gen, "_comfyui_available", return_value=False),
                patch.object(gen, "_gpt_image2_available", return_value=False),
                patch.object(gen, "_nano_banana_available", return_value=False),
            ):
                img_path = gen.generate_slide_image({"title": "Test Slide", "topic": "Testing"})
                assert Path(img_path).exists()

                # Clean up generated mock image
                try:
                    os.remove(img_path)
                except OSError:
                    pass

                # Warning logged during fallback
                assert any(
                    "LOUD WARNING: Slide image mock is active!" in rec.message
                    for rec in caplog.records
                )


def test_writing_intelligence_disabled():
    """Verify WritingIntelligenceOrchestrator raises MemorizationError when stub is OFF and copyright match is hit."""
    with patch.dict(os.environ, {"KAIRO_PARAPHRASE_STUB": "0"}):
        orch = WritingIntelligenceOrchestrator()

        # GNU GENERAL PUBLIC LICENSE triggers high risk / blocking verbatim copyright check
        copyrighted_text = (
            "This file is distributed under the GNU GENERAL PUBLIC LICENSE version 3."
        )

        with pytest.raises(MemorizationError) as excinfo:
            orch.process_and_sanitize(copyrighted_text)
        assert "Paraphrase stub is disabled and real service is unavailable" in str(excinfo.value)


def test_writing_intelligence_enabled(caplog):
    """Verify WritingIntelligenceOrchestrator logs warning and paraphrases when stub is ON."""
    with patch.dict(os.environ, {"KAIRO_PARAPHRASE_STUB": "1"}):
        with caplog.at_level(logging.WARNING):
            orch = WritingIntelligenceOrchestrator()
            copyrighted_text = (
                "This file is distributed under the GNU GENERAL PUBLIC LICENSE version 3."
            )

            sanitized, result = orch.process_and_sanitize(copyrighted_text)

            # Sanitization replaces "GNU GENERAL PUBLIC LICENSE" with "GNU public software sharing agreement"
            assert "GNU GENERAL PUBLIC LICENSE" not in sanitized
            assert "GNU public software sharing agreement" in sanitized

            # Warning logged during sanitization
            assert any(
                "LOUD WARNING: Paraphrase stub is active!" in rec.message for rec in caplog.records
            )
