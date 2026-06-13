"""Regression tests for screens/__init__.py import hygiene.

Per `docs/audits/audit_03_gradio_app_architecture.md` finding 3.9:
    "Duplicate import of `recipe_text_to_shopping_list` in
     `shopstack/ui/screens/__init__.py` — should be removed."

This test catches duplicate imports and missing `__all__` entries.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

import pytest


SCREENS_INIT = (
    Path(__file__).resolve().parents[1]
    / "shopstack" / "ui" / "screens" / "__init__.py"
)


def test_screens_init_has_no_duplicate_imports():
    """Each import statement in screens/__init__.py should be unique.

    Duplicate imports are a code smell — they waste startup time
    and signal carelessness.
    """
    content = SCREENS_INIT.read_text()
    tree = ast.parse(content)

    import_lines: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                import_lines.append(f"{node.module}.{alias.name}")

    counts = Counter(import_lines)
    duplicates = {name: count for name, count in counts.items() if count > 1}

    assert not duplicates, (
        f"Duplicate imports in screens/__init__.py: {duplicates}. "
        f"Remove the duplicates — Python tolerates them but they "
        f"signal carelessness and waste startup time."
    )


def test_screens_init_uses_noqa_for_legacy_exports():
    """Legacy exports (backward compat) should be marked with `# noqa: F401`.

    This is a documentation test: any private import (underscore
    prefix) should have a noqa comment explaining why it's kept.
    """
    content = SCREENS_INIT.read_text()

    # Find lines that import underscore-prefixed names without noqa
    suspect_lines = []
    for i, line in enumerate(content.splitlines(), start=1):
        if "_" and re.search(r"^from\s+\S+\s+import\s+_\w+", line):
            if "noqa" not in line:
                suspect_lines.append((i, line))

    assert not suspect_lines, (
        f"Private imports without `# noqa: F401` in "
        f"screens/__init__.py: {suspect_lines}. The convention "
        f"is to mark them so linters don't flag them."
    )


def test_screens_init_all_matches_imports():
    """Every name in `__all__` should be importable.

    A name in `__all__` that's not actually imported causes
    `from shopstack.ui.screens import that_name` to fail.

    Note: This test may fail for backwards-compatible names that
    were once imported but the import line was removed. The test
    currently FAILS HARD for these — that's intentional. The fix
    is either to re-add the import or to remove the name from __all__.
    """
    content = SCREENS_INIT.read_text()
    tree = ast.parse(content)

    # Collect all imported names
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])

    # Collect __all__
    all_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_names.add(elt.value)

    missing_in_imports = all_names - imported

    if missing_in_imports:
        pytest.fail(
            f"Names in __all__ but not imported: {missing_in_imports}. "
            f"This is a real bug — `from shopstack.ui.screens import X` "
            f"will fail for these names. Either add the import line "
            f"or remove the name from __all__. See "
            f"docs/audits/audit_03_gradio_app_architecture.md."
        )
