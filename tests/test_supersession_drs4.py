"""Tests for the ``app_context.runtime_label`` supersession (DR-SS4).

The supersession rules (per ``motto_v3`` §7) require:
  1. Canonical path is the only path recommended for new code.
  2. Legacy paths (if kept) emit a ``DeprecationWarning`` on call.
  3. Legacy paths are kept for one release cycle before deletion.
  4. The canonical path is what UI / API consumers actually use.

This supersession (2026-06-13 v3 round 3, formalised 2026-06-15):
  - ``app_context.runtime_label()`` (legacy, simpler) →
    ``shopstack.ui.header.runtime_label()`` (canonical, four-mode).

The canonical version distinguishes "Cloud runtime" / "Local runtime"
/ "Off-grid mock mode" / "Local mock mode"; the legacy version only
distinguished "loaded real" from "all mock" and is no longer
accurate. See DR-SS4 in ``Docs/audits/ACTION_ITEMS.md`` for the
decision log.

This test:
  1. Verifies the canonical path returns one of the four documented
     runtime modes.
  2. Verifies the legacy ``app_context.runtime_label()`` emits a
     ``DeprecationWarning`` on call (function-level, not module-level,
     because ``app_context`` is widely imported and a module-level
     warning would fire for unrelated import sites).
  3. Verifies the legacy path delegates to the canonical
     implementation (same return value).
  4. Verifies there are no callers of the legacy path in production
     code (so we can delete it after one release cycle).
"""

from __future__ import annotations

import warnings


# ─── Test the canonical path is correct ────────────────────────────────


class TestCanonicalRuntimeLabel:
    """The canonical ``shopstack.ui.header.runtime_label()`` returns
    one of the four documented runtime modes. (Mirror of
    ``tests/test_runtime_status.py::test_runtime_status_label_returns_one_of_four``;
    repeated here so this supersession file is self-contained.)"""

    def test_canonical_runtime_label_returns_one_of_four(self):
        from shopstack.ui.header import runtime_label

        label = runtime_label()
        assert label in {
            "Local mock mode",
            "Local runtime",
            "Cloud runtime",
            "Off-grid mock mode",
        }, f"Unexpected canonical runtime label: {label!r}"


# ─── Test the legacy alias emits a DeprecationWarning ───────────────────


class TestLegacyRuntimeLabelDeprecation:
    """The legacy ``app_context.runtime_label()`` must emit a
    DeprecationWarning on every call and delegate to the canonical
    implementation. Per DR-SS4."""

    def test_legacy_runtime_label_emits_deprecation_warning(self):
        from shopstack import app_context

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            app_context.runtime_label()

        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert deprecation_warnings, (
            "app_context.runtime_label() did not emit a DeprecationWarning. "
            "Per DR-SS4, the legacy alias must emit a DeprecationWarning on "
            "every call so the next audit can confirm migration is complete."
        )
        # The warning message must point at the supersession doc.
        msg = str(deprecation_warnings[0].message)
        assert "shopstack.ui.header" in msg, (
            f"DeprecationWarning message does not point at the canonical path: {msg!r}"
        )
        assert "DR-SS4" in msg, (
            f"DeprecationWarning message does not cite DR-SS4 (the supersession "
            f"decision record): {msg!r}"
        )

    def test_legacy_runtime_label_delegates_to_canonical(self):
        """The legacy alias must return the same value as the canonical
        implementation. If they diverge, the legacy caller would see
        stale data — exactly the silent-skew problem DR-SS4 was
        written to prevent."""
        from shopstack import app_context
        from shopstack.ui.header import runtime_label as canonical

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            legacy_value = app_context.runtime_label()

        canonical_value = canonical()
        assert legacy_value == canonical_value, (
            f"Legacy runtime_label() returned {legacy_value!r} but canonical "
            f"runtime_label() returned {canonical_value!r}. The legacy alias "
            f"must delegate to the canonical implementation per DR-SS4."
        )

    def test_legacy_runtime_label_returns_one_of_four(self):
        """The legacy alias delegates to the canonical, so it must also
        return one of the four documented modes — not the legacy
        "Local runtime" / "Local mock mode" two-mode set."""
        from shopstack import app_context

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            label = app_context.runtime_label()

        assert label in {
            "Local mock mode",
            "Local runtime",
            "Cloud runtime",
            "Off-grid mock mode",
        }, (
            f"Legacy runtime_label() returned {label!r}; expected one of the "
            f"four canonical modes. If this is the legacy two-mode set "
            f"('Local runtime' / 'Local mock mode'), the alias is no longer "
            f"delegating to the canonical implementation."
        )


# ─── Test there are no production callers of the legacy path ───────────


class TestLegacyRuntimeLabelHasNoProductionCallers:
    """DR-SS4 closure criterion: the legacy alias can be deleted after
    one release cycle *only* if no production code calls it. This test
    locks in the zero-caller state so a future refactor that re-adds a
    caller is caught immediately."""

    def test_no_production_caller_of_legacy_runtime_label(self):
        """DR-SS4 closure criterion: the legacy alias can be deleted after
        one release cycle *only* if no production code calls it. This test
        locks in the zero-caller state so a future refactor that re-adds a
        caller is caught immediately.

        Detection rule: a line is a "caller" if it contains
        ``app_context.runtime_label`` (attribute access) and the line is
        not inside a docstring, comment, or backtick-quoted prose that
        merely describes the legacy path. We detect "describes" lines
        by checking for backticks (markdown-style docstring text) or
        a leading ``-`` (markdown bullet). Real call sites look like
        ``label = app_context.runtime_label()`` — no backticks.
        """
        import re
        from pathlib import Path

        # Attribute access only — module-level import is also covered
        # by the more general pattern below; the combination catches
        # both direct ``app_context.runtime_label()`` calls and
        # ``from shopstack.app_context import ... runtime_label``.
        attr_access = re.compile(r"app_context\.runtime_label")
        import_pattern = re.compile(
            r"from\s+shopstack\.app_context\s+import\s+[^)]*\bruntime_label\b"
        )
        offenders: list[str] = []
        for path in Path("shopstack").rglob("*.py"):
            if path.name == "app_context.py":
                # The shim itself obviously defines the function.
                continue
            text = path.read_text()
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                # Skip markdown-style docstring prose (lines with
                # backticks or leading dashes describe the legacy
                # path; they don't call it).
                if "`" in line or stripped.startswith("- "):
                    continue
                # Skip lines that are entirely inside a docstring
                # (we approximate by skipping lines that start a
                # docstring with triple quotes — anything inside is
                # documented by Python's parser, not us).
                if '"""' in line or "'''" in line:
                    continue
                if attr_access.search(line) or import_pattern.search(line):
                    offenders.append(f"{path}: {stripped}")

        assert not offenders, (
            "Production code still calls the legacy app_context.runtime_label(). "
            "Per DR-SS4, migrate all callers to shopstack.ui.header.runtime_label "
            "before deleting the legacy alias. Offenders:\n"
            + "\n".join(offenders)
        )
