"""Tests for Gradio 6.x compatibility fixes (2026-06-13 cleanup pass).

This is a regression test for the single real deprecation site that
shipped in the Gradio 6.x transition. The cross-cutting observation
in ``Docs/BUILD_OPPORTUNITIES_2026-06-12.md`` claimed 17 col_count
deprecation sites; the actual audit found 1: a ``gr.Dropdown`` with
empty initial ``choices`` and a fixed ``value=""`` that fired a
``UserWarning`` on construction.

The fix: add ``allow_custom_value=True`` to the ``recipe_selector``
in ``shopstack/ui/tabs/cookbook_filter.py``. Plus a pin cleanup in
``requirements.txt`` (``<6.0`` → ``<7.0``).

These tests assert the structural fix (the kwarg is present) so a
future refactor can't quietly re-introduce the warning.
"""

from __future__ import annotations

import re
from pathlib import Path


# ─── Test the fix is in place ──────────────────────────────────────────


class TestRecipeSelectorFix:
    """The recipe_selector dropdown must allow custom values so the
    empty-initial-choices pattern doesn't fire the Gradio 6.x
    UserWarning on construction."""

    def test_recipe_selector_allows_custom_value(self):
        path = Path("shopstack/ui/tabs/cookbook_filter.py")
        assert path.exists(), f"{path} not found"
        text = path.read_text()
        # Find the recipe_selector dropdown and verify the kwarg.
        match = re.search(
            r"recipe_selector\s*=\s*gr\.Dropdown\(\s*([^)]+?)\)",
            text,
            re.DOTALL,
        )
        assert match, "recipe_selector = gr.Dropdown(...) not found"
        block = match.group(1)
        assert "allow_custom_value" in block, (
            "recipe_selector dropdown is missing allow_custom_value kwarg. "
            "This is a regression: it was added on 2026-06-13 to fix the "
            "Gradio 6.x UserWarning about empty choices."
        )
        # And it should be True (not False).
        av_match = re.search(r"allow_custom_value\s*=\s*(True|False)", block)
        assert av_match, "allow_custom_value value not found"
        assert av_match.group(1) == "True", (
            f"allow_custom_value is {av_match.group(1)}; should be True"
        )

    def test_recipe_selector_still_has_value_placeholder(self):
        """The fix must not break the 'Open recipe' placeholder behavior."""
        path = Path("shopstack/ui/tabs/cookbook_filter.py")
        text = path.read_text()
        match = re.search(
            r"recipe_selector\s*=\s*gr\.Dropdown\(\s*([^)]+?)\)",
            text,
            re.DOTALL,
        )
        assert match
        block = match.group(1)
        assert 'value=""' in block, "value=\"\" placeholder is missing"


# ─── Test the pin is updated ───────────────────────────────────────────


class TestGradioPinFix:
    """The requirements.txt pin must allow Gradio 6.x (we run on 6.17)."""

    def test_requirements_txt_allows_gradio_6(self):
        path = Path("requirements.txt")
        assert path.exists()
        text = path.read_text()
        for line in text.splitlines():
            if line.startswith("#"):
                continue
            if line.lower().startswith("gradio"):
                # Must be <7.0 (not <6.0) and must allow 6.x.
                assert "<7.0" in line or "< 7.0" in line, (
                    f"requirements.txt pins gradio to {line!r}; "
                    "should be <7.0 (allowing 6.x)."
                )
                assert "<6.0" not in line and "< 6.0" not in line, (
                    f"requirements.txt still excludes Gradio 6.x: {line!r}"
                )
                return
        pytest.skip("No gradio pin in requirements.txt")


# ─── Audit: verify the cross-cutting observation is now stale ──────────


class TestGradio6Audit:
    """Lock in the audit findings so a future agent doesn't repeat the
    '17 col_count sites' claim against the codebase."""

    def test_no_col_count_usages(self):
        """The doc claimed 17 col_count deprecation sites; the real state
        is 0. This test guards against re-introducing col_count usage
        in the future without realizing it's a Gradio 5.x pattern.
        """
        # Scan all Python files in the project (excluding the venv).
        for path in Path("shopstack").rglob("*.py"):
            text = path.read_text()
            # Look for the keyword form, not the string.
            if re.search(r"col_count\s*=", text):
                # Some legitimate usages may exist in comments; the
                # audit's claim was about real Gradio component kwarg
                # usages, so we tolerate lines that start with #.
                bad_lines = [
                    line
                    for line in text.splitlines()
                    if re.search(r"col_count\s*=", line)
                    and not line.strip().startswith("#")
                ]
                assert not bad_lines, (
                    f"col_count used as kwarg in {path}:\n"
                    + "\n".join(bad_lines)
                )

    def test_no_autocomplete_kwarg_in_gr_textbox(self):
        """The earlier session note claimed 3 'autocomplete' sites in
        memory.py and 1 in p2.py; neither file exists in the codebase,
        so the claim was a memory error. This test guards against the
        incorrect memory recurring in future sessions.

        Gradio 6.x gr.Textbox has no ``autocomplete`` kwarg, so any
        use of ``gr.Textbox(..., autocomplete=...)`` is a TypeError,
        not just a deprecation. We assert no such calls exist.
        """
        for path in Path("shopstack").rglob("*.py"):
            text = path.read_text()
            for line in text.splitlines():
                if line.strip().startswith("#"):
                    continue
                # The gr.Textbox case is the dangerous one.
                if re.search(r"gr\.Textbox\([^)]*autocomplete\s*=", line):
                    pytest.fail(
                        f"gr.Textbox(autocomplete=...) in {path}: {line!r} "
                        "— Gradio 6.x has no autocomplete kwarg on Textbox. "
                        "Use HTML5's autocomplete attribute on a custom "
                        "component or handle via JS injection."
                    )
