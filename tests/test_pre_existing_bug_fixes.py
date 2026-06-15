"""Regression tests for pre-existing import/syntax bugs fixed in 2026-06-14.

These tests lock in the fixes so the bugs don't silently come back:

  1. Circular import: services/receipt.py → shopstack.portability →
     persistence.database → services.training_capture → services.__init__
     → services.receipt (FIXED: moved ImportResult import inside the
     function that uses it)

  2. Missing import: ui/screens/onboarding.py used home_card() but
     didn't import it (FIXED: added home_card to the import)

  3. Missing import: ui/household_settings.py used db() but didn't
     import it (FIXED: added db to the import)

  4. Double-comma typo: ui/screens/household_map.py had
     ``stat_card,, home_card,`` — invalid syntax (FIXED: removed
     the extra comma)

  5. Missing use_soon_view alias: ui/screens/inventory.py renamed
     use_soon_view to use_first_view but the import chain still
     expected use_soon_view (FIXED: added deprecated alias)

Per motto_v3 §6 (Pre-existing Is Not an Excuse — Fix It), these
were pre-existing failures in the blast radius of the 2026-06-14
hardening pass.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestCircularImportRegression:
    """The receipt.py ↔ portability circular import must not come back."""

    def test_portability_imports_without_circular_error(self):
        """``import shopstack.portability`` must succeed.

        If the ImportResult import in services/receipt.py is moved back
        to the module top, this will raise ImportError.
        """
        result = subprocess.run(
            [sys.executable, "-c", "import shopstack.portability; print('OK')"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"shopstack.portability import failed (circular import regressed): "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
        assert "OK" in result.stdout

    def test_receipt_imports_after_portability(self):
        """``from shopstack.services.receipt import confirm_receipt``
        must succeed after portability is already loaded."""
        result = subprocess.run(
            [sys.executable, "-c",
             "import shopstack.portability; "
             "from shopstack.services.receipt import confirm_receipt; "
             "print('OK')"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"Confirm receipt import failed: stdout={result.stdout!r}, "
            f"stderr={result.stderr!r}"
        )

    def test_confirm_receipt_lazy_imports_import_result(self):
        """The confirm_receipt function must lazily import ImportResult
        (not at module top) to break the cycle.

        A "module-level" import means a non-indented ``from shopstack.portability``
        statement at the top of the file. The lazy import inside the
        confirm_receipt() function body is fine.
        """
        import shopstack.services.receipt as receipt_module
        source = Path(receipt_module.__file__).read_text(encoding="utf-8")
        # Find lines that start with ``from shopstack.portability`` at
        # column 0 (no indentation = module level). Skip comment lines.
        module_level_imports = []
        for line in source.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Module-level imports are at column 0 (no leading whitespace)
            if line.startswith("from shopstack.portability") or \
               line.startswith("import shopstack.portability"):
                module_level_imports.append(stripped)
        assert not module_level_imports, (
            f"Found module-level portability imports in receipt.py — "
            f"this would re-introduce the circular import. "
            f"Imports found: {module_level_imports}. "
            f"Move them inside the function that uses ImportResult."
        )


class TestMissingImportsRegression:
    """Modules that previously used names without importing them."""

    def test_onboarding_imports_home_card(self):
        """The canonical onboarding module must import home_card.

        Note: shopstack/ui/screens/onboarding.py is a backward-compat
        shim that re-exports from shopstack/ui/tabs/onboarding.py. The
        actual implementation lives in tabs/.
        """
        path = REPO_ROOT / "shopstack" / "ui" / "tabs" / "onboarding.py"
        source = path.read_text(encoding="utf-8")
        assert "home_card" in source, (
            "tabs/onboarding.py should import home_card from primitives"
        )
        # And the import line must be present
        assert re.search(
            r"from\s+shopstack\.ui\.components\.primitives\s+import.*\bhome_card\b",
            source,
        ), "tabs/onboarding.py must import home_card from primitives"

    def test_household_settings_imports_db(self):
        """ui/household_settings.py must import db from app_context."""
        path = REPO_ROOT / "shopstack" / "ui" / "household_settings.py"
        source = path.read_text(encoding="utf-8")
        assert re.search(
            r"from\s+shopstack\.app_context\s+import.*\bdb\b",
            source,
        ), "household_settings.py must import db from app_context"

    def test_app_builds(self):
        """The full app must build without import errors."""
        result = subprocess.run(
            [sys.executable, "-c", "from app import build_app; build_app(); print('OK')"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, (
            f"App build failed: stdout={result.stdout!r}, stderr={result.stderr!r}"
        )


class TestTypoRegression:
    """The double-comma typo in household_map.py must not come back."""

    def test_no_double_commas_in_primitives_imports(self):
        """No ``xxx,, yyy`` patterns in any file's primitives imports."""
        for py_file in (REPO_ROOT / "shopstack").rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            source = py_file.read_text(encoding="utf-8")
            # Look for ,, inside multi-line import parens
            if re.search(r"^\s*\w+,,", source, re.MULTILINE):
                pytest.fail(
                    f"Double-comma typo found in {py_file.relative_to(REPO_ROOT)}"
                )


class TestUseSoonViewSupersessionRegression:
    """The use_soon_view deprecated alias must remain importable."""

    def test_use_soon_view_importable_from_inventory(self):
        """The deprecated alias must work for at least one release cycle."""
        from shopstack.ui.screens.inventory import use_soon_view, use_first_view
        assert callable(use_soon_view)
        assert callable(use_first_view)
        # They should be the same function (alias)
        assert use_soon_view is not use_first_view, (
            "use_soon_view should be a deprecated wrapper, not the "
            "same function object as use_first_view"
        )

    def test_use_soon_view_emits_deprecation_warning(self):
        """Calling use_soon_view must emit DeprecationWarning."""
        import warnings

        from shopstack.ui.screens.inventory import use_soon_view

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # The function requires a DB; we don't need to test the
            # return value, just the warning emission
            try:
                use_soon_view(days=3)
            except Exception:
                pass  # The DB may not be initialized; we only care about the warning
            deprecation_warnings = [
                w for w in caught
                if issubclass(w.category, DeprecationWarning)
                and "use_soon_view" in str(w.message)
            ]
            assert deprecation_warnings, (
                "use_soon_view should emit a DeprecationWarning directing "
                "users to use_first_view"
            )


# Local import for re (imported at function level to keep test collection fast)
import re
