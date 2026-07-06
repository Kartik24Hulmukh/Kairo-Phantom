# PROVENANCE: original | Web-forms/apps domain oracle tests per VERIFICATION_ORACLES.md
"""Web-forms/apps domain oracle tests — form_fill_readback + uistate_readback + kill-proofs.

Tests verify:
  1. form_fill_readback: after filling a local HTML form, re-parse DOM and
     assert every field's value matches spec. Kill-proof: wrong value → FAILS.
  2. uistate_readback: field count + types + required-field presence + post-fill
     state match expected. Kill-proof: drop/alter a field → FAILS.
  3. Honest degradation: HTML unparseable → fail loud; live browser/page-agent
     requested but unavailable → fail loud (Experimental).
  4. >=3 gauntlet scenarios: (a) text+email+password, (b) select+checkbox+radio,
     (c) required field left blank → correctly flagged (not silently submitted).
  5. Trust stack integration: audit log + egress report.
  6. CLI integration: webforms subcommand works end-to-end.
  7. Perception integration: field resolution via 03 element map.
  8. CUA verifier integration: submit gated by 04 verifier.

All tests run fully offline. No mocks on production paths. Zero skips.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kairo.domains.webforms.engine import (  # noqa: E402
    WebFormsError,
    WebFormsExperimentalError,
    fill_form,
    form_to_element_map,
    live_browser_navigate,
    live_page_agent_submit,
    read_form,
    resolve_field_by_query,
    verify_form_fill,
    webforms_pipeline,
)
from kairo.domains.webforms.oracles import (  # noqa: E402
    form_fill_readback,
    uistate_readback,
)

# Fixture paths
_FIX = os.path.join(_REPO_ROOT, "kairo", "domains", "webforms", "fixtures")
_TEXT_HTML = os.path.join(_FIX, "form_text_fields.html")
_SELECT_HTML = os.path.join(_FIX, "form_select_checkbox_radio.html")
_REQUIRED_HTML = os.path.join(_FIX, "form_required_blank.html")
_GT_JSON = os.path.join(_FIX, "ground_truth.json")


def _load_ground_truth() -> dict:
    with open(_GT_JSON, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Oracle 1: form_fill_readback
# ---------------------------------------------------------------------------


class TestFormFillReadback:
    """form_fill_readback oracle — fill, re-parse, verify all field values."""

    def test_text_fields_readback(self):
        """Fill text+email+password fields, re-parse, verify all match."""
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "johndoe123"},
            "email": {"selector": "#email", "type": "email", "value": "john.doe@example.com"},
            "password": {"selector": "#password", "type": "password", "value": "SecurePass!2024"},
            "confirm_password": {"selector": "#confirm_password", "type": "password", "value": "SecurePass!2024"},
            "phone": {"selector": "#phone", "type": "tel", "value": "+1-555-0123"},
        }
        expected = {
            "username": "johndoe123",
            "email": "john.doe@example.com",
            "password": "SecurePass!2024",
            "confirm_password": "SecurePass!2024",
            "phone": "+1-555-0123",
        }
        result = form_fill_readback(_TEXT_HTML, fill_spec, expected, "registration_form")
        assert result is True

    def test_select_readback(self):
        """Fill a select field, re-parse, verify selected option matches."""
        fill_spec = {
            "country": {"selector": "#country", "type": "select", "value": "de"},
        }
        expected = {"country": "de"}
        result = form_fill_readback(_SELECT_HTML, fill_spec, expected, "survey_form")
        assert result is True

    def test_checkbox_readback(self):
        """Fill checkboxes, re-parse, verify checked state matches."""
        fill_spec = {
            "interest_tech": {"selector": "#interest_tech", "type": "checkbox", "value": True},
            "interest_sports": {"selector": "#interest_sports", "type": "checkbox", "value": False},
            "interest_music": {"selector": "#interest_music", "type": "checkbox", "value": True},
        }
        expected = {
            "interest_tech": True,
            "interest_sports": False,
            "interest_music": True,
        }
        result = form_fill_readback(_SELECT_HTML, fill_spec, expected, "survey_form")
        assert result is True

    def test_radio_readback(self):
        """Fill a radio group, re-parse, verify checked radio matches."""
        fill_spec = {
            "plan_pro": {"selector": "#plan_pro", "type": "radio", "value": True},
        }
        expected = {"plan_pro": True}
        result = form_fill_readback(_SELECT_HTML, fill_spec, expected, "survey_form")
        assert result is True

    def test_textarea_readback(self):
        """Fill a textarea, re-parse, verify content matches."""
        fill_spec = {
            "feedback": {"selector": "#feedback", "type": "textarea", "value": "Great product!"},
        }
        expected = {"feedback": "Great product!"}
        result = form_fill_readback(_SELECT_HTML, fill_spec, expected, "survey_form")
        assert result is True

    def test_all_field_types_readback(self):
        """Fill all field types at once, verify all match."""
        fill_spec = {
            "country": {"selector": "#country", "type": "select", "value": "uk"},
            "plan_pro": {"selector": "#plan_pro", "type": "radio", "value": True},
            "interest_tech": {"selector": "#interest_tech", "type": "checkbox", "value": True},
            "interest_music": {"selector": "#interest_music", "type": "checkbox", "value": True},
            "feedback": {"selector": "#feedback", "type": "textarea", "value": "Love it!"},
            "newsletter": {"selector": "#newsletter", "type": "checkbox", "value": True},
        }
        expected = {
            "country": "uk",
            "plan_pro": True,
            "interest_tech": True,
            "interest_music": True,
            "feedback": "Love it!",
            "newsletter": True,
        }
        result = form_fill_readback(_SELECT_HTML, fill_spec, expected, "survey_form")
        assert result is True


# ---------------------------------------------------------------------------
# Oracle 1 Kill-Proofs
# ---------------------------------------------------------------------------


class TestFormFillReadbackKillProofs:
    """Kill-proofs: perturbing expected values → FAILS."""

    def test_kill_wrong_text_value(self):
        """Kill-proof: wrong text value → readback FAILS."""
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "johndoe123"},
        }
        wrong_expected = {"username": "WRONG_VALUE"}
        with pytest.raises(AssertionError, match="value mismatch"):
            form_fill_readback(_TEXT_HTML, fill_spec, wrong_expected, "registration_form")

    def test_kill_wrong_select_value(self):
        """Kill-proof: wrong select value → readback FAILS."""
        fill_spec = {
            "country": {"selector": "#country", "type": "select", "value": "de"},
        }
        wrong_expected = {"country": "us"}
        with pytest.raises(AssertionError, match="value mismatch"):
            form_fill_readback(_SELECT_HTML, fill_spec, wrong_expected, "survey_form")

    def test_kill_wrong_checkbox_state(self):
        """Kill-proof: wrong checkbox state → readback FAILS."""
        fill_spec = {
            "interest_tech": {"selector": "#interest_tech", "type": "checkbox", "value": True},
        }
        wrong_expected = {"interest_tech": False}
        with pytest.raises(AssertionError, match="value mismatch"):
            form_fill_readback(_SELECT_HTML, fill_spec, wrong_expected, "survey_form")

    def test_kill_wrong_radio_state(self):
        """Kill-proof: wrong radio state → readback FAILS."""
        fill_spec = {
            "plan_pro": {"selector": "#plan_pro", "type": "radio", "value": True},
        }
        wrong_expected = {"plan_pro": False}
        with pytest.raises(AssertionError, match="value mismatch"):
            form_fill_readback(_SELECT_HTML, fill_spec, wrong_expected, "survey_form")

    def test_kill_missing_field(self):
        """Kill-proof: expected field not in filled DOM → FAILS."""
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "johndoe123"},
        }
        wrong_expected = {"nonexistent": "value"}
        with pytest.raises(AssertionError, match="no selector for field"):
            form_fill_readback(_TEXT_HTML, fill_spec, wrong_expected, "registration_form")

    def test_kill_wrong_textarea_value(self):
        """Kill-proof: wrong textarea content → readback FAILS."""
        fill_spec = {
            "feedback": {"selector": "#feedback", "type": "textarea", "value": "Original text"},
        }
        wrong_expected = {"feedback": "TAMPERED"}
        with pytest.raises(AssertionError, match="value mismatch"):
            form_fill_readback(_SELECT_HTML, fill_spec, wrong_expected, "survey_form")


# ---------------------------------------------------------------------------
# Oracle 2: uistate_readback
# ---------------------------------------------------------------------------


class TestUIStateReadback:
    """uistate_readback oracle — field count + types + required + post-fill state."""

    def test_field_count_text_form(self):
        """Text form has correct field count."""
        result = uistate_readback(_TEXT_HTML, expected_field_count=6, form_id="registration_form")
        assert result is True

    def test_field_count_select_form(self):
        """Select/checkbox/radio form has correct field count."""
        result = uistate_readback(_SELECT_HTML, expected_field_count=11, form_id="survey_form")
        assert result is True

    def test_field_types_text_form(self):
        """Text form has correct field types in order."""
        result = uistate_readback(
            _TEXT_HTML,
            expected_field_count=6,
            expected_field_types=["text", "email", "password", "password", "tel", "submit"],
            form_id="registration_form",
        )
        assert result is True

    def test_field_types_select_form(self):
        """Select form has correct field types in order."""
        result = uistate_readback(
            _SELECT_HTML,
            expected_field_count=11,
            expected_field_types=["select", "radio", "radio", "radio", "checkbox", "checkbox", "checkbox", "checkbox", "textarea", "checkbox", "submit"],
            form_id="survey_form",
        )
        assert result is True

    def test_required_fields_present(self):
        """Required fields are correctly detected."""
        result = uistate_readback(
            _TEXT_HTML,
            expected_field_count=6,
            expected_required_fields=["username", "email", "password", "confirm_password"],
            form_id="registration_form",
        )
        assert result is True

    def test_required_fields_contact_form(self):
        """Contact form required fields are correctly detected."""
        result = uistate_readback(
            _REQUIRED_HTML,
            expected_field_count=7,
            expected_required_fields=["name", "email", "subject", "message"],
            form_id="contact_form",
        )
        assert result is True

    def test_post_fill_state(self):
        """Post-fill state: filled values are present in read-back."""
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "testuser"},
            "email": {"selector": "#email", "type": "email", "value": "test@test.com"},
        }
        result = uistate_readback(
            _TEXT_HTML,
            expected_field_count=6,
            form_id="registration_form",
            fill_spec=fill_spec,
        )
        assert result is True

    def test_required_blank_detected(self):
        """Required blank fields are correctly detected after fill."""
        fill_spec = {
            "name": {"selector": "#name", "type": "text", "value": ""},
            "email": {"selector": "#email", "type": "email", "value": "jane@example.com"},
            "subject": {"selector": "#subject", "type": "text", "value": ""},
            "message": {"selector": "#message", "type": "textarea", "value": "Hello"},
        }
        result = uistate_readback(
            _REQUIRED_HTML,
            expected_field_count=7,
            form_id="contact_form",
            fill_spec=fill_spec,
            expected_required_blank=["name", "subject"],
        )
        assert result is True


# ---------------------------------------------------------------------------
# Oracle 2 Kill-Proofs
# ---------------------------------------------------------------------------


class TestUIStateReadbackKillProofs:
    """Kill-proofs: wrong structure → FAILS."""

    def test_kill_wrong_field_count(self):
        """Kill-proof: wrong field count → FAILS."""
        with pytest.raises(AssertionError, match="field count mismatch"):
            uistate_readback(_TEXT_HTML, expected_field_count=99, form_id="registration_form")

    def test_kill_wrong_field_types(self):
        """Kill-proof: wrong field types → FAILS."""
        with pytest.raises(AssertionError, match="field types mismatch"):
            uistate_readback(
                _TEXT_HTML,
                expected_field_count=6,
                expected_field_types=["email", "text", "password", "password", "tel", "submit"],
                form_id="registration_form",
            )

    def test_kill_missing_required_field(self):
        """Kill-proof: expected required field not present → FAILS."""
        with pytest.raises(AssertionError, match="required field.*not found"):
            uistate_readback(
                _TEXT_HTML,
                expected_field_count=6,
                expected_required_fields=["nonexistent_field"],
                form_id="registration_form",
            )

    def test_kill_expected_blank_not_blank(self):
        """Kill-proof: expected blank field has a value → FAILS."""
        fill_spec = {
            "name": {"selector": "#name", "type": "text", "value": "filled_in"},
            "email": {"selector": "#email", "type": "email", "value": "jane@example.com"},
            "subject": {"selector": "#subject", "type": "text", "value": "filled_subject"},
            "message": {"selector": "#message", "type": "textarea", "value": "Hello"},
        }
        with pytest.raises(AssertionError, match="expected required field.*to be blank"):
            uistate_readback(
                _REQUIRED_HTML,
                expected_field_count=7,
                form_id="contact_form",
                fill_spec=fill_spec,
                expected_required_blank=["name"],
            )


# ---------------------------------------------------------------------------
# Honest Degradation
# ---------------------------------------------------------------------------


class TestHonestDegradation:
    """Honest degradation: live browser/page-agent → Experimental, fail loud."""

    def test_live_browser_unavailable_raises(self):
        """Live browser navigation (Experimental) fails loud when unavailable."""
        with pytest.raises(WebFormsExperimentalError, match="Live browser.*Experimental"):
            live_browser_navigate("https://example.com")

    def test_live_page_agent_unavailable_raises(self):
        """Live page-agent submission (Experimental) fails loud when unavailable."""
        with pytest.raises(WebFormsExperimentalError, match="Live page-agent.*Experimental"):
            live_page_agent_submit("https://example.com", {})

    def test_missing_file_raises(self):
        """Reading a non-existent file raises WebFormsError."""
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = os.path.join(tmp, "nonexistent.html")
            with pytest.raises(WebFormsError, match="HTML file not found"):
                read_form(bad_path)

    def test_empty_file_raises(self):
        """Reading an empty file raises WebFormsError."""
        with tempfile.TemporaryDirectory() as tmp:
            empty_path = os.path.join(tmp, "empty.html")
            with open(empty_path, "w") as f:
                f.write("")
            with pytest.raises(WebFormsError, match="HTML file is empty"):
                read_form(empty_path)

    def test_no_form_raises(self):
        """HTML with no form raises WebFormsError."""
        with tempfile.TemporaryDirectory() as tmp:
            no_form_path = os.path.join(tmp, "no_form.html")
            with open(no_form_path, "w") as f:
                f.write("<html><body><h1>No form here</h1></body></html>")
            with pytest.raises(WebFormsError, match="No.*form.*found"):
                read_form(no_form_path)

    def test_form_id_not_found_raises(self):
        """Non-existent form ID raises WebFormsError."""
        with pytest.raises(WebFormsError, match="Form with id.*not found"):
            read_form(_TEXT_HTML, "nonexistent_form_id")


# ---------------------------------------------------------------------------
# Gauntlet Scenarios (>=3 end-to-end)
# ---------------------------------------------------------------------------


class TestGauntletScenarios:
    """>=3 end-to-end gauntlet scenarios."""

    def test_scenario_a_text_email_password(self):
        """Scenario (a): text + email + password fields filled and verified."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["a_text_email_password"]
        html_path = os.path.join(_FIX, sc["html_file"])

        fill_spec = {}
        expected_values = {}
        for key, field_spec in sc["fields"].items():
            fill_spec[key] = field_spec
            ftype = field_spec["type"]
            if ftype in ("checkbox", "radio"):
                expected_values[key] = bool(field_spec["value"])
            else:
                expected_values[key] = str(field_spec["value"])

        # Oracle 1: form_fill_readback
        readback_ok = form_fill_readback(
            html_path, fill_spec, expected_values, sc["form_id"]
        )
        assert readback_ok is True

        # Oracle 2: uistate_readback
        uistate_ok = uistate_readback(
            html_path,
            expected_field_count=sc["expected_field_count"],
            expected_field_types=sc["expected_field_types"],
            expected_required_fields=sc["required_fields"],
            form_id=sc["form_id"],
        )
        assert uistate_ok is True

        # Pipeline verification (04 CUA verifier)
        result = webforms_pipeline(
            html_path=html_path,
            fill_spec=fill_spec,
            form_id=sc["form_id"],
        )
        assert result.ok is True
        assert result.verified is True
        assert result.submit_blocked is False
        assert len(result.required_blank) == 0

    def test_scenario_b_select_checkbox_radio(self):
        """Scenario (b): select + checkbox + radio group filled and verified."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["b_select_checkbox_radio"]
        html_path = os.path.join(_FIX, sc["html_file"])

        fill_spec = {}
        expected_values = {}
        for key, field_spec in sc["fields"].items():
            fill_spec[key] = field_spec
            ftype = field_spec["type"]
            if ftype in ("checkbox", "radio"):
                expected_values[key] = bool(field_spec["value"])
            else:
                expected_values[key] = str(field_spec["value"])

        # Oracle 1: form_fill_readback
        readback_ok = form_fill_readback(
            html_path, fill_spec, expected_values, sc["form_id"]
        )
        assert readback_ok is True

        # Oracle 2: uistate_readback
        uistate_ok = uistate_readback(
            html_path,
            expected_field_count=sc["expected_field_count"],
            expected_field_types=sc["expected_field_types"],
            form_id=sc["form_id"],
        )
        assert uistate_ok is True

        # Pipeline verification (04 CUA verifier)
        result = webforms_pipeline(
            html_path=html_path,
            fill_spec=fill_spec,
            form_id=sc["form_id"],
        )
        assert result.ok is True
        assert result.verified is True
        assert result.submit_blocked is False

    def test_scenario_c_required_blank_flagged(self):
        """Scenario (c): required field left blank → correctly flagged, submit blocked."""
        gt = _load_ground_truth()
        sc = gt["scenarios"]["c_required_blank"]
        html_path = os.path.join(_FIX, sc["html_file"])

        fill_spec = {}
        for key, field_spec in sc["fields"].items():
            fill_spec[key] = field_spec

        # Pipeline: should detect required blanks and block submit
        result = webforms_pipeline(
            html_path=html_path,
            fill_spec=fill_spec,
            form_id=sc["form_id"],
            expected_required_blank=True,
        )
        assert result.ok is True
        # Submit should be blocked (required fields blank)
        assert result.submit_blocked is True
        # Required blanks should include "name" and "subject"
        assert "name" in result.required_blank
        assert "subject" in result.required_blank

        # uistate_readback: verify required blank fields are detected
        uistate_ok = uistate_readback(
            html_path,
            expected_field_count=sc["expected_field_count"],
            expected_required_fields=sc["required_fields"],
            form_id=sc["form_id"],
            fill_spec=fill_spec,
            expected_required_blank=["name", "subject"],
        )
        assert uistate_ok is True


# ---------------------------------------------------------------------------
# Trust Stack Integration
# ---------------------------------------------------------------------------


class TestTrustStackIntegration:
    """Audit log + zero-egress report integration."""

    def test_audit_log_generated(self):
        """Pipeline generates Ed25519 audit log."""
        private_key, _ = ed25519.Ed25519PrivateKey.generate(), None
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "testuser"},
            "email": {"selector": "#email", "type": "email", "value": "test@test.com"},
        }
        result = webforms_pipeline(
            html_path=_TEXT_HTML,
            fill_spec=fill_spec,
            form_id="registration_form",
            private_key=private_key,
        )
        assert result.ok is True
        assert len(result.audit_log_json) > 0
        audit_data = json.loads(result.audit_log_json)
        assert "entries" in audit_data
        assert len(audit_data["entries"]) > 0

    def test_egress_report_generated(self):
        """Pipeline generates signed zero-egress report."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "testuser"},
        }
        result = webforms_pipeline(
            html_path=_TEXT_HTML,
            fill_spec=fill_spec,
            form_id="registration_form",
            private_key=private_key,
        )
        assert result.ok is True
        assert len(result.egress_report_json) > 0
        report_data = json.loads(result.egress_report_json)
        assert "signature" in report_data
        assert len(report_data["signature"]) > 0
        assert "offline_attestation" in report_data

    def test_audit_log_chained(self):
        """Audit log entries are hash-chained."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "u1"},
            "email": {"selector": "#email", "type": "email", "value": "e@e.com"},
        }
        result = webforms_pipeline(
            html_path=_TEXT_HTML,
            fill_spec=fill_spec,
            form_id="registration_form",
            private_key=private_key,
        )
        audit_data = json.loads(result.audit_log_json)
        entries = audit_data["entries"]
        # Each entry (after first) should have a non-empty prev_hash
        for i, entry in enumerate(entries):
            if i > 0:
                assert entry["prev_hash"] != ""
        # Last entry should be run_completed
        assert entries[-1]["action"] == "run_completed"


# ---------------------------------------------------------------------------
# Perception Integration (03 element map)
# ---------------------------------------------------------------------------


class TestPerceptionIntegration:
    """Field resolution via 03 perception element map."""

    def test_form_to_element_map(self):
        """HTML form converts to perception ElementMap."""
        screen_map = form_to_element_map(_TEXT_HTML, "registration_form")
        assert screen_map.element_map.element_count == 6
        assert screen_map.source == "fixture"

    def test_resolve_field_by_query(self):
        """Field resolution via 03's resolve() finds the right element."""
        screen_map = form_to_element_map(_TEXT_HTML, "registration_form")
        elem = resolve_field_by_query("email", screen_map)
        assert elem is not None
        assert "email" in elem.name.lower()

    def test_resolve_username_field(self):
        """Resolve 'username' field via perception."""
        screen_map = form_to_element_map(_TEXT_HTML, "registration_form")
        elem = resolve_field_by_query("username", screen_map)
        assert elem is not None
        assert "username" in elem.name.lower()

    def test_resolve_select_field(self):
        """Resolve 'country' select field via perception."""
        screen_map = form_to_element_map(_SELECT_HTML, "survey_form")
        elem = resolve_field_by_query("country", screen_map)
        assert elem is not None
        assert "country" in elem.name.lower()


# ---------------------------------------------------------------------------
# CUA Verifier Integration (04 verify-before-commit)
# ---------------------------------------------------------------------------


class TestCUAVerifierIntegration:
    """Submit gated by 04 CUA verifier — no receipt on unverified/failed."""

    def test_verified_fill_passes(self):
        """Complete fill with no required blanks → verified."""
        fill_spec = {
            "username": {"selector": "#username", "type": "text", "value": "user1"},
            "email": {"selector": "#email", "type": "email", "value": "a@b.com"},
            "password": {"selector": "#password", "type": "password", "value": "pass1"},
            "confirm_password": {"selector": "#confirm_password", "type": "password", "value": "pass1"},
        }
        _, form_info = fill_form(_TEXT_HTML, fill_spec, "registration_form")
        verified, details = verify_form_fill(form_info, fill_spec)
        assert verified is True

    def test_required_blank_not_verified(self):
        """Required blank → not verified, submit blocked."""
        fill_spec = {
            "name": {"selector": "#name", "type": "text", "value": ""},
            "email": {"selector": "#email", "type": "email", "value": "j@j.com"},
            "subject": {"selector": "#subject", "type": "text", "value": ""},
            "message": {"selector": "#message", "type": "textarea", "value": "msg"},
        }
        _, form_info = fill_form(_REQUIRED_HTML, fill_spec, "contact_form")
        verified, details = verify_form_fill(form_info, fill_spec)
        assert verified is False
        assert details["submit_blocked"] is True

    def test_expected_required_blank_verified(self):
        """Expected required blank (scenario c) → verified as expected state."""
        fill_spec = {
            "name": {"selector": "#name", "type": "text", "value": ""},
            "email": {"selector": "#email", "type": "email", "value": "j@j.com"},
            "subject": {"selector": "#subject", "type": "text", "value": ""},
            "message": {"selector": "#message", "type": "textarea", "value": "msg"},
        }
        _, form_info = fill_form(_REQUIRED_HTML, fill_spec, "contact_form")
        verified, details = verify_form_fill(form_info, fill_spec, expected_required_blank=True)
        assert verified is True


# ---------------------------------------------------------------------------
# CLI Integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """webforms CLI subcommand works end-to-end."""

    def test_cli_inspect(self):
        """CLI inspect action reads form structure."""
        from kairo.cli import main

        rc = main(["webforms", "inspect", _TEXT_HTML, "--form-id", "registration_form",
                    "--outdir", tempfile.mkdtemp()])
        assert rc == 0

    def test_cli_fill(self):
        """CLI fill action fills form and generates artifacts."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "spec.json")
            with open(spec_path, "w") as f:
                json.dump({
                    "username": {"selector": "#username", "type": "text", "value": "cliuser"},
                    "email": {"selector": "#email", "type": "email", "value": "cli@test.com"},
                }, f)
            rc = main(["webforms", "fill", _TEXT_HTML, spec_path,
                        "--form-id", "registration_form", "--outdir", tmp])
            assert rc == 0

    def test_cli_verify(self):
        """CLI verify action fills + verifies form."""
        from kairo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "spec.json")
            with open(spec_path, "w") as f:
                json.dump({
                    "username": {"selector": "#username", "type": "text", "value": "vuser"},
                    "email": {"selector": "#email", "type": "email", "value": "v@v.com"},
                    "password": {"selector": "#password", "type": "password", "value": "pass1"},
                    "confirm_password": {"selector": "#confirm_password", "type": "password", "value": "pass1"},
                }, f)
            rc = main(["webforms", "verify", _TEXT_HTML, spec_path,
                        "--form-id", "registration_form", "--outdir", tmp])
            assert rc == 0

    def test_cli_no_action_returns_1(self):
        """CLI with no action returns 1."""
        from kairo.cli import main

        rc = main(["webforms"])
        assert rc == 1
