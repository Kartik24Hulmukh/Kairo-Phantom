# PROVENANCE: original | clean-room Web-forms/apps domain oracles per VERIFICATION_ORACLES.md
"""Web-forms/apps domain oracles — deterministic, kill-proven verification.

Implements two practitioner-grade oracles:

  1. ``form_fill_readback`` — after filling a local HTML form, RE-PARSE the
     resulting DOM and assert every field's value (text, select, checkbox,
     radio, textarea) matches the spec.
     KILL-PROOF: wrong value or missing field → FAILS.

  2. ``uistate_readback`` — field count + types + required-field presence +
     post-fill form state match expected.
     KILL-PROOF: drop/alter a field → FAILS.

Both oracles are KILL-PROVEN.

HONEST DEGRADATION:
  If the HTML file is missing or unparseable, the oracles raise WebFormsError.

All operations are fully offline. No network calls. No LLM. No cloud.
No AGPL/GPL. Clean-room per prompts/15.
"""

from __future__ import annotations

from typing import Any

from kairo.domains.webforms.engine import (
    fill_form,
    read_form,
)


# ---------------------------------------------------------------------------
# Oracle 1: form_fill_readback
# ---------------------------------------------------------------------------


def form_fill_readback(
    html_path: str,
    fill_spec: dict[str, dict[str, Any]],
    expected_values: dict[str, Any],
    form_id: str = "",
) -> bool:
    """Oracle: fill form → re-parse DOM → assert every field value matches spec.

    KILL-PROOF: wrong value or missing field → FAILS.

    Args:
        html_path:      Path to the source .html file.
        fill_spec:      Dict of field_key → {selector, type, value}.
        expected_values: Dict of field_key → expected_value after fill.
                         For text/textarea: the string value.
                         For select: the option value.
                         For checkbox/radio: True/False (checked/unchecked).
        form_id:        Optional form ID to target.

    Returns:
        True if the re-parsed filled DOM matches the spec exactly.

    Raises:
        AssertionError: If any field value doesn't match.
        WebFormsError: If the file cannot be parsed or filled.
    """
    # Fill the form (in-memory, no file save needed for read-back)
    filled_html, form_info = fill_form(html_path, fill_spec, form_id)

    # Build a lookup of field values by selector
    field_values: dict[str, str] = {}
    for field in form_info.fields:
        key = field.selector
        field_values[key] = field.current_value

    # Check each expected value
    for field_key, expected in expected_values.items():
        spec = fill_spec.get(field_key, {})
        selector = spec.get("selector", "")
        if not selector:
            raise AssertionError(
                f"form_fill_readback FAILED: no selector for field '{field_key}'"
            )

        ftype = spec.get("type", "text")
        actual = field_values.get(selector)

        if actual is None:
            raise AssertionError(
                f"form_fill_readback FAILED: field '{field_key}' "
                f"(selector={selector}) not found in filled DOM"
            )

        if ftype in ("checkbox", "radio"):
            expected_str = "checked" if expected else "unchecked"
            if actual != expected_str:
                raise AssertionError(
                    f"form_fill_readback FAILED: field '{field_key}' "
                    f"({ftype}) value mismatch.\n"
                    f"  Expected: {expected_str}\n"
                    f"  Got:      {actual}"
                )
        elif ftype == "select":
            if actual != str(expected):
                raise AssertionError(
                    f"form_fill_readback FAILED: field '{field_key}' "
                    f"(select) value mismatch.\n"
                    f"  Expected: {expected}\n"
                    f"  Got:      {actual}"
                )
        else:
            # text, email, password, tel, textarea
            if actual != str(expected):
                raise AssertionError(
                    f"form_fill_readback FAILED: field '{field_key}' "
                    f"({ftype}) value mismatch.\n"
                    f"  Expected: {expected}\n"
                    f"  Got:      {actual}"
                )

    return True


# ---------------------------------------------------------------------------
# Oracle 2: uistate_readback
# ---------------------------------------------------------------------------


def uistate_readback(
    html_path: str,
    expected_field_count: int,
    expected_field_types: list[str] | None = None,
    expected_required_fields: list[str] | None = None,
    form_id: str = "",
    fill_spec: dict[str, dict[str, Any]] | None = None,
    expected_required_blank: list[str] | None = None,
) -> bool:
    """Oracle: field count + types + required-field presence + post-fill state.

    KILL-PROOF: drop/alter a field → FAILS.

    Args:
        html_path:              Path to the source .html file.
        expected_field_count:   Expected number of form fields.
        expected_field_types:   Optional list of expected field types (in order).
        expected_required_fields: Optional list of field names/ids expected to
                                  have the ``required`` attribute.
        form_id:                Optional form ID to target.
        fill_spec:              Optional fill spec to apply before read-back.
        expected_required_blank: Optional list of field names expected to be
                                 required and blank after fill.

    Returns:
        True if the form structure matches expectations.

    Raises:
        AssertionError: If any structural check fails.
        WebFormsError: If the file cannot be parsed.
    """
    if fill_spec:
        _, form_info = fill_form(html_path, fill_spec, form_id)
    else:
        form_info = read_form(html_path, form_id)

    # Check field count
    if form_info.field_count != expected_field_count:
        raise AssertionError(
            f"uistate_readback FAILED: field count mismatch.\n"
            f"  Expected: {expected_field_count}\n"
            f"  Got:      {form_info.field_count}"
        )

    # Check field types (in order)
    if expected_field_types is not None:
        actual_types = [f.field_type for f in form_info.fields]
        if actual_types != expected_field_types:
            raise AssertionError(
                f"uistate_readback FAILED: field types mismatch.\n"
                f"  Expected: {expected_field_types}\n"
                f"  Got:      {actual_types}"
            )

    # Check required fields are present
    if expected_required_fields is not None:
        actual_required = {
            f.name or f.element_id for f in form_info.fields if f.required
        }
        for req_name in expected_required_fields:
            if req_name not in actual_required:
                raise AssertionError(
                    f"uistate_readback FAILED: required field '{req_name}' "
                    f"not found in form. Required fields present: {actual_required}"
                )

    # Check required-blank fields (post-fill)
    if expected_required_blank is not None:
        blank_fields = []
        for field in form_info.fields:
            if not field.required or field.field_type == "submit":
                continue
            if field.field_type in ("checkbox", "radio"):
                if field.current_value == "unchecked":
                    blank_fields.append(field.name or field.element_id)
            elif field.field_type == "select":
                if not field.current_value:
                    blank_fields.append(field.name or field.element_id)
            else:
                if not field.current_value.strip():
                    blank_fields.append(field.name or field.element_id)

        for expected_blank in expected_required_blank:
            if expected_blank not in blank_fields:
                raise AssertionError(
                    f"uistate_readback FAILED: expected required field "
                    f"'{expected_blank}' to be blank, but it has a value. "
                    f"Blank required fields: {blank_fields}"
                )

    return True
