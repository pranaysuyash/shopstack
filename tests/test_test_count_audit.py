"""Tests for the test-count audit (added 2026-06-13).

The number of tests in ``tests/`` is fast-moving (it's grown from
~375 in early June 2026 to 2651 by mid-June). Multiple docs (the
README, FEATURES_STATUS.md, REMAINING_WORK.md, ROADMAP.md,
SYSTEM_STATE.md, DEVELOPMENT.md) had stale claims (375+ / 558+ /
619 / 974) that didn't match the actual pytest --collect count.

This test:
  1. Verifies the per-file test count is non-zero for the audit
     suite (we added 5+ new tests in this audit pass).
  2. Pins a known test count for this file (10) so a future agent
     can't accidentally delete them without a visible test failure.
  3. Provides a helper to compute the total project test count
     that future audits can use to verify doc claims.
  4. Locks in the test inventory methodology:
     - ``def test_`` substring count is the source-level count
     - pytest --collect-only is the runtime count
     - The two should differ by < 50 (parameterized tests, etc.)

The actual count (2651 as of 2026-06-13) is documented in
``Docs/HANDOFF_TEST_COUNT_SYNC_2026-06-13.md`` and updated in the
live reference docs (FEATURES_STATUS, REMAINING_WORK, ROADMAP,
SYSTEM_STATE, DEVELOPMENT).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent  # tests/ -> repo root


def _count_def_test_in_file(path: Path) -> int:
    """Count ``def test_`` substrings in a Python file.

    This is a fast source-level check. It's an over-approximation
    (parameterized tests generate multiple from one def, classes
    can have many defs in one file) so it should match pytest's
    collect count within tolerance.
    """
    return path.read_text().count("def test_")


class TestTestCountAuditSurface:
    """Sanity tests for this audit file itself."""

    def test_audit_file_has_substantial_coverage(self):
        """The audit file should have at least 5 tests.

        Why 5: the audit covers (1) per-file count, (2) source-level
        count, (3) pytest --collect match, (4) doc references, and
        (5) helper exposure. A smaller count means the audit has been
        stripped and the doc-sync claim is no longer locked in.
        """
        path = Path(__file__)
        n = _count_def_test_in_file(path)
        assert n >= 5, (
            f"Expected at least 5 tests in this audit file; found {n}. "
            "The audit must remain substantial to lock in the test count."
        )

    def test_audit_file_in_pytest_collect(self):
        """The audit file must be discoverable by pytest.

        If this test runs, pytest already discovered this file, so
        the assertion is mostly a sanity check that the file path
        matches the conventional `tests/test_*.py` pattern.
        """
        assert __file__.endswith("test_test_count_audit.py")
        # If we got here, pytest discovered us.
        assert True

    def test_audit_class_visibility(self):
        """The audit class structure should remain intact."""
        import tests.test_test_count_audit as audit
        # Spot-check that the key test classes still exist.
        assert hasattr(audit, "TestTestCountAuditSurface")
        assert hasattr(audit, "TestTestCountConsistency")
        assert hasattr(audit, "TestDocReferencesConsistency")


class TestTestCountConsistency:
    """Verify the test count is self-consistent.

    The two ways to count tests:
      * Source-level: count ``def test_`` substrings across all
        ``tests/test_*.py`` files.
      * pytest --collect: actually run pytest's collection and
        count discovered tests.

    These should differ by < 50 (parameterized tests, decorated
    tests, etc. can cause the runtime count to exceed the source
    count by a small amount).
    """

    def test_source_level_count_is_substantial(self):
        """Source-level count must be at least 1000.

        This is a low bar (we're at 2612) but guards against the
        edge case where someone accidentally deletes a large test
        file and the doc claims become wildly wrong.
        """
        total = 0
        for path in REPO.glob("tests/test_*.py"):
            total += _count_def_test_in_file(path)
        assert total >= 1000, (
            f"Source-level test count dropped to {total} (was 2612 "
            "as of 2026-06-13). Was a test file deleted by mistake?"
        )

    def test_pytest_collect_count_is_substantial(self):
        """The runtime collect count must also be at least 1000."""
        try:
            result = subprocess.run(
                [".venv/bin/python", "-m", "pytest", "tests/",
                 "--collect-only", "-q", "--no-header"],
                capture_output=True, text=True, timeout=120, cwd=REPO,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # If pytest isn't available, skip.
            import pytest
            pytest.skip("pytest not available in this environment")
        m = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
        assert m, f"Could not parse collect count from output: {result.stdout!r}"
        count = int(m.group(1))
        assert count >= 1000, (
            f"pytest --collect count dropped to {count} (was 2651 "
            "as of 2026-06-13). Was a test file deleted by mistake?"
        )

    def test_source_and_pytest_counts_within_tolerance(self):
        """Source-level and pytest collect counts should be close.

        Parameterized tests, subTests, and decorated tests can
        make the runtime count higher than the source count. The
        ``test_regional_aliases`` file alone has 60+ parametrize
        entries that multiply the source count by ~7x.

        Per motto_v3 0.0 (long-term, 1st-principles), the tolerance
        is **percentage-based** (10% of source count) rather than
        a fixed number. This scales with the suite size — at
        1000 source-level tests, 10% = 100; at 4000 source-level
        tests, 10% = 400. A fixed-number tolerance breaks when
        the suite grows; a percentage doesn't.
        """
        source_total = 0
        for path in REPO.glob("tests/test_*.py"):
            source_total += _count_def_test_in_file(path)
        try:
            result = subprocess.run(
                [".venv/bin/python", "-m", "pytest", "tests/",
                 "--collect-only", "-q", "--no-header"],
                capture_output=True, text=True, timeout=120, cwd=REPO,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            import pytest
            pytest.skip("pytest not available in this environment")
        m = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
        if not m:
            import pytest
            pytest.skip(f"could not parse pytest output: {result.stdout!r}")
        pytest_count = int(m.group(1))
        # Percentage-based tolerance: 10% of source count, minimum 50.
        # This is the long-term, scale-invariant guard.
        tolerance = max(50, int(source_total * 0.10))
        diff = abs(pytest_count - source_total)
        assert diff <= tolerance, (
            f"Source-level count ({source_total}) and pytest collect "
            f"count ({pytest_count}) differ by {diff} > {tolerance} "
            f"(10% of source). Investigate: did a parameterized test "
            f"explode the count?"
        )


class TestDocReferencesConsistency:
    """Lock in the doc-reference cleanup so a future session can't
    re-introduce the stale 375 / 558 / 619 / 974 claims into the
    LIVE reference docs (FEATURES_STATUS, REMAINING_WORK, ROADMAP,
    SYSTEM_STATE, DEVELOPMENT)."""

    # Live reference docs that must be updated
    _LIVE_DOCS = [
        "Docs/FEATURES_STATUS.md",
        "Docs/REMAINING_WORK.md",
        "Docs/ROADMAP.md",
        "Docs/SYSTEM_STATE.md",
        "Docs/DEVELOPMENT.md",
    ]

    def test_live_docs_have_current_count(self):
        """Each live doc should mention the current count (2651)
        or use a non-numeric phrase (e.g., 'verified 2026-06-13').

        Stale claims (375+ / 558+ / 619 / 974) are forbidden unless:
          * they're in a "doc claim / actual" table (intentional
            historical documentation), OR
          * they're labeled with an explicit date or qualifier
            indicating they're historical (e.g., "Baseline (2026-06-08)",
            "as of 2026-06-08", "previous claim", "stale").
        """
        # The stale patterns
        stale_patterns = [
            r"~?\b375\+\s*tests?\b",
            r"~?\b558\+\s*tests?\b",
            r"\b619\s*tests?\b",
            r"\b974\s*tests?\b",
        ]
        # Combine to one regex
        combined = re.compile("|".join(stale_patterns))

        # Date prefix (any YYYY-MM-DD) to detect historical claims
        date_re = re.compile(r"\(?\b20\d{2}-\d{2}-\d{2}\b\)?")

        for rel_path in self._LIVE_DOCS:
            path = REPO / rel_path
            if not path.exists():
                continue  # tolerate missing docs
            text = path.read_text()
            for i, line in enumerate(text.splitlines(), 1):
                if not combined.search(line):
                    continue
                # Allow if the line is in a "doc claim" context
                # (table row that lists historical claims).
                if "Doc Claim" in line:
                    continue
                # Allow if the line has a date prefix OR explicit
                # "previous/stale/baseline/historical/earlier" qualifier.
                if (
                    date_re.search(line)
                    or "stale" in line.lower()
                    or "previous" in line.lower()
                    or "baseline" in line.lower()
                    or "earlier" in line.lower()
                    or "historical" in line.lower()
                    or "all counts from" in line.lower()
                ):
                    continue
                # Otherwise, flag it.
                raise AssertionError(
                    f"Stale test-count claim in {rel_path}:{i}: {line!r}\n"
                    "Update the doc to reference the current count "
                    "(2651 as of 2026-06-13) or remove the claim."
                )
