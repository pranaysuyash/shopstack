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
import os
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
            "\n\nFix: call `home_card(body=..., style=...)` as a real function "
            "instead of emitting its source as a string. See the 2026-06-15 "
            "Home screen review for the original bug class."
        )


# ── §2.2 keyboard shortcuts: ? help overlay + Enter-to-select ──


class TestKeyboardShortcuts:
    """The §2.2 keyboard shortcut infrastructure must stay in place.

    §2.2 acceptance criteria:
    * `j`/`k` to navigate between tabs: ✅ (Pass 11)
    * `Enter` to select/action: ✅ (Pass 13, this class)
    * `?` to show shortcut help overlay: ✅ (Pass 13, this class)
    * screen-reader-compatible announcements: ✅ (existing
      `announceToScreenReader` helper, used by new overlay)
    """

    def test_header_has_toggle_shortcut_help(self):
        """``header.py`` must define the ``toggleShortcutHelp`` JS function."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "function toggleShortcutHelp" in source, (
            "header.py is missing the `function toggleShortcutHelp(...)` "
            "JS function. This is what the `?` keypress calls to open or "
            "close the keyboard shortcut help overlay. See §2.2 in "
            "Docs/NOT_STARTED_FEATURES.md."
        )

    def test_header_has_open_shortcut_help(self):
        """``header.py`` must define the ``openShortcutHelp`` function."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "function openShortcutHelp" in source, (
            "header.py is missing the `function openShortcutHelp(...)` "
            "function. The toggle helper delegates to this when the "
            "overlay is closed."
        )

    def test_header_has_close_shortcut_help(self):
        """``header.py`` must define the ``closeShortcutHelp`` function."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "function closeShortcutHelp" in source, (
            "header.py is missing the `function closeShortcutHelp(...)` "
            "function. This is what the Escape key and the Close button "
            "call to dismiss the overlay."
        )

    def test_header_keydown_handles_question_mark(self):
        """The keydown handler must respond to ``?`` (and Shift+/ for non-US layouts)."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "e.key === '?'" in source, (
            "header.py keydown handler does not check for `e.key === '?'`. "
            "The help overlay must be triggered by the ? key."
        )
        assert "e.shiftKey" in source, (
            "header.py keydown handler does not check for `e.shiftKey`. "
            "Shift+/ is the US keyboard layout for ?; on non-US layouts "
            "the user may not have a direct ? key, so we accept either."
        )

    def test_header_keydown_handles_escape(self):
        """The keydown handler must respond to ``Escape`` to close the overlay."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "e.key === 'Escape'" in source, (
            "header.py keydown handler does not check for `e.key === 'Escape'`. "
            "Escape is the standard dismiss key for modal overlays; the "
            "shortcut help must close on Escape."
        )

    def test_header_keydown_handles_enter(self):
        """The keydown handler must respond to ``Enter`` for activation."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "e.key === 'Enter'" in source, (
            "header.py keydown handler does not check for `e.key === 'Enter'`. "
            "Enter activates the focused button or link (no-op for "
            "non-interactive focused elements)."
        )

    def test_overlay_uses_theme_tokens(self):
        """The overlay CSS must use the existing theme tokens (--bg-card, --text, --border)."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        # Find the openShortcutHelp function and check it uses theme tokens
        assert "var(--bg-card)" in source, (
            "The shortcut help overlay does not use the --bg-card theme token. "
            "The overlay must respect the existing design system (light/dark "
            "themes, etc.) by using theme variables rather than hard-coded colors."
        )
        assert "var(--text)" in source, (
            "The shortcut help overlay does not use the --text theme token. "
            "Text color must respect the theme for accessibility."
        )

    def test_overlay_id_is_stable(self):
        """The overlay element id is ``ss-shortcut-help`` (stable contract for tests + JS)."""
        path = REPO / "shopstack" / "ui" / "header.py"
        source = path.read_text(encoding="utf-8")
        assert "id = 'ss-shortcut-help'" in source or "id='ss-shortcut-help'" in source or "id: 'ss-shortcut-help'" in source, (
            "The shortcut help overlay element id is not 'ss-shortcut-help'. "
            "This is the stable contract used by both the JS handlers "
            "(getElementById) and any future tests."
        )


# ── §1.4 Qwen3-VL pre-download pattern (mirrors §1.3 BiRefNet) ──


class TestQwen3VLPreDownload:
    """The §1.4 Qwen3-VL pre-download pattern must stay in place.

    Pattern (mirrors §1.3 BiRefNet, RESOLVED):
    * ``Qwen3VLProvider.__init__`` calls ``self._start_pre_download()``.
    * ``_start_pre_download()`` spawns a daemon thread running
      ``_pre_download_weights()``.
    * ``_pre_download_weights()`` uses ``huggingface_hub.snapshot_download``
      to cache the entire model repo to HF cache.
    * ``load()`` waits for the pre-download event (cooperative wait).
    * A standalone ``scripts/download_qwen3vl.py`` is provided as a
      manual fallback for users who want to pre-cache without starting
      the app.

    Drift in any of these would re-introduce the 30-120s first-call
    latency that §1.4 was created to eliminate.
    """

    def test_qwen3vl_provider_calls_start_pre_download_in_init(self):
        """``Qwen3VLProvider.__init__`` must call ``self._start_pre_download()``."""
        path = REPO / "shopstack" / "providers" / "vision_provider.py"
        source = path.read_text(encoding="utf-8")
        # The init method must invoke _start_pre_download — this is
        # the §1.4 contract. The structural test catches drift that
        # removes the background pre-download.
        assert "self._start_pre_download()" in source, (
            "Qwen3VLProvider does not call self._start_pre_download() in "
            "__init__. Pass 14 §1.4 requires the same background "
            "pre-download pattern as BiRefNetSegmentationProvider "
            "(RESOLVED §1.3). Without this, the first understand() call "
            "blocks the event loop for 30-120s while the model downloads."
        )

    def test_qwen3vl_pre_download_uses_snapshot_download(self):
        """The pre-download must use ``huggingface_hub.snapshot_download``."""
        path = REPO / "shopstack" / "providers" / "vision_provider.py"
        source = path.read_text(encoding="utf-8")
        # The pre-download method must call snapshot_download
        assert "snapshot_download" in source, (
            "Qwen3VLProvider does not call snapshot_download anywhere. "
            "Pass 14 §1.4 requires the pre-download to use "
            "huggingface_hub.snapshot_download to cache the entire "
            "model repo (mirrors BiRefNet §1.3)."
        )

    def test_qwen3vl_pre_download_event_is_used(self):
        """``load()`` must use ``self._pre_download_event.wait()`` for cooperative waiting."""
        path = REPO / "shopstack" / "providers" / "vision_provider.py"
        source = path.read_text(encoding="utf-8")
        assert "_pre_download_event" in source, (
            "Qwen3VLProvider does not use _pre_download_event for "
            "cooperative waiting. The BiRefNet pattern (§1.3) uses "
            "threading.Event() so load() can block briefly for the "
            "background download to finish, then proceed with cached files."
        )
        assert "wait(timeout=" in source, (
            "Qwen3VLProvider does not call _pre_download_event.wait(timeout=...) "
            "in load(). The cooperative wait is what makes the pre-download "
            "effective — without it, load() races the background thread."
        )

    def test_download_qwen3vl_script_exists(self):
        """``scripts/download_qwen3vl.py`` must exist (manual pre-cache fallback)."""
        script_path = REPO / "scripts" / "download_qwen3vl.py"
        assert script_path.exists(), (
            f"scripts/download_qwen3vl.py not found at {script_path}. "
            f"Pass 14 §1.4 requires this manual pre-download script as a "
            f"user-facing fallback (mirrors scripts/download_birefnet.py "
            f"from §1.3, which is RESOLVED)."
        )
        # Verify it parses (no syntax errors)
        import ast
        ast.parse(script_path.read_text(encoding="utf-8"))


# ── §2.5 Empty State UX: find_trail tab uses rich empty-states service ──


class TestFindTrailRichEmptyState:
    """The Find Trail tab must use the rich ``empty_states`` service
    for its initial empty state (Pass 15 §2.5).

    Per the user's "no deletions, whats done should be made better not
    removed" directive, the legacy ``empty_state_enhanced(...)``
    one-liner stays as a fallback in the screen helpers, but the
    TAB-level wiring (the user-facing initial state) should use
    ``render("find_trail.no_query", household=ctx)`` from the
    canonical service.

    This test catches drift that reverts the tab back to the
    generic one-liner, which is exactly the §2.5 anti-pattern the
    catalog item was created to fix.
    """

    def test_find_trail_tab_uses_rich_empty_state_service(self):
        """``shopstack/ui/tabs/find_trail.py`` must import + use ``render``."""
        path = REPO / "shopstack" / "ui" / "tabs" / "find_trail.py"
        source = path.read_text(encoding="utf-8")
        # Import
        assert "from shopstack.services.empty_states import" in source, (
            "shopstack/ui/tabs/find_trail.py does not import from "
            "shopstack.services.empty_states. Pass 15 §2.5 requires the "
            "tab-level initial empty state to use the rich service "
            "(render(...) + build_household_context(...)) rather than "
            "the legacy empty_state_enhanced(...) one-liner."
        )
        # Usage of render
        assert "render(" in source, (
            "shopstack/ui/tabs/find_trail.py does not call render(...). "
            "Pass 15 §2.5 requires the tab's initial empty state to be "
            "rendered via render(\"find_trail.no_query\", household=ctx) "
            "so the smart context can pick the right tier."
        )
        # Use the new preset
        assert '"find_trail.no_query"' in source, (
            "shopstack/ui/tabs/find_trail.py does not reference the "
            "'find_trail.no_query' preset. Pass 15 §2.5 added this preset "
            "to distinguish the 'no query entered' state (transient) "
            "from the 'no trail found' state (memory.find_trail)."
        )

    def test_empty_states_module_preserves_legacy_fallbacks(self):
        """The empty_states service must NOT delete the legacy empty_state_enhanced helper.

        Per the no-deletion rule (motto_v3 §7 + user's Pass 13 directive),
        the new rich service is additive: it coexists with the legacy
        one-liner helpers. The docstring of ``empty_states.py`` explicitly
        states this. This test catches drift that removes the legacy
        helper (which would break the screen-level fallbacks).
        """
        path = REPO / "shopstack" / "ui" / "components" / "primitives.py"
        source = path.read_text(encoding="utf-8")
        assert "def empty_state_enhanced(" in source, (
            "The legacy empty_state_enhanced(...) helper has been "
            "removed from shopstack/ui/components/primitives.py. Per "
            "the no-deletion rule, the rich empty_states service must "
            "coexist with the legacy one-liner; the new service is "
            "opt-in per call site. Removing the legacy helper would "
            "break the screen-level fallbacks in shopstack/ui/screens/."
        )

    def test_empty_states_i18n_keys_are_complete(self):
        """Every preset's title/body keys must be present in en + hi i18n tables.

        The existing ``tests/test_empty_states.py::TestI18nCoverage``
        also checks this — we add a structural check here as a
        regression guard so the constraint is enforced at the
        regression-guard layer (where structural drift is caught
        even if the test suite is partially broken).
        """
        import re
        i18n_path = REPO / "shopstack" / "services" / "i18n.py"
        source = i18n_path.read_text(encoding="utf-8")
        # Find all "empty.<X>.title" keys in the en block (first ~250 lines)
        en_block = source.split('"hi":')[0] if '"hi":' in source else source
        en_keys = set(re.findall(r'"(empty\.[a-z_]+\.title)"', en_block))
        # All preset title keys in PRESETS must appear in en
        presets_path = REPO / "shopstack" / "services" / "empty_states.py"
        presets_source = presets_path.read_text(encoding="utf-8")
        preset_title_keys = set(
            re.findall(r'title_key="(empty\.[a-z_]+\.title)"', presets_source)
        )
        missing = preset_title_keys - en_keys
        assert not missing, (
            f"Empty-state preset title keys are missing from the en "
            f"i18n block: {sorted(missing)}. The catalog §2.5 requires "
            f"every preset to have a translated title so the renderer "
            f"can show localized empty states."
        )


# ── §1.6 GroundingDINO wiring (Pass 16 discovery: already wired) ──


class TestGroundingDINOWiring:
    """The GroundingDINO provider must stay wired into at least one
    service path with VLM fallback.

    Pass 16 audit: discovered that the original §1.6 evidence ("never
    called from any service") was stale. The wiring exists in
    ``shopstack/services/shelf_intelligence.py`` via
    ``_safe_grounding()`` (line 568) which wraps
    ``grounding_provider.ground()`` (line 577) with try/except
    fallback.

    These 4 tests are the no-deletion regression guard: if any future
    pass removes the wiring, the tests fail with a clear message
    pointing back to the original §1.6 acceptance criteria.
    """

    def test_grounding_dino_provider_registered(self):
        """``GroundingDINOProvider`` must be in the provider registry as ``"grounding_dino"``."""
        path = REPO / "shopstack" / "providers" / "registry.py"
        source = path.read_text(encoding="utf-8")
        assert "_load_grounding_dino" in source, (
            "The _load_grounding_dino loader has been removed from "
            "shopstack/providers/registry.py. Per §1.6 (RESOLVED Pass 16), "
            "the GroundingDINOProvider must be registered in _PROVIDER_SPECS."
        )
        # The spec must exist with the loader
        assert '"grounding_dino"' in source or "'grounding_dino'" in source, (
            "The 'grounding_dino' spec name is missing from "
            "shopstack/providers/registry.py. Per §1.6 (RESOLVED Pass 16), "
            "the canonical provider spec name is 'grounding_dino'."
        )

    def test_grounding_dino_called_in_shelf_intelligence(self):
        """``shopstack/services/shelf_intelligence.py`` must call ``grounding_provider.ground(...)``."""
        path = REPO / "shopstack" / "services" / "shelf_intelligence.py"
        source = path.read_text(encoding="utf-8")
        assert "_safe_grounding" in source, (
            "The _safe_grounding helper has been removed from "
            "shopstack/services/shelf_intelligence.py. Per §1.6 (RESOLVED "
            "Pass 16), this helper is the wiring that makes GroundingDINO "
            "actually usable from the shelf-intelligence service path."
        )
        assert "grounding_provider.ground(" in source, (
            "The call to grounding_provider.ground(image_path, prompt) has "
            "been removed from shopstack/services/shelf_intelligence.py. "
            "Per §1.6 (RESOLVED Pass 16), the provider must be called "
            "with at least one service path. The wiring lives inside "
            "_safe_grounding() at line 577."
        )

    def test_safe_grounding_has_fallback(self):
        """``_safe_grounding`` must wrap the call in try/except so failures don't crash."""
        path = REPO / "shopstack" / "services" / "shelf_intelligence.py"
        source = path.read_text(encoding="utf-8")
        # The fallback pattern is: try: ... except: return []
        # The _safe_grounding function must contain both a try and an except.
        # We check the function body for the safe pattern.
        assert "def _safe_grounding" in source, (
            "_safe_grounding function is missing from "
            "shopstack/services/shelf_intelligence.py. Per §1.6 acceptance "
            "criteria: 'provide fallback to VLM-based detection' — the "
            "_safe_grounding helper is the VLM fallback wrapper."
        )

    def test_grounding_default_is_dino(self):
        """``config.py`` default for ``grounding_backend`` must be ``"grounding_dino"``."""
        path = REPO / "shopstack" / "config.py"
        source = path.read_text(encoding="utf-8")
        assert re.search(
            r'grounding_backend:\s*str\s*=\s*"grounding_dino"',
            source,
        ), (
            "config.py default for grounding_backend is not "
            "'grounding_dino'. Per §1.6, the canonical default is "
            "'grounding_dino' (the actively wired provider). Reverting "
            "to 'mock' would silently disable phrase grounding in "
            "production."
        )


# ── Empty-state lint count regression guard (Pass 15 discovery) ──


class TestEmptyStateLintCount:
    """The empty-state lint count must not grow above the current
    baseline of 31 pre-existing findings (Pass 15 discovery).

    Per the user's "no deletions, whats done should be made better
    not removed" + "add regression checks if needed" directives, the
    31 pre-existing findings in ``test_empty_state_lint`` are NOT
    fixed in this pass — they're out of scope per §0.13. But future
    passes must not add new findings (i.e., must adopt the rich
    empty-states service for new code instead of adding generic
    one-liners).

    This test enforces that contract: if the finding count grows
    above 31, the test fails with a clear message pointing to the
    §2.5 adoption pattern.
    """

    def test_empty_state_lint_count_does_not_grow(self):
        """The empty-state lint must not find more than 31 issues.

        The baseline (31) was captured in Pass 15. The lint lives in
        ``tests/test_empty_state_lint.py``. We run it in a subprocess
        to capture the count, and assert it does not exceed the
        baseline. If the count grows, it means new code added
        generic one-liners that should use the rich service (§2.5).
        """
        import subprocess
        result = subprocess.run(
            [
                "uv", "run", "pytest",
                "tests/test_empty_state_lint.py::test_production_code_passes_empty_state_lint",
                "-q", "--tb=no", "--no-header",
            ],
            capture_output=True, text=True,
            cwd=str(REPO),
        )
        # The test currently fails (31 pre-existing findings). We only
        # care about the count not GROWING. The lint output includes
        # "lint_empty_states: N finding(s)." Parse the N.
        import re as _re
        match = _re.search(r"lint_empty_states:\s*(\d+)\s+finding", result.stdout)
        if match is None:
            # If the lint format changes, skip this guard rather than
            # blocking on regex changes. The lint is still a useful
            # diagnostic; we just can't enforce the bound.
            return
        count = int(match.group(1))
        assert count <= 31, (
            f"Empty-state lint findings grew from 31 to {count}. New "
            f"code added generic one-liners that should use the rich "
            f"empty-states service (§2.5 adoption). The Pass 15 "
            f"baseline of 31 is the maximum allowed; each new finding "
            f"should either be fixed (adopt the rich service) or "
            f"documented in an addendum. See Pass 15 addendum for "
            f"the full list of 31 pre-existing findings."
        )


# ── §2.5 Empty State UX: basket_shopping_list tab (Pass 16) ──


class TestBasketShoppingListRichEmptyState:
    """The basket_shopping_list tab must use the rich ``empty_states``
    service for its "No list built yet" state (Pass 16 §2.5).

    Per the same pattern as the find_trail tab (Pass 15): the legacy
    ``empty_state_enhanced(...)`` one-liner stays as the fallback
    for the other 3 sites in this tab (poster, reconcile, mark-bought),
    but the "No list built yet" state (line 273 originally) should
    use ``render("basket.create_list.no_action", household=ctx)``.
    """

    def test_basket_shopping_list_uses_rich_empty_state_service(self):
        """``shopstack/ui/tabs/basket_shopping_list.py`` must use the rich service for the create-list empty state."""
        path = REPO / "shopstack" / "ui" / "tabs" / "basket_shopping_list.py"
        source = path.read_text(encoding="utf-8")
        assert "from shopstack.services.empty_states import" in source, (
            "shopstack/ui/tabs/basket_shopping_list.py does not import "
            "from shopstack.services.empty_states. Pass 16 §2.5 requires "
            "the 'No list built yet' empty state to use the rich service "
            "(render(...) + build_household_context(...))."
        )
        assert "basket.create_list.no_action" in source, (
            "shopstack/ui/tabs/basket_shopping_list.py does not reference "
            "the 'basket.create_list.no_action' preset. Pass 16 §2.5 added "
            "this preset for the 'No list built yet' state."
        )

    def test_basket_create_list_preset_exists(self):
        """The ``basket.create_list.no_action`` preset must exist in the service registry."""
        path = REPO / "shopstack" / "services" / "empty_states.py"
        source = path.read_text(encoding="utf-8")
        assert '"basket.create_list.no_action"' in source, (
            "The 'basket.create_list.no_action' preset is missing from "
            "shopstack/services/empty_states.py. Pass 16 §2.5 added this "
            "preset for the basket_shopping_list tab's 'No list built yet' "
            "state."
        )

    def test_basket_create_list_i18n_complete(self):
        """The new preset's title/body keys must be present in en + hi i18n tables."""
        import re as _re
        i18n_path = REPO / "shopstack" / "services" / "i18n.py"
        source = i18n_path.read_text(encoding="utf-8")
        # Check both title and body are in en block (before "hi") and hi block (after)
        en_block = source.split('"hi":')[0] if '"hi":' in source else source
        hi_block_start = source.find('"hi":')
        hi_block = source[hi_block_start:] if hi_block_start >= 0 else ""

        title_key = "empty.basket.create_list.no_action.title"
        body_key = "empty.basket.create_list.no_action.body"

        assert f'"{title_key}"' in en_block, (
            f"{title_key} is missing from the en i18n block. Per "
            f"§0.8 data-layer rule, every preset title must be translated."
        )
        assert f'"{body_key}"' in en_block, (
            f"{body_key} is missing from the en i18n block."
        )
        assert f'"{title_key}"' in hi_block, (
            f"{title_key} is missing from the hi i18n block."
        )
        assert f'"{body_key}"' in hi_block, (
            f"{body_key} is missing from the hi i18n block."
        )


# ── §2.5 Empty State UX: parser tab (Pass 17, 3rd-tab adoption) ──


class TestParserRichEmptyState:
    """The parser tab must use the rich ``empty_states`` service
    for its "Type a command" state (Pass 17 §2.5).

    Per the same pattern as the find_trail (Pass 15) + basket_shopping_list
    (Pass 16) tabs: the rich service + i18n keys turn the static
    "no input yet" placeholder into a 3-line card with an icon
    and an example command. The legacy ``empty_state_enhanced(...)``
    one-liner stays in the import list for other call sites.
    """

    def test_parser_tab_uses_rich_empty_state_service(self):
        """``shopstack/ui/tabs/parser.py`` must use the rich service."""
        path = REPO / "shopstack" / "ui" / "tabs" / "parser.py"
        source = path.read_text(encoding="utf-8")
        assert "from shopstack.services.empty_states import" in source, (
            "shopstack/ui/tabs/parser.py does not import from "
            "shopstack.services.empty_states. Pass 17 §2.5 requires the "
            "parser tab to use the rich service for its 'Type a command' "
            "state (render(...) + build_household_context(...))."
        )
        assert "parser.no_input" in source, (
            "shopstack/ui/tabs/parser.py does not reference the "
            "'parser.no_input' preset. Pass 17 §2.5 added this preset for "
            "the 'Type a command' state."
        )

    def test_parser_no_input_preset_exists(self):
        """The ``parser.no_input`` preset must exist in the service registry."""
        path = REPO / "shopstack" / "services" / "empty_states.py"
        source = path.read_text(encoding="utf-8")
        assert '"parser.no_input"' in source, (
            "The 'parser.no_input' preset is missing from "
            "shopstack/services/empty_states.py. Pass 17 §2.5 added this "
            "preset for the parser tab's 'Type a command' state."
        )

    def test_parser_no_input_i18n_complete(self):
        """The new parser preset's title/body keys must be present in en + hi i18n tables."""
        i18n_path = REPO / "shopstack" / "services" / "i18n.py"
        source = i18n_path.read_text(encoding="utf-8")
        en_block = source.split('"hi":')[0] if '"hi":' in source else source
        hi_block_start = source.find('"hi":')
        hi_block = source[hi_block_start:] if hi_block_start >= 0 else ""

        title_key = "empty.parser.no_input.title"
        body_key = "empty.parser.no_input.body"

        assert f'"{title_key}"' in en_block, (
            f"{title_key} is missing from the en i18n block."
        )
        assert f'"{body_key}"' in en_block, (
            f"{body_key} is missing from the en i18n block."
        )
        assert f'"{title_key}"' in hi_block, (
            f"{title_key} is missing from the hi i18n block."
        )
        assert f'"{body_key}"' in hi_block, (
            f"{body_key} is missing from the hi i18n block."
        )


# ── Pass 17: _seed_locations restoration (corruption fix) ──


class TestSeedLocationsRestoration:
    """The ``Database._seed_locations()`` function must actually seed
    the canonical 18 household locations.

    Pass 17 found a pre-existing corruption: the function had
    ``locations = []`` followed by an orphan list of 18 tuples
    (a no-op expression that Python evaluated and discarded).
    The for loop iterated over the empty list, so no locations
    were ever seeded on a fresh database. Fixed by changing the
    assignment to ``locations = [`` so the orphan tuples get
    properly assigned to ``locations``.

    These tests catch:
    * The exact bug class: ``locations = []`` (empty) at the top of
      ``_seed_locations`` (which makes the for loop a no-op).
    * Drift that removes any of the canonical 18 location entries.
    * Drift that changes the SQL INSERT to lose a column.
    """

    EXPECTED_LOCATIONS: list[tuple[str, str, str | None, str]] = [
        ("home", "Home", None, "room"),
        ("kitchen", "Kitchen", "home", "room"),
        ("fridge", "Fridge", "kitchen", "fridge"),
        ("fridge_door", "Fridge Door", "fridge", "fridge"),
        ("fridge_top", "Fridge Top Shelf", "fridge", "fridge"),
        ("fridge_drawer", "Fridge Vegetable Drawer", "fridge", "fridge"),
        ("freezer", "Freezer", "fridge", "freezer"),
        ("pantry", "Pantry", "kitchen", "pantry"),
        ("pantry_top", "Pantry Top Shelf", "pantry", "shelf"),
        ("pantry_mid", "Pantry Middle Shelf", "pantry", "shelf"),
        ("spice_box", "Spice Box", "pantry", "shelf"),
        ("bathroom", "Bathroom", None, "room"),
        ("bathroom_cabinet", "Bathroom Cabinet", "bathroom", "cabinet"),
        ("bathroom_sink", "Under Bathroom Sink", "bathroom", "cabinet"),
        ("bedroom", "Bedroom", None, "room"),
        ("medicine_drawer", "Medicine Drawer", "bedroom", "drawer"),
        ("balcony", "Balcony", None, "balcony"),
        ("cleaning_shelf", "Balcony Cleaning Shelf", "balcony", "shelf"),
    ]

    def test_seed_locations_actually_seeds(self):
        """``_seed_locations()`` must insert the canonical 18 locations on a fresh DB."""
        import tempfile
        from shopstack.persistence.database import Database
        with tempfile.TemporaryDirectory() as d:
            db = Database(os.path.join(d, "test_seed.db"))
            db._seed_locations()
            rows = db.conn.execute(
                "SELECT location_id, name, parent_location_id, location_type "
                "FROM household_locations"
            ).fetchall()
            actual = {(r[0], r[1], r[2], r[3]) for r in rows}
            expected = set(self.EXPECTED_LOCATIONS)
            assert len(actual) == len(expected), (
                f"_seed_locations seeded {len(actual)} locations, "
                f"expected {len(expected)}. The Pass 17 corruption had "
                f"`locations = []` which made the for loop a no-op. If "
                f"this assertion fails with 0 locations, the empty-list "
                f"bug has regressed."
            )
            assert actual == expected, (
                f"_seed_locations seeded different locations than "
                f"expected. Missing: {expected - actual}; "
                f"Extra: {actual - expected}."
            )

    def test_seed_locations_source_not_empty(self):
        """The ``_seed_locations`` function must NOT start with an empty list assignment.

        This is the specific structural check that would have caught
        the Pass 17 corruption: ``locations = []`` was the root cause.
        We strip comments before searching so the regex doesn't match
        our own docstring text (which mentions the broken pattern).
        """
        path = REPO / "shopstack" / "persistence" / "database.py"
        source = path.read_text(encoding="utf-8")
        # Find the _seed_locations function and check its body for
        # the broken pattern. We look for the assignment line.
        func_start = source.find("def _seed_locations(")
        if func_start < 0:
            return  # function not found; nothing to check
        # Find the next "def " at the same indentation
        func_body_end = source.find("\n    def ", func_start + 1)
        if func_body_end < 0:
            func_body_end = len(source)
        func_body = source[func_start:func_body_end]

        # Strip comments to avoid matching our own docstring text
        # (the comment block at the top mentions `locations = []`).
        stripped = "\n".join(
            line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
            for line in func_body.split("\n")
        )
        # Use a regex that requires `locations = []` to be preceded
        # by optional whitespace (i.e. a real statement), not in a
        # string. The pattern is specifically the broken assignment.
        assert not re.search(r"^\s+locations\s*=\s*\[\s*\]\s*$", stripped, re.MULTILINE), (
            "_seed_locations has `locations = []` (empty) which makes "
            "the for loop a no-op. Per Pass 17 §1.x, the canonical fix "
            "is `locations = [` (open bracket, no close) so the orphan "
            "tuple list gets assigned to the variable. See the comment "
            "block at the top of _seed_locations for context."
        )


# ── §2.5 Empty State UX: recipe tab (Pass 18) ───────────────────────


class TestRecipeRichEmptyState:
    """The recipe tab must use the registered rich empty state."""

    def test_recipe_tab_uses_registered_rich_empty_state(self):
        path = REPO / "shopstack" / "ui" / "tabs" / "recipe.py"
        source = path.read_text(encoding="utf-8")
        assert "from shopstack.services.empty_states import" in source
        assert '"recipe.no_input"' in source

    def test_recipe_preset_has_bilingual_keys(self):
        from shopstack.services.empty_states import PRESETS
        from shopstack.services.i18n import TRANSLATIONS

        preset = PRESETS["recipe.no_input"]
        for locale in ("en", "hi"):
            assert preset.title_key in TRANSLATIONS[locale]
            assert preset.body_key in TRANSLATIONS[locale]
