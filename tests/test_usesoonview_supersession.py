"""Tests for the use_soon_view / use_first_view supersession.

Added 2026-06-13 as part of the broader supersession audit
(``Docs/HANDOFF_SUPERSESSION_AUDIT_2026-06-13.md``).

Background:
  The function was renamed from ``use_soon_view`` to ``use_first_view``
  (clearer name: it shows items to *use first*, not items that
  are *soon* to expire). The old name was kept in
  ``shopstack/ui/screens/__init__.py:__all__`` but the function
  itself was missing — causing ``from shopstack.ui.screens import *``
  to fail with ``AttributeError: module 'shopstack.ui.screens' has
  no attribute 'use_soon_view'``.

Fix:
  1. Added a ``use_soon_view`` deprecated alias in
     ``shopstack/ui/screens/inventory.py`` that delegates to
     ``use_first_view`` and emits a ``DeprecationWarning`` on call.
  2. Kept the import in ``__init__.py`` (for one release cycle per
     the supersession protocol).
  3. Added this test file to lock in the supersession state.

Future work:
  After the next minor release, remove the alias. The audit test
  will then start failing, which is the signal that it's safe to
  delete.
"""

from __future__ import annotations

import warnings

import pytest


class TestUseSoonViewCanonical:
    """The canonical name (``use_first_view``) is the primary API."""

    def test_canonical_in_screens_all(self):
        from shopstack.ui.screens import __all__ as screens_all
        assert "use_first_view" in screens_all, (
            "Canonical use_first_view must be in screens.__all__."
        )

    def test_canonical_is_callable(self):
        from shopstack.ui.screens import use_first_view
        assert callable(use_first_view)

    def test_canonical_returns_table(self):
        """The canonical function returns a list-of-lists table."""
        from shopstack.ui.screens import use_first_view
        result = use_first_view(days=3)
        # Empty inventory returns an empty list, not an error
        assert isinstance(result, list)


class TestUseSoonViewDeprecatedAlias:
    """The legacy ``use_soon_view`` is a deprecated alias that
    delegates to the canonical ``use_first_view``."""

    def test_legacy_is_in_screens_all(self):
        """Kept for one release cycle per the supersession protocol."""
        from shopstack.ui.screens import __all__ as screens_all
        assert "use_soon_view" in screens_all, (
            "Legacy use_soon_view must remain in screens.__all__ for "
            "one release cycle. Per the supersession protocol, it is "
            "deleted AFTER the next minor release, not now."
        )

    def test_legacy_is_importable_via_screens(self):
        from shopstack.ui.screens import use_soon_view
        assert callable(use_soon_view)

    def test_legacy_emits_deprecation_warning(self):
        from shopstack.ui.screens import use_soon_view
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            use_soon_view()
        deprecations = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert deprecations, (
            "use_soon_view() did not emit a DeprecationWarning. "
            "Per the supersession protocol, the alias must warn so "
            "callers migrate to use_first_view."
        )
        msg = str(deprecations[0].message)
        assert "use_first_view" in msg, (
            f"DeprecationWarning should mention the canonical name "
            f"'use_first_view'. Got: {msg!r}"
        )

    def test_legacy_delegates_to_canonical(self):
        """The legacy returns the same shape as the canonical."""
        from shopstack.ui.screens import use_first_view, use_soon_view
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            legacy = use_soon_view(days=3)
            canonical = use_first_view(days=3)
        assert legacy == canonical, (
            "use_soon_view (legacy) must return the same value as "
            "use_first_view (canonical). They are the same function."
        )


class TestUseSoonViewNoCallSitesInShopstack:
    """The legacy should have zero internal call sites in shopstack/.

    Allowed matches:
      * The alias definition itself (``def use_soon_view``)
      * The deprecation message inside the alias
      * The export in __init__.py (kept for one release cycle)
      * This test file (the audit file)

    The 2 test_views.py call sites were migrated to use_first_view
    in the same PR (see tests/test_views.py after this audit).
    After migration, no internal shopstack/ callers should remain.
    """

    def test_no_internal_shopstack_callers(self):
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        real_callers = []
        for py_file in (repo / "shopstack").rglob("*.py"):
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                # Match "use_soon_view" as a function call (followed by '(')
                if "use_soon_view(" not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                rel = str(py_file.relative_to(repo))
                # Allowed: the alias definition itself
                if stripped == "def use_soon_view(days: int = 3) -> list[list[str]]:":  # noqa
                    continue
                # Allowed: the deprecation message string
                if (
                    rel == "shopstack/ui/screens/inventory.py"
                    and "use_soon_view" in stripped
                    and '"""' not in line
                    and "use_soon_view is deprecated" in stripped
                ):
                    continue
                real_callers.append((rel, i, line))
        assert not real_callers, (
            "Unexpected internal callers of use_soon_view (legacy):\n"
            + "\n".join(f"  {p}:{n}: {l!r}" for p, n, l in real_callers)
            + "\n\nMigrate these callers to use_first_view, then "
            "remove the use_soon_view alias after the next minor release."
        )
