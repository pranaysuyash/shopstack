"""Regression test: every Python file in shopstack/ parses cleanly.

Catches the "parallel-agent-introduced syntax corruption" failure
mode observed in 2026-06-15 where 82 files had broken f-string
continuations and several had unterminated string literals.

Per motto_v3 §6 ("pre-existing is not an excuse"), this is the
runtime verification of the systemic f-string repair. If any file
fails to parse, this test fails with the exact file + line number
+ error message.

Catches:
- Unterminated string literals (e.g., ``f"abc'``)
- Unterminated triple-quoted strings
- Stray characters in f-string expressions (``{x' instead of``{x}'``)
- Invalid syntax from duplicated list blocks
- Missing colons / parentheses / brackets
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_GLOBS = (
    ".venv/*",
    "**/__pycache__/*",
    "**/node_modules/*",
    ".git/*",
    ".mypy_cache/*",
    ".pytest_cache/*",
    "*.egg-info/*",
    "build/*",
    "dist/*",
    "tools/*",
    ".playwright-mcp/*",
)


def _is_excluded(rel: str) -> bool:
    """True if the path matches any of the EXCLUDED_GLOBS patterns."""
    return any(fnmatch.fnmatch(rel, g) for g in EXCLUDED_GLOBS)


def _collect_python_files() -> list[str]:
    files = []
    for p in ROOT.rglob("*.py"):
        rel = str(p.relative_to(ROOT))
        if _is_excluded(rel):
            continue
        files.append(rel)
    files.sort()
    return files


PYTHON_FILES = _collect_python_files()


class TestAllPythonFilesParse:
    """``ast.parse`` over every ``.py`` file in the repo must succeed."""

    @pytest.mark.parametrize("rel_path", PYTHON_FILES)
    def test_parses(self, rel_path: str):
        path = ROOT / rel_path
        try:
            ast.parse(path.read_text(), filename=rel_path)
        except SyntaxError as e:
            pytest.fail(
                f"Syntax error in {rel_path}:{e.lineno}:{e.offset}: {e.msg}\n"
                f"  Text: {(e.text or '<empty>').rstrip()}"
            )


class TestSyntaxCheckMeta:
    """Meta-tests about the regression suite itself."""

    def test_python_file_count_is_nonzero(self):
        """We should have at least 100 Python files to test (sanity)."""
        assert len(PYTHON_FILES) >= 100, (
            f"Expected ≥ 100 Python files, found {len(PYTHON_FILES)}"
        )

    def test_shopstack_module_count_is_nonzero(self):
        shopstack_files = [
            f for f in PYTHON_FILES if f.startswith("shopstack/")
        ]
        assert len(shopstack_files) >= 100, (
            f"Expected ≥ 100 shopstack/ Python files, found {len(shopstack_files)}"
        )

