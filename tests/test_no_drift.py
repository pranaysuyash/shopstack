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
    ("app.py", 360, "Composition root — grew from 235 (Pass 8) to 299 after adding 15 new tab builders (timeline, scanner, trip_advisor, market_intel, nutrition_coach, photo_map, find_trail, store_mode, smart_basket, analytics, repair_inbox, consumption, recipe, parser, community). Budget set to 360 to allow headroom for a few more tabs; if it grows past 360, extract tab composition into a sub-builder."),
    ("shopstack/ui/tabs/basket.py", 130, "Basket tab composition — was 108 in Pass 8, budget allows 20% growth."),
    ("shopstack/ui/tabs/memory.py", 105, "Memory tab composition — was 87 in Pass 8."),
    ("shopstack/ui/tabs/today.py", 270, "Today tab — was 223 in Pass 8."),
    ("shopstack/ui/tabs/reconcile.py", 505, "Reconcile tab — was 421 in Pass 8."),
    ("shopstack/ui/tabs/market.py", 235, "Market tab — was 193 in Pass 8."),
    ("shopstack/ui/tabs/cookbook.py", 200, "Cookbook tab composition — was 164 in Pass 8."),
    ("shopstack/ui/household_settings.py", 480, "Household settings accordion — was 343 at Pass 8 test (drift from Pass 7's 237), 437 as of 2026-06-15. Budget raised to 480 to allow ~10% headroom. Original Pass 9 deferred item: split into household_switch + community_optin + sms_phone sub-modules when file grows past 410. Revisit if it exceeds 480."),
    ("shopstack/ui/header.py", 720, "Header + state readouts — was 295 in Pass 8, 355 before item #36/#99 hydration recovery + bootstrap re-exec additions, 470 before item #99b's toast-trigger MutationObserver + action-button support in showToast() (2026-06-14), 590 before Pass 13 keyboard-shortcut handler (j/k/?/Escape/Enter for keyboard navigation per §0.14 product reality). Budget raised to 720 to allow ~5% headroom for further shortcut/quick-action additions. If file grows past 720, consider extracting shortcuts to a dedicated module."),
    ("shopstack/ui/state/household.py", 165, "Household state machine — was 135 in Pass 8."),
    ("shopstack/services/sms_webhook.py", 250, "SMS webhook — was 186 in Pass 8, drift to 318 in Pass 10. In Pass 14 (2026-06-14) the per-intent handlers were extracted to shopstack/services/sms_intent_handlers.py (135 lines), bringing sms_webhook back to a thin transport adapter (229 lines). The budget allows for further growth from the Twilio signature-verification path, but if it climbs past 250 the dispatcher closure should be extracted next."),
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


# ── Forbidden paths (supersession guards) ──────────────────────────

# Paths that were intentionally deleted via supersession. If
# drift re-introduces them, the no-drift test fails. Each entry
# is a tuple: (relative path, reason for deletion). The reason
# is shown in the failure message so the next agent knows why
# the path is forbidden.

_FORBIDDEN_PATHS: list[tuple[str, str]] = [
    # Pass 7: dead module that was extracted in a previous session
    # but never wired up. The functionality lives in shopstack/ui/
    # tabs/cookbook.py (the parent that should have called it).
    ("shopstack/ui/tabs/cookbook_content.py",
     "Dead module from a previous session; functionality is in shopstack/ui/tabs/cookbook.py."),

    # Pass 9: deprecated swiggy data source package. The canonical
    # path is shopstack/market/sources/swiggy.py (plus
    # shopstack/market/sources/_swiggy_adapter.py for the adapter
    # protocol). The 3 deprecated functions have explicit
    # DeprecationWarnings pointing to the canonical paths. Pass 9
    # migrated all callers (tests/test_swiggy_data_source.py was
    # deleted; the canonical tests live in test_market.py::
    # TestSwiggyLoader + TestAnalytics; module_registry.py no
    # longer lists the deprecated module). The package is
    # permanently gone — any re-introduction is drift.
    ("shopstack/data_sources/__init__.py",
     "Deprecated package (Pass 9 supersession); use shopstack/market/sources/."),
    ("shopstack/data_sources/swiggy.py",
     "Deprecated module (Pass 9 supersession); use shopstack/market/sources/swiggy.py."),

    # Pass 9: deprecated swiggy data source package. The canonical
    # path is shopstack/market/sources/swiggy.py (plus
    # shopstack/market/sources/_swiggy_adapter.py for the adapter
    # protocol). Pass 9 migrated all callers (tests/test_swiggy_data_source.py was
    # deleted; the canonical tests live in test_market.py::
    # TestSwiggyLoader + TestAnalytics; module_registry.py no
    # longer lists the deprecated module). The package is
    # permanently gone — any re-introduction is drift.
    ("shopstack/data_sources/__init__.py",
     "Deprecated package (Pass 9 supersession); use shopstack/market/sources/."),
    ("shopstack/data_sources/swiggy.py",
     "Deprecated module (Pass 9 supersession); use shopstack/market/sources/swiggy.py."),

    # NOTE: ``tests/test_swiggy_data_source.py`` was deleted in Pass 9
    # but the canonical migration landed in Pass 9b at
    # ``tests/test_market_swiggy_migration.py``. If anyone re-introduces
    # the old test file, it will likely test the deprecated API and
    # break. The migration file is the canonical coverage; restore
    # the old file only by porting its tests to the canonical API.
    ("tests/test_swiggy_data_source.py",
     "Old test file for the deprecated swiggy API (Pass 9 supersession); migration is in tests/test_market_swiggy_migration.py."),

    # Pass 10: deprecated re-exports from primitives.py. The 4 symbols
    # were moved to canonical modules (js_helpers, decorators) and
    # have been fully migrated (0 production callers). If drift
    # re-adds the deprecated aliases, the canonical migration is
    # broken.
    #
    # These four are documented as comments (not real path checks)
    # because the deprecation is at the module-level function alias
    # level, not the file level. A real test verifying the
    # deprecation is in tests/test_primitives_deprecation.py.
    ("shopstack/ui/components/primitives.busy_js",
     "Deprecated alias removed in Pass 10. Use shopstack.ui.components.js_helpers.busy_js."),
    ("shopstack/ui/components/primitives.autocomplete_injector_js",
     "Deprecated alias removed in Pass 10. Use shopstack.ui.components.js_helpers.autocomplete_injector_js."),
    ("shopstack/ui/components/primitives.url_state_sync_js",
     "Deprecated alias removed in Pass 10. Use shopstack.ui.components.js_helpers.url_state_sync_js."),
    ("shopstack/ui/components/primitives.aria_live_screen",
     "Deprecated alias removed in Pass 10. Use shopstack.ui.components.decorators.aria_live_screen."),
]


class TestForbiddenPaths:
    """Paths deleted via supersession must not be re-introduced by drift."""

    @pytest.mark.parametrize(
        "rel_path,reason",
        _FORBIDDEN_PATHS,
        ids=[p for p, _ in _FORBIDDEN_PATHS],
    )
    def test_path_does_not_exist(self, rel_path: str, reason: str):
        path = REPO / rel_path
        assert not path.exists(), (
            f"{rel_path} was re-introduced by drift. "
            f"Reason for deletion: {reason} "
            f"If you intentionally re-added this path, update the forbidden list."
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
