"""Smoke test for the 80-endpoint API surface (AI-10).

Per `docs/audits/ACTION_ITEMS.md` AI-10: Verify the full API
surface is discoverable without needing to run `gradio info`
against a live server.

This test wraps ``tests/test_api_discoverability.py``'s static
inventory in a single ``test_gradio_info_smoke`` function. It
also runs a contract test: each tab builder that should expose
endpoints does expose them.

Why static (not ``gradio info`` against a live server):
- Building the full app requires DB, providers, etc. — slow
- A static inventory is enough to catch the regressions the
  test cares about (duplicate api_name, missing description, etc.)
- For runtime shape verification, run the full ``test_app.py``
  integration suite separately
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import ast

# Same paths as test_api_discoverability.py
UI_DIR = Path(__file__).resolve().parents[1] / "shopstack" / "ui"
APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _collect_api_endpoints() -> list[dict]:
    """Walk source files and extract (api_name, api_description) pairs."""
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
            try:
                file = str(src.relative_to(Path(__file__).resolve().parents[1]))
            except ValueError:
                file = str(src.name)

            api_desc = _extract_string_value(api_desc_kw.value) if api_desc_kw else None

            endpoints.append({
                "file": file,
                "line": line,
                "api_name": api_name,
                "api_description": api_desc,
            })

    return endpoints


def _extract_string_value(node) -> str | None:
    """Recursively extract a string from AST (handles string concat)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _extract_string_value(node.left)
        right = _extract_string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


ENDPOINTS = _collect_api_endpoints()


def test_gradio_info_smoke():
    """The full Gradio API surface is discoverable.

    This is the smoke test that the app would show 75+ named
    endpoints to ``gradio info`` consumers. If the count drops
    below 75, investigate (per AI-10 closure path).
    """
    assert len(ENDPOINTS) >= 75, (
        f"Only {len(ENDPOINTS)} endpoints found. Expected >= 75. "
        f"Per AI-10, the API surface should stay above 75 to "
        f"keep ``gradio info`` consumers in sync. If you intentionally "
        f"removed endpoints, update the test threshold."
    )


def test_critical_endpoints_present():
    """The 22 critical endpoints must be present.

    This is a stronger check than ``test_gradio_info_smoke`` —
    it asserts specific named endpoints are present. If a
    refactor removes any of these, the test fails immediately.
    """
    names = {e["api_name"] for e in ENDPOINTS}
    required = {
        # Core orchestration
        "save_locale",
        "runtime_status",
        "switch_household",
        "create_household",
        # Ask / Ask submit (dual-trigger)
        "ask",
        "ask_submit",
        # Market lens
        "market_scan",
        "home_scan",
        # Basket tab (key endpoints)
        "build_list",
        "mark_purchased",
        "complete_list",
        "unified_plan",
        # Reconcile tab
        "add_purchase",
        "consume_item",
        "move_inventory",
        # Memory tab (trace endpoints)
        "trace_search",
        "trace_export",
        # Memory tab (notes)
        "notes_save",
        "notes_reload",
        # Data portability
        "export_json",
        "export_csv",
        "import_data",
    }

    missing = required - names
    assert not missing, (
        f"Missing critical API endpoints: {missing}. "
        f"If you intentionally renamed, update this test."
    )


def test_no_duplicate_endpoints_in_smoke():
    """Duplicate api_name values are a hard failure (Gradio will raise).

    This is a strict duplicate check. The full
    test_api_discoverability.py:test_all_api_names_unique test
    is more thorough (cross-file) but this one is the smoke version.
    """
    names = [e["api_name"] for e in ENDPOINTS]
    counts = Counter(names)
    duplicates = {name: count for name, count in counts.items() if count > 1}

    assert not duplicates, (
        f"Duplicate api_name values in static inventory: {duplicates}. "
        f"Gradio will raise on app build. Rename the conflicting "
        f"endpoints."
    )
