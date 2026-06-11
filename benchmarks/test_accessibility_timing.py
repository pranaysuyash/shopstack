"""Timing benchmarks for the accessibility test suite.

Measures collection and total execution wall-clock time for
``tests/test_accessibility_components.py``. Each measurement runs
pytest as a subprocess — these are coarse regression detectors,
not micro-benchmarks.

Uses manual ``time.perf_counter()`` timing (not pytest-benchmark's
``benchmark`` fixture) because the subprocess per run is too expensive
for the multiple rounds pytest-benchmark would need (default min_rounds=5).
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.benchmark(group="accessibility_timing")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Base pytest args shared by both collection and execution runs.
_PYTEST_ARGS = [
    "tests/test_accessibility_components.py",
    "-q",
    "--tb=short",
    "-p", "no:cacheprovider",
]

# ── Helpers ───────────────────────────────────────────────────────────────


def _parse_pytest_summary(stdout: str) -> dict[str, int]:
    """Parse the summary line from ``pytest -q`` output.

    Example input line::

        147 passed, 2 warnings in 18.61s

    Returns ``{"passed": …, "failed": …}``.  If no summary line is
    found, ``failed`` is set to ``-1`` to distinguish from a clean
    zero-failure run.
    """
    for line in stdout.splitlines():
        m = re.search(r"(\d+)\s+passed", line)
        if m:
            passed = int(m.group(1))
            failed = 0
            fm = re.search(r"(\d+)\s+failed", line)
            if fm:
                failed = int(fm.group(1))
            return {"passed": passed, "failed": failed}
    return {"passed": 0, "failed": -1}


# ── Measurement tests ─────────────────────────────────────────────────────


class TestAccessibilityCollectionTime:
    """Measure pytest collection (import) time for the accessibility tests.

    Collection exercises the full ``shopstack.ui`` import chain end-to-end:
    every screen module, component, renderer, and service module must be
    imported and registered.  A regression here typically means a new
    circular import, an unexpectedly heavy transitive dependency, or a
    change in the test discovery pattern.
    """

    def test_collection_time(self) -> None:
        """Collect-only wall-clock time should be <30s."""
        start = time.perf_counter()
        result = subprocess.run(
            ["uv", "run", "pytest", *_PYTEST_ARGS, "--collect-only"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        elapsed = time.perf_counter() - start

        assert result.returncode == 0, (
            f"pytest --collect-only failed:\n{result.stderr[:500]}"
        )
        assert elapsed < 30.0, (
            f"Collection took {elapsed:.2f}s — expected <30s. "
            "This may indicate a new circular import or heavy transitive dependency."
        )

        summary = _parse_pytest_summary(result.stdout)
        assert summary["passed"] >= 140, (
            f"Expected ≥140 tests, got {summary['passed']}. "
            f"Output preview:\n{result.stdout[:500]}"
        )
        assert summary["failed"] not in (-1,), (
            f"Could not parse test count from --collect-only output. "
            f"Full stdout:\n{result.stdout}"
        )


class TestAccessibilityTotalTime:
    """Measure total (collection + execution) wall-clock time for all 147+
    accessibility tests.

    This is the primary regression detector: any change that slows down
    the full test run (new imports, slower renderers, larger test data)
    will cause this benchmark to fail.
    """

    def test_total_time(self) -> None:
        """Full test-suite wall-clock time should be <45s."""
        start = time.perf_counter()
        result = subprocess.run(
            ["uv", "run", "pytest", *_PYTEST_ARGS],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        elapsed = time.perf_counter() - start

        # Parse summary *before* the assertion so we can report both
        # timing and pass/fail in a single error message.
        summary = _parse_pytest_summary(result.stdout)

        assert result.returncode == 0, (
            f"pytest run failed (exit {result.returncode}):\n"
            f"{result.stderr[:500]}"
        )
        assert elapsed < 45.0, (
            f"Total test time {elapsed:.2f}s exceeds 45s threshold. "
            "This may indicate a performance regression in the import chain "
            "or test execution."
        )
        assert summary["passed"] >= 140, (
            f"Expected ≥140 passed, got {summary['passed']}. "
            f"Output preview:\n{result.stdout[:500]}"
        )
        assert summary["failed"] == 0, (
            f"Expected 0 failures, got {summary['failed']}. "
            "All accessibility tests must pass before timing is meaningful."
        )
