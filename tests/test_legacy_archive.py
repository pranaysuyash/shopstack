"""Regression tests for the _legacy/ archive and supersession shims.

Per `motto_v3` §7 (Supersession Rule), §11 (Engineering Standards),
and `Docs/DECISION_RECORDS_CODE_REMOVALS_2026-06-13.md`:
- Functions that look "dead" (no Python callers) should NOT be
  deleted. They should be ARCHIVED with a compatibility shim so
  external consumers don't break.
- The archive process is documented in
  `shopstack/ui/screens/_legacy/_LEGACY.md`.

This test verifies:
1. The `_legacy/` directory exists and contains the archived modules
2. Each archived module is still importable from its original path
3. Each archived module is still re-exported from `screens/__init__.py`
4. The `_LEGACY.md` documentation exists
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREENS_DIR = PROJECT_ROOT / "shopstack" / "ui" / "screens"
LEGACY_DIR = SCREENS_DIR / "_legacy"


def test_legacy_directory_exists():
    """The _legacy/ directory must exist (DR-SS1 supersession archive)."""
    assert LEGACY_DIR.is_dir(), (
        "Expected _legacy/ directory at "
        + str(LEGACY_DIR)
        + ". Per DR-SS1 (2026-06-13), archived screens live here. "
        "If you deleted it, follow motto_v3 §7 — re-create it or "
        "document the change in DECISION_RECORDS_CODE_REMOVALS."
    )


def test_legacy_documentation_exists():
    """`_LEGACY.md` must exist and document the archive rationale."""
    legacy_md = LEGACY_DIR / "_LEGACY.md"
    assert legacy_md.is_file(), (
        f"Expected _LEGACY.md at {legacy_md}. Per motto_v3 §15 "
        f"('If logic is preserved but not used, inventory it before "
        f"deleting or archiving'), the archive rationale must be "
        f"documented. Add a _LEGACY.md explaining each archived file."
    )

    content = legacy_md.read_text()
    # Must reference the supersession rules
    assert "motto_v3" in content, (
        f"_LEGACY.md must reference motto_v3. Current content "
        f"doesn't mention it."
    )
    assert "§7" in content or "§11" in content, (
        f"_LEGACY.md must cite the specific motto_v3 sections. "
        f"§7 (Supersession) and §11 (Engineering Standards) are the "
        f"two most relevant."
    )


def test_households_archived_in_legacy():
    """`households.py` must be in `_legacy/`, not in `screens/`."""
    legacy_file = LEGACY_DIR / "households.py"
    original_file = SCREENS_DIR / "households.py"

    assert legacy_file.is_file(), (
        f"Expected archived `households.py` at {legacy_file}. Per "
        f"DR-SS1 (2026-06-13), this file is Phase 10 #1 wiring "
        f"preserved per motto_v3 §11."
    )
    # The original `households.py` should be the SHIM (3-line re-export)
    assert original_file.is_file(), (
        f"Expected a compatibility shim at {original_file} so the "
        f"original import path continues to work."
    )

    shim_content = original_file.read_text()
    assert "from shopstack.ui.screens._legacy.households import" in shim_content, (
        f"The shim at {original_file} must re-export from the "
        f"_legacy/ module. Current content doesn't follow the "
        f"supersession pattern documented in _LEGACY.md."
    )


def test_households_5_functions_still_importable():
    """The 5 archived households functions must still be importable."""
    expected_functions = [
        "add_member_screen",
        "change_role_screen",
        "households_panel_screen",
        "list_user_households_screen",
        "remove_member_screen",
    ]

    # Import via __init__.py
    from shopstack.ui.screens import __all__ as screens_all
    for fn_name in expected_functions:
        assert fn_name in screens_all, (
            f"Expected {fn_name} in screens/__init__.py:__all__. "
            f"Without this, the function is no longer part of the "
            f"public API. Per supersession, archived functions stay "
            f"in __all__ for backward compatibility."
        )

    # Import via direct module path
    from shopstack.ui.screens import households
    for fn_name in expected_functions:
        assert hasattr(households, fn_name), (
            f"Expected {households.__name__}.{fn_name} to be "
            f"importable from `from shopstack.ui.screens import "
            f"households`."
        )

    # Import via _legacy/ path
    from shopstack.ui.screens._legacy import households as legacy_households
    for fn_name in expected_functions:
        assert hasattr(legacy_households, fn_name), (
            f"Expected {fn_name} in _legacy/households.py."
        )


def test_households_shim_preserves_actual_implementation():
    """The shim must re-export the REAL implementation, not a stub."""
    from shopstack.ui.screens import households
    from shopstack.ui.screens._legacy import households as legacy

    # The function objects should be the SAME (not just same name)
    assert households.add_member_screen is legacy.add_member_screen, (
        f"Shim at shopstack.ui.screens.households must re-export the "
        f"same function object as _legacy.households. If they're "
        f"different objects, the shim is creating a new function "
        f"instead of re-exporting — a copy-paste bug."
    )


def test_archived_households_documented_in_legacy_md():
    """_LEGACY.md must list the households.py archive with rationale."""
    legacy_md = (LEGACY_DIR / "_LEGACY.md").read_text()
    assert "households.py" in legacy_md, (
        f"_LEGACY.md must list households.py in its inventory. "
        f"Without this, future agents won't know why this file "
        f"exists in _legacy/."
    )
    # Must reference Phase 10
    assert "Phase 10" in legacy_md or "PHASE10" in legacy_md, (
        f"_LEGACY.md must reference the Phase 10 handoff that "
        f"documents households.py as canonical Phase 10 wiring."
    )


def test_screens_init_does_not_break_with_archived_module():
    """Importing `shopstack.ui.screens` must still work after archive.

    This is a smoke test: if the archive broke __init__.py, this
    fails. Per motto_v3 §7, backward compatibility is a hard
    requirement.
    """
    try:
        mod = importlib.import_module("shopstack.ui.screens")
    except Exception as exc:
        pytest.fail(
            f"Importing shopstack.ui.screens raised {exc}. The "
            f"archive of households.py should not have broken "
            f"__init__.py."
        )

    # Also import the specific archived functions
    try:
        from shopstack.ui.screens import (
            add_member_screen,
            change_role_screen,
            households_panel_screen,
            list_user_households_screen,
            remove_member_screen,
        )
    except ImportError as exc:
        pytest.fail(
            f"Failed to import archived functions from "
            f"shopstack.ui.screens: {exc}"
        )
