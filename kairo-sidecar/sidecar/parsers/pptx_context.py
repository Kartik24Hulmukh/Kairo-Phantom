"""PPTX SmartContextCapture — Auto-context for presentations."""

from sidecar.parsers.pptx_mcp_bridge import PptxMcpBridge
import logging

log = logging.getLogger("kairo-sidecar.pptx_context")


class PptxContextCapture:
    """Captures rich presentation context before every Alt+Ctrl+M."""

    def __init__(self):
        self.bridge = PptxMcpBridge()

    def capture(self, pres_id: str, slide_index: int = None) -> dict:
        """Capture full presentation context for the LLM."""
        context = {
            "full_text": "",
            "current_slide": {},
            "slide_text": "",
            "slide_count": 0,
            "theme": "Default",
            "user_preferences": self._get_user_ppt_preferences(),
        }

        if not pres_id:
            return context

        try:
            # 1. Full presentation text
            res_text = self.bridge.extract_presentation_text(pres_id)
            context["full_text"] = res_text.get("text", "")

            # 2. Current slide details
            if slide_index is not None:
                context["current_slide"] = self.bridge.get_slide_info(pres_id, slide_index)
                res_slide_text = self.bridge.extract_slide_text(pres_id, slide_index)
                context["slide_text"] = res_slide_text.get("text", "")

            # 3. Presentation structure
            info = self.bridge.get_presentation_info(pres_id)
            context["slide_count"] = info.get("slide_count", 0)
            context["theme"] = info.get("theme_name", "Default")
        except Exception as e:
            log.warning(f"Error capturing PowerPoint context: {e}")

        return context

    def to_system_prompt_fragment(self, context: dict) -> str:
        """Convert captured context to a system prompt fragment."""
        frag = []

        slide_count = context.get("slide_count", 0)
        frag.append(f"Presentation has {slide_count} slides.")
        frag.append(f"Current theme: {context.get('theme', 'Default')}")

        current = context.get("current_slide", {})
        if current:
            frag.append(f"Active slide: {current.get('title', 'Untitled')}")
            frag.append(f"Layout: {current.get('layout_name', 'Standard')}")

        prefs = context.get("user_preferences", {})
        if prefs:
            frag.append(f"User preferences: {prefs}")

        frag.append(
            "CRITICAL: Generate slide-appropriate content. "
            "Segoe UI typography is the default. "
            "Titles ≤ 7 words. Bullets ≤ 7 words each. "
            "Maximum 5 bullets per slide. "
            "Use the active presentation's theme fonts and colors. "
            "Generate speaker notes for every slide."
        )

        return "\n".join(frag)

    def _get_user_ppt_preferences(self) -> dict:
        """Retrieve user's PPT formatting preferences from MemMachine."""
        # Query MemMachine for PPT-specific learned preferences - default to empty dict for now
        return {"preferred_font": "Segoe UI", "preferred_format": "bullets"}
