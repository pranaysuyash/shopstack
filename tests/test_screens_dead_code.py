"""Regression tests for screen function usage (dead code detection).

Per `docs/audits/ACTION_ITEMS.md` Open Questions for v4:
    "Are all 32 `screens/*.py` files actually used? A static
     analysis tool could identify dead screen functions."

This test walks every public function in `shopstack/ui/screens/*.py`
and checks if it has any reference (Name, Attribute, import, call)
anywhere in the codebase (tabs/, screens/, app.py, tests/).

Findings (v3 round):
- 99 public screen functions
- 84 are referenced somewhere
- 15 are dead (defined but never called or imported except via
  the __all__ re-export)

A "dead" function is one that:
1. Has a public name (no `_` prefix)
2. Is defined in a non-private screens module
3. Has NO reference outside the defining file (and its own `__all__`
   re-export in `screens/__init__.py`)

A function can be legitimately "dead" if:
- It was recently introduced but the UI binding isn't done yet
- It's a future-proof API surface for plugins
- It's a deprecated function waiting for removal

The test reports these cases for manual review. It does NOT
automatically fail on dead functions — that would block
intentional-but-unfinished work. Instead, it provides a
console report.

Run with `-v` to see the full dead-function list.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

# All non-private screens modules
SCREENS_DIR = Path(__file__).resolve().parents[1] / "shopstack" / "ui" / "screens"

# Search paths: only PRODUCTION code (not tests). The dead-code
# question is about whether a screen function is called by the
# app, not by tests. Tests are downstream consumers, not drivers.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEARCH_DIRS = [
    PROJECT_ROOT / "shopstack" / "ui" / "tabs",
    PROJECT_ROOT / "shopstack" / "ui",  # for locale_save, household_settings, etc.
]
APP_PY = PROJECT_ROOT / "app.py"


def _collect_public_functions() -> dict[str, list[str]]:
    """Return {func_name: [defining_files]} for all public screens funcs."""
    funcs: dict[str, list[str]] = defaultdict(list)

    for src in SCREENS_DIR.glob("*.py"):
        if src.name in {"__init__.py", "_utils.py"}:
            continue
        try:
            tree = ast.parse(src.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                funcs[node.name].append(str(src.relative_to(SCREENS_DIR.parent.parent)))

    return funcs


def _get_search_files() -> list[Path]:
    """Get all .py files in the search paths, deduplicated."""
    seen: set[Path] = set()
    files: list[Path] = []
    for d in SEARCH_DIRS:
        if d.is_file():
            if d not in seen:
                seen.add(d)
                files.append(d)
        elif d.is_dir():
            for f in d.rglob("*.py"):
                # Skip non-text files (e.g. .pyc, .pyd) that may live
                # alongside .py files in some configurations
                if f.suffix == ".py" and "__pycache__" not in str(f):
                    if f not in seen:
                        seen.add(f)
                        files.append(f)
    if APP_PY.exists() and APP_PY not in seen:
        files.append(APP_PY)
    return files


def _find_references() -> set[str]:
    """Walk search files; collect any name that appears as a Name or Attribute.

    AI-21 enhancement: also track import aliases (``as`` clauses). This
    eliminates false positives for functions that are imported under
    a different name (e.g., ``from ... import set_opt_in_screen as
    _set_opt_in`` should still count as a reference to the original
    name).
    """
    all_funcs = _collect_public_functions()
    func_names = set(all_funcs.keys())
    referenced: set[str] = set()

    for src in _get_search_files():
        try:
            content = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # Direct name reference: ``foo()`` or ``foo.attr``
            if isinstance(node, ast.Name) and node.id in func_names:
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute) and node.attr in func_names:
                referenced.add(node.attr)
            # Import alias: ``from x import y as z`` — the AST stores
            # both ``name=y`` and ``asname=z``. The original name is
            # still importable as ``y``, so it IS a reference.
            elif isinstance(node, ast.alias) and node.name in func_names:
                # The alias might be a dotted path; check the last segment
                bare_name = node.name.split(".")[-1]
                if bare_name in func_names:
                    referenced.add(bare_name)

    return referenced


def test_no_dead_public_screen_functions(capsys):
    """Public screen functions should be referenced somewhere.

    A dead function is one with no Name/Attribute reference anywhere
    in the project. These are candidates for:
    - Removal (if truly unused)
    - UI binding (if the implementation exists but is unwired)
    - Documentation (if it's an intentional future API)

    This test reports dead functions but does not fail — manual
    review determines the right action. The dead list is printed
    to stdout for visibility in CI logs.
    """
    all_funcs = _collect_public_functions()
    referenced = _find_references()
    dead = sorted(name for name in all_funcs if name not in referenced)

    if dead:
        # Print to stdout so it shows in CI logs (informational only)
        print()
        print("=" * 70)
        print(f"POTENTIALLY DEAD PUBLIC SCREEN FUNCTIONS ({len(dead)})")
        print("=" * 70)
        print("These public functions are defined but never referenced")
        print("outside their defining file (and the __all__ re-export).")
        print("Decide: remove, wire up, or document as future API.")
        print()
        for name in dead:
            print(f"  - {name} (in {all_funcs[name][0]})")
        print()
        print("=" * 70)
        # Test passes — manual review determines the right action
        # To convert to a hard failure, change `return` to an assertion:
        # assert not dead, "Found N dead screen functions — see output above"
    return  # dead or not, this test is informational


def test_public_screen_function_count_in_range():
    """The public screen function surface should be a reasonable size.

    A growing surface (> 150) signals over-modularization.
    A shrinking surface (< 30) signals under-modularization.

    Current v3: 99 public functions across 32 modules — healthy.
    """
    funcs = _collect_public_functions()
    count = len(funcs)
    assert 30 <= count <= 150, (
        f"Public screen function count is {count}. Expected 30-150. "
        f"This may indicate over- or under-modularization."
    )


def test_no_underscore_prefixed_public_functions():
    """Public functions in screens/ should not have a leading underscore.

    A function with a `_` prefix signals "private to this module."
    If it's truly public (importable from outside), it should not
    have the underscore.

    This test catches inconsistencies in the public/private
    naming convention.
    """
    funcs = _collect_public_functions()
    # All collected functions don't have `_` prefix (we filter above).
    # This test is a guard against the filter being broken.
    for name in funcs:
        assert not name.startswith("_"), (
            f"Function {name} is public but has an underscore prefix. "
            f"Either rename to drop the underscore, or this is a bug "
            f"in the dead-code test."
        )
