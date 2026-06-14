"""Tests for the supersession audit (added 2026-06-13).

The supersession rules (per ``motto_v3`` §7 and the system prompt
hard rule on duplicate API routes) require:
  1. Canonical path is the only path exported from ``__all__``.
  2. Legacy paths (if kept) emit a ``DeprecationWarning`` on call.
  3. Legacy paths are kept for one release cycle before deletion.
  4. No call sites of legacy paths in the codebase.

This audit (2026-06-13) found one real supersession in progress:
  - ``shopping_list_view()`` (4-tuple return) → ``shopping_list_view_with_cards()``
    (6-tuple return).

The fix (this PR):
  - Added the missing ``DeprecationWarning`` to ``shopping_list_view()``.
  - Removed ``shopping_list_view`` from ``screens/__init__.py:__all__``
    (to match the docstring's claim that it was already removed; the
    import statement is kept so the function is still accessible
    via direct module import — for one release cycle).
  - Added a test that locks in the supersession state.

This test:
  1. Verifies the canonical path is in ``__all__`` and importable.
  2. Verifies the legacy path emits a ``DeprecationWarning`` on call.
  3. Verifies the legacy path is NOT in ``__all__`` (it's hidden from
     wildcard imports but still accessible via direct module import).
  4. Verifies there are no call sites of the legacy path in the
     codebase (so we can delete it after one release cycle).
"""

from __future__ import annotations

import warnings
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


class TestSupersessionCanonical:
    """The canonical path must be the primary exported API."""

    def test_canonical_path_in_screens_all(self):
        from shopstack.ui.screens import __all__ as screens_all
        assert "shopping_list_view_with_cards" in screens_all, (
            "Canonical shopping_list_view_with_cards must be in "
            "screens.__all__."
        )

    def test_legacy_path_not_in_screens_all(self):
        """The legacy path must be REMOVED from screens.__all__.

        It is still accessible via direct module import
        (``from shopstack.ui.screens.shopping import shopping_list_view``)
        for one release cycle, but should NOT appear in wildcard
        imports (``from shopstack.ui.screens import *``).
        """
        from shopstack.ui.screens import __all__ as screens_all
        assert "shopping_list_view" not in screens_all, (
            "Legacy shopping_list_view is still in screens.__all__. "
            "Per the supersession protocol, it must be removed from "
            "__all__ (but kept in the import block for one release "
            "cycle). See HANDOFF_SUPERSESSION_AUDIT_2026-06-13.md."
        )

    def test_canonical_path_importable_via_wildcard(self):
        from shopstack.ui import screens
        # Simulate wildcard import
        ns = {n: getattr(screens, n) for n in screens.__all__}
        assert "shopping_list_view_with_cards" in ns
        assert callable(ns["shopping_list_view_with_cards"])
        assert "shopping_list_view" not in ns

    def test_legacy_path_still_importable_via_direct_module(self):
        """One release cycle: legacy still accessible via direct import.

        This is the safety valve — if a third-party script or old
        test imports the legacy function directly, it still works
        (with a DeprecationWarning).
        """
        from shopstack.ui.screens.shopping import shopping_list_view
        assert callable(shopping_list_view)


class TestSupersessionDeprecationWarning:
    """The legacy path must emit a DeprecationWarning on call."""

    def test_legacy_emits_deprecation_warning(self):
        from shopstack.ui.screens.shopping import shopping_list_view
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                shopping_list_view()
            except Exception:
                # If the call fails for environmental reasons, we
                # still want to check the warning was emitted.
                pass
        deprecations = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert deprecations, (
            "shopping_list_view() did not emit a DeprecationWarning. "
            "Per the supersession protocol, the legacy path must "
            "warn callers so they migrate to the canonical path."
        )
        # The warning message should mention the canonical replacement
        msg = str(deprecations[0].message)
        assert "shopping_list_view_with_cards" in msg, (
            f"DeprecationWarning message should mention the canonical "
            f"replacement 'shopping_list_view_with_cards'. Got: {msg!r}"
        )

    def test_legacy_still_returns_correct_shape(self):
        """The legacy must still return its 4-tuple shape for back-compat."""
        from shopstack.ui.screens.shopping import shopping_list_view
        with warnings.catch_warnings():
            # Suppress the warning so the test output is clean
            warnings.simplefilter("ignore", DeprecationWarning)
            result = shopping_list_view()
        assert isinstance(result, tuple)
        assert len(result) == 4, (
            f"Legacy shopping_list_view must return a 4-tuple. "
            f"Got {len(result)}-tuple: {result!r}"
        )


class TestSupersessionNoInternalCallSites:
    """The legacy path should have zero internal call sites so it's
    safe to delete after one release cycle."""

    def test_no_internal_call_sites_of_legacy(self):
        """Scan the codebase for non-doc, non-deprecation uses.

        Allowed matches (the audit tolerates these):
          * The function definition itself (``def shopping_list_view():``)
          * The deprecation message inside the function
          * The import line in __init__.py (kept for back-compat)
          * The commented-out __all__ entry (audit marker)

        Any OTHER match is a real call site and means we should NOT
        delete the legacy function yet.
        """
        path_to_check = REPO / "shopstack"

        real_call_sites = []
        for py_file in path_to_check.rglob("*.py"):
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                if "shopping_list_view" not in line:
                    continue
                # Skip the canonical and other variants
                if (
                    "shopping_list_view_with_cards" in line
                    or "shopping_list_substitutions_view" in line
                    or "shopping_list_item_choices" in line
                ):
                    continue
                stripped = line.strip()
                # Skip comments
                if stripped.startswith("#"):
                    continue
                # Skip these specific allowed patterns:
                rel_path = str(py_file.relative_to(REPO))
                # 1. The function definition itself
                if stripped == "def shopping_list_view():":
                    continue
                # 2. The deprecation warning message inside the function
                if rel_path == "shopstack/ui/screens/shopping.py" and (
                    stripped.startswith('"shopping_list_view()')
                    or "shopping_list_view() is deprecated" in stripped
                ):
                    continue
                # 3. The import line in __init__.py
                if (
                    rel_path == "shopstack/ui/screens/__init__.py"
                    and stripped == "shopping_list_view,"
                ):
                    continue
                real_call_sites.append((rel_path, i, line))

        assert not real_call_sites, (
            "Unexpected call sites of legacy shopping_list_view: \n"
            + "\n".join(f"  {p}:{n}: {l!r}" for p, n, l in real_call_sites)
            + "\n\nFix: migrate the call site to shopping_list_view_with_cards, "
            "then remove the entry. See HANDOFF_SUPERSESSION_AUDIT_2026-06-13.md."
        )
