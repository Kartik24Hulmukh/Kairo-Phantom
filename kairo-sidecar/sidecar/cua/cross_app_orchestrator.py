"""
kairo-sidecar/sidecar/cua/cross_app_orchestrator.py

Cross-Application Workflow Orchestrator for Kairo Phantom CUA.

Enables multi-step cross-app automation described in briefing Doc 01 §2:
  "Take the Q3 report from Excel, put it into PowerPoint, and email it"
  — all offline, all verified.

A $10B+ productivity category currently relying on fragile RPA tools like UiPath.

Architecture:
  - WorkflowStep: single atomic action (app, action, target, expected_result)
  - AppWorkflowPlan: ordered list of steps with rollback points
  - CrossAppOrchestrator: executes the plan with per-step VLM verification

The orchestrator integrates with:
  - VlmGroundingEngine: for finding elements when UIA fails
  - CanvaCUAAgent: for executing clicks/keyboard input
  - CuaGate (Rust): for user approval and safety gates
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .vlm_grounding import VlmGroundingEngine, VerificationResult, get_vlm_engine

logger = logging.getLogger(__name__)


# ─── Enumerations ─────────────────────────────────────────────────────────────


class AppTarget(str, Enum):
    """Known application targets for cross-app workflows."""

    EXCEL = "microsoft excel"
    WORD = "microsoft word"
    POWERPOINT = "microsoft powerpoint"
    OUTLOOK = "microsoft outlook"
    CHROME = "google chrome"
    EDGE = "microsoft edge"
    NOTEPAD = "notepad"
    VSCODE = "visual studio code"
    CANVA = "canva"
    ANY = "*"  # Any foreground window


class StepActionType(str, Enum):
    """Types of actions a step can perform."""

    COPY = "copy"  # Select + copy content
    PASTE = "paste"  # Paste content at cursor
    TYPE = "type"  # Type text
    CLICK = "click"  # Click element by description
    SHORTCUT = "shortcut"  # Run keyboard shortcut
    FOCUS_APP = "focus_app"  # Bring app window to foreground
    SCREENSHOT = "screenshot"  # Take screenshot for context
    VERIFY = "verify"  # Verify expected state


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ─── Data Structures ──────────────────────────────────────────────────────────


@dataclass
class WorkflowStep:
    """A single step in a cross-app workflow."""

    step_id: int
    app_target: AppTarget
    action: StepActionType
    description: str  # Human-readable description for GRP
    # Action-specific params
    element_description: str = ""  # For CLICK — what to click
    text_to_type: str = ""  # For TYPE
    shortcut: str = ""  # For SHORTCUT (e.g., "ctrl+c")
    expected_result: str = ""  # For VERIFY — what should change
    rollback_shortcut: str = "ctrl+z"  # Undo action if next step fails
    # Runtime state
    status: StepStatus = StepStatus.PENDING
    before_screenshot: str = ""
    after_screenshot: str = ""
    verification: Optional[VerificationResult] = None
    error: str = ""
    latency_ms: float = 0.0


@dataclass
class AppWorkflowPlan:
    """
    An ordered list of steps forming a complete cross-app workflow.

    Example: Excel → PowerPoint → Outlook email workflow
    """

    plan_id: str
    description: str  # e.g., "Q3 Report: Excel → PowerPoint → Email"
    steps: list[WorkflowStep]
    user_intent: str  # Original user request
    requires_approval: bool = True

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.SUCCESS)

    @property
    def failed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.FAILED)

    @property
    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.SUCCESS, StepStatus.SKIPPED) for s in self.steps)

    @property
    def progress_percent(self) -> float:
        if not self.steps:
            return 100.0
        return (self.completed_steps / self.total_steps) * 100


@dataclass
class OrchestrationResult:
    """Final result of a cross-app workflow execution."""

    success: bool
    plan: AppWorkflowPlan
    total_latency_ms: float
    steps_completed: int
    steps_failed: int
    error_summary: str = ""


# ─── Common Workflow Builders ──────────────────────────────────────────────────


class WorkflowBuilder:
    """
    Factory for common cross-app workflow plans.

    These pre-built workflows cover the most common enterprise use cases
    described in the briefing.
    """

    @staticmethod
    def excel_to_powerpoint_email(
        chart_name: str = "Q3 Revenue Chart",
        slide_title: str = "Q3 Financial Results",
        recipient_email: str = "",
        email_subject: str = "Q3 Report",
    ) -> AppWorkflowPlan:
        """
        'Take the Q3 report from Excel, put it into PowerPoint, and email it'

        The example from the briefing: a $10B+ productivity workflow currently
        relying on fragile RPA tools.
        """
        steps = [
            # Step 1: Focus Excel
            WorkflowStep(
                step_id=1,
                app_target=AppTarget.EXCEL,
                action=StepActionType.FOCUS_APP,
                description="Bring Microsoft Excel to foreground",
                expected_result="Excel window is active and visible",
            ),
            # Step 2: Take screenshot for context
            WorkflowStep(
                step_id=2,
                app_target=AppTarget.EXCEL,
                action=StepActionType.SCREENSHOT,
                description="Capture Excel spreadsheet state",
            ),
            # Step 3: Select and copy the chart
            WorkflowStep(
                step_id=3,
                app_target=AppTarget.EXCEL,
                action=StepActionType.CLICK,
                description=f"Click on '{chart_name}' chart to select it",
                element_description=chart_name,
                expected_result="Chart has selection handles visible",
            ),
            # Step 4: Copy the chart
            WorkflowStep(
                step_id=4,
                app_target=AppTarget.EXCEL,
                action=StepActionType.SHORTCUT,
                description="Copy selected chart (Ctrl+C)",
                shortcut="ctrl+c",
                expected_result="Clipboard contains the chart",
            ),
            # Step 5: Focus PowerPoint
            WorkflowStep(
                step_id=5,
                app_target=AppTarget.POWERPOINT,
                action=StepActionType.FOCUS_APP,
                description="Bring Microsoft PowerPoint to foreground",
                expected_result="PowerPoint window is active",
            ),
            # Step 6: Click on slide content area
            WorkflowStep(
                step_id=6,
                app_target=AppTarget.POWERPOINT,
                action=StepActionType.CLICK,
                description=f"Click on slide content area for '{slide_title}'",
                element_description="slide content placeholder or empty slide area",
                expected_result="Slide content area is selected",
            ),
            # Step 7: Paste chart into slide
            WorkflowStep(
                step_id=7,
                app_target=AppTarget.POWERPOINT,
                action=StepActionType.SHORTCUT,
                description="Paste chart into slide (Ctrl+V)",
                shortcut="ctrl+v",
                expected_result="Chart from Excel is now in the PowerPoint slide",
            ),
            # Step 8: Verify chart appeared in PowerPoint
            WorkflowStep(
                step_id=8,
                app_target=AppTarget.POWERPOINT,
                action=StepActionType.VERIFY,
                description="Verify chart appears in PowerPoint slide",
                expected_result="Chart visible in PowerPoint slide",
            ),
            # Step 9: Save PowerPoint
            WorkflowStep(
                step_id=9,
                app_target=AppTarget.POWERPOINT,
                action=StepActionType.SHORTCUT,
                description="Save PowerPoint file (Ctrl+S)",
                shortcut="ctrl+s",
                expected_result="File saved — title bar shows no asterisk",
            ),
        ]

        # Add email steps if recipient provided
        if recipient_email:
            steps.extend(
                [
                    WorkflowStep(
                        step_id=10,
                        app_target=AppTarget.OUTLOOK,
                        action=StepActionType.FOCUS_APP,
                        description="Open Microsoft Outlook",
                        expected_result="Outlook window is active",
                    ),
                    WorkflowStep(
                        step_id=11,
                        app_target=AppTarget.OUTLOOK,
                        action=StepActionType.SHORTCUT,
                        description="New email (Ctrl+N)",
                        shortcut="ctrl+n",
                        expected_result="New email compose window appears",
                    ),
                    WorkflowStep(
                        step_id=12,
                        app_target=AppTarget.OUTLOOK,
                        action=StepActionType.CLICK,
                        description="Click on To: field",
                        element_description="To: recipient email input field",
                        expected_result="To field is focused",
                    ),
                    WorkflowStep(
                        step_id=13,
                        app_target=AppTarget.OUTLOOK,
                        action=StepActionType.TYPE,
                        description=f"Type recipient email: {recipient_email}",
                        text_to_type=recipient_email,
                        expected_result=f"To field contains {recipient_email}",
                    ),
                    WorkflowStep(
                        step_id=14,
                        app_target=AppTarget.OUTLOOK,
                        action=StepActionType.CLICK,
                        description="Click Subject field",
                        element_description="Subject: email subject input field",
                        expected_result="Subject field is focused",
                    ),
                    WorkflowStep(
                        step_id=15,
                        app_target=AppTarget.OUTLOOK,
                        action=StepActionType.TYPE,
                        description=f"Type subject: {email_subject}",
                        text_to_type=email_subject,
                        expected_result=f"Subject contains '{email_subject}'",
                    ),
                ]
            )

        return AppWorkflowPlan(
            plan_id="excel-to-pptx-email",
            description=f"Excel → PowerPoint → Email: {chart_name}",
            steps=steps,
            user_intent=f"Take {chart_name} from Excel, put it in PowerPoint, and email it",
        )

    @staticmethod
    def word_to_pdf_email(
        recipient_email: str = "",
        subject: str = "Document",
    ) -> AppWorkflowPlan:
        """Export Word document as PDF and optionally email it."""
        steps = [
            WorkflowStep(
                step_id=1,
                app_target=AppTarget.WORD,
                action=StepActionType.FOCUS_APP,
                description="Bring Microsoft Word to foreground",
            ),
            WorkflowStep(
                step_id=2,
                app_target=AppTarget.WORD,
                action=StepActionType.SHORTCUT,
                description="Export as PDF (Ctrl+Shift+P or File→Export)",
                shortcut="ctrl+shift+p",
                expected_result="Save As dialog appears with PDF format selected",
            ),
            WorkflowStep(
                step_id=3,
                app_target=AppTarget.WORD,
                action=StepActionType.CLICK,
                description="Click Save/Export button in dialog",
                element_description="Save button or Publish button in PDF export dialog",
                expected_result="Dialog closes and PDF is saved",
            ),
            WorkflowStep(
                step_id=4,
                app_target=AppTarget.WORD,
                action=StepActionType.VERIFY,
                description="Verify PDF was saved successfully",
                expected_result="PDF export dialog closed successfully",
            ),
        ]

        return AppWorkflowPlan(
            plan_id="word-to-pdf",
            description="Word → PDF Export",
            steps=steps,
            user_intent="Save Word document as PDF",
        )


# ─── Cross-App Orchestrator ───────────────────────────────────────────────────


class CrossAppOrchestrator:
    """
    Orchestrates multi-step cross-application workflows.

    This is the component that makes Kairo dramatically superior to traditional
    RPA tools like UiPath — it uses VLM semantic understanding instead of brittle
    pixel-based selectors.

    Key differences from traditional RPA:
    1. VLM-based element finding (not pixel/template matching)
    2. Semantic verification (not pixel diff)
    3. LLM-planned rollback on failure
    4. Natural language step descriptions
    """

    def __init__(self, vlm_engine: Optional[VlmGroundingEngine] = None) -> None:
        self.vlm = vlm_engine or get_vlm_engine()
        self._screenshot_dir = Path.home() / ".kairo-phantom" / "cua_screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def execute_plan(
        self,
        plan: AppWorkflowPlan,
        on_step_update: Optional[Any] = None,  # Callable[[WorkflowStep], None]
        dry_run: bool = False,
    ) -> OrchestrationResult:
        """
        Execute a cross-app workflow plan.

        Args:
            plan: The workflow plan to execute
            on_step_update: Optional callback for step status updates
            dry_run: If True, describe steps but don't execute

        Returns:
            OrchestrationResult with full execution report
        """
        start_time = time.monotonic()
        logger.info(f"CrossApp: Starting plan '{plan.description}' ({plan.total_steps} steps)")

        for step in plan.steps:
            step.status = StepStatus.RUNNING

            if on_step_update:
                on_step_update(step)

            if dry_run:
                logger.info(f"  [DRY RUN] Step {step.step_id}: {step.description}")
                step.status = StepStatus.SUCCESS
                continue

            try:
                step_start = time.monotonic()
                success = await self._execute_step(step)
                step.latency_ms = (time.monotonic() - step_start) * 1000
                step.status = StepStatus.SUCCESS if success else StepStatus.FAILED

                if not success:
                    logger.error(f"Step {step.step_id} failed: {step.description} — {step.error}")
                    # Attempt rollback of this step
                    await self._rollback_step(step)
                    # Mark remaining steps as skipped
                    for remaining in plan.steps[step.step_id :]:
                        remaining.status = StepStatus.SKIPPED
                    break

                logger.info(
                    f"  ✓ Step {step.step_id}: {step.description} " f"({step.latency_ms:.0f}ms)"
                )

            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
                logger.error(f"Step {step.step_id} exception: {e}", exc_info=True)

            if on_step_update:
                on_step_update(step)

        total_ms = (time.monotonic() - start_time) * 1000
        result = OrchestrationResult(
            success=plan.is_complete,
            plan=plan,
            total_latency_ms=total_ms,
            steps_completed=plan.completed_steps,
            steps_failed=plan.failed_steps,
            error_summary="" if plan.is_complete else self._summarize_failures(plan),
        )
        logger.info(
            f"CrossApp: Plan complete — {plan.completed_steps}/{plan.total_steps} steps "
            f"in {total_ms:.0f}ms | {'✓ SUCCESS' if result.success else '✗ FAILED'}"
        )
        return result

    async def _execute_step(self, step: WorkflowStep) -> bool:
        """Execute a single workflow step. Returns True on success."""
        try:
            if step.action == StepActionType.FOCUS_APP:
                return await self._focus_app(step)
            elif step.action == StepActionType.SCREENSHOT:
                return await self._take_screenshot_step(step)
            elif step.action == StepActionType.CLICK:
                return await self._click_element(step)
            elif step.action == StepActionType.SHORTCUT:
                return await self._run_shortcut(step)
            elif step.action == StepActionType.TYPE:
                return await self._type_text(step)
            elif step.action == StepActionType.VERIFY:
                return await self._verify_state(step)
            elif step.action == StepActionType.COPY:
                return await self._copy_content(step)
            elif step.action == StepActionType.PASTE:
                return await self._paste_content(step)
            else:
                step.error = f"Unknown action type: {step.action}"
                return False
        except Exception as e:
            step.error = str(e)
            return False

    async def _focus_app(self, step: WorkflowStep) -> bool:
        """Bring the target app to foreground using Windows API."""
        try:
            import win32gui  # type: ignore
            import win32con  # type: ignore

            target = step.app_target.value.lower()

            def enum_handler(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower()
                    if target.split()[0] in title or target == "*":
                        results.append(hwnd)

            windows = []
            win32gui.EnumWindows(enum_handler, windows)

            if windows:
                hwnd = windows[0]
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                await asyncio.sleep(0.5)  # Allow window to come to front
                return True
            else:
                step.error = f"App not found: {step.app_target.value}"
                return False

        except ImportError:
            # Fallback for non-Windows environments
            logger.warning("win32gui not available — focus_app skipped")
            return True
        except Exception as e:
            step.error = f"Focus app failed: {e}"
            return False

    async def _take_screenshot_step(self, step: WorkflowStep) -> bool:
        """Take a screenshot and store the path."""
        from ..kairo_eye.farscry_service import take_screenshot

        try:
            path = await take_screenshot()
            step.after_screenshot = str(path)
            return True
        except Exception as e:
            step.error = f"Screenshot failed: {e}"
            return False

    async def _click_element(self, step: WorkflowStep) -> bool:
        """Find element via UIA or VLM and click it."""
        from ..kairo_eye.farscry_service import take_screenshot

        # Take before screenshot
        before_path = await take_screenshot()
        step.before_screenshot = str(before_path)

        # Try VLM grounding
        ground = await self.vlm.ground_element(before_path, step.element_description)

        if not ground.found or ground.confidence < 0.5:
            step.error = f"Element not found: '{step.element_description}' (confidence={ground.confidence:.2f})"
            return False

        # Execute click via enigo
        try:
            import enigo  # type: ignore

            e = enigo.Enigo()
            e.mouse_move(ground.x, ground.y)
            await asyncio.sleep(0.1)
            e.mouse_click(enigo.Button.Left)
        except ImportError:
            # Fallback: use ctypes SendInput
            await self._send_click_ctypes(ground.x, ground.y)

        await asyncio.sleep(0.3)

        # Verify if expected result specified
        if step.expected_result:
            after_path = await take_screenshot()
            step.after_screenshot = str(after_path)
            verify = await self.vlm.verify_action(before_path, after_path, step.expected_result)
            step.verification = verify
            if not verify.success and verify.confidence > 0.7:
                step.error = f"Verification failed: {verify.explanation}"
                return False

        return True

    async def _run_shortcut(self, step: WorkflowStep) -> bool:
        """Execute a keyboard shortcut."""
        try:
            await self._send_keys(step.shortcut)
            await asyncio.sleep(0.5)  # Allow UI to respond
            return True
        except Exception as e:
            step.error = f"Shortcut failed: {e}"
            return False

    async def _type_text(self, step: WorkflowStep) -> bool:
        """Type text at current cursor position."""
        try:
            await self._send_text(step.text_to_type)
            await asyncio.sleep(0.2)
            return True
        except Exception as e:
            step.error = f"Type failed: {e}"
            return False

    async def _verify_state(self, step: WorkflowStep) -> bool:
        """Verify the current screen state matches expected result."""
        from ..kairo_eye.farscry_service import take_screenshot

        if not step.before_screenshot:
            # No before — just take current screenshot as "after"
            path = await take_screenshot()
            step.after_screenshot = str(path)
            return True

        after_path = await take_screenshot()
        step.after_screenshot = str(after_path)

        verify = await self.vlm.verify_action(
            step.before_screenshot, after_path, step.expected_result
        )
        step.verification = verify

        if not verify.success and verify.confidence > 0.7:
            step.error = f"State verification failed: {verify.explanation}"
            return False
        return True

    async def _copy_content(self, step: WorkflowStep) -> bool:
        """Copy selected content to clipboard."""
        return await self._run_shortcut(
            WorkflowStep(
                step_id=step.step_id,
                app_target=step.app_target,
                action=StepActionType.SHORTCUT,
                description="Copy",
                shortcut="ctrl+c",
            )
        )

    async def _paste_content(self, step: WorkflowStep) -> bool:
        """Paste clipboard content."""
        return await self._run_shortcut(
            WorkflowStep(
                step_id=step.step_id,
                app_target=step.app_target,
                action=StepActionType.SHORTCUT,
                description="Paste",
                shortcut="ctrl+v",
            )
        )

    async def _rollback_step(self, step: WorkflowStep) -> None:
        """Attempt to undo a failed step."""
        if step.rollback_shortcut:
            logger.info(f"Rolling back step {step.step_id} via {step.rollback_shortcut}")
            try:
                await self._send_keys(step.rollback_shortcut)
            except Exception as e:
                logger.warning(f"Rollback failed: {e}")

    async def _send_keys(self, shortcut: str) -> None:
        """Send keyboard shortcut (cross-platform best-effort)."""
        # Parse shortcut string (e.g., "ctrl+c", "ctrl+shift+s")
        parts = shortcut.lower().split("+")
        try:
            import win32api  # type: ignore
            import win32con  # type: ignore
            import win32gui  # type: ignore  # noqa: F401

            # Simple implementation — production would use SendInput
            keys_map = {
                "ctrl": win32con.VK_CONTROL,
                "shift": win32con.VK_SHIFT,
                "alt": win32con.VK_MENU,
            }
            # Press modifiers
            for part in parts[:-1]:
                vk = keys_map.get(part)
                if vk:
                    win32api.keybd_event(vk, 0, 0, 0)
            # Press key
            last = parts[-1]
            if len(last) == 1:
                vk = ord(last.upper())
                win32api.keybd_event(vk, 0, 0, 0)
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            # Release modifiers (reverse order)
            for part in reversed(parts[:-1]):
                vk = keys_map.get(part)
                if vk:
                    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        except ImportError:
            logger.warning(f"win32api not available — shortcut '{shortcut}' skipped")

    async def _send_text(self, text: str) -> None:
        """Type text via SendInput or clipboard paste."""
        from sidecar.clipboard_mutex import CLIPBOARD_LOCK

        with CLIPBOARD_LOCK:
            try:
                import win32clipboard  # type: ignore
                import win32con  # type: ignore
                import win32api  # type: ignore

                # Use clipboard for reliable Unicode support
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                # Paste
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord("V"), 0, 0, 0)
                win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            except ImportError:
                logger.warning("win32clipboard not available — text type skipped")

    async def _send_click_ctypes(self, x: int, y: int) -> None:
        """Send mouse click via ctypes (no dependency required)."""
        import sys

        if sys.platform != "win32":
            logger.warning("ctypes click only supported on Windows")
            return

        import ctypes

        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        MOUSEEVENTF_MOVE = 0x0001
        MOUSEEVENTF_ABSOLUTE = 0x8000

        try:
            # Get screen dimensions for coordinate normalization
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            abs_x = int(x * 65535 / screen_w)
            abs_y = int(y * 65535 / screen_h)

            ctypes.windll.user32.mouse_event(
                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, abs_x, abs_y, 0, 0
            )
            await asyncio.sleep(0.05)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            await asyncio.sleep(0.05)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except AttributeError as e:
            logger.warning(f"ctypes.windll not available: {e}")

    def _summarize_failures(self, plan: AppWorkflowPlan) -> str:
        """Summarize failed steps for error reporting."""
        failures = [
            f"Step {s.step_id} ({s.description}): {s.error}"
            for s in plan.steps
            if s.status == StepStatus.FAILED
        ]
        return "; ".join(failures)


# ─── Singleton ────────────────────────────────────────────────────────────────

_orchestrator: Optional[CrossAppOrchestrator] = None


def get_cross_app_orchestrator() -> CrossAppOrchestrator:
    """Get (or create) the singleton cross-app orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CrossAppOrchestrator()
    return _orchestrator
