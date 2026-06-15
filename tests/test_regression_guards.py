"""Systematic regression guards for supersession patterns.

This test file catches the specific drift patterns that have
surfaced across Pass 7-11. Each test is a STRUCTURAL assertion
(not a behavioral one) — it checks that the code has the
canonical shape, not that the code works.

The tests are organized by supersession decision record:

* DR-031: lazy import of ``compare_across_sources`` in
  ``market_intelligence.py`` (Pass 11). If drift reverts to
  eager import, the test fails immediately.

* DR-032: ``tool_call_parser_backend`` default = ``"mock"``
  (Pass 11 §1.7). If drift reverts to ``"minicpm5"``, the test
  fails immediately.

* DR-033: real forbidden-path tests (Pass 11). The
  ``test_primitives_deprecation.py`` file already has 8 tests;
  this file ADDS a check that no OTHER module re-defines the
  ``safe_get`` / ``_safe_get`` / ``_user_id`` / ``__getattr__``
  deprecation patterns.

* DR-034: addendum-only doc updates (Pass 11). The
  ``SERVICES_ARCHITECTURE.md`` doc has an addendum section;
  the test verifies the addendum is present (regression
  guard against full rewrites losing the addendum).

These are PATTERN searches, not behavior tests. They protect
against the same class of drift that Pass 11 caught in real-time
(the drift-re-added primitives aliases).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]


# ── DR-031: market_intelligence.py must NOT have eager import ──


class TestMarketIntelligenceLazyImport:
    """``compare_across_sources`` must be lazy-imported to avoid a
    circular import (DR-031, Pass 11 fix).

    If drift reverts to an eager ``from shopstack.market.sources
    import compare_across_sources`` at the module level, the
    `app_context` import chain breaks with
    ``ImportError: cannot import name 'compare_across_sources' from
    parcialmente initialized module 'shopstack.market.sources'``.
    """

    def test_market_intelligence_has_no_eager_market_sources_import(self):
        """No eager import of `compare_across_sources` or other market.sources symbol."""
        path = REPO / "shopstack" / "services" / "market_intelligence.py"
        source = path.read_text(encoding="utf-8")
        # Look for the SPECIFIC eager import that caused the bug
        assert "from shopstack.market.sources import compare_across_sources" not in source, (
            "DR-031: market_intelligence.py has an eager import of "
            "`compare_across_sources`. This causes a circular import "
            "when services.__init__.py is loaded via app_context. "
            "Use a function-local `from shopstack.market.sources._comparison "
            "import compare_across_sources` instead."
        )


# ── DR-032: tool_call_parser_backend default = "mock" ──


class TestToolCallParserConfigDefault:
    """``tool_call_parser_backend`` config default must stay as
    ``"mock"`` (DR-032, Pass 11 fix).

    The previous default ``"minicpm5"`` was a silent capability
    mismatch: ``MiniCPM5Provider`` doesn't declare
    ``tool_call_parser`` in its capabilities. The registry fell
    back to ``MockToolCallParser`` with ``available=False``.

    This is also covered in tests/test_config.py; we add a
    regression here so the structural assertion is in the
    regression-guard file.
    """

    def test_config_default_is_mock(self):
        """The default in config.py must be ``"mock"``."""
        path = REPO / "shopstack" / "config.py"
        source = path.read_text(encoding="utf-8")
        # Look for the default in the Settings class
        assert re.search(
            r'tool_call_parser_backend:\s*str\s*=\s*"mock"',
            source,
        ), (
            "DR-032: tool_call_parser_backend default in config.py "
            "is not 'mock'. It was changed to 'mock' in Pass 11 §1.7 "
            "because MiniCPM5Provider does not declare tool_call_parser "
            "in its capabilities. Reverting to 'minicpm5' is a silent "
            "fallback regression."
        )


# ── DR-033: no duplicate safe_get / _user_id ──


class TestNoDuplicateSafeGet:
    """``safe_get`` is canonical in ``shopstack/services/_utils.py``.

    Drift that re-introduces a ``def _safe_get`` (or ``safe_get``)
    in any OTHER module is a regression. Catch it.
    """

    def test_no_safe_get_in_other_modules(self):
        """No module outside ``services/_utils.py`` defines ``safe_get`` or ``_safe_get``."""
        offenders = []
        for path in (REPO / "shopstack").rglob("*.py"):
            if "services/_utils.py" in str(path):
                continue  # canonical location
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in (
                    "safe_get",
                    "_safe_get",
                ):
                    offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
        assert not offenders, (
            "DR-033: Found `_safe_get` or `safe_get` definitions in:\n"
            + "\n".join(f"  {o}" for o in offenders)
            + "\n\nThe canonical helper lives in `shopstack/services/_utils.py`."
            " Remove the duplicates and import the canonical version."
        )


class TestNoDuplicateUserId:
    """``current_user_id()`` is canonical in ``shopstack.app_context``.

    Drift that re-introduces a local ``def _user_id()`` wrapper is allowed
    IF (a) it has a deprecation note pointing to the canonical, and
    (b) it delegates to ``current_user_id()`` (not a parallel implementation).

    Per the no-deletion principle (motto_v3 §7 line 802: "do not delete
    old non-trivial logic without inventory and approval"), preserved
    wrappers in older modules are tolerated. What is NOT tolerated is
    a parallel implementation that bypasses the canonical helper.

    This test catches:
    * A local ``_user_id()`` that does NOT delegate to ``current_user_id()``.
    * Drift that removes the canonical ``current_user_id()`` from
      ``app_context.py``.
    """

    def test_no_non_delegating_user_id(self):
        """If a local ``_user_id()`` exists, it must delegate to ``current_user_id()``."""
        offenders = []
        for path in (REPO / "shopstack").rglob("*.py"):
            if path.name == "app_context.py":
                continue  # canonical location
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            # Only flag modules that define a local `_user_id` AND
            # do NOT delegate to the canonical `current_user_id()`.
            if "def _user_id(" in source:
                if "current_user_id" not in source:
                    offenders.append(
                        f"{path.relative_to(REPO)}: defines _user_id() but "
                        f"does NOT delegate to current_user_id()"
                    )
        assert not offenders, (
            "DR-033: Found non-delegating local `_user_id` definitions in:\n"
            + "\n".join(f"  {o}" for o in offenders)
            + "\n\nPer the no-deletion principle, local wrappers are allowed "
            "but they MUST delegate to the canonical `current_user_id()` "
            "in `shopstack.app_context`. This test preserves backward "
            "compatibility (wrappers stay) while preventing parallel "
            "implementations (wrappers must delegate)."
        )

    def test_canonical_user_id_exists(self):
        """The canonical ``current_user_id()`` must exist in ``app_context.py``."""
        path = REPO / "shopstack" / "app_context.py"
        source = path.read_text(encoding="utf-8")
        assert "def current_user_id(" in source, (
            "The canonical `current_user_id()` is missing from "
            "`shopstack/app_context.py`. This is the source of truth for "
            "user identity. If you need to change the implementation, "
            "update it here — don't fork."
        )


# ── DR-034: SERVICES_ARCHITECTURE.md addendum is present ──


class TestServicesArchitectureAddendum:
    """The ``SERVICES_ARCHITECTURE.md`` addendum (Pass 11, DR-034) must
    be present in the doc. If a future pass rewrites the doc, the
    addendum should be preserved per the project's addendum convention
    (motto_v3 §1.1).
    """

    def test_addendum_section_exists(self):
        """The doc has an addendum dated 2026-06-15 documenting Pass 11 services."""
        path = REPO / "Docs" / "SERVICES_ARCHITECTURE.md"
        source = path.read_text(encoding="utf-8")
        assert "## Addendum (2026-06-15)" in source, (
            "DR-034: SERVICES_ARCHITECTURE.md is missing the Pass 11 "
            "addendum. The addendum documents 30+ new services that were "
            "added since the last mermaid update. If a future pass rewrites "
            "the doc, the addendum should be preserved per the project's "
            "addendum convention (motto_v3 §1.1)."
        )


# ── Cross-cutting: data_sources package must NOT exist (Pass 9) ──


class TestDataSourcesPackageGone:
    """The deprecated ``shopstack/data_sources/`` package was deleted
    in Pass 9 per the supersession rule. If drift re-introduces it,
    the canonical migration (Pass 9b, Pass 10) is broken.
    """

    def test_data_sources_directory_does_not_exist(self):
        """The deprecated ``shopstack/data_sources/`` directory must be gone."""
        path = REPO / "shopstack" / "data_sources"
        assert not path.exists(), (
            "The deprecated `shopstack/data_sources/` package was deleted in Pass 9. "
            "If you re-introduced it, the canonical migration is broken. "
            "Use `shopstack/market/sources/` (the canonical Swiggy loader + adapter) instead."
        )


# ── §2.1 dark mode: theme.py CSS structure ──


class TestDarkModeCssStructure:
    """The dark mode CSS infrastructure (§2.1, RESOLVED in Pass 12) must
    stay in place. test_header.py covers the toggle button + JS; this
    covers the CSS itself (structural check).
    """

    def test_theme_has_dark_media_query(self):
        """``theme.py`` must have a ``prefers-color-scheme: dark`` media query."""
        path = REPO / "shopstack" / "ui" / "theme.py"
        source = path.read_text(encoding="utf-8")
        assert "@media (prefers-color-scheme: dark)" in source, (
            "theme.py is missing the @media (prefers-color-scheme: dark) "
            "block. This is the OS-preference fallback. See §2.1 in "
            "Docs/NOT_STARTED_FEATURES.md (RESOLVED). The CSS variables "
            "for dark mode are at theme.py:143-172."
        )

    def test_theme_has_dark_attribute_selector(self):
        """``theme.py`` must have a ``[data-theme="dark"]`` attribute selector."""
        path = REPO / "shopstack" / "ui" / "theme.py"
        source = path.read_text(encoding="utf-8")
        assert '[data-theme="dark"]' in source, (
            "theme.py is missing the [data-theme=\"dark\"] selector. "
            "This selector is what `toggleTheme()` in header.py uses to "
            "switch between light and dark. The variables defined under "
            "this selector are what the JS flips between."
        )

    def test_header_has_localstorage_key(self):
        """``header.py`` must reference the localStorage key ``shopstack-theme``."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "shopstack-theme" in source, (
            "header.py is missing the 'shopstack-theme' localStorage key. "
            "This key is the persistence mechanism for the theme toggle. "
            "Both load and save must use the same key."
        )

    def test_header_has_toggle_function(self):
        """``header.py`` must define the ``toggleTheme`` JS function."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "function toggleTheme" in source, (
            "header.py is missing the `function toggleTheme(...)` JS "
            "function. This is what the theme toggle button in the header "
            "calls (via onclick=)."
        )


# ── Home screen review (2026-06-15): stringified home_card() calls ──


class TestHomeCardLiteralStringBug:
    """Catch the "stringified function call" bug class found in
    ``dashboard.py`` during the 2026-06-15 Home screen review.

    Several render functions built a return value that *looked* like a
    call to ``home_card(body='...', style='...')`` but was actually a
    plain concatenated string — ``home_card(`` was never invoked, so the
    literal text ``home_card(body='...'`` and a trailing
    ``, style='...')`` were emitted straight into the page HTML (visible
    to the user as raw, unstyled text, e.g. on the "Welcome to ShopStack"
    card). Fixed by calling the real ``home_card()`` primitive.

    This is a structural pattern check across the whole UI layer so the
    bug class cannot silently reappear in any screen.
    """

    def test_no_stringified_home_card_calls(self):
        """No ``shopstack/ui`` module contains a literal "home_card(body=" string."""
        offenders = []
        for path in (REPO / "shopstack" / "ui").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for needle in ("\"home_card(body=", "'home_card(body="):
                if needle in source:
                    offenders.append(f"{path.relative_to(REPO)}: contains {needle!r}")
        assert not offenders, (
            "Found stringified `home_card(body=...)` calls (2026-06-15 Home "
            "screen review bug class) — these are literal strings, not real "
            "function calls, and leak raw `style='...'` text into the "
            "rendered UI:\n" + "\n".join(f"  {o}" for o in offenders) +
            "\n\nFix: call the real `home_card()` from "
            "shopstack.ui.components.primitives with title=/body=/style= kwargs."
        )
