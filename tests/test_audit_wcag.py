"""Tests for shopstack.tools.audit_wcag (Phase 7 #28)."""
from __future__ import annotations

from pathlib import Path

import pytest

from shopstack.tools.audit_wcag import (
    WCAGReport,
    WCAGResult,
    render_report_html,
    render_report_markdown,
    run_audit,
)


# ── Pure unit tests of individual checks ──────────────────────


def test_check_1_1_1_no_images_passes():
    from shopstack.tools.audit_wcag import check_1_1_1_alt_text
    r = check_1_1_1_alt_text({"a.py": "no html here"})
    assert r.status == "pass"


def test_check_1_1_1_img_without_alt_fails():
    from shopstack.tools.audit_wcag import check_1_1_1_alt_text
    r = check_1_1_1_alt_text({"a.py": "<img src='x.png'>"})
    assert r.status == "fail"
    assert "alt=" in r.remediation


def test_check_1_1_1_img_with_alt_passes():
    from shopstack.tools.audit_wcag import check_1_1_1_alt_text
    r = check_1_1_1_alt_text({"a.py": '<img src="x.png" alt="X">'})
    assert r.status == "pass"


def test_check_1_1_1_svg_with_role_passes():
    from shopstack.tools.audit_wcag import check_1_1_1_alt_text
    r = check_1_1_1_alt_text({"a.py": '<svg role="img" aria-label="X"></svg>'})
    assert r.status == "pass"


def test_check_1_1_1_svg_without_role_warns():
    from shopstack.tools.audit_wcag import check_1_1_1_alt_text
    r = check_1_1_1_alt_text({"a.py": "<svg></svg>"})
    assert r.status == "warn"


def test_check_1_3_1_with_enough_labels_passes():
    from shopstack.tools.audit_wcag import check_1_3_1_semantic
    content = "label=" * 50 + 'class="brand-title"'
    r = check_1_3_1_semantic({"a.py": content})
    assert r.status == "pass"


def test_check_1_3_1_few_labels_fails():
    from shopstack.tools.audit_wcag import check_1_3_1_semantic
    r = check_1_3_1_semantic({"a.py": "no labels"})
    assert r.status == "fail"


def test_check_1_4_3_contrast_passes():
    from shopstack.tools.audit_wcag import check_1_4_3_contrast
    r = check_1_4_3_contrast({})
    # The documented token pairs all pass AA
    assert r.status == "pass"


def test_check_1_4_4_all_rem_passes():
    from shopstack.tools.audit_wcag import check_1_4_4_resize_text
    r = check_1_4_4_resize_text({"a.css": "font-size: 1rem; line-height: 1.5em;"})
    assert r.status == "pass"


def test_check_1_4_4_some_px_warns():
    from shopstack.tools.audit_wcag import check_1_4_4_resize_text
    r = check_1_4_4_resize_text({"a.css": "font-size: 12px; font-size: 13px;"})
    assert r.status == "warn"


def test_check_1_4_4_many_px_fails():
    from shopstack.tools.audit_wcag import check_1_4_4_resize_text
    css = "\n".join(f"font-size: {i}px;" for i in range(10))
    r = check_1_4_4_resize_text({"a.css": css})
    assert r.status == "fail"


def test_check_1_4_10_no_fixed_widths_passes():
    from shopstack.tools.audit_wcag import check_1_4_10_reflow
    r = check_1_4_10_reflow({"a.css": "max-width: 100%; width: 50%;"})
    assert r.status == "pass"


def test_check_1_4_10_fixed_widths_warn():
    from shopstack.tools.audit_wcag import check_1_4_10_reflow
    r = check_1_4_10_reflow({"a.css": "width: 800px;"})
    assert r.status == "warn"


def test_check_1_4_13_focus_visible_present_passes():
    from shopstack.tools.audit_wcag import check_1_4_13_focus_indicators
    r = check_1_4_13_focus_indicators({"a.py": ":focus-visible { outline: 2px solid; }"})
    assert r.status == "pass"


def test_check_1_4_13_no_focus_fails():
    from shopstack.tools.audit_wcag import check_1_4_13_focus_indicators
    r = check_1_4_13_focus_indicators({"a.py": "no focus here"})
    assert r.status == "fail"


def test_check_2_1_1_keyboard_passes_with_keydown():
    from shopstack.tools.audit_wcag import check_2_1_1_keyboard
    r = check_2_1_1_keyboard({
        "a.py": (
            "document.addEventListener('keydown', ...)\n"
            'aria-label="btn"\n'
        )
    })
    assert r.status == "pass"


def test_check_2_1_1_keyboard_fails_without():
    from shopstack.tools.audit_wcag import check_2_1_1_keyboard
    r = check_2_1_1_keyboard({"a.py": "no events"})
    assert r.status == "fail"


def test_check_2_4_2_page_title_passes():
    from shopstack.tools.audit_wcag import check_2_4_2_page_title
    r = check_2_4_2_page_title({"a.py": 'gr.Blocks(title="ShopStack")'})
    assert r.status == "pass"


def test_check_2_4_2_page_title_fails():
    from shopstack.tools.audit_wcag import check_2_4_2_page_title
    r = check_2_4_2_page_title({"a.py": "gr.Blocks()"})
    assert r.status == "fail"


def test_check_2_4_6_with_markdown_and_labels_passes():
    from shopstack.tools.audit_wcag import check_2_4_6_headings_labels
    content = "gr.Markdown" * 10 + "label=" * 20
    r = check_2_4_6_headings_labels({"a.py": content})
    assert r.status == "pass"


def test_check_3_1_1_with_html_lang_passes():
    from shopstack.tools.audit_wcag import check_3_1_1_language
    r = check_3_1_1_language({"a.html": '<html lang="en">'})
    assert r.status == "pass"


def test_check_3_1_1_with_data_locale_passes():
    from shopstack.tools.audit_wcag import check_3_1_1_language
    r = check_3_1_1_language({"a.html": '<html data-locale="hi">'})
    assert r.status == "pass"


def test_check_3_1_1_without_lang_fails():
    from shopstack.tools.audit_wcag import check_3_1_1_language
    r = check_3_1_1_language({"a.html": "<html>"})
    assert r.status == "fail"


def test_check_3_3_1_toast_passes():
    from shopstack.tools.audit_wcag import check_3_3_1_error_identification
    r = check_3_3_1_error_identification({"a.py": "toast('Failed')"})
    assert r.status == "pass"


def test_check_3_3_1_no_toast_no_aria_fails():
    from shopstack.tools.audit_wcag import check_3_3_1_error_identification
    r = check_3_3_1_error_identification({"a.py": "raise Exception"})
    assert r.status == "fail"


def test_check_3_3_2_with_label_passes():
    from shopstack.tools.audit_wcag import check_3_3_2_labels
    r = check_3_3_2_labels({"a.py": 'gr.Textbox(label="X")'})
    assert r.status == "pass"


def test_check_3_3_2_without_label_warns():
    from shopstack.tools.audit_wcag import check_3_3_2_labels
    r = check_3_3_2_labels({"a.py": "gr.Textbox()"})
    assert r.status == "warn"


def test_check_4_1_2_with_aria_passes():
    from shopstack.tools.audit_wcag import check_4_1_2_aria_custom_widgets
    r = check_4_1_2_aria_custom_widgets({
        "a.py": 'role="dialog" aria-modal="true" aria-label="X" aria-label="Y" aria-label="Z"'
    })
    assert r.status == "pass"


# ── WCAGResult dataclass ──────────────────────────────────────


def test_wcag_result_default_status_pass():
    r = WCAGResult("1.1.1", "Test", "A")
    assert r.status == "pass"
    assert r.evidence == []
    assert r.remediation == ""


def test_wcag_report_pass_count():
    r = WCAGReport(results=[
        WCAGResult("1", "A", "A", status="pass"),
        WCAGResult("2", "B", "A", status="pass"),
        WCAGResult("3", "C", "A", status="fail"),
    ])
    assert r.pass_count == 2
    assert r.fail_count == 1
    assert r.warn_count == 0


def test_wcag_report_score_calculation():
    # 1 pass + 1 warn + 0 fail → (1 + 0.5) / 2 = 0.75 → 75
    r = WCAGReport(results=[
        WCAGResult("1", "A", "A", status="pass"),
        WCAGResult("2", "B", "A", status="warn"),
    ])
    assert r.score == 75


def test_wcag_report_score_all_pass():
    r = WCAGReport(results=[
        WCAGResult("1", "A", "A", status="pass"),
        WCAGResult("2", "B", "A", status="pass"),
    ])
    assert r.score == 100


def test_wcag_report_score_empty():
    r = WCAGReport()
    assert r.score == 0


def test_wcag_report_remediations_deduped():
    r = WCAGReport(results=[
        WCAGResult("1", "A", "A", status="fail", remediation="Fix X"),
        WCAGResult("2", "B", "A", status="fail", remediation="Fix X"),
        WCAGResult("3", "C", "A", status="fail", remediation="Fix Y"),
    ])
    rems = r.remediations
    assert rems == ["Fix X", "Fix Y"]


# ── HTML / Markdown rendering ───────────────────────────────


def test_render_report_html_basic():
    r = WCAGReport(results=[
        WCAGResult("1.1.1", "Test", "A", status="pass"),
    ])
    html = render_report_html(r)
    assert "wcag-block" in html
    assert "WCAG 2.1 AA score:" in html
    assert "1.1.1" in html


def test_render_report_html_escapes_xss():
    r = WCAGReport(results=[
        WCAGResult("1.1.1", "<script>alert(1)</script>", "A", status="pass"),
    ])
    html = render_report_html(r)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_report_markdown_basic():
    r = WCAGReport(results=[
        WCAGResult("1.1.1", "Test", "A", status="pass"),
    ])
    md = render_report_markdown(r)
    assert "WCAG 2.1 AA Audit" in md
    assert "| 1.1.1 |" in md
    assert "pass" in md


def test_render_report_markdown_includes_remediation():
    r = WCAGReport(results=[
        WCAGResult("1.1.1", "Test", "A", status="fail", remediation="Add alt"),
    ])
    md = render_report_markdown(r)
    assert "Add alt" in md


# ─- run_audit on the actual codebase ────────────────────────


def test_run_audit_against_repo():
    """Run the full audit on the actual repo and verify it produces a report."""
    report = run_audit(".")
    assert isinstance(report, WCAGReport)
    assert len(report.results) > 0
    assert report.score >= 0
    # Should have at least one pass (we know the contrast + keyboard checks pass)
    assert report.pass_count >= 1


def test_run_audit_excludes_test_files():
    """Verify the audit excludes the tests/ directory."""
    report = run_audit(".")
    # The audit should NOT include tests/test_*.py in its audited_files
    for fp in report.audited_files:
        assert "/tests/" not in fp
        assert "/.venv/" not in fp
        assert "/__pycache__/" not in fp


def test_run_audit_excludes_itself():
    """The audit script itself is excluded to avoid false positives."""
    report = run_audit(".")
    for fp in report.audited_files:
        assert not fp.endswith("audit_wcag.py")
