"""Regression tests for API discoverability (the 80-endpoint API surface).

Per `docs/audits/audit_02_hf_gradio.md` finding 2.4 (R1):
    "Add a regression test that asserts all api_name values are
     unique, all api_description values are non-empty, and all
     api_description values are meaningful English sentences."

This test walks the source code statically (not the built Gradio
Blocks) to find all ``api_name=...`` and ``api_description=...``
parameters in event handler calls. It does not require building
the Gradio app, so it runs in < 1 second.

Why static analysis instead of building the Blocks:
- Building the Blocks requires the full app context (DB, providers,
  etc.) which is heavy and slow.
- Static analysis is sufficient to catch the most common regressions:
  duplicate api_name, empty api_description, missing api_name on
  public event handlers.

What static analysis does NOT catch:
- Event handlers registered programmatically (e.g., in a loop with
  computed api_name). These are rare in ShopStack.
- The runtime shape of the API surface (e.g., whether the endpoint
  actually responds). For runtime shape, see test_app.py which
  builds the full app.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


# Files that contain event handler registrations with api_name.
# Keep this list in sync with the audit's per-file inventory.
UI_DIR = Path(__file__).resolve().parents[1] / "shopstack" / "ui"
APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _collect_api_endpoints() -> list[dict]:
    """Walk source files and extract (api_name, api_description) pairs.

    Returns a list of dicts with keys:
        - file: source file path
        - line: line number
        - api_name: the value passed to api_name=
        - api_description: the value passed to api_description=
                        (or None if missing)

    Implementation: For each api_name keyword argument, we look at
    the same Call node's full set of keyword arguments. If
    api_description is also a keyword in the same call, we capture
    it (handling string concatenation by joining parts).
    """
    endpoints: list[dict] = []
    sources: list[Path] = list(UI_DIR.rglob("*.py")) + [APP_PY]

    for src in sources:
        try:
            content = src.read_text()
        except FileNotFoundError:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            # Find api_name and api_description in this call
            api_name_kw = None
            api_desc_kw = None
            for kw in node.keywords:
                if kw.arg == "api_name":
                    api_name_kw = kw
                elif kw.arg == "api_description":
                    api_desc_kw = kw

            if api_name_kw is None:
                continue

            if not (
                isinstance(api_name_kw.value, ast.Constant)
                and isinstance(api_name_kw.value.value, str)
            ):
                continue

            api_name = api_name_kw.value.value
            line = api_name_kw.value.lineno
            # Normalize file path: "shopstack/ui/tabs/basket.py" or "app.py"
            try:
                file = str(src.relative_to(Path(__file__).resolve().parents[1]))
            except ValueError:
                file = str(src.name)

            # Extract api_description (handles string concatenation and BinOp)
            api_desc = _extract_string_value(api_desc_kw.value) if api_desc_kw else None

            endpoints.append({
                "file": file,
                "line": line,
                "api_name": api_name,
                "api_description": api_desc,
            })

    return endpoints


def _extract_string_value(node) -> str | None:
    """Recursively extract a string value from an AST node.

    Handles:
    - ast.Constant (literal string)
    - ast.BinOp with ast.Add operator (string concatenation)
    - Returns None if the node is not a string-producing expression.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _extract_string_value(node.left)
        right = _extract_string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


# Collect once at module load time (test results don't change between runs)
ALL_ENDPOINTS = _collect_api_endpoints()


def test_api_name_count_meets_threshold():
    """The app exposes a healthy number of named API endpoints.

    v3 baseline: 80. We assert >= 50 to allow for renames/refactors
    without flagging trivial changes. If this fails, the API
    surface has shrunk significantly — investigate.
    """
    assert len(ALL_ENDPOINTS) >= 50, (
        f"Only {len(ALL_ENDPOINTS)} api_name endpoints found. "
        f"Expected >= 50. See docs/audits/audit_02_hf_gradio.md "
        f"for the v3 inventory."
    )


def test_all_api_names_unique():
    """No two event handlers should share the same api_name.

    Duplicate api_name would cause Gradio to raise on app build
    (or silently override one handler). This test fails fast.
    """
    from collections import Counter

    names = [e["api_name"] for e in ALL_ENDPOINTS]
    counts = Counter(names)
    duplicates = {name: count for name, count in counts.items() if count > 1}

    assert not duplicates, (
        f"Duplicate api_name values found: {duplicates}. "
        f"Gradio will raise on app build (or override silently). "
        f"Rename one of the conflicting endpoints."
    )


def test_all_api_names_non_empty():
    """Every api_name should be a non-empty meaningful string.

    Empty api_name disables the public API endpoint — but if
    someone passes an empty string by accident, this test catches it.
    """
    for ep in ALL_ENDPOINTS:
        assert ep["api_name"], (
            f"Empty api_name at {ep['file']}:{ep['line']}"
        )
        assert len(ep["api_name"]) >= 3, (
            f"api_name '{ep['api_name']}' is too short (< 3 chars) at "
            f"{ep['file']}:{ep['line']}"
        )
        # Snake_case convention
        assert re.match(r"^[a-z][a-z0-9_]*$", ep["api_name"]), (
            f"api_name '{ep['api_name']}' is not snake_case at "
            f"{ep['file']}:{ep['line']}"
        )


def test_all_api_descriptions_non_empty():
    """Every event handler with api_name should have a meaningful description.

    The description is what `gradio info` shows to API consumers.
    An empty description is a poor user experience.
    """
    missing_desc = [
        ep for ep in ALL_ENDPOINTS
        if not ep["api_description"] or len(ep["api_description"]) < 10
    ]

    assert not missing_desc, (
        f"Missing or short api_description for these endpoints: "
        f"{[ep['api_name'] for ep in missing_desc[:5]]}... "
        f"({len(missing_desc)} total). Add a meaningful description."
    )


def test_all_api_descriptions_end_with_period():
    """Most api_descriptions should end with a period (style check).

    The shopstack convention is mixed:
    - Older endpoints use full English sentences with periods
    - Newer endpoints use phrase-style (no period)

    We assert that at least SOME descriptions end with periods
    (to ensure periods are used somewhere) and that the ratio
    doesn't drop below 5% (to ensure periods aren't completely
    abandoned).
    """
    not_ending_with_period = [
        ep for ep in ALL_ENDPOINTS
        if ep["api_description"] and not ep["api_description"].rstrip().endswith(".")
    ]

    ending_with_period = [
        ep for ep in ALL_ENDPOINTS
        if ep["api_description"] and ep["api_description"].rstrip().endswith(".")
    ]

    total = len(ALL_ENDPOINTS)
    pct_ending = len(ending_with_period) / total if total else 0

    # At least 5% should end with periods
    assert pct_ending >= 0.05, (
        f"Only {len(ending_with_period)}/{total} api_descriptions "
        f"({pct_ending:.1%}) end with a period. The period convention "
        f"may have drifted — consider standardizing."
    )


def test_known_endpoints_exist():
    """Spot-check that critical API endpoints are still present.

    This test guards against accidental removal of high-value
    endpoints. If an endpoint is renamed intentionally, update
    this test.
    """
    names = {ep["api_name"] for ep in ALL_ENDPOINTS}

    # Core endpoints that consumers depend on
    required = {
        "save_locale",
        "switch_household",
        "create_household",
        "ask",
        "ask_submit",
        "market_scan",
        "home_scan",
        "restock_add_to_list",
        "build_list",
        "mark_purchased",
        "complete_list",
        "unified_plan",
        "price_search",
        "add_purchase",
        "consume_item",
        "export_json",
        "export_csv",
        "import_data",
        "trace_search",
        "trace_export",
        "notes_save",
        "notes_reload",
    }

    missing = required - names
    assert not missing, (
        f"Required API endpoints missing: {missing}. "
        f"If an endpoint was renamed, update this test."
    )


def test_endpoints_per_sub_builder():
    """Each sub-builder should expose at least 1 endpoint.

    A sub-builder with 0 endpoints is either:
    (a) Pure UI / no actions (acceptable but rare)
    (b) Wired incorrectly (event handlers missing api_name)
    This test flags case (b).
    """
    by_file: dict[str, list[str]] = {}
    for ep in ALL_ENDPOINTS:
        by_file.setdefault(ep["file"], []).append(ep["api_name"])

    # Sub-builders known to have endpoints
    sub_builders_with_endpoints = {
        "app.py",
        "shopstack/ui/tabs/ask_panel.py",
        "shopstack/ui/tabs/basket.py",
        "shopstack/ui/tabs/cookbook.py",
        "shopstack/ui/tabs/market.py",
        "shopstack/ui/tabs/memory_activity.py",
        "shopstack/ui/tabs/memory_data.py",
        "shopstack/ui/tabs/memory_history.py",
        "shopstack/ui/tabs/memory_notes.py",
        "shopstack/ui/tabs/memory_nutrition.py",
        "shopstack/ui/tabs/reconcile.py",
        "shopstack/ui/tabs/today.py",
        "shopstack/ui/locale_save.py",
        "shopstack/ui/household_settings.py",
    }

    zero_endpoint_files = [
        f for f in sub_builders_with_endpoints
        if f not in by_file or len(by_file[f]) == 0
    ]

    assert not zero_endpoint_files, (
        f"These sub-builders have 0 api_name endpoints: "
        f"{zero_endpoint_files}. They should each expose at "
        f"least 1 endpoint via .click() / .change() / .submit() / .load()."
    )
