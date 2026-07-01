import time
import logging
from typing import Dict, Any, Optional

log = logging.getLogger("kairo-sidecar.context_assembler")


class ContextAssembler:
    """
    Assembles the final context package sent to the domain master.
    Combines: preloaded document parse + UIA element info + cursor position + MemMachine query.
    Ensures context is ready in under 100ms (preload handles the heavy work).
    """

    def assemble(
        self,
        preloaded_ctx: Optional[Dict[str, Any]],
        uia_info: Optional[Dict[str, Any]] = None,
        cursor_pos: Any = 0,
        mem_ctx: str = "",
        domain: str = "unknown",
        file_path: str = "",
    ) -> Dict[str, Any]:
        start = time.monotonic()

        # Use preloaded context if available (zero parse latency)
        ctx = preloaded_ctx or {}

        # Merge UIA accessibility info
        if uia_info:
            ctx["uia"] = uia_info

        # Add cursor position
        ctx["cursor_pos"] = cursor_pos

        # Add MemMachine context
        ctx["mem_context"] = mem_ctx

        # Add domain metadata
        ctx["domain"] = domain
        ctx["file_path"] = file_path
        ctx["assembled_at"] = time.time()
        ctx["assembly_latency_ms"] = (time.monotonic() - start) * 1000

        elapsed_ms = (time.monotonic() - start) * 1000
        log.debug(
            f"ContextAssembler: assembled in {elapsed_ms:.1f}ms "
            f"(preloaded={preloaded_ctx is not None})"
        )

        return ctx

    def assemble_screen_context(
        self,
        farscry_result: Dict[str, Any],
        preloaded_ctx: Optional[Dict[str, Any]],
        cursor_x: int,
        cursor_y: int,
        mem_ctx: str = "",
    ) -> Dict[str, Any]:
        """Assemble context for Alt+Shift+M pointer mode (visual analysis)."""
        ctx = self.assemble(
            preloaded_ctx=preloaded_ctx,
            cursor_pos={"x": cursor_x, "y": cursor_y},
            mem_ctx=mem_ctx,
        )
        ctx["visual_element"] = {
            "type": farscry_result.get("element_type"),
            "text": farscry_result.get("element_text", ""),
            "actions": farscry_result.get("contextual_actions", []),
        }
        return ctx
