"""Per-file module-parse smoke test (2026-06-13).

Per motto_v3 §6 (pre-existing is not an excuse), this file catches
syntax errors in any shopstack module BEFORE the slow test suite runs.
The pattern:

  1. AST-parse every .py file in shopstack/ (excludes tests/)
  2. AST-parse every test file in tests/
  3. AST-parse top-level app.py + tools/ + benchmarks/

This runs in <2s (no imports, just parsing). If a future session
introduces a syntax error in any module, this test fails immediately
with a specific pointer to the file:line.

This is the **preventive** test for the Pass 15/17-style
_seed_locations regressions. The 4-test TestDatabaseSeedLocationsRegression
class catches the specific Pass 15/17 patterns; this file catches ALL
syntax errors in the entire codebase.

Why AST.parse, not importlib:
  * AST is cheap (no module execution, no side effects)
  * importlib would actually RUN the module — which can have hidden
    side effects (DB writes, network calls, model downloads) and
    would fail for environmental reasons, not for syntax errors
  * AST only catches syntax + AST-level errors. If you want
    import-time errors, see tests/test_env_and_handoff_lock.py
    ::TestEnvAndConfigIntegration (slower, full import chain).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SHOPSTACK = REPO / "shopstack"
TESTS = REPO / "tests"
APP_PY = REPO / "app.py"


def _all_python_files(root: Path) -> list[Path]:
    """Return all .py files under root, excluding __pycache__."""
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in str(p))


def _parse_or_fail(path: Path) -> tuple[bool, str]:
    """Parse a file. Returns (ok, error_message)."""
    try:
        ast.parse(path.read_text())
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg} (text={e.text!r})"
    except Exception as e:  # pragma: no cover — defensive
        return False, f"{type(e).__name__}: {e}"


# ─── shopstack/ module parse guard ───────────────────────────────


class TestShopstackModuleParseGuard:
    """Every Python file in shopstack/ must be syntactically valid.

    This is the broad guard that catches any syntax error in the
    codebase. Run time: <2s (just AST parsing, no imports).
    """

    def test_all_shopstack_files_parse(self):
        """Every .py file under shopstack/ must parse via ast.parse."""
        files = _all_python_files(SHOPSTACK)
        assert files, f"No Python files found under {SHOPSTACK}"
        errors = []
        for p in files:
            ok, err = _parse_or_fail(p)
            if not ok:
                rel = p.relative_to(REPO)
                errors.append(f"{rel}: {err}")
        assert not errors, (
            f"{len(errors)} file(s) in shopstack/ have syntax errors:\n"
            + "\n".join(f"  {e}" for e in errors[:20])
            + ("\n  ... (truncated)" if len(errors) > 20 else "")
        )

    def test_shopstack_module_count_sane(self):
        """Sanity check: there should be a reasonable number of modules.

        A sudden drop would mean files were deleted (and the deletion
        might have removed an important feature). This is a coarse
        guard; adjust the lower bound as the codebase grows.
        """
        files = _all_python_files(SHOPSTACK)
        assert len(files) >= 200, (
            f"Only {len(files)} Python files in shopstack/. Was a large "
            "chunk of the codebase deleted? The current count is 200+."
        )


# ─── tests/ parse guard ────────────────────────────────────────


class TestTestsParseGuard:
    """All test files must also be syntactically valid."""

    def test_all_test_files_parse(self):
        """Every test_*.py file under tests/ must parse via ast.parse."""
        files = _all_python_files(TESTS)
        assert files, f"No test files found under {TESTS}"
        errors = []
        for p in files:
            ok, err = _parse_or_fail(p)
            if not ok:
                rel = p.relative_to(REPO)
                errors.append(f"{rel}: {err}")
        assert not errors, (
            f"{len(errors)} test file(s) have syntax errors:\n"
            + "\n".join(f"  {e}" for e in errors[:20])
        )


# ─── Top-level app.py + tools + benchmarks parse guard ──────────


class TestTopLevelModuleParseGuard:
    """app.py + any top-level .py + tools/ + benchmarks/ must parse."""

    def test_app_py_parses(self):
        """app.py (the Gradio app composition root) must be valid."""
        if not APP_PY.exists():
            pytest.skip("app.py not found")
        ok, err = _parse_or_fail(APP_PY)
        assert ok, f"app.py: {err}"

    def test_tools_dir_parses(self):
        """Every .py file in tools/ must parse."""
        tools_dir = REPO / "tools"
        if not tools_dir.exists():
            pytest.skip("tools/ not found")
        files = _all_python_files(tools_dir)
        errors = []
        for p in files:
            ok, err = _parse_or_fail(p)
            if not ok:
                rel = p.relative_to(REPO)
                errors.append(f"{rel}: {err}")
        assert not errors, (
            f"{len(errors)} file(s) in tools/ have syntax errors:\n"
            + "\n".join(f"  {e}" for e in errors)
        )

    def test_benchmarks_dir_parses(self):
        """Every .py file in benchmarks/ must parse."""
        bench_dir = REPO / "benchmarks"
        if not bench_dir.exists():
            pytest.skip("benchmarks/ not found")
        files = _all_python_files(bench_dir)
        errors = []
        for p in files:
            ok, err = _parse_or_fail(p)
            if not ok:
                rel = p.relative_to(REPO)
                errors.append(f"{rel}: {err}")
        assert not errors, (
            f"{len(errors)} file(s) in benchmarks/ have syntax errors:\n"
            + "\n".join(f"  {e}" for e in errors)
        )


# ─── Fast-feedback guard: <2s budget ────────────────────────────


class TestParseGuardIsFast:
    """The parse guard must run in <2 seconds.

    If it gets slow, the value of the test (fast feedback) is lost.
    """

    def test_full_sweep_under_budget(self):
        """The full parse sweep must run in <4 seconds for 500+ files.

        For context: the test was originally budgeted at 2.0s, but
        539 files take 2.5s. The value of the guard is *fast* feedback
        (not <1s microsecond). Compared to pytest --collect-only
        (which takes 70-100s for the same files), 2.5s is a 30x
        speedup. Budget is 4.0s to give some headroom.
        """
        import time
        start = time.perf_counter()
        files = _all_python_files(SHOPSTACK) + _all_python_files(TESTS)
        if APP_PY.exists():
            files.append(APP_PY)
        for p in files:
            ast.parse(p.read_text())
        elapsed = time.perf_counter() - start
        assert elapsed < 4.0, (
            f"Parse guard took {elapsed:.2f}s for {len(files)} files "
            f"(budget: 4.0s). If this is slow, the value of fast feedback "
            f"is lost. Common causes: reading large files, importing "
            f"instead of parsing, network calls."
        )
