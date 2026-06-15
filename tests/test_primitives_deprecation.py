"""Tests verifying the Pass 10 deletion of the 4 deprecated primitives aliases.

These aliases were deleted in Pass 10 (supersession cleanup, per §7).
The 4 forbidden-path comments in ``test_no_drift.py`` document why the
symbols must not be re-added; this test file provides the runtime
verification that they're actually gone.

The aliases were moved to canonical modules:
    * ``primitives.busy_js`` → ``js_helpers.busy_js``
    * ``primitives.autocomplete_injector_js`` → ``js_helpers.autocomplete_injector_js``
    * ``primitives.url_state_sync_js`` → ``js_helpers.url_state_sync_js``
    * ``primitives.aria_live_screen`` → ``decorators.aria_live_screen``

If any of these re-appear in ``primitives.py`` (e.g., via drift
re-adding the deprecated re-exports), these tests will fail with
``AttributeError`` or ``ImportError``, surfacing the regression.
"""
from __future__ import annotations

import pytest


class TestPrimitivesDeprecatedAliases:
    """The 4 deprecated re-exports are GONE from primitives.py."""

    def test_busy_js_is_gone(self):
        """``primitives.busy_js`` must not be importable (superseded)."""
        with pytest.raises((ImportError, AttributeError)):
            from shopstack.ui.components.primitives import busy_js  # noqa: F401

    def test_autocomplete_injector_js_is_gone(self):
        """``primitives.autocomplete_injector_js`` must not be importable."""
        with pytest.raises((ImportError, AttributeError)):
            from shopstack.ui.components.primitives import autocomplete_injector_js  # noqa: F401

    def test_url_state_sync_js_is_gone(self):
        """``primitives.url_state_sync_js`` must not be importable."""
        with pytest.raises((ImportError, AttributeError)):
            from shopstack.ui.components.primitives import url_state_sync_js  # noqa: F401

    def test_aria_live_screen_is_gone(self):
        """``primitives.aria_live_screen`` must not be importable."""
        with pytest.raises((ImportError, AttributeError)):
            from shopstack.ui.components.primitives import aria_live_screen  # noqa: F401


class TestCanonicalPathsStillWork:
    """The canonical paths for the 4 symbols still work (regression guard)."""

    def test_canonical_busy_js(self):
        """``js_helpers.busy_js`` is the canonical path."""
        from shopstack.ui.components.js_helpers import busy_js
        assert callable(busy_js)

    def test_canonical_autocomplete_injector_js(self):
        """``js_helpers.autocomplete_injector_js`` is the canonical path."""
        from shopstack.ui.components.js_helpers import autocomplete_injector_js
        assert callable(autocomplete_injector_js)

    def test_canonical_url_state_sync_js(self):
        """``js_helpers.url_state_sync_js`` is the canonical path."""
        from shopstack.ui.components.js_helpers import url_state_sync_js
        assert callable(url_state_sync_js)

    def test_canonical_aria_live_screen(self):
        """``decorators.aria_live_screen`` is the canonical path."""
        from shopstack.ui.components.decorators import aria_live_screen
        assert callable(aria_live_screen)
