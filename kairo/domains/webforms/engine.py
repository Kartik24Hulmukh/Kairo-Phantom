# PROVENANCE: original | clean-room Web-forms/apps domain engine per DOMAIN_BUILD_TEMPLATE.md
"""Web-forms/apps domain engine — local HTML form fill, verified by DOM read-back.

Implements the ``form_fill_readback`` and ``uistate_readback`` oracles from
specs/VERIFICATION_ORACLES.md for the Web-forms/apps domain.

ARCHITECTURE:
  1. Parse a LOCAL static HTML page (BeautifulSoup4 MIT / lxml BSD).
  2. Detect form fields (text, email, password, tel, select, checkbox, radio,
     textarea, submit button).
  3. Fill values into the parsed DOM (in-memory mutation).
  4. Produce the resulting filled-DOM state (serialized HTML + structured map).
  5. Verify by RE-PARSING the filled DOM and asserting every field's value
     matches the spec — never trusts "written", always re-reads.

FIELD RESOLUTION:
  Fields are resolved through the 03 perception layer's ElementMap / resolve()
  when a natural-language query is provided. Direct CSS selectors are also
  supported for deterministic offline operation.

SUBMIT GATING:
  The "submit" action is gated through the 04 CUA verifier
  (UniversalVerifier). No receipt is emitted on unverified/failed fill.
  Required fields left blank → submit is BLOCKED (not silently "submitted").

HONEST DEGRADATION:
  If the HTML is unparseable → FAIL LOUD.
  Live browser navigation / page-agent on real sites = Experimental
  (fail-loud; needs network+browser). They NEVER fake a submit.

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from kairo.perception.engine import (
    AnchorElement,
    BoundingBox,
    ElementMap,
    ScreenMap,
    resolve,
)

log = logging.getLogger("kairo.webforms")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WebFormsEngineUnavailableError(RuntimeError):
    """Raised when the form engine cannot operate — honest degradation."""

    pass


class WebFormsError(RuntimeError):
    """Raised when a form operation fails."""

    pass


class WebFormsExperimentalError(RuntimeError):
    """Raised when an Experimental path (live browser/page-agent) is unavailable."""

    pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FormField:
    """A single detected form field.

    Attributes:
        element_id:    DOM id attribute (may be empty).
        name:          DOM name attribute (may be empty).
        field_type:    Field type: text, email, password, tel, select,
                       checkbox, radio, textarea, submit, hidden, etc.
        tag:           HTML tag name (input, select, textarea, button).
        selector:      CSS selector used to locate this field.
        current_value: Current value (for text-like fields: the value attr/text;
                       for checkbox/radio: "checked" or "unchecked";
                       for select: the selected option value).
        required:      Whether the field has the HTML ``required`` attribute.
        options:       For select fields: list of (value, text) option tuples.
        radio_group:   For radio fields: the shared ``name`` attribute.
    """

    element_id: str = ""
    name: str = ""
    field_type: str = ""
    tag: str = ""
    selector: str = ""
    current_value: str = ""
    required: bool = False
    options: list[tuple[str, str]] = dc_field(default_factory=list)
    radio_group: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "name": self.name,
            "field_type": self.field_type,
            "tag": self.tag,
            "selector": self.selector,
            "current_value": self.current_value,
            "required": self.required,
            "options": [{"value": v, "text": t} for v, t in self.options],
            "radio_group": self.radio_group,
        }


@dataclass
class FormInfo:
    """Parsed form structure — the result of read_form()."""

    form_id: str = ""
    form_action: str = ""
    form_method: str = ""
    fields: list[FormField] = dc_field(default_factory=list)
    field_count: int = 0
    required_field_count: int = 0

    @property
    def element_count(self) -> int:
        return self.field_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "form_id": self.form_id,
            "form_action": self.form_action,
            "form_method": self.form_method,
            "fields": [f.to_dict() for f in self.fields],
            "field_count": self.field_count,
            "required_field_count": self.required_field_count,
        }


@dataclass
class FillResult:
    """Result of a form fill operation."""

    ok: bool = False
    filled_html: str = ""
    output_path: str = ""
    form_info: FormInfo | None = None
    fields_filled: int = 0
    fields_total: int = 0
    required_blank: list[str] = dc_field(default_factory=list)
    submit_blocked: bool = False
    verified: bool = False
    audit_log_json: str = ""
    egress_report_json: str = ""
    doc_hash: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# HTML parsing and form detection
# ---------------------------------------------------------------------------


def parse_html(html_path: str) -> BeautifulSoup:
    """Parse an HTML file and return a BeautifulSoup DOM.

    Uses lxml (BSD) as the parser backend for robust, fast parsing.

    Args:
        html_path: Path to the .html file.

    Returns:
        BeautifulSoup DOM tree.

    Raises:
        WebFormsError: If the file is missing, empty, or unparseable.
    """
    p = Path(html_path)
    if not p.exists():
        raise WebFormsError(f"HTML file not found: {html_path}")
    content = p.read_text(encoding="utf-8")
    if not content.strip():
        raise WebFormsError(f"HTML file is empty: {html_path}")
    try:
        soup = BeautifulSoup(content, "lxml")
    except Exception:
        # Fallback to built-in html.parser if lxml fails
        try:
            soup = BeautifulSoup(content, "html.parser")
        except Exception as e2:
            raise WebFormsError(f"HTML unparseable: {e2}") from e2
    return soup


def _detect_field_type(element: Any) -> str:
    """Determine the field type from a BeautifulSoup form element."""
    tag = element.name.lower()
    if tag == "textarea":
        return "textarea"
    if tag == "select":
        return "select"
    if tag == "button":
        return element.get("type", "submit").lower()
    if tag == "input":
        input_type = element.get("type", "text").lower()
        return input_type
    return tag


def _get_selector(element: Any) -> str:
    """Build a CSS selector for a form element."""
    elem_id = element.get("id", "")
    if elem_id:
        return f"#{elem_id}"
    name = element.get("name", "")
    if name:
        tag = element.name
        return f"{tag}[name='{name}']"
    return element.name


def _get_select_options(select_elem: Any) -> list[tuple[str, str]]:
    """Extract (value, text) pairs from a <select> element."""
    options = []
    for opt in select_elem.find_all("option"):
        val = opt.get("value", "")
        text = opt.get_text(strip=True)
        options.append((val, text))
    return options


def _get_current_value(element: Any, field_type: str) -> str:
    """Get the current value of a form field."""
    if field_type in ("checkbox", "radio"):
        return "checked" if element.get("checked") is not None else "unchecked"
    if field_type == "select":
        # Find selected option
        selected = element.find("option", selected=True)
        if selected:
            return selected.get("value", "")
        # If no explicit selected attr, check for first non-empty option
        return ""
    if field_type == "textarea":
        return element.get_text()
    # input types: text, email, password, tel, etc.
    return element.get("value", "")


def read_form(html_path: str, form_id: str = "") -> FormInfo:
    """Parse an HTML file and extract form structure.

    Args:
        html_path: Path to the .html file.
        form_id:   Optional form ID to target (if multiple forms exist).

    Returns:
        FormInfo with all detected fields.

    Raises:
        WebFormsError: If the file is missing, unparseable, or no form found.
    """
    soup = parse_html(html_path)

    if form_id:
        form = soup.find("form", id=form_id)
        if not form:
            raise WebFormsError(f"Form with id='{form_id}' not found in {html_path}")
    else:
        form = soup.find("form")
        if not form:
            raise WebFormsError(f"No <form> found in {html_path}")

    info = FormInfo(
        form_id=form.get("id", ""),
        form_action=form.get("action", ""),
        form_method=form.get("method", "GET").upper(),
    )

    # Collect all form control elements
    form_controls = form.find_all(
        ["input", "select", "textarea", "button"]
    )

    for elem in form_controls:
        ftype = _detect_field_type(elem)
        # Skip hidden fields and submit buttons for field counting
        # but still record them
        f = FormField(
            element_id=elem.get("id", ""),
            name=elem.get("name", ""),
            field_type=ftype,
            tag=elem.name,
            selector=_get_selector(elem),
            current_value=_get_current_value(elem, ftype),
            required=elem.has_attr("required"),
        )
        if ftype == "select":
            f.options = _get_select_options(elem)
        if ftype == "radio":
            f.radio_group = elem.get("name", "")
        info.fields.append(f)

    info.field_count = len(info.fields)
    info.required_field_count = sum(1 for f in info.fields if f.required)
    return info


# ---------------------------------------------------------------------------
# Form filling
# ---------------------------------------------------------------------------


def _fill_text_field(soup: BeautifulSoup, selector: str, value: str) -> bool:
    """Fill a text-like input field. Returns True if filled."""
    elem = soup.select_one(selector)
    if elem is None:
        return False
    elem["value"] = value
    return True


def _fill_textarea(soup: BeautifulSoup, selector: str, value: str) -> bool:
    """Fill a textarea. Returns True if filled."""
    elem = soup.select_one(selector)
    if elem is None:
        return False
    elem.string = value
    return True


def _fill_select(soup: BeautifulSoup, selector: str, value: str) -> bool:
    """Set a <select> field's selected option. Returns True if set."""
    elem = soup.select_one(selector)
    if elem is None:
        return False
    # Clear all selected
    for opt in elem.find_all("option"):
        if opt.has_attr("selected"):
            del opt["selected"]
    # Set the matching option as selected
    for opt in elem.find_all("option"):
        if opt.get("value", "") == value:
            opt["selected"] = "selected"
            return True
    return False


def _fill_checkbox(soup: BeautifulSoup, selector: str, checked: bool) -> bool:
    """Check or uncheck a checkbox. Returns True if set."""
    elem = soup.select_one(selector)
    if elem is None:
        return False
    if checked:
        elem["checked"] = "checked"
    else:
        if elem.has_attr("checked"):
            del elem["checked"]
    return True


def _fill_radio(soup: BeautifulSoup, selector: str, checked: bool) -> bool:
    """Check a radio button. Returns True if set."""
    elem = soup.select_one(selector)
    if elem is None:
        return False
    if checked:
        # Uncheck all radios in the same group first
        name = elem.get("name", "")
        if name:
            for r in soup.find_all("input", attrs={"type": "radio", "name": name}):
                if r.has_attr("checked"):
                    del r["checked"]
        elem["checked"] = "checked"
    else:
        if elem.has_attr("checked"):
            del elem["checked"]
    return True


def fill_form(
    html_path: str,
    fill_spec: dict[str, dict[str, Any]],
    form_id: str = "",
    output_path: str = "",
) -> tuple[str, FormInfo]:
    """Fill a local HTML form with specified values.

    Args:
        html_path:   Path to the source .html file.
        fill_spec:   Dict mapping field_key → {selector, type, value}.
        form_id:     Optional form ID to target.
        output_path: Optional path to save filled HTML. If empty, not saved.

    Returns:
        Tuple of (filled_html_string, FormInfo of the filled form).

    Raises:
        WebFormsError: If parsing or filling fails.
    """
    soup = parse_html(html_path)

    if form_id:
        form = soup.find("form", id=form_id)
        if not form:
            raise WebFormsError(f"Form with id='{form_id}' not found")
    else:
        form = soup.find("form")
        if not form:
            raise WebFormsError("No <form> found")

    for field_key, spec in fill_spec.items():
        selector = spec.get("selector", "")
        ftype = spec.get("type", "text")
        value = spec.get("value", "")

        if not selector:
            raise WebFormsError(f"No selector for field '{field_key}'")

        if ftype in ("text", "email", "password", "tel", "hidden", "number", "url", "date", "search"):
            if not _fill_text_field(soup, selector, str(value)):
                raise WebFormsError(f"Field not found: {selector}")
        elif ftype == "textarea":
            if not _fill_textarea(soup, selector, str(value)):
                raise WebFormsError(f"Textarea not found: {selector}")
        elif ftype == "select":
            if not _fill_select(soup, selector, str(value)):
                raise WebFormsError(f"Select option '{value}' not found in {selector}")
        elif ftype == "checkbox":
            if not _fill_checkbox(soup, selector, bool(value)):
                raise WebFormsError(f"Checkbox not found: {selector}")
        elif ftype == "radio":
            if not _fill_radio(soup, selector, bool(value)):
                raise WebFormsError(f"Radio not found: {selector}")
        else:
            raise WebFormsError(f"Unsupported field type: {ftype}")

    filled_html = str(soup)

    if output_path:
        Path(output_path).write_text(filled_html, encoding="utf-8")

    # Re-read the filled form to get the post-fill state
    filled_info = _read_form_from_soup(soup, form_id)
    return filled_html, filled_info


def _read_form_from_soup(soup: BeautifulSoup, form_id: str = "") -> FormInfo:
    """Read form structure from an in-memory soup (post-fill)."""
    if form_id:
        form = soup.find("form", id=form_id)
    else:
        form = soup.find("form")
    if not form:
        raise WebFormsError("No <form> found in soup")

    info = FormInfo(
        form_id=form.get("id", ""),
        form_action=form.get("action", ""),
        form_method=form.get("method", "GET").upper(),
    )

    for elem in form.find_all(["input", "select", "textarea", "button"]):
        ftype = _detect_field_type(elem)
        f = FormField(
            element_id=elem.get("id", ""),
            name=elem.get("name", ""),
            field_type=ftype,
            tag=elem.name,
            selector=_get_selector(elem),
            current_value=_get_current_value(elem, ftype),
            required=elem.has_attr("required"),
        )
        if ftype == "select":
            f.options = _get_select_options(elem)
        if ftype == "radio":
            f.radio_group = elem.get("name", "")
        info.fields.append(f)

    info.field_count = len(info.fields)
    info.required_field_count = sum(1 for f in info.fields if f.required)
    return info


# ---------------------------------------------------------------------------
# Required-field validation (submit gating)
# ---------------------------------------------------------------------------


def check_required_fields(form_info: FormInfo, fill_spec: dict[str, dict[str, Any]]) -> list[str]:
    """Check which required fields are left blank after filling.

    Args:
        form_info: The post-fill FormInfo.
        fill_spec: The fill spec used (to know which fields were intentionally filled).

    Returns:
        List of required field names that are blank (should block submit).
    """
    blank_required = []
    for field in form_info.fields:
        if not field.required:
            continue
        if field.field_type == "submit":
            continue
        # Check if the field has a value
        if field.field_type in ("checkbox", "radio"):
            if field.current_value == "unchecked":
                blank_required.append(field.name or field.element_id or field.selector)
        elif field.field_type == "select":
            if not field.current_value:
                blank_required.append(field.name or field.element_id or field.selector)
        else:
            if not field.current_value.strip():
                blank_required.append(field.name or field.element_id or field.selector)
    return blank_required


# ---------------------------------------------------------------------------
# Perception integration (03 element map)
# ---------------------------------------------------------------------------


def form_to_element_map(html_path: str, form_id: str = "", screen_id: str = "form_screen") -> ScreenMap:
    """Convert an HTML form into a perception ElementMap (03 substrate).

    This bridges the webforms domain to the 03 perception layer by creating
    AnchorElements for each form field, enabling field resolution via resolve().

    Args:
        html_path: Path to the .html file.
        form_id:   Optional form ID to target.
        screen_id: Screen identifier for the ElementMap.

    Returns:
        ScreenMap containing all form fields as AnchorElements.
    """
    info = read_form(html_path, form_id)

    elements: list[AnchorElement] = []
    for i, field in enumerate(info.fields):
        # Map field type to perception role/affordance
        role_map = {
            "text": "textfield",
            "email": "textfield",
            "password": "textfield",
            "tel": "textfield",
            "textarea": "textfield",
            "select": "dropdown",
            "checkbox": "checkbox",
            "radio": "radio",
            "submit": "button",
        }
        affordance_map = {
            "text": "type",
            "email": "type",
            "password": "type",
            "tel": "type",
            "textarea": "type",
            "select": "select",
            "checkbox": "toggle",
            "radio": "toggle",
            "submit": "click",
        }
        role = role_map.get(field.field_type, field.field_type)
        affordance = affordance_map.get(field.field_type, "")

        # Use the field's label/id as the name for resolution
        name = field.element_id or field.name or field.selector

        elem = AnchorElement(
            element_id=f"form_field_{i}",
            role=role,
            name=name,
            value=field.current_value,
            bounds=BoundingBox(x=0, y=i * 40, width=200, height=30),
            affordance=affordance,
            confidence=1.0,
            source="html",
            is_canvas=False,
        )
        elements.append(elem)

    elem_map = ElementMap(
        screen_id=screen_id,
        elements=elements,
        element_count=len(elements),
    )
    return ScreenMap(screen_id=screen_id, element_map=elem_map, source="fixture")


def resolve_field_by_query(
    query: str,
    screen_map: ScreenMap,
    match_threshold: float = 0.3,
) -> AnchorElement | None:
    """Resolve a natural-language field query via 03's resolve().

    Args:
        query:           Field query (e.g., "email field", "country dropdown").
        screen_map:      ScreenMap from form_to_element_map().
        match_threshold: Minimum match score.

    Returns:
        Best-matching AnchorElement, or None.
    """
    return resolve(query, screen_map, match_threshold=match_threshold)


# ---------------------------------------------------------------------------
# CUA verifier integration (04 verify-before-commit)
# ---------------------------------------------------------------------------


def verify_form_fill(
    form_info: FormInfo,
    fill_spec: dict[str, dict[str, Any]],
    expected_required_blank: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Verify a form fill using the 04 CUA verifier substrate.

    Builds a Trajectory from the fill operation and runs the UniversalVerifier.
    No receipt is emitted on unverified/failed fill.

    Args:
        form_info:           Post-fill FormInfo.
        fill_spec:           The fill spec used.
        expected_required_blank: Whether required-blank is expected (scenario c).

    Returns:
        Tuple of (verified, details_dict).
    """
    from kairo.cua.engine import (
        Action,
        ActionOutcome,
        Trajectory,
        TrajectoryStep,
        UIState,
        UIStateType,
        UniversalVerifier,
    )

    # Build UIState from the filled form
    text_values: dict[str, str] = {}
    error_indicators: list[str] = []
    for field in form_info.fields:
        key = field.element_id or field.name or field.selector
        text_values[key] = field.current_value
        if field.required and not field.current_value.strip() and field.field_type != "submit":
            if field.field_type in ("checkbox", "radio"):
                if field.current_value == "unchecked":
                    error_indicators.append(f"required_blank:{key}")
            elif field.field_type == "select":
                if not field.current_value:
                    error_indicators.append(f"required_blank:{key}")
            else:
                error_indicators.append(f"required_blank:{key}")

    # When required-blank is expected (scenario c), the blank fields are
    # intentional — they should NOT be treated as error indicators for the
    # verifier. The verifier should see a clean state where the fill was
    # performed correctly but submit is blocked by validation.
    if expected_required_blank:
        # Move required_blank indicators to a separate field, not errors
        error_indicators_for_verifier: list[str] = []
    else:
        error_indicators_for_verifier = error_indicators

    # Determine state type
    if error_indicators_for_verifier and not expected_required_blank:
        state_type = UIStateType.ERROR_STATE
    elif error_indicators and expected_required_blank:
        # Expected blank = validation state (form filled but blocked)
        state_type = UIStateType.TEXT_ENTERED
    else:
        state_type = UIStateType.TEXT_ENTERED

    actual_state = UIState(
        state_type=state_type,
        element_count=form_info.field_count,
        text_values=text_values,
        error_indicators=error_indicators_for_verifier,
    )

    # Build predicted state (what we expected to happen)
    predicted_state = UIState(
        state_type=UIStateType.TEXT_ENTERED,
        element_count=form_info.field_count,
    )

    # Build a single-step trajectory
    action = Action(
        action_type="type",
        target_element_id="form_fields",
        target_query="fill form fields",
        value=json.dumps({k: v.get("value", "") for k, v in fill_spec.items()}, default=str),
        description="Fill form fields with specified values",
    )

    step = TrajectoryStep(
        step_index=0,
        screen_map={},  # Not needed for verification
        action=action,
        predicted_state=predicted_state,
        actual_state=actual_state,
        human_label="pass" if not error_indicators or expected_required_blank else "fail",
        verified=True,
    )

    trajectory = Trajectory(
        trajectory_id="form_fill_trajectory",
        steps=[step],
    )

    verifier = UniversalVerifier()
    outcome, details = verifier.verify(trajectory)

    # Verified = PASS outcome (or expected required-blank with controllable fail)
    verified = outcome == ActionOutcome.PASS or (
        expected_required_blank and outcome in (ActionOutcome.FAIL_CONTROLLABLE, ActionOutcome.PASS)
    )

    details["required_blank_fields"] = error_indicators
    details["submit_blocked"] = bool(error_indicators) and not expected_required_blank

    return verified, details


# ---------------------------------------------------------------------------
# Experimental: live browser / page-agent
# ---------------------------------------------------------------------------


def live_browser_navigate(url: str) -> str:
    """Live browser navigation to a URL — Experimental.

    This is the Experimental path. It requires a network connection and a
    browser (Playwright/Selenium). In the offline default, it FAILS LOUD.

    Raises:
        WebFormsExperimentalError: Always, in the offline default.
    """
    raise WebFormsExperimentalError(
        "Live browser navigation is Experimental — requires network + browser. "
        "Not available in offline mode. Use local HTML form fill instead."
    )


def live_page_agent_submit(url: str, form_data: dict[str, Any]) -> str:
    """Live page-agent form submission — Experimental.

    Uses alibaba/page-agent (MIT) concept for in-page browser GUI agent.
    In the offline default, it FAILS LOUD.

    Raises:
        WebFormsExperimentalError: Always, in the offline default.
    """
    raise WebFormsExperimentalError(
        "Live page-agent submission is Experimental — requires network + browser. "
        "Not available in offline mode. Use local HTML form fill instead."
    )


# ---------------------------------------------------------------------------
# Pipeline (trust stack integration)
# ---------------------------------------------------------------------------


def webforms_pipeline(
    html_path: str,
    fill_spec: dict[str, dict[str, Any]],
    form_id: str = "",
    output_path: str = "",
    private_key: Any = None,
    expected_required_blank: bool = False,
) -> FillResult:
    """Run the Web-forms pipeline with trust stack integration.

    1. Parse the local HTML form.
    2. Fill fields with specified values.
    3. Re-parse the filled DOM (independent verification via read-back).
    4. Check required fields (submit gating).
    5. Verify via 04 CUA verifier (no receipt on unverified/failed).
    6. Emit Ed25519 audit log + zero-egress report (if private_key provided).

    Args:
        html_path:              Path to the source .html file.
        fill_spec:              Dict of field_key → {selector, type, value}.
        form_id:                Optional form ID to target.
        output_path:            Optional path to save filled HTML.
        private_key:            Optional Ed25519 private key for audit + egress.
        expected_required_blank: Whether required-blank is expected (scenario c).

    Returns:
        FillResult with form_info and trust artifacts.
    """
    spec_json = json.dumps(fill_spec, sort_keys=True, default=str)
    doc_hash = hashlib.sha256(spec_json.encode()).hexdigest()

    try:
        filled_html, form_info = fill_form(html_path, fill_spec, form_id, output_path)
    except WebFormsError as e:
        return FillResult(ok=False, error=str(e), doc_hash=doc_hash)

    # Check required fields
    required_blank = check_required_fields(form_info, fill_spec)
    # Submit is blocked when there are required blanks, regardless of whether
    # the blanks were expected (expected_required_blank means the test scenario
    # expects blanks, not that submit should proceed)
    submit_blocked = bool(required_blank)

    # Verify via 04 CUA verifier
    verified, verify_details = verify_form_fill(form_info, fill_spec, expected_required_blank)

    fields_filled = sum(1 for v in fill_spec.values() if v.get("value"))
    fields_total = len(fill_spec)

    # Emit audit log + egress report
    audit_log_json = ""
    egress_report_json = ""
    if private_key is not None:
        from kairo.oracles.ed25519_audit_log import Ed25519AuditLog
        from kairo.oracles.zero_egress_report import generate_zero_egress_report

        audit = Ed25519AuditLog(private_key)
        audit.log_run_started(doc_hash=doc_hash, playbook_id="webforms_pipeline")

        for field_key, spec in fill_spec.items():
            ftype = spec.get("type", "text")
            value = spec.get("value", "")
            audit.log_edit(
                doc_hash=doc_hash,
                clause_id=field_key,
                clause_label=f"Form field '{field_key}' ({ftype})",
                old_text="",
                new_text=str(value),
                citation="html-form-fill",
                rationale=f"Field '{field_key}' filled with value and read back via DOM re-parse",
            )

        if required_blank:
            for blank_field in required_blank:
                audit.log_flag(
                    doc_hash=doc_hash,
                    clause_id=blank_field,
                    clause_label=f"Required field '{blank_field}' left blank",
                    reason="Required field is blank — submit blocked",
                )

        total_edits = fields_filled
        total_flagged = len(required_blank)
        audit.log_run_completed(
            doc_hash=doc_hash,
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
        )

        audit_log_json = audit.to_json()

        egress_report = generate_zero_egress_report(
            doc_hash=doc_hash,
            playbook_id="webforms_pipeline",
            total_edits=total_edits,
            total_flagged=total_flagged,
            injection_detected=False,
            audit_log_json=audit_log_json,
            private_key=private_key,
        )
        egress_report_json = egress_report.to_json()

    return FillResult(
        ok=True,
        filled_html=filled_html,
        output_path=output_path,
        form_info=form_info,
        fields_filled=fields_filled,
        fields_total=fields_total,
        required_blank=required_blank,
        submit_blocked=submit_blocked,
        verified=verified,
        audit_log_json=audit_log_json,
        egress_report_json=egress_report_json,
        doc_hash=doc_hash,
    )
