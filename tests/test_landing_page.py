"""
W10 Oracle: Landing page + scripted demo.

Verifies that:
1. The landing page HTML exists and builds (valid HTML)
2. All metric claims on the page cite a reproducible command
3. No unverifiable marketing claims (every metric has a source command)
4. The scripted demo steps reference real commands that exist
5. The demo produces a visible signed receipt concept
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SITE_DIR = REPO_ROOT / "site"
INDEX_HTML = SITE_DIR / "index.html"
STYLES_CSS = SITE_DIR / "styles.css"
APP_JS = SITE_DIR / "app.js"


class TestLandingPageExists:
    """Verify the landing page files exist."""

    def test_index_html_exists(self):
        assert INDEX_HTML.exists(), "site/index.html must exist"

    def test_styles_css_exists(self):
        assert STYLES_CSS.exists(), "site/styles.css must exist"

    def test_app_js_exists(self):
        assert APP_JS.exists(), "site/app.js must exist"


class TestLandingPageContent:
    """Verify the landing page has required content."""

    def test_has_title(self):
        html = INDEX_HTML.read_text()
        assert "<title>" in html, "Landing page must have a title"

    def test_has_offline_first_messaging(self):
        html = INDEX_HTML.read_text()
        assert "offline" in html.lower(), "Landing page must mention offline-first"

    def test_has_signed_receipt_messaging(self):
        html = INDEX_HTML.read_text()
        assert "signed" in html.lower() and "receipt" in html.lower(), (
            "Landing page must mention signed receipts"
        )

    def test_has_metrics_section(self):
        html = INDEX_HTML.read_text()
        assert "metrics" in html.lower(), "Landing page must have a metrics section"

    def test_has_demo_section(self):
        html = INDEX_HTML.read_text()
        assert "demo" in html.lower(), "Landing page must have a demo section"

    def test_has_does_not_section(self):
        html = INDEX_HTML.read_text()
        assert "Does NOT" in html or "does not" in html.lower(), (
            "Landing page must have a 'Does NOT' section (honest scope)"
        )


class TestMetricClaimsAreSourced:
    """Every metric on the landing page must cite a reproducible command."""

    def test_metrics_have_source_commands(self):
        html = INDEX_HTML.read_text()
        # Find all metric-source elements
        sources = re.findall(r'class="metric-source"><code>(.*?)</code>', html)
        assert len(sources) >= 4, (
            f"Must have at least 4 sourced metrics, found {len(sources)}"
        )
        for source in sources:
            # Each source must reference a real command (pytest, python, etc.)
            assert "pytest" in source or "python" in source, (
                f"Metric source must cite a reproducible command: {source}"
            )

    def test_grounding_accuracy_metric(self):
        html = INDEX_HTML.read_text()
        assert "99.2%" in html or "595/600" in html, (
            "Landing page must show grounding accuracy metric (99.2% or 595/600)"
        )

    def test_injection_block_rate_metric(self):
        html = INDEX_HTML.read_text()
        assert "65/65" in html, (
            "Landing page must show injection block rate (65/65)"
        )


class TestScriptedDemo:
    """Verify the scripted demo references real commands."""

    def test_demo_has_redline_command(self):
        html = INDEX_HTML.read_text()
        assert "kairo.cli redline" in html, (
            "Demo must reference the redline command"
        )

    def test_demo_has_sealed_mode(self):
        html = INDEX_HTML.read_text()
        assert "sealed" in html.lower(), (
            "Demo must include sealed mode step"
        )

    def test_demo_has_verify_command(self):
        html = INDEX_HTML.read_text()
        assert "verify_receipts" in html, (
            "Demo must include receipt verification command"
        )

    def test_demo_has_signed_receipt_display(self):
        html = INDEX_HTML.read_text()
        assert "self_hash" in html or "signature" in html, (
            "Demo must show a visible signed receipt (self_hash or signature)"
        )

    def test_demo_commands_reference_real_files(self):
        """Demo commands must reference files that actually exist."""
        html = INDEX_HTML.read_text()
        # Check that the demo NDA fixture exists
        assert (REPO_ROOT / "fixtures" / "demo" / "sample_nda.docx").exists(), (
            "Demo references sample_nda.docx but file doesn't exist"
        )
        assert (REPO_ROOT / "fixtures" / "demo" / "nda_playbook.json").exists(), (
            "Demo references nda_playbook.json but file doesn't exist"
        )
        assert (REPO_ROOT / "tools" / "verify_receipts_external.py").exists(), (
            "Demo references verify_receipts_external.py but file doesn't exist"
        )


class TestNoUnverifiableClaims:
    """Verify no unverifiable marketing claims."""

    def test_no_fake_user_counts(self):
        html = INDEX_HTML.read_text()
        # Must NOT claim user counts, revenue, etc.
        for pattern in [r'\d+\s+users', r'\d+\s+MRR', r'\$\d+K\s+revenue', r'\d+\s+customers']:
            assert not re.search(pattern, html, re.IGNORECASE), (
                f"Landing page must not contain unverifiable claim matching {pattern}"
            )

    def test_no_fake_partnerships(self):
        html = INDEX_HTML.read_text()
        for word in ["trusted by", "partner", "enterprise customer", "SOC2", "FedRAMP"]:
            assert word.lower() not in html.lower(), (
                f"Landing page must not claim '{word}' (unverifiable)"
            )

    def test_no_experimental_claimed_as_real(self):
        html = INDEX_HTML.read_text()
        # Medical must not be claimed as Real
        assert "medical" not in html.lower() or "experimental" in html.lower(), (
            "Landing page must not claim Medical as Real without Experimental label"
        )
