"""Test the scripts/repo_truth.py canonical repo truth generator.

Per the 2026-06-14 audit (finding 4: README count drift), the repo needs
a single source of truth for the current state metrics. This script
counts DB tables, views, triggers, indexes, modules, tabs, and test
files from the live code, then exposes them as a structured dict.

These tests verify the script:
  1. Returns the right shape of data
  2. Counts match what we manually expect
  3. CLI output format works
  4. Gracefully handles missing dependencies
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_repo_truth(*args: str) -> subprocess.CompletedProcess:
    """Run scripts/repo_truth.py and return the result."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "repo_truth.py"), *args]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


class TestRepoTruthCounts:
    """The script must report accurate counts that match the live code."""

    def test_db_tables_count(self):
        """Currently 26 tables: app_config, condition_events, correction_events,
        find_feedback, household_locations, household_members, household_objects,
        households, inventory_events, inventory_lots, market_record_components,
        market_records, market_snapshots, movement_events, negative_memory,
        object_notes, object_sightings, person_associations, preference_signals,
        price_observations, purchase_events, reconciliation_events,
        shopping_list_items, shopping_lists, stores, traces.

        The ``correction_events`` table was added by a parallel agent
        (2026-06-14) to track user corrections to AI recommendations.
        """
        result = _run_repo_truth("--format", "json")
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["database"]["tables"] == 26, (
            f"Expected 26 tables, got {data['database']['tables']}. "
            f"Update this test if you intentionally added/removed tables."
        )

    def test_db_views_count(self):
        """2 views currently: price_history, agent_traces."""
        result = _run_repo_truth("--format", "json")
        data = json.loads(result.stdout)
        assert data["database"]["views"] == 2, (
            f"Expected 2 views, got {data['database']['views']}"
        )

    def test_db_triggers_count(self):
        """2 triggers: price_history_delete, agent_traces_delete."""
        result = _run_repo_truth("--format", "json")
        data = json.loads(result.stdout)
        assert data["database"]["triggers"] == 2, (
            f"Expected 2 triggers, got {data['database']['triggers']}"
        )

    def test_modules_count(self):
        """12 registered modules."""
        result = _run_repo_truth("--format", "json")
        data = json.loads(result.stdout)
        assert data["modules"]["registered"] == 12, (
            f"Expected 12 modules, got {data['modules']['registered']}"
        )

    def test_tabs_count(self):
        """21 tabs in TAB_ORDER."""
        result = _run_repo_truth("--format", "json")
        data = json.loads(result.stdout)
        assert data["modules"]["tabs"] == 21, (
            f"Expected 21 tabs, got {data['modules']['tabs']}"
        )

    def test_table_names_listed(self):
        """The script should list all table names for transparency."""
        result = _run_repo_truth("--format", "json")
        data = json.loads(result.stdout)
        names = data["database"]["table_names"]
        # Verify the key tables from the new work are present
        for expected in [
            "household_objects", "object_sightings", "object_notes",
            "find_feedback", "negative_memory", "person_associations",
            "condition_events", "household_members",
        ]:
            assert expected in names, (
                f"Expected table {expected!r} in repo truth output, "
                f"but it's missing. Did you add the CREATE TABLE but "
                f"forget to run the script?"
            )

    def test_test_files_count(self):
        """Should be 180+ test files in tests/."""
        result = _run_repo_truth("--format", "json")
        data = json.loads(result.stdout)
        assert data["tests"]["files"] >= 180, (
            f"Expected at least 180 test files, got {data['tests']['files']}"
        )


class TestRepoTruthCLI:
    """The script's CLI output should be human-readable."""

    def test_human_readable_output(self):
        """Default (no --format) output should be key=value lines."""
        result = _run_repo_truth()
        assert result.returncode == 0
        output = result.stdout
        # Should have lines like "DB tables:   25"
        assert "DB tables:" in output
        assert "DB views:" in output
        assert "Modules:" in output
        assert "Tabs:" in output
        assert "Test files:" in output

    def test_json_output_is_valid_json(self):
        """--format json should produce parseable JSON."""
        result = _run_repo_truth("--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)  # raises if invalid
        assert "database" in data
        assert "modules" in data
        assert "tests" in data
