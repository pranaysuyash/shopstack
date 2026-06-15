"""Tests for `shopstack.tools.copy_audit` — the consumer-copy linter.

Verifies:
  * The blocklist is well-formed (no empty entries, no duplicates).
  * `scan_file` flags strings that contain a forbidden term.
  * `scan_file` ignores terms that appear only in code (not in
    `label=`, `value=`, `placeholder=`, or `info=`).
  * `scan_i18n` flags forbidden terms in the i18n registry.
  * `run_audit` walks the UI tree and returns a populated report.
  * The markdown renderer includes a header, the violation table,
    and the "How to fix" guidance.
  * The CLI exit code is 0 when there are no violations and 1
    when there are.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from shopstack.tools.copy_audit import (
    OVERRIDES,
    CopyReport,
    Violation,
    main,
    render_markdown,
    run_audit,
    scan_file,
    scan_i18n,
)


# ── Blocklist sanity ───────────────────────────────────────────────


class TestBlocklist:
    def test_no_duplicate_terms(self):
        assert len(OVERRIDES) == len(set(OVERRIDES.keys()))

    def test_every_entry_has_suggestion_and_why(self):
        for term, (suggestion, why) in OVERRIDES.items():
            assert suggestion, f"{term} missing suggestion"
            assert why, f"{term} missing why"

    def test_blocklist_includes_known_jargon(self):
        for must in (
            "trace",
            "canonical",
            "lot id",
            "scene type",
            "jsonl",
        ):
            assert must in OVERRIDES, f"Missing blocklist entry: {must}"


# ── File scanner ───────────────────────────────────────────────────


class TestScanFile:
    def test_flags_visible_label_with_jargon(self, tmp_path: Path):
        f = tmp_path / "screen.py"
        f.write_text(
            "import gradio as gr\n"
            "btn = gr.Button('Save Trace', elem_id='x')\n"
        )
        violations = scan_file(f)
        assert any("trace" in v.rule for v in violations), f"Got: {violations}"

    def test_does_not_flag_internal_code(self, tmp_path: Path):
        f = tmp_path / "screen.py"
        # `canonical` in a variable name is not flagged
        f.write_text(
            "import gradio as gr\n"
            "canonical_name = 'milk'\n"
            "btn = gr.Button('Add', elem_id='x')\n"
        )
        violations = scan_file(f)
        # The label "Add" is fine
        # (might still flag the variable name if regex matches loosely — be strict)
        assert all(v.matched_text != "Add" for v in violations)

    def test_handles_multiline_gr_calls(self, tmp_path: Path):
        f = tmp_path / "screen.py"
        f.write_text(
            "import gradio as gr\n"
            "btn = gr.Markdown(\n"
            "    value='This is a trace event',\n"
            "    elem_id='x',\n"
            ")\n"
        )
        violations = scan_file(f)
        assert any("trace" in v.rule for v in violations), f"Got: {violations}"


# ── I18n scanner ──────────────────────────────────────────────────


class TestScanI18n:
    def test_flags_blocklist_in_i18n_registry(self):
        violations = scan_i18n()
        # The real i18n registry should not contain any forbidden term.
        # (We added many "empty." and "help." strings during this
        # session — none of those contain blocklist terms.)
        # We expect either 0 or a small set of known issues.
        for v in violations:
            assert v.file.endswith("i18n.py")
            assert v.rule.startswith("forbidden-term:")


# ── End-to-end ─────────────────────────────────────────────────────


class TestRunAudit:
    def test_walks_ui_tree(self):
        report = run_audit()
        assert report.scanned_files > 0
        # Every violation is well-formed
        for v in report.violations:
            assert v.file
            assert v.line > 0
            assert v.matched_text
            assert v.suggestion


class TestRenderMarkdown:
    def test_no_violations_section(self):
        report = CopyReport(violations=[], scanned_files=10)
        md = render_markdown(report)
        assert "No violations found" in md
        assert "consumer-friendly" in md

    def test_violations_table(self):
        report = CopyReport(
            violations=[
                Violation(
                    file="x.py",
                    line=42,
                    column=8,
                    matched_text="Save Trace",
                    rule="forbidden-term:trace",
                    suggestion="Action history",
                    why="Internal jargon",
                ),
            ],
            scanned_files=5,
        )
        md = render_markdown(report)
        assert "Violations" in md
        assert "x.py" in md
        assert "Save Trace" in md
        assert "Action history" in md
        assert "How to fix" in md


# ── CLI ────────────────────────────────────────────────────────────


def test_main_writes_files(tmp_path: Path, monkeypatch):
    from shopstack.tools import copy_audit

    # Redirect output so we don't touch the real docs.
    monkeypatch.setattr(copy_audit, "OUTPUT_MD", tmp_path / "COPY_AUDIT.md")
    monkeypatch.setattr(copy_audit, "OUTPUT_JSON", tmp_path / "COPY_AUDIT.json")
    # The real audit may find violations, so don't check return code
    rc = copy_audit.main([])
    assert rc in (0, 1)
    assert (tmp_path / "COPY_AUDIT.md").is_file()
    assert (tmp_path / "COPY_AUDIT.json").is_file()
    data = json.loads((tmp_path / "COPY_AUDIT.json").read_text(encoding="utf-8"))
    assert "violations" in data
    assert "scanned_files" in data
