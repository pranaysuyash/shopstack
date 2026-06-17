"""Baseline storage and comparison for CI-compatible performance regression detection.

Usage
-----

**Run benchmarks and compare against baselines (CI mode):**

    uv run pytest benchmarks/ --ci-benchmarks

**Update baselines after intentional performance changes:**

    uv run python benchmarks/update_baselines.py

Design
------

* Baseline files are stored in ``benchmarks/.baselines/`` as one JSON file per
  benchmark group (``db.json``, ``services.json``, ``portability.json``).
* Each entry records: ``mean``, ``stddev``, ``min``, ``max``, ``median``,
  ``rounds``, ``timestamp``, ``commit``.
* Tolerance is an integer percentage (default 100% = 2.0x the baseline mean).
  A test whose mean exceeds ``baseline_mean * (1 + tolerance_pct / 100)`` fails.
* Groups can override tolerance via ``_GROUP_TOLERANCE`` (e.g. services with
  higher variance get 150% tolerance).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────

_BENCHMARKS_DIR = Path(__file__).resolve().parent
_BASELINES_DIR = _BENCHMARKS_DIR / ".baselines"

#: Per-group tolerance multipliers (as percentage above baseline mean).
#: A test in group "services" is allowed to be up to 150% slower than
#: its baseline mean before failing.
_GROUP_TOLERANCE: dict[str, int] = {
    "db": 100,          # 2.0x — tight for simple DB ops
    "services": 150,    # 2.5x — higher variance from real data
    "portability": 150, # 2.5x — import/export depends on data size
}

#: Default tolerance when no group override exists.
_DEFAULT_TOLERANCE_PCT: int = 100  # 2.0x


# ── Data classes ─────────────────────────────────────────────────────────


class BaselineEntry:
    """A single benchmark's baseline measurement."""

    __slots__ = (
        "mean", "stddev", "min", "max", "median", "rounds",
        "timestamp", "commit",
    )

    def __init__(
        self,
        mean: float,
        stddev: float = 0.0,
        min: float = 0.0,
        max: float = 0.0,
        median: float = 0.0,
        rounds: int = 1,
        timestamp: str = "",
        commit: str = "",
    ) -> None:
        self.mean = mean
        self.stddev = stddev
        self.min = min
        self.max = max
        self.median = median
        self.rounds = rounds
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.commit = commit or _get_git_commit()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "stddev": self.stddev,
            "min": self.min,
            "max": self.max,
            "median": self.median,
            "rounds": self.rounds,
            "timestamp": self.timestamp,
            "commit": self.commit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BaselineEntry:
        return cls(
            mean=d["mean"],
            stddev=d.get("stddev", 0.0),
            min=d.get("min", 0.0),
            max=d.get("max", 0.0),
            median=d.get("median", 0.0),
            rounds=d.get("rounds", 1),
            timestamp=d.get("timestamp", ""),
            commit=d.get("commit", ""),
        )


# ── Git helper ───────────────────────────────────────────────────────────


def _get_git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_BENCHMARKS_DIR,
        ).stdout.strip()
    except Exception:
        return "unknown"


# ── Baseline store ───────────────────────────────────────────────────────


class BaselineStore:
    """Persistent storage and comparison for benchmark baselines.

    Baselines are stored as one JSON file per group in
    ``benchmarks/.baselines/``.
    """

    def __init__(self, baselines_dir: str | Path | None = None) -> None:
        self._baselines_dir = Path(baselines_dir) if baselines_dir else _BASELINES_DIR
        self._baselines_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, BaselineEntry]] = {}

    # ── Path helpers ─────────────────────────────────────────────────

    def _group_path(self, group: str) -> Path:
        return self._baselines_dir / f"{group}.json"

    # ── Read ─────────────────────────────────────────────────────────

    def load_group(self, group: str) -> dict[str, BaselineEntry]:
        """Load all baselines for a group. Returns ``{test_name: entry}``."""
        if group in self._cache:
            return self._cache[group]

        path = self._group_path(group)
        if not path.exists():
            self._cache[group] = {}
            return {}

        try:
            with open(path) as f:
                raw = json.load(f)
            entries = {name: BaselineEntry.from_dict(data) for name, data in raw.items()}
            self._cache[group] = entries
            return entries
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to load baselines for group %s: %s", group, exc)
            self._cache[group] = {}
            return {}

    # ── Write ────────────────────────────────────────────────────────

    def save_group(self, group: str, entries: dict[str, BaselineEntry]) -> None:
        """Save baselines for a group."""
        path = self._group_path(group)
        raw = {name: e.to_dict() for name, e in entries.items()}
        with open(path, "w") as f:
            json.dump(raw, f, indent=2)
        self._cache[group] = entries
        logger.info(
            "Saved %d baselines for group '%s' to %s",
            len(entries), group, path,
        )

    def update_from_results(
        self,
        results: dict[str, dict[str, Any]],
        groups: set[str] | None = None,
    ) -> int:
        """Update baselines from pytest-benchmark results dict.

        Args:
            results: Dict mapping test_name → stats dict (as produced by
                ``pytest_benchmark_generate_json`` hook).
            groups: If provided, only update baselines for these groups.
                Otherwise update all encountered groups.

        Returns:
            Number of baseline entries updated.
        """
        by_group: dict[str, dict[str, BaselineEntry]] = {}
        for test_name, stats in results.items():
            group = stats.get("group", "default")
            if groups is not None and group not in groups:
                continue
            entry = BaselineEntry(
                mean=stats["mean"],
                stddev=stats.get("stddev", 0.0),
                min=stats.get("min", 0.0),
                max=stats.get("max", 0.0),
                median=stats.get("median", 0.0),
                rounds=stats.get("rounds", 1),
            )
            by_group.setdefault(group, {})[test_name] = entry

        for group, entries in by_group.items():
            self.save_group(group, entries)

        return sum(len(e) for e in by_group.values())

    # ── Comparison ──────────────────────────────────────────────────

    def compare(
        self,
        results: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Compare benchmark results against stored baselines.

        Args:
            results: Dict mapping test_name → stats dict (as produced by
                ``pytest_benchmark_generate_json`` hook).

        Returns:
            List of result dicts, one per benchmark test. Each result has:
            - ``name``: test name
            - ``group``: benchmark group
            - ``baseline_mean``: stored baseline mean (or None if no baseline)
            - ``current_mean``: measured mean
            - ``ratio``: current_mean / baseline_mean (or None)
            - ``tolerance_pct``: allowed percentage above baseline
            - ``passed``: True if within tolerance or no baseline exists
            - ``message``: human-readable status
        """
        comparisons: list[dict[str, Any]] = []

        for test_name, stats in results.items():
            group = stats.get("group", "default")
            current_mean = stats["mean"]

            baselines = self.load_group(group)
            baseline = baselines.get(test_name)

            tolerance_pct = _GROUP_TOLERANCE.get(group, _DEFAULT_TOLERANCE_PCT)

            if baseline is None:
                comparisons.append({
                    "name": test_name,
                    "group": group,
                    "baseline_mean": None,
                    "current_mean": current_mean,
                    "ratio": None,
                    "tolerance_pct": tolerance_pct,
                    "passed": True,
                    "message": (
                        f"NO BASELINE — current mean={_fmt_us(current_mean)}. "
                        f"Run --update-benchmarks to record."
                    ),
                })
                continue

            ratio = current_mean / max(baseline.mean, 1e-12)
            max_allowed = baseline.mean * (1.0 + tolerance_pct / 100.0)
            passed = current_mean <= max_allowed

            if passed:
                comparisons.append({
                    "name": test_name,
                    "group": group,
                    "baseline_mean": baseline.mean,
                    "current_mean": current_mean,
                    "ratio": ratio,
                    "tolerance_pct": tolerance_pct,
                    "passed": True,
                    "message": (
                        f"OK — {_fmt_us(current_mean)} vs baseline "
                        f"{_fmt_us(baseline.mean)} "
                        f"({ratio:.2f}x, tolerance {tolerance_pct}%)"
                    ),
                })
            else:
                comparisons.append({
                    "name": test_name,
                    "group": group,
                    "baseline_mean": baseline.mean,
                    "current_mean": current_mean,
                    "ratio": ratio,
                    "tolerance_pct": tolerance_pct,
                    "passed": False,
                    "message": (
                        f"REGRESSION — {_fmt_us(current_mean)} exceeds baseline "
                        f"{_fmt_us(baseline.mean)} by {ratio:.2f}x "
                        f"(tolerance {tolerance_pct}%)"
                    ),
                })

        return comparisons

    def report(self, comparisons: list[dict[str, Any]]) -> tuple[int, int]:
        """Print a human-readable comparison report.

        Returns ``(passed, failed)`` counts.
        """
        passed = sum(1 for c in comparisons if c["passed"])
        failed = sum(1 for c in comparisons if not c["passed"])

        if not comparisons:
            print("  (no benchmark results to compare)")
            return 0, 0

        print(f"\n{'=' * 70}")
        print("PERFORMANCE REGRESSION REPORT")
        print(f"{'=' * 70}")

        for c in comparisons:
            status = "✓" if c["passed"] else "✗ FAIL"
            print(f"  [{status}] {c['name']:<45} {c['message']}")

        print(f"{'=' * 70}")
        print(f"  {passed} passed, {failed} failed out of {len(comparisons)} benchmarks")
        print(f"{'=' * 70}\n")

        return passed, failed


# ── Format helpers ───────────────────────────────────────────────────────


def _fmt_us(seconds: float) -> str:
    """Format a time in seconds to a human-readable string."""
    if seconds < 1e-6:
        return f"{seconds * 1e9:.1f}ns"
    if seconds < 1e-3:
        return f"{seconds * 1e6:.1f}µs"
    if seconds < 1.0:
        return f"{seconds * 1e3:.1f}ms"
    return f"{seconds:.3f}s"


# ── CLI: update baselines ────────────────────────────────────────────────


def _load_pytest_benchmark_results(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load the most recent pytest-benchmark autosave result file.

    Returns a dict mapping ``test_name → {mean, stddev, min, max, median,
    rounds, group}``.
    """
    path = Path(path)
    if not path.exists():
        logger.error("Results file not found: %s", path)
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    results: dict[str, dict[str, Any]] = {}
    for bench in data.get("benchmarks", []):
        # Use fullname to match conftest.py's key (avoids test-name collisions).
        fullname = bench.get("fullname", bench["name"])
        stats = bench["stats"]
        results[fullname] = {
            "mean": stats["mean"],
            "stddev": stats["stddev"],
            "min": stats["min"],
            "max": stats["max"],
            "median": stats["median"],
            "rounds": stats["rounds"],
            "group": bench.get("group", "default"),
        }

    return results


def _find_latest_benchmark_file(benchmarks_dir: str | Path) -> Path | None:
    """Find the most recent pytest-benchmark JSON file in .benchmarks/."""
    benchmarks_dir = Path(benchmarks_dir)
    if not benchmarks_dir.exists():
        return None

    json_files = sorted(benchmarks_dir.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return json_files[0] if json_files else None


def update_baselines_main() -> None:
    """CLI entry point for ``uv run python benchmarks/update_baselines.py``."""
    import argparse

    parser = argparse.ArgumentParser(description="Update benchmark baselines")
    parser.add_argument(
        "--results",
        type=str,
        default=None,
        help="Path to a pytest-benchmark JSON results file. "
             "If not provided, uses the most recent autosaved file.",
    )
    parser.add_argument(
        "--groups",
        type=str,
        nargs="*",
        default=None,
        help="Only update baselines for these groups (e.g. --groups db services).",
    )
    args = parser.parse_args()

    if args.results:
        results_path = Path(args.results)
    else:
        results_path = _find_latest_benchmark_file(_BENCHMARKS_DIR / ".benchmarks")
        if results_path is None:
            print(
                "No benchmark results found. Run benchmarks first:\n"
                "  uv run pytest benchmarks/ --benchmark-autosave --no-header -q\n"
            )
            sys.exit(1)

    print(f"Loading benchmark results from: {results_path}")
    results = _load_pytest_benchmark_results(results_path)
    print(f"Found {len(results)} benchmark results")

    groups_set = set(args.groups) if args.groups else None
    store = BaselineStore()
    n = store.update_from_results(results, groups=groups_set)
    print(f"Updated {n} baseline entries")

    # Print new baselines
    print(f"\n{'=' * 70}")
    print("NEW BASELINES")
    print(f"{'=' * 70}")
    for group_path in sorted(_BASELINES_DIR.glob("*.json")):
        group = group_path.stem
        baselines = store.load_group(group)
        if baselines:
            print(f"\n  Group: {group} ({len(baselines)} entries)")
            for name in sorted(baselines):
                entry = baselines[name]
                print(f"    {name:<50} {_fmt_us(entry.mean)} ({entry.rounds} rounds)")


if __name__ == "__main__":
    update_baselines_main()
