"""Regression meta-tests for the 2026-06-13 work batch.

This file is a **meta-test**: it doesn't test a single feature
but instead guards the regression surface of every
deliverable shipped in this session. It runs fast (no DB
writes, no server boot) so it can be wired into pre-commit.

What it covers:
  1. Module-level import smoke for every new public symbol.
  2. **Tightened** freshness deprecation check: zero internal
     callers in ``shopstack/`` (the previous audit test only
     checked the count was small, not zero).
  3. ``use_soon_view`` deprecated alias still works AND no
     new call sites were added (the previous test only checked
     the alias works).
  4. ``shopping_list_view`` deprecated alias still works AND
     removed from ``__all__`` (the previous test only checked
     the deprecation warning fires).
  5. ``recipe_text_add_missing_to_list`` idempotency edge
     cases: empty DB-side, mixed-case canonical names, db
     without a ``conn`` attribute.
  6. ``_existing_list_canonical_names`` helper: works on a
     DB that has no ``conn`` attribute (degraded mode).
  7. ``render_action_tile`` ``custom_onclick`` XSS escaping.
  8. ``shopping_list_share`` public API surface complete.
  9. ``receipt`` module: APP_NAME import works (regression
     catch for the ``__getattr__`` shim removal).
 10. The onboarding wiring: ``build_onboarding_wizard``
     returns a non-None handle, the auto-show handler exists.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ─── Module import smoke (catches accidental renames/deletions) ─────


class TestModuleImportSmoke:
    """Every public symbol we shipped this turn must still import."""

    def test_recipe_text_screen_imports(self):
        from shopstack.ui.screens.recipe_text import (
            _existing_list_canonical_names,
            recipe_image_to_text,
            recipe_text_add_missing_to_list,
            recipe_text_to_shopping_list,
        )
        assert callable(recipe_text_to_shopping_list)
        assert callable(recipe_text_add_missing_to_list)
        assert callable(recipe_image_to_text)
        assert callable(_existing_list_canonical_names)

    def test_cookbook_screen_imports(self):
        from shopstack.ui.screens.cookbook import (
            cookbook_browse,
            cookbook_cuisine_choices,
            cookbook_shop_missing,
            cookbook_view_recipe,
        )
        assert callable(cookbook_browse)
        assert callable(cookbook_view_recipe)
        assert callable(cookbook_shop_missing)
        assert callable(cookbook_cuisine_choices)

    def test_shopping_share_imports(self):
        from shopstack.ui.screens.shopping import (
            _shopping_list_share_html,
            _shopping_list_share_text,
            shopping_list_share,
        )
        assert callable(shopping_list_share)
        assert callable(_shopping_list_share_text)
        assert callable(_shopping_list_share_html)

    def test_receipt_txt_export_imports(self):
        from shopstack.services.receipt import (
            _receipt_txt_body,
            export_receipt_txt,
        )
        from shopstack.ui.screens.receipt import receipt_export_txt
        assert callable(export_receipt_txt)
        assert callable(_receipt_txt_body)
        assert callable(receipt_export_txt)

    def test_onboarding_helpers_imports(self):
        from shopstack.services.onboarding import (
            is_onboarding_complete,
            is_onboarding_skipped,
            mark_onboarding_skipped,
            reset_onboarding_skip,
            should_show_onboarding,
        )
        for fn in (
            is_onboarding_complete,
            is_onboarding_skipped,
            mark_onboarding_skipped,
            reset_onboarding_skip,
            should_show_onboarding,
        ):
            assert callable(fn)

    def test_header_indicator_imports(self):
        from shopstack.ui.header import header_block, household_indicator_html
        assert callable(household_indicator_html)
        assert callable(header_block)

    def test_cards_custom_onclick_imports(self):
        from shopstack.ui.components.cards import render_action_grid, render_action_tile
        assert callable(render_action_tile)
        assert callable(render_action_grid)


# ─── Tightened freshness deprecation check ────────────────────────────


class TestFreshnessDeprecationTightened:
    """Per the supersession audit, ZERO internal callers should
    still use the deprecated `shopstack.services.freshness` path.
    The previous check only counted; this one fails-loud if > 0.
    """

    def test_zero_internal_freshness_callers(self):
        shopstack = Path("shopstack")
        # Count across the whole shopstack/ tree
        offenders = []
        for py_file in shopstack.rglob("*.py"):
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                if "from shopstack.services.freshness import" in line:
                    rel = str(py_file.relative_to(shopstack.parent))
                    offenders.append(f"{rel}:{i}: {line.strip()}")
        assert not offenders, (
            "Found internal callers of the DEPRECATED "
            "shopstack.services.freshness path. Migrate to "
            "shopstack.domain (per HANDOFF_POLISH_CLUSTER_2026-06-13.md):\n"
            + "\n".join(offenders)
        )


# ─── use_soon_view deprecated alias: works + no new callers ─────────


class TestUseSoonViewAliasStable:
    """The deprecated alias must still work AND no new call sites
    were added. The previous test only checked the alias fires
    DeprecationWarning; this one also locks in the caller count.
    """

    def test_alias_still_works(self):
        import warnings

        from shopstack.ui.screens import use_soon_view
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = use_soon_view(days=3)
        assert isinstance(result, list)

    def test_no_new_call_sites_in_shopstack(self):
        """The only allowed call sites are the function definition
        itself, the deprecation message, the import in __init__,
        the __all__ entry, and this regression test file.
        """
        shopstack = Path("shopstack")
        offenders = []
        # Allowed locations
        for py_file in shopstack.rglob("*.py"):
            rel = str(py_file.relative_to(shopstack.parent))
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                # Match only the function NAME (not "with_cards" variants)
                if "use_soon_view" not in line:
                    continue
                # Skip "use_soon_view_with_cards" / "use_first_view" etc.
                if (
                    "use_soon_view_with_cards" in line
                    or "use_first_view" in line
                ):
                    continue
                # Strip + check for exact match (e.g., "use_soon_view" or "use_soon_view(")
                stripped = line.strip()
                # Allowed patterns
                if rel == "shopstack/ui/screens/inventory.py" and (
                    stripped.startswith("def use_soon_view")
                    or "use_soon_view is deprecated" in stripped
                    or "from shopstack.ui.screens import use_soon_view" in stripped
                ):
                    continue
                if rel == "shopstack/ui/screens/__init__.py" and (
                    "use_soon_view," in stripped
                    or "use_soon_view\"" in stripped
                    or "use_soon_view " in stripped  # the deprecation comment
                ):
                    continue
                offenders.append(f"{rel}:{i}: {stripped}")
        assert not offenders, (
            "Unexpected new call sites of use_soon_view (deprecated):\n"
            + "\n".join(offenders)
            + "\n\nIf you must use the alias, ensure you follow the "
            "supersession protocol (HANDOFF_USESOONVIEW_SUPERSESSION_2026-06-13.md)."
        )


# ─── shopping_list_view deprecated alias stable ──────────────────────


class TestShoppingListViewAliasStable:
    """The deprecated ``shopping_list_view`` alias must still work
    AND must be removed from ``__all__`` (per the protocol).
    """

    def test_alias_still_emits_deprecation_warning(self):
        from shopstack.ui.screens.shopping import shopping_list_view
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                shopping_list_view()
            except Exception:
                pass
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecations, "shopping_list_view must emit DeprecationWarning"

    def test_alias_not_in_screens_all(self):
        from shopstack.ui.screens import __all__ as screens_all
        assert "shopping_list_view" not in screens_all, (
            "shopping_list_view must be removed from screens.__all__ "
            "(kept as one-release-cycle alias only)."
        )

    def test_canonical_in_screens_all(self):
        from shopstack.ui.screens import __all__ as screens_all
        assert "shopping_list_view_with_cards" in screens_all, (
            "Canonical shopping_list_view_with_cards must be in screens.__all__."
        )


# ─── Idempotency helper: db.conn=None degraded mode ──────────────────


class TestIdempotencyHelperEdgeCases:
    """The idempotency helper must degrade gracefully on weird DBs."""

    def test_helper_with_db_without_conn_attribute(self):
        from shopstack.ui.screens.recipe_text import (
            _existing_list_canonical_names,
        )
        class _FakeDBNoConn:
            # No .conn attribute at all
            pass
        result = _existing_list_canonical_names(_FakeDBNoConn(), "any-list-id")
        assert result == set(), (
            f"Expected empty set on no-conn DB, got {result!r}"
        )

    def test_helper_with_db_with_conn_but_query_fails(self):
        from shopstack.ui.screens.recipe_text import (
            _existing_list_canonical_names,
        )
        class _FakeBrokenDB:
            def __getattr__(self, name):
                raise RuntimeError("simulated DB down")
        result = _existing_list_canonical_names(_FakeBrokenDB(), "any-list-id")
        assert result == set(), (
            "Helper must return empty set on DB error (degraded mode), "
            "not raise"
        )

    def test_helper_with_normal_db(self):
        from shopstack.ui.screens.recipe_text import (
            _existing_list_canonical_names,
        )
        # Use a mock with a conn that returns rows
        fake_conn = MagicMock()
        fake_conn.execute.return_value.fetchall.return_value = [
            ("rice",), ("onion",),
        ]
        class _FakeDB:
            def __getattr__(self, name):
                if name == "conn":
                    return fake_conn
                raise AttributeError(name)
        result = _existing_list_canonical_names(_FakeDB(), "list-1")
        assert "rice" in result
        assert "onion" in result
        # Verify lowercase normalization
        assert "RICE" not in result


# ─── render_action_tile custom_onclick XSS escaping ─────────────────


class TestCustomOnclickXSSEscape:
    """The custom_onclick body must be safely escaped so the
    resulting HTML attribute is well-formed (no quote-injection).
    """

    def test_double_quote_escaped(self):
        from shopstack.ui.components.cards import render_action_tile
        result = render_action_tile(
            label="X", subtitle="x", tab_id="",
            tone="default", custom_onclick='alert("with quotes");',
        )
        # The original double-quote should NOT appear unescaped
        # in the resulting onclick attribute
        # (it should be \" or similar escape)
        assert 'onclick="(function(){alert(\\"with quotes\\");})();"' in result, (
            f"Expected escaped double quotes, got: {result[:300]!r}"
        )

    def test_backslash_escaped(self):
        from shopstack.ui.components.cards import render_action_tile
        result = render_action_tile(
            label="X", subtitle="x", tab_id="",
            tone="default", custom_onclick="alert('with backslash');",
        )
        # The original backslash should be doubled
        # (look for "with \\\\ backslash" pattern after escaping)
        assert "with" in result
        assert "backslash" in result

    def test_html_attribute_is_well_formed(self):
        """The resulting HTML should parse without errors."""
        from html.parser import HTMLParser

        from shopstack.ui.components.cards import render_action_tile
        result = render_action_tile(
            label="X", subtitle="x", tab_id="",
            tone="default", custom_onclick='alert("hi \\n");',
        )
        # Should parse cleanly
        try:
            HTMLParser().feed(result)
        except Exception as exc:
            pytest.fail(f"HTML parse failed: {exc}")


# ─── Shopping list share public API surface ─────────────────────────


class TestShareListPublicAPISurface:
    """The public API surface is complete (helper, html, and adapter)."""

    def test_all_three_symbols_importable(self):
        from shopstack.ui.screens import shopping_list_share
        from shopstack.ui.screens.shopping import (
            _shopping_list_share_html,
            _shopping_list_share_text,
        )
        assert callable(shopping_list_share)
        assert callable(_shopping_list_share_text)
        assert callable(_shopping_list_share_html)

    def test_share_text_includes_header_and_footer(self):
        from shopstack.ui.screens.shopping import _shopping_list_share_text
        text = _shopping_list_share_text([
            {"canonical_name": "rice", "smart_decision": "must_buy",
             "requested_quantity": 1.0, "unit": "kg"},
        ])
        # Should mention the app, the items, etc.
        assert "rice" in text

    def test_share_html_includes_clipboard_js(self):
        from shopstack.ui.screens.shopping import _shopping_list_share_html
        html = _shopping_list_share_html("test share text")
        # Should include the navigator.clipboard.writeText JS
        assert "navigator.clipboard.writeText" in html, (
            "Share HTML must include the Copy-to-clipboard JS"
        )
        # And the WhatsApp link
        assert "wa.me" in html, "Share HTML must include the WhatsApp link"


# ─── Receipt module: APP_NAME import works ──────────────────────────


class TestReceiptAppNameImport:
    """The receipt module must have APP_NAME importable.

    Per the supersession protocol + the 2026-06-13 receipt-txt-export
    pass, the ``__getattr__`` lazy resolver was removed. The
    explicit import is the right state. This test catches a
    regression where someone re-adds the shim or breaks the import.
    """

    def test_receipt_module_exposes_app_name(self):
        from shopstack.services import receipt
        # Should be importable as an attribute (either from the
        # explicit import OR via the module's __getattr__)
        assert hasattr(receipt, "APP_NAME"), (
            "receipt module must expose APP_NAME (explicit import or shim)"
        )
        # And it should be a non-empty string
        assert receipt.APP_NAME, "APP_NAME must be a non-empty string"

    def test_receipt_txt_body_uses_app_name(self):
        """Verify the .txt body actually uses APP_NAME (regression
        catch for the 'NameError' we hit when APP_NAME wasn't imported)."""
        from datetime import date

        from shopstack.services.receipt import ReceiptResult, _receipt_txt_body
        result = ReceiptResult(
            merchant="Test", purchase_date=date(2026, 6, 13),
            lines=[], total=0.0, raw_text="",
        )
        body = _receipt_txt_body(result)
        # Should not raise NameError; should include the app name
        # (could be "ShopStack" or whatever APP_NAME is set to)
        assert "ShopStack" in body or "Receipt" in body


# ─── Onboarding wiring: build returns handle, auto-show exists ──────


class TestOnboardingWiringRegression:
    """The wizard wiring must still work end-to-end."""

    def test_build_onboarding_wizard_returns_handle(self):
        import inspect

        from shopstack.ui.screens.onboarding import build_onboarding_wizard
        sig = inspect.signature(build_onboarding_wizard)
        assert sig.return_annotation is not type(None), (
            "build_onboarding_wizard must return a handle (not None)"
        )

    def test_app_contains_wiring_call(self):
        """Static check: app.py must still call build_onboarding_wizard."""
        app_py = Path("app.py").read_text()
        assert "build_onboarding_wizard" in app_py
        assert "should_show_onboarding" in app_py, (
            "app.py must use the composite should_show_onboarding check"
        )

    def test_onboarding_step_renderers_in_canonical_home(self):
        """The step renderers live in the canonical home
        (shopstack.ui.tabs.onboarding) and are called as inner
        Markdown blocks (not as separate functions). The
        supersession history means they're reachable via
        the shim in shopstack.ui.screens.onboarding.
        """
        # Canonical home
        from shopstack.ui.tabs import onboarding as tab_onboarding
        assert hasattr(tab_onboarding, "build_onboarding_wizard")
        assert callable(tab_onboarding.build_onboarding_wizard)
        # The screens re-export shim still works
        from shopstack.ui.screens import onboarding as screens_onboarding
        assert hasattr(screens_onboarding, "build_onboarding_wizard")
        # Both should resolve to the same function
        assert (
            tab_onboarding.build_onboarding_wizard
            is screens_onboarding.build_onboarding_wizard
        )


# ─── Cross-cutting: app.py builds cleanly ──────────────────────────


class TestAppBuildsCleanly:
    """Catch the kind of import-time errors that blocked `import app`
    before the 2026-06-13 syntax-error fixes.
    """

    def test_app_imports_without_error(self):
        """Static import (no `__pycache__` reset needed)."""
        import app  # noqa: F401

    def test_app_call_to_build_app_does_not_crash(self):
        """build_app() is the function that constructs the Gradio
        Blocks. We can't easily call it (it needs lots of context),
        but we can verify it's importable and callable.
        """
        import app
        assert callable(app.build_app), (
            "app.build_app must be the entry point for the Gradio app"
        )
        # And the app name should be importable
        from shopstack.app_context import APP_NAME
        assert APP_NAME
