"""Regression tests for the Gradio app composition layer.

Per `docs/audits/audit_03_gradio_app_architecture.md` finding 3.2:
    "app.py should not import from shopstack.ui.screens directly.
     The composition layer should be a pure seam between the Gradio
     framework and the domain code."

These tests enforce composition discipline and verify that the
tab builder registry stays in sync with the module registry.
"""
from __future__ import annotations

import re
from pathlib import Path


def test_app_py_does_not_import_screens():
    """app.py must not import from shopstack.ui.screens (composition seam)."""
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text()

    # Find all 'from shopstack.ui.screens import ...' lines
    pattern = re.compile(
        r"^\s*from\s+shopstack\.ui\.screens[\w.]*\s+import\s+",
        re.MULTILINE,
    )
    matches = pattern.findall(app_source)

    assert not matches, (
        f"app.py imports from shopstack.ui.screens — this violates the "
        f"composition-seam discipline. The composition layer should "
        f"only talk to sub-builders (in shopstack/ui/tabs/, "
        f"shopstack/ui/household_settings.py, etc.), not screens. "
        f"Found: {matches}"
    )


def test_app_py_does_not_have_business_logic():
    """app.py should not contain domain-mutating business logic.

    A simple heuristic: no ``tools.do_*()`` calls (those mutate
    inventory, shopping lists, etc.) and no ``db.create_*()`` /
    ``db.update_*()`` / ``db.delete_*()`` calls (those are domain
    mutations). Read-only calls like ``db.get_locations()`` are
    acceptable at the composition layer because they're needed
    to populate dropdowns.

    If you need domain mutations in app.py, they belong in a
    sub-builder or a service.
    """
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text()

    # Disallowed business-logic patterns
    forbidden = [
        # tools.* mutating calls
        re.compile(r"^[^#]*\btools\.(get_|create_|update_|delete_|consume_|add_|record_)",
                   re.MULTILINE),
        # db.* mutating calls (NOT read-only get_/list_/query_)
        re.compile(r"^[^#]*\bdb\.(create_|update_|delete_|save_|insert_|set_)",
                   re.MULTILINE),
    ]

    for pat in forbidden:
        matches = pat.findall(app_source)
        assert not matches, (
            f"app.py contains business-mutating calls that should "
            f"be in a service or sub-builder. Pattern: {pat.pattern}. "
            f"Found: {matches}"
        )


def test_app_py_under_300_lines():
    """app.py must stay under 300 lines.

    A growing app.py is a signal that concerns are not being
    extracted. Tab wiring is delegated to the builder registry
    (``shopstack.ui.tabs.registry``), so app.py should stay lean
    regardless of how many tabs exist.
    """
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    line_count = sum(1 for _ in app_path.open())

    assert line_count < 300, (
        f"app.py is {line_count} lines (> 300). Consider extracting "
        f"the next concern into its own sub-builder module. See "
        f"docs/audits/audit_03_gradio_app_architecture.md."
    )


def test_app_py_uses_registry_for_tabs():
    """app_builder.py must use build_all_tabs() for tab wiring, not individual imports.

    The build_app() function was extracted from app.py to
    shopstack/app_builder.py (Pass 26, 2026-06-17). This test
    enforces the registry-driven composition pattern in the
    canonical builder module.
    """
    builder_source = (Path(__file__).resolve().parents[1] / "shopstack/app_builder.py").read_text()

    assert "from shopstack.ui.tabs.registry import build_all_tabs" in builder_source, (
        "app_builder.py must import build_all_tabs from the tab registry. "
        "Tab wiring should be registry-driven, not hardcoded."
    )

    # Ensure no individual build_*_tab imports (they belong in the registry)
    pattern = re.compile(
        r"^\s*from\s+shopstack\.ui\.tabs\.(today|cookbook|basket|market|reconcile|memory|scanner|timeline|find_trail|photo_map|repair_inbox|nutrition_coach|store_mode|smart_basket|analytics|consumption|recipe|parser|community|market_intel|trip_advisor)\s+import\s+build_",
        re.MULTILINE,
    )
    matches = pattern.findall(builder_source)
    assert not matches, (
        f"app_builder.py imports individual build_*_tab functions from tab modules. "
        f"These belong in shopstack/ui/tabs/registry.py, not app_builder.py. "
        f"Found: {matches}"
    )

    # Essential composition helpers that must be referenced in the builder
    essential_imports = [
        "build_all_tabs",
        "build_household_settings",
        "build_locale_save",
        "build_onboarding_wizard",
        "wire_household_handlers",
    ]
    missing = [name for name in essential_imports if name not in builder_source]
    assert not missing, (
        f"app_builder.py does not reference these essential composition helpers: {missing}."
    )

    # Verify app.py delegates to app_builder.py
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert "from shopstack.app_builder import build_app" in app_source, (
        "app.py must delegate build_app() to shopstack.app_builder."
    )


def test_app_py_guards_required_handles():
    """app_builder.py must assert that required tab handles are non-None.

    The handle guards were extracted from app.py to
    shopstack/app_builder.py (Pass 26, 2026-06-17). This test
    verifies they exist in the canonical builder module.

    Per audit 2026-06-14 P0 finding: if build_today_tab or
    build_reconcile_tab returns None (or is silently skipped by the
    registry), build_app() would crash with AttributeError deep inside the
    event wiring. This is a P0 guard.

    The guards must:
    - Check handles.get("today") and handles.get("reconcile")
    - Raise a clear RuntimeError with diagnostic context
    - Mention which builder is missing and where to look
    """
    builder_source = (Path(__file__).resolve().parents[1] / "shopstack/app_builder.py").read_text()

    # Check for the guard pattern
    required_patterns = [
        ('handles.get("today")', "Today tab handle extraction"),
        ('handles.get("reconcile")', "Reconcile tab handle extraction"),
        ("RuntimeError", "Explicit runtime error (not silent AttributeError)"),
    ]
    missing_patterns = [name for pattern, name in required_patterns
                        if pattern not in builder_source]
    assert not missing_patterns, (
        f"app_builder.py is missing required handle guards: {missing_patterns}. "
        f"Per audit 2026-06-14, app_builder.py must fail fast with a clear "
        f"RuntimeError if today or reconcile builders return None. "
        f"Without these guards, a broken tab builder would crash with "
        f"a confusing AttributeError deep in the event wiring."
    )


def test_app_py_refreshes_home_flow_on_household_switch():
    """The household switch wiring must refresh the new home_flow handle.

    Added 2026-06-15 (Home screen review). The state-aware home flow
    panel (Home flow state machine) must re-render when the user
    switches households — otherwise a new household with different
    data would still show the old household's hero. The wiring was
    extracted from app.py into ``shopstack/app_builder.py`` (Pass 26)
    and ``shopstack/ui/state/household_wiring.py`` (Pass 15); both
    files are checked here to keep the contract visible.
    """
    builder_source = (Path(__file__).resolve().parents[1] / "shopstack/app_builder.py").read_text()
    # The app composition layer must call the household-wiring
    # sub-builder, which in turn references the home_flow handle.
    assert "wire_household_handlers" in builder_source, (
        "app_builder.py must call wire_household_handlers() to register "
        "the cross-tab event handlers (household switch, "
        "create-household, per-render refresh, JS shims)."
    )

    wiring_source = (
        Path(__file__).resolve().parents[1]
        / "shopstack/ui/state/household_wiring.py"
    ).read_text()
    assert "home_flow" in wiring_source, (
        "shopstack/ui/state/household_wiring.py must reference "
        "'home_flow' so the state-aware hero re-renders when the "
        "active household changes."
    )
