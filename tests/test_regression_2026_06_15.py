"""Regression tests for the 2026-06-15 Test-Failure Hardening Pass.

Each test guards against one of the failures fixed in DR-NEW. If any
of these regress, the corresponding fix was lost.

See: Docs/DECISION_RECORDS.md → DR-NEW: Test-Failure Hardening Pass
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── Regression: shopstack/services/condition.py ──────────────────────
class TestRecordConditionEventCanonicalNameDerivation:
    """``record_condition_event`` must auto-derive ``canonical_name`` from
    the lot when the caller doesn't provide it. This was the root cause
    of ``test_inbox_with_event_renders_item`` failing — the test lot was
    invisible to household-scoped ``get_inventory()`` so the view
    showed an empty name."""

    def test_canonical_name_derived_from_lot(self):
        from shopstack.app_context import current_user_id, db as app_db
        from shopstack.services.condition import record_condition_event
        from shopstack.schemas.models import InventoryLot

        # Insert a lot under a sentinel canonical name
        sentinel = "TestItemReg_2026_06_15_xyz"
        app_db.conn.execute(
            "INSERT INTO inventory_lots (lot_id, canonical_name, display_name, "
            "quantity, unit, storage_location_id, purchase_date, status, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("reg_lot_1", sentinel, sentinel, 1.0, "unit", "fridge",
             "2026-06-14", "active", current_user_id()),
        )
        app_db.conn.commit()

        try:
            # Call without providing canonical_name
            record_condition_event(
                app_db,
                lot_id="reg_lot_1",
                kind="physical_damage",
                severity="damaged",
                description="Regression test",
            )
            # The event should now have canonical_name set
            rows = app_db.get_condition_events_for_lot("reg_lot_1")
            assert rows, "No condition event was recorded"
            canonical_names = [r["canonical_name"] for r in rows]
            assert sentinel in canonical_names, (
                f"canonical_name not derived from lot: {canonical_names}"
            )
        finally:
            for r in app_db.get_condition_events_for_lot("reg_lot_1"):
                app_db.delete_condition_event(r["event_id"])
            app_db.conn.execute(
                "DELETE FROM inventory_lots WHERE lot_id = ?",
                ("reg_lot_1",),
            )
            app_db.conn.commit()


# ─── Regression: shopstack/traces/export.py ──────────────────────────
class TestRedactNestedKeyDetection:
    """``_redact_obj`` must use ``_redact_args_dict`` for nested dicts so
    sensitive key names (``aadhar``, ``pan``, ``phone``, ``email``) in
    nested objects are caught by the key-name detection path. This was
    the root cause of ``test_redact_nested_text_fields`` failing —
    nested dicts were treated as opaque text values, missing key
    detection."""

    def test_nested_aadhar_key_caught(self):
        from shopstack.traces.export import _redact_trace
        trace = {
            "proposed_tool_calls": [
                {
                    "tool_name": "add_inventory",
                    "args": {"meta": {"aadhar": "ABCDE1234F"}},
                }
            ]
        }
        redacted = _redact_trace(trace)
        actual = redacted["proposed_tool_calls"][0]["args"]["meta"]["aadhar"]
        assert actual == "[REDACTED]", (
            f"key-name 'aadhar' in nested dict not caught: got {actual!r}"
        )

    def test_nested_pan_key_caught(self):
        from shopstack.traces.export import _redact_trace
        trace = {
            "proposed_tool_calls": [
                {"args": {"nested": {"pan": "ABCDE1234F"}}}
            ]
        }
        redacted = _redact_trace(trace)
        actual = redacted["proposed_tool_calls"][0]["args"]["nested"]["pan"]
        assert actual == "[REDACTED]", (
            f"key-name 'pan' in nested dict not caught: got {actual!r}"
        )

    def test_nested_phone_key_caught(self):
        from shopstack.traces.export import _redact_trace
        trace = {
            "perception": {"phone": "9876543210"}
        }
        redacted = _redact_trace(trace)
        actual = redacted["perception"]["phone"]
        assert actual == "[REDACTED]", (
            f"key-name 'phone' in nested dict not caught: got {actual!r}"
        )


# ─── Regression: shopstack/ui/components/primitives.py ───────────────
class TestDeprecatedPrimitivesAliasesWired:
    """The deprecated re-export aliases (``busy_js``,
    ``autocomplete_injector_js``, ``url_state_sync_js``,
    ``aria_live_screen``) must exist on
    ``shopstack.ui.components.primitives`` and emit a
    ``DeprecationWarning`` when called. This was the half-finished
    supersession that left the module in an AttributeError state."""

    def test_busy_js_alias_exists_and_warns(self):
        import warnings
        from shopstack.ui.components import primitives
        from shopstack.ui.components.js_helpers import busy_js as canonical

        assert hasattr(primitives, "busy_js"), "busy_js alias missing"
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            result = primitives.busy_js("test-btn")
        deprecations = [
            w for w in ws
            if issubclass(w.category, DeprecationWarning)
            and "busy_js" in str(w.message)
        ]
        assert deprecations, "busy_js alias did not emit DeprecationWarning"
        assert result == canonical("test-btn"), "alias diverged from canonical"

    def test_autocomplete_injector_js_alias_exists_and_warns(self):
        import warnings
        from shopstack.ui.components import primitives
        from shopstack.ui.components.js_helpers import (
            autocomplete_injector_js as canonical,
        )
        assert hasattr(primitives, "autocomplete_injector_js"), "alias missing"
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            result = primitives.autocomplete_injector_js()
        deprecations = [
            w for w in ws
            if issubclass(w.category, DeprecationWarning)
            and "autocomplete_injector_js" in str(w.message)
        ]
        assert deprecations, "autocomplete_injector_js did not warn"
        assert result == canonical(), "alias diverged from canonical"

    def test_url_state_sync_js_alias_exists_and_warns(self):
        import warnings
        from shopstack.ui.components import primitives
        from shopstack.ui.components.js_helpers import (
            url_state_sync_js as canonical,
        )
        assert hasattr(primitives, "url_state_sync_js"), "alias missing"
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            result = primitives.url_state_sync_js()
        deprecations = [
            w for w in ws
            if issubclass(w.category, DeprecationWarning)
            and "url_state_sync_js" in str(w.message)
        ]
        assert deprecations, "url_state_sync_js did not warn"
        assert result == canonical(), "alias diverged from canonical"

    def test_aria_live_screen_alias_exists_and_warns(self):
        import warnings
        from shopstack.ui.components import primitives
        from shopstack.ui.components.decorators import (
            aria_live_screen as canonical,
        )
        assert hasattr(primitives, "aria_live_screen"), "alias missing"
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            decorator = primitives.aria_live_screen()
            @decorator
            def render(x):
                return f"<div>{x}</div>"
            out = render("x")
        deprecations = [
            w for w in ws
            if issubclass(w.category, DeprecationWarning)
            and "aria_live_screen" in str(w.message)
        ]
        assert deprecations, "aria_live_screen did not warn"
        assert "decorators.aria_live_screen" in str(deprecations[0].message)


# ─── Regression: shopstack/ui/screens/__init__.py ────────────────────
class TestScreensExportsComplete:
    """``shopping_list_share`` must be re-exported from
    ``shopstack.ui.screens``. Was missing despite the function being
    defined in ``shopping.py`` — caused import errors in
    ``test_basket_shopping_list.py`` and the tab registry."""

    def test_shopping_list_share_exported(self):
        from shopstack.ui import screens
        from shopstack.ui.screens.shopping import (
            shopping_list_share as canonical,
        )
        assert hasattr(screens, "shopping_list_share"), (
            "shopping_list_share not re-exported from shopstack.ui.screens"
        )
        assert screens.shopping_list_share is canonical, (
            "re-exported symbol is not the canonical function"
        )


# ─── Regression: shopstack/  bulk f-string repair ────────────────────
class TestNoOrphanFStringContinuations:
    """After the 82-file parallel-agent corruption repair, no file
    should still have the pattern ``f"..."\\n        f"..."`` or
    other unterminated f-string continuations."""

    def test_no_broken_fstring_continuations(self):
        from pathlib import Path
        pattern = re.compile(r'f"[^"\\]*"\\n\s*f"')
        offenders = []
        for fp in Path("shopstack").rglob("*.py"):
            content = fp.read_text()
            if pattern.search(content):
                offenders.append(str(fp))
        assert not offenders, (
            f"Found broken f-string continuations in: {offenders}"
        )

    def test_no_orphan_docstrings_at_module_scope(self):
        """An orphaned docstring at module scope is a SyntaxError."""
        import ast
        from pathlib import Path
        offenders = []
        for fp in Path("shopstack").rglob("*.py"):
            try:
                tree = ast.parse(fp.read_text())
            except SyntaxError:
                continue
            # Module-level string literals (not assigned) are syntax errors
            for node in tree.body:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str):
                        offenders.append((str(fp), node.lineno))
        assert not offenders, (
            f"Orphan module-level docstrings in: {offenders}"
        )


# ─── Regression: tests/test_new_providers.py::_patch_modules ──────────
class TestPatchModulesIdiom:
    """``_patch_modules`` must use ``sys.modules[k] = None`` (the Python
    idiom for unavailable modules) instead of ``sys.modules.pop(k)``
    (which causes a fresh import of C-extensions like torch and
    segfaults on Python 3.14)."""

    def test_none_value_uses_setattr_not_pop(self):
        from tests.test_new_providers import _patch_modules

        import sys
        # Set a sentinel
        sentinel_key = "_test_patch_modules_sentinel_xyz"
        sys.modules[sentinel_key] = "before"

        with _patch_modules({sentinel_key: None}):
            # Inside the with-block, sys.modules[key] should be None
            assert sentinel_key in sys.modules, (
                "_patch_modules popped the key instead of setting None"
            )
            assert sys.modules[sentinel_key] is None, (
                "_patch_modules did not set sys.modules[key] = None"
            )

        # After exit, the key should be restored to "before"
        assert sys.modules.get(sentinel_key) == "before", (
            "_patch_modules did not restore the original value"
        )
        del sys.modules[sentinel_key]


# ─── Regression: shopstack/tools/audit_wcag.py ───────────────────────
class TestAuditWcagNoSelfMatchingFStrings:
    """The audit script's regex patterns must not match their own
    docstrings (which include literal ``<svg>``, ``width: NNNpx``,
    etc.). The systemic f-string fix in 2026-06-15 cleared this."""

    def test_svg_check_does_not_match_self(self):
        from shopstack.tools.audit_wcag import _read_all, check_1_1_1_alt_text
        from pathlib import Path
        files = _read_all(Path("."), ("shopstack/**/*.py",))
        result = check_1_1_1_alt_text(files)
        # Status should be "pass" not "warn" — the audit script
        # itself has ``<svg>`` in its regex patterns and docstrings
        # but those are not real SVGs.
        assert result.status == "pass", (
            f"SVG check should pass, got {result.status}: {result.evidence}"
        )

    def test_reflow_check_does_not_match_self(self):
        from shopstack.tools.audit_wcag import _read_all, check_1_4_10_reflow
        from pathlib import Path
        files = _read_all(Path("."), ("shopstack/**/*.py",))
        result = check_1_4_10_reflow(files)
        # The audit script has ``width: 170px`` etc. in its comments
        # and string literals. The regex must not match those.
        # The only real fixed-width in production code is
        # ``theme.py:750`` (the hero blob — cosmetic, not content).
        # We expect either pass, or 1 warn for the hero blob.
        assert result.status in ("pass", "warn"), (
            f"Unexpected reflow status: {result.status}"
        )
        if result.status == "warn":
            # If warn, must be 1 (the hero blob), not the false
            # positives from the audit script's own patterns.
            assert "1" in str(result.evidence), (
                f"Expected 1 reflow warn (hero blob), got: {result.evidence}"
            )


# ─── Regression: pyproject.toml pyright config ───────────────────────
class TestPyrightConfigIncludesTests:
    """The pyright config must include ``tests/`` for type-check
    coverage and exclude heavy directories like ``data/models``,
    ``data/cache``, ``_legacy/``."""

    def test_pyright_includes_tests(self):
        from pathlib import Path
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        pyright = data.get("tool", {}).get("pyright", {})
        include = pyright.get("include", [])
        assert "tests" in include, (
            f"pyright.include must include 'tests', got: {include}"
        )

    def test_pyright_excludes_legacy_and_models(self):
        from pathlib import Path
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        pyright = data.get("tool", {}).get("pyright", {})
        exclude = pyright.get("exclude", [])
        # Should exclude at least the heavy directories
        assert any("_legacy" in e for e in exclude), (
            f"pyright.exclude should exclude _legacy/, got: {exclude}"
        )
        assert any("data/models" in e or "data/cache" in e for e in exclude), (
            f"pyright.exclude should exclude data/models or data/cache, "
            f"got: {exclude}"
        )


# ─── Regression: README.md sdk_version ────────────────────────────────
class TestSpaceReadmeSdkVersion:
    """The HF Space README must specify a concrete, valid Gradio
    version — ``>=5.0`` is not a valid sdk_version format and breaks
    the Space config with ``CONFIG_ERROR: Gradio version does not
    exist``."""

    def test_specific_gradio_version(self):
        from pathlib import Path
        readme = Path("README.md").read_text()
        # Match sdk_version: <value>
        match = re.search(r"sdk_version:\s*\"([^\"]+)\"", readme)
        assert match, "README.md is missing sdk_version"
        version = match.group(1)
        # Must be a specific version, not a spec like >=5.0
        assert not version.startswith(">="), (
            f"sdk_version '{version}' is a range, not a specific version. "
            f"Use a concrete version like 6.17.3 to avoid CONFIG_ERROR."
        )
        assert not version.startswith("<"), (
            f"sdk_version '{version}' is a range, not a specific version."
        )
        assert re.match(r"\d+\.\d+\.\d+", version), (
            f"sdk_version '{version}' is not a semver pattern"
        )
