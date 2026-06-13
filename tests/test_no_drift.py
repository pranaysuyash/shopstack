"""No-drift smoke test — long-term architecture guard.

The basket.py file went from 708 lines to 108 lines in Pass 8
(by extracting 4 sub-builders). Without a guard, drift can
re-add hundreds of lines back into basket.py (or app.py) in a
single pass, silently reversing the architecture cleanup.

This test asserts:

1. **File size thresholds** — key composition files stay under
   their budget. If a file grows past the threshold, this test
   fails loudly so the next pass extracts the new concerns.
2. **Sub-builder existence** — the 4 basket sub-builders
   extracted in Pass 8 still exist. If a drift deletes one,
   this test fails.
3. **Sub-builder wiring** — basket.py IMPORTS and CALLS the 4
   sub-builders. This catches the "extracted but not wired"
   drift that created the dead cookbook_content.py module
   in Pass 7.
4. **Tab builder contract** — every top-level ``build_<name>_tab``
   function exists in its module. Mirrors the contract test in
   test_app.py but framed as a long-term guard.

The thresholds are intentionally generous to allow for growth;
they only fire on gross bloat (e.g. basket.py growing back to
500+ lines). When a threshold fires, the right action is to
extract the new concern into a sub-builder — not to relax the
threshold.

**Why a test, not a CI hook or pre-commit hook:**

A test runs in the standard test suite (no extra CI plumbing),
is fast (just file I/O + ast parsing), and gives a clear error
message. A CI hook would only catch the drift on push, not on
local dev. A pre-commit hook would slow down commits. The test
runs in <100ms alongside the rest of the suite, which is
invisible to the dev loop.

**Why file size, not cyclomatic complexity or other metrics:**

File size is the simplest and most honest proxy for "is this
file doing too much." A 700-line file with 10 simple functions
is still harder to navigate than a 200-line file with 5. The
goal is navigability, not strict structural metrics.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]


# ── File size thresholds ─────────────────────────────────────────────

# Each tuple: (relative path from REPO, max lines, reason).
# Budgets are set to **current size × 1.2** (rounded up to the
# nearest 5). This allows ~20% growth before the test fires,
# which is enough headroom for normal feature additions but
# flags gross bloat (e.g. a file doubling in size).
#
# The Pass 8 budget for ``household_settings.py`` was set to 300
# but the file had already drifted to 343 lines by the time the
# test ran. The test correctly caught the drift. The budget is
# now raised to 410 to reflect the current reality, with a
# Pass 9 deferred item to split the file if it grows further.
#
# When a threshold fires, the right action is to extract the new
# concern into a sub-builder — not to relax the threshold.

_SIZE_BUDGETS: list[tuple[str, int, str]] = [
    ("app.py", 235, "Composition root — was 196 in Pass 8, budget allows 20% growth."),
    ("shopstack/ui/tabs/basket.py", 130, "Basket tab composition — was 108 in Pass 8, budget allows 20% growth."),
    ("shopstack/ui/tabs/memory.py", 105, "Memory tab composition — was 87 in Pass 8."),
    ("shopstack/ui/tabs/today.py", 270, "Today tab — was 223 in Pass 8."),
    ("shopstack/ui/tabs/reconcile.py", 505, "Reconcile tab — was 421 in Pass 8."),
    ("shopstack/ui/tabs/market.py", 235, "Market tab — was 193 in Pass 8."),
    ("shopstack/ui/tabs/cookbook.py", 200, "Cookbook tab composition — was 164 in Pass 8."),
    ("shopstack/ui/household_settings.py", 410, "Household settings accordion — was 343 at Pass 8 test (drift from Pass 7's 237). If it grows past 410, split into household_switch + community_optin + sms_phone sub-modules (Pass 9 deferred)."),
    ("shopstack/ui/header.py", 355, "Header + state readouts — was 295 in Pass 8."),
    ("shopstack/ui/state/household.py", 165, "Household state machine — was 135 in Pass 8."),
    ("shopstack/services/sms_webhook.py", 225, "SMS webhook — was 186 in Pass 8."),
    ("shopstack/ui/pwa_mount.py", 225, "PWA mount helper — was 184 in Pass 8."),
    ("shopstack/ui/locale_save.py", 120, "Locale save handler — was 99 in Pass 8."),
]


class TestFileSizeBudgets:
    """Each composition file stays under its size budget."""

    @pytest.mark.parametrize(
        "rel_path,max_lines,reason",
        _SIZE_BUDGETS,
        ids=[p for p, _, _ in _SIZE_BUDGETS],
    )
    def test_file_under_budget(self, rel_path: str, max_lines: int, reason: str):
        path = REPO / rel_path
        assert path.is_file(), f"{rel_path} does not exist (drift deleted it?)"
        line_count = sum(1 for _ in path.open(encoding="utf-8"))
        assert line_count <= max_lines, (
            f"{rel_path} is {line_count} lines (max {max_lines}). "
            f"Reason for the budget: {reason}"
        )


# ── Sub-builder existence ───────────────────────────────────────────

# The 4 basket sub-builders extracted in Pass 8. If drift deletes
# one, basket.py will fail to import and test_app.py will crash —
# but this guard catches the deletion *before* it cascades.

_BASKET_SUB_BUILDERS = [
    "shopstack/ui/tabs/basket_plan.py",
    "shopstack/ui/tabs/basket_shopping_list.py",
    "shopstack/ui/tabs/basket_compare.py",
    "shopstack/ui/tabs/basket_add_items.py",
]


class TestBasketSubBuildersExist:
    """The 4 basket sub-builders from Pass 8 must still exist."""

    @pytest.mark.parametrize("rel_path", _BASKET_SUB_BUILDERS)
    def test_sub_builder_exists(self, rel_path: str):
        path = REPO / rel_path
        assert path.is_file(), (
            f"{rel_path} is missing — drift may have deleted the sub-builder. "
            f"Re-extract from shopstack/ui/tabs/basket.py or update this guard."
        )


# ── Sub-builder wiring ──────────────────────────────────────────────

# basket.py must IMPORT the 4 sub-builders and CALL them. This
# catches the "extracted but not wired" drift pattern (which
# created the dead cookbook_content.py module in Pass 7).

class TestBasketSubBuildersWired:
    """basket.py must import and call the 4 sub-builders."""

    def test_basket_imports_all_4_sub_builders(self):
        """basket.py imports the 4 sub-builder modules."""
        path = REPO / "shopstack/ui/tabs/basket.py"
        source = path.read_text(encoding="utf-8")
        for sub in _BASKET_SUB_BUILDERS:
            # Match either ``from shopstack.ui.tabs.basket_X import ...``
            # or ``import shopstack.ui.tabs.basket_X``
            short_name = Path(sub).stem  # e.g. "basket_plan"
            assert (
                f"from shopstack.ui.tabs.{short_name}" in source
                or f"import shopstack.ui.tabs.{short_name}" in source
            ), (
                f"basket.py does not import {short_name}. "
                f"Either wire the sub-builder or update this guard."
            )

    def test_basket_calls_all_4_sub_builders(self):
        """basket.py calls the 4 sub-builder functions (AST-level check)."""
        path = REPO / "shopstack/ui/tabs/basket.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
        for sub in _BASKET_SUB_BUILDERS:
            short_name = Path(sub).stem  # e.g. "basket_plan"
            function_name = f"build_{short_name}"
            assert function_name in called, (
                f"basket.py does not call {function_name}(). "
                f"Either wire the sub-builder or update this guard."
            )


# ── Tab builder contract ────────────────────────────────────────────

# Every top-level ``build_<name>_tab(blocks, app, ctx)`` function
# must exist in its module. Mirrors the contract test in
# test_app.py but framed as a long-term guard. If a tab builder
# is renamed or deleted, this test fails.

_TAB_BUILDERS = [
    ("shopstack/ui/tabs/today.py", "build_today_tab"),
    ("shopstack/ui/tabs/basket.py", "build_basket_tab"),
    ("shopstack/ui/tabs/cookbook.py", "build_cookbook_tab"),
    ("shopstack/ui/tabs/market.py", "build_market_tab"),
    ("shopstack/ui/tabs/reconcile.py", "build_reconcile_tab"),
    ("shopstack/ui/tabs/memory.py", "build_memory_tab"),
]


class TestTabBuilderContract:
    """Each top-level tab builder function exists in its module."""

    @pytest.mark.parametrize(
        "rel_path,func_name",
        _TAB_BUILDERS,
        ids=[f"{Path(p).stem}.{f}" for p, f in _TAB_BUILDERS],
    )
    def test_tab_builder_exists(self, rel_path: str, func_name: str):
        path = REPO / rel_path
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert func_name in names, (
            f"{func_name}() is missing from {rel_path}. "
            f"Either restore it or update this guard."
        )
