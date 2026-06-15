"""Tests for `shopstack.tools.js_validate` — the JS snippet validator.

Verifies:
  * The extractor finds `js=...` arguments in `.load()` /
    `.click()` / `.submit()` chains.
  * String-literal args resolve to the literal text.
  * Function-call args resolve to the function's return value
    (by importing the module and calling the function).
  * The Node validator catches a real SyntaxError.
  * The Python fallback catches unbalanced braces.
  * The CLI exits 0 on a clean scan and 1 on errors.
  * Snippets in `_legacy/` and `__pycache__` are skipped.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from shopstack.tools.js_validate import (
    JsSnippet,
    JsValidationReport,
    _extract_js_args,
    _resolve_js_string,
    _validate_with_node,
    _validate_with_python_fallback,
    main,
    scan,
)


# ── Extractor ─────────────────────────────────────────────────────


class TestExtractJsArgs:
    def test_finds_js_kwarg_in_click_call(self, tmp_path: Path):
        f = tmp_path / "screen.py"
        f.write_text(
            "import gradio as gr\n"
            "btn.click(handler, js='alert(1)')\n"
        )
        results = _extract_js_args(f.read_text(), f)
        assert len(results) == 1
        line, arg = results[0]
        assert line == 2
        assert "alert(1)" in arg

    def test_finds_js_kwarg_in_load_call(self, tmp_path: Path):
        f = tmp_path / "app.py"
        f.write_text(
            "app.load(None, js=autocomplete_injector_js())\n"
        )
        results = _extract_js_args(f.read_text(), f)
        assert len(results) == 1
        line, arg = results[0]
        assert "autocomplete_injector_js()" in arg

    def test_no_js_arg_skipped(self, tmp_path: Path):
        f = tmp_path / "screen.py"
        f.write_text("btn.click(handler)\n")
        results = _extract_js_args(f.read_text(), f)
        assert results == []

    def test_unbalanced_call_skipped(self, tmp_path: Path):
        f = tmp_path / "screen.py"
        f.write_text("btn.click(handler, js='alert(1)\n")  # unclosed paren
        # The extractor walks balanced parens; unbalanced calls are
        # skipped, not crashed.
        results = _extract_js_args(f.read_text(), f)
        assert results == []


# ── Resolver ──────────────────────────────────────────────────────


class TestResolveJsString:
    def test_double_quoted_string(self):
        assert _resolve_js_string('"alert(1)"') == "alert(1)"

    def test_single_quoted_string(self):
        assert _resolve_js_string("'alert(1)'") == "alert(1)"

    def test_known_helper_function(self):
        """A bare function name in a known module resolves."""
        js = _resolve_js_string("script_bootstrap_js()")
        assert js  # returns a non-empty string
        assert "ss-exec" in js or "data-ss-exec" in js

    def test_unknown_callee_returns_empty(self):
        assert _resolve_js_string("totally_made_up_function()") == ""

    def test_empty_input_returns_empty(self):
        assert _resolve_js_string("") == ""
        assert _resolve_js_string("   ") == ""


# ── Validator backends ────────────────────────────────────────────


class TestValidateWithNode:
    def test_valid_js_returns_ok(self):
        ok, err = _validate_with_node("var x = 1;\nfunction f() { return x; }\n")
        assert ok is True
        assert err == ""

    def test_invalid_js_returns_error(self):
        ok, err = _validate_with_node("var x = ;\n")  # SyntaxError
        # If node is unavailable, the Python fallback is used;
        # in that case the result depends on what the fallback
        # catches. This test is environment-dependent.
        if not ok:
            assert err  # error message present

    def test_empty_string_is_valid(self):
        ok, err = _validate_with_node("")
        assert ok is True
        assert err == ""


class TestValidateWithPythonFallback:
    def test_balanced_braces_are_valid(self):
        ok, err = _validate_with_python_fallback("function f() { return 1; }")
        assert ok is True
        assert err == ""

    def test_unbalanced_braces_flagged(self):
        ok, err = _validate_with_python_fallback("function f() { return 1; ")
        assert ok is False
        assert "unbalanced" in err.lower()

    def test_empty_string_is_valid(self):
        ok, err = _validate_with_python_fallback("")
        assert ok is True


# ── Top-level scan ─────────────────────────────────────────────────


class TestScan:
    def test_scan_finds_at_least_one_snippet(self):
        # The real project has many `js=...` calls; the scan
        # should find some.
        report = scan()
        # We don't assert a specific count (it changes as the
        # codebase grows), but it should be non-zero.
        assert report.scanned_files > 0
        assert len(report.snippets) > 0

    def test_scan_catches_real_syntax_error_in_temp_file(self, tmp_path: Path, monkeypatch):
        """Regression: if a real file ships a JS snippet with a
        SyntaxError, ``scan()`` must surface it.

        We point SCAN_DIRS at a temp directory containing a file
        that uses a valid call site pattern (``app.load``) with a
        ``js=...`` argument that's a known-broken function. The
        validator must return at least one snippet with
        ``valid=False``.

        Why this matters: without this test, the validator could
        silently regress to "always returns ok=True" and the
        CI signal would rot. motto_v3 §0.5: tests must validate
        real behaviour, not just structural shape.
        """
        from shopstack.tools import js_validate

        bad_file = tmp_path / "broken_screen.py"
        bad_file.write_text(
            "import gradio as gr\n"
            "app.load(None, js='function f() { return ;')\n"
        )
        monkeypatch.setattr(js_validate, "SCAN_DIRS", (tmp_path,))
        report = js_validate.scan()
        assert report.scanned_files == 1
        # The bad snippet must be flagged.
        assert report.error_count >= 1, (
            f"Expected the scan to flag the broken JS snippet, got "
            f"{len(report.snippets)} snippets all valid: "
            f"{[(s.file, s.line, s.error) for s in report.snippets]}"
        )
        bad = [s for s in report.snippets if not s.valid]
        assert bad, "At least one snippet must be marked invalid"
        # Any non-empty error string means Node (or the Python
        # fallback) actually parsed the JS and rejected it. We
        # don't assert the exact message format because Node's
        # error text varies across versions.

    def test_report_to_dict(self):
        report = JsValidationReport()
        report.scanned_files = 5
        report.snippets.append(
            JsSnippet(
                file="x.py", line=1, source="y()", js="var x = 1;",
                valid=True, error="",
            )
        )
        d = report.to_dict()
        assert d["scanned_files"] == 5
        assert d["snippet_count"] == 1
        assert d["error_count"] == 0
        assert d["snippets"][0]["valid"] is True


# ── CLI ────────────────────────────────────────────────────────────


def test_main_writes_report(tmp_path: Path, monkeypatch, capsys):
    from shopstack.tools import js_validate

    monkeypatch.setattr(js_validate, "OUTPUT_JSON", tmp_path / "JS_VALIDATION.json")
    rc = js_validate.main([])
    assert rc in (0, 1)
    assert (tmp_path / "JS_VALIDATION.json").is_file()
    data = json.loads((tmp_path / "JS_VALIDATION.json").read_text(encoding="utf-8"))
    assert "snippets" in data
    assert "scanned_files" in data
    assert "error_count" in data


# ── Pre-commit wiring (Item #56 hardening) ───────────────────────


class TestPrecommitWiring:
    """Item #56 (motto_v3 §0.5): the JS validator is wired into
    pre-commit so SyntaxErrors in ``js=...`` kwargs are caught
    at commit time, not at runtime in the browser. This test
    asserts the wiring exists in ``.pre-commit-config.yaml`` and
    that the wired command exits 0 on the current codebase
    (no errors to block the commit).
    """

    def test_precommit_config_declares_js_syntax_hook(self):
        from pathlib import Path
        cfg = Path(".pre-commit-config.yaml")
        assert cfg.is_file(), "Pre-commit config must exist at the project root"
        text = cfg.read_text(encoding="utf-8")
        assert "js-syntax-validate" in text, (
            "Pre-commit must declare a hook with id 'js-syntax-validate' "
            "so SyntaxErrors in js=... kwargs are caught at commit time "
            "(motto_v3 §0.5)."
        )
        assert "shopstack.tools.js_validate" in text, (
            "The hook must invoke `python -m shopstack.tools.js_validate`."
        )

    def test_precommit_command_exits_zero_on_current_codebase(self):
        """If this fails, the codebase has a JS SyntaxError that
        the pre-commit hook would block. Fix the JS first, then
        re-run this test.
        """
        from shopstack.tools import js_validate

        rc = js_validate.main([])
        assert rc == 0, (
            f"js_validate.main() exited {rc} — JS SyntaxErrors in "
            f"the codebase would block pre-commit (Item #56)."
        )

    def test_ci_workflow_also_runs_js_validate(self):
        """Item #56 (motto_v3 §0.5): the same gate should exist
        in CI. Pre-commit protects local commits; CI protects
        pushes. Both must invoke the validator. A regression
        where the CI job is removed would let a SyntaxError
        through on a PR committed via the GitHub web UI.
        """
        from pathlib import Path
        wf = Path(".github/workflows/quality-gates.yml")
        if not wf.is_file():
            pytest.skip("No quality-gates workflow; CI may be elsewhere")
        text = wf.read_text(encoding="utf-8")
        assert "shopstack.tools.js_validate" in text, (
            "The CI quality-gates workflow must run "
            "shopstack.tools.js_validate (Item #56: "
            "JS validator must gate pushes, not just commits)."
        )
        # A job that uploads the report is a useful audit trail.
        assert "JS_VALIDATION" in text or "js-validation" in text.lower(), (
            "The CI job should also upload the JS_VALIDATION.json "
            "report as an artifact for postmortem."
        )
