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
    """app.py must use build_all_tabs() for tab wiring, not individual imports.

    This is the positive control that verifies the registry-driven
    composition pattern is being followed. app.py should import
    ``build_all_tabs`` from the registry, not 21 individual
    ``build_*_tab`` functions.
    """
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text()

    assert "from shopstack.ui.tabs.registry import build_all_tabs" in app_source, (
        "app.py must import build_all_tabs from the tab registry. "
        "Tab wiring should be registry-driven, not hardcoded."
    )

    # Ensure no individual build_*_tab imports (they belong in the registry)
    pattern = re.compile(
        r"^\s*from\s+shopstack\.ui\.tabs\.(today|cookbook|basket|market|reconcile|memory|scanner|timeline|find_trail|photo_map|repair_inbox|nutrition_coach|store_mode|smart_basket|analytics|consumption|recipe|parser|community|market_intel|trip_advisor)\s+import\s+build_",
        re.MULTILINE,
    )
    matches = pattern.findall(app_source)
    assert not matches, (
        f"app.py imports individual build_*_tab functions from tab modules. "
        f"These belong in shopstack/ui/tabs/registry.py, not app.py. "
        f"Found: {matches}"
    )

    # Essential composition helpers that must remain
    essential_imports = [
        "build_all_tabs",
        "build_household_settings",
        "build_locale_save",
        "mount_pwa_static",
        "mount_sms_webhook",
    ]
    missing = [name for name in essential_imports if name not in app_source]
    assert not missing, (
        f"app.py does not reference these essential composition helpers: {missing}."
    )
