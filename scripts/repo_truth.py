#!/usr/bin/env python3
"""Generate canonical repo truth numbers from the live codebase.

Outputs:
- DB table count
- DB view count
- DB trigger count
- DB index count
- Module count from module_registry
- Tab count from TAB_ORDER
- Service module count
- Test count from pytest collection

Usage:
    python3 scripts/repo_truth.py
    python3 scripts/repo_truth.py --format json

This script exists per motto_v3 §0.3 (documentation continuity) and
the 2026-06-14 audit recommendation. Run it to keep README.md and
docs/ in sync with the actual code state.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def count_db_tables() -> int:
    """Count CREATE TABLE IF NOT EXISTS statements in database.py."""
    db_file = REPO_ROOT / "shopstack" / "persistence" / "database.py"
    content = db_file.read_text(encoding="utf-8")
    return len(re.findall(r"CREATE TABLE\s+IF NOT EXISTS\s+\w+", content))


def count_db_views() -> int:
    """Count CREATE VIEW statements in database.py."""
    db_file = REPO_ROOT / "shopstack" / "persistence" / "database.py"
    content = db_file.read_text(encoding="utf-8")
    return len(re.findall(r"CREATE VIEW\s+IF NOT EXISTS\s+\w+", content))


def count_db_triggers() -> int:
    """Count CREATE TRIGGER statements in database.py."""
    db_file = REPO_ROOT / "shopstack" / "persistence" / "database.py"
    content = db_file.read_text(encoding="utf-8")
    return len(re.findall(r"CREATE TRIGGER\s+IF NOT EXISTS\s+\w+", content))


def count_db_indexes() -> int:
    """Count CREATE INDEX statements in database.py."""
    db_file = REPO_ROOT / "shopstack" / "persistence" / "database.py"
    content = db_file.read_text(encoding="utf-8")
    return len(re.findall(r"CREATE INDEX\s+IF NOT EXISTS\s+\w+", content))


def list_table_names() -> list[str]:
    """List all DB table names."""
    db_file = REPO_ROOT / "shopstack" / "persistence" / "database.py"
    content = db_file.read_text(encoding="utf-8")
    return sorted(re.findall(r"CREATE TABLE\s+IF NOT EXISTS\s+(\w+)", content))


def count_modules() -> int:
    """Count registered modules in module_registry."""
    try:
        from shopstack.module_registry import get_all
        return len(get_all())
    except Exception:
        return -1


def count_tabs() -> int:
    """Count tabs in TAB_ORDER."""
    try:
        from shopstack.module_registry import TAB_ORDER
        return len(TAB_ORDER)
    except Exception:
        return -1


def count_test_files() -> int:
    """Count test files in tests/."""
    tests_dir = REPO_ROOT / "tests"
    return sum(1 for p in tests_dir.glob("test_*.py") if p.is_file())


def collect_pytest_output() -> dict[str, int | str]:
    """Run pytest --collect-only and parse the summary line."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "--collect-only", "-q"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        # Look for "N tests collected" or similar
        m = re.search(r"(\d+)\s+tests?\s+collected", output)
        if m:
            return {"tests_collected": int(m.group(1))}
    except Exception as e:
        return {"error": str(e)}
    return {}


def main() -> int:
    tables = list_table_names()
    truth = {
        "database": {
            "tables": count_db_tables(),
            "views": count_db_views(),
            "triggers": count_db_triggers(),
            "indexes": count_db_indexes(),
            "table_names": tables,
        },
        "modules": {
            "registered": count_modules(),
            "tabs": count_tabs(),
        },
        "tests": {
            "files": count_test_files(),
            **collect_pytest_output(),
        },
    }

    if "--format" in sys.argv and "json" in sys.argv:
        print(json.dumps(truth, indent=2))
    else:
        print(f"DB tables:   {truth['database']['tables']}")
        print(f"DB views:    {truth['database']['views']}")
        print(f"DB triggers: {truth['database']['triggers']}")
        print(f"DB indexes:  {truth['database']['indexes']}")
        print(f"Modules:     {truth['modules']['registered']}")
        print(f"Tabs:        {truth['modules']['tabs']}")
        print(f"Test files:  {truth['tests']['files']}")
        if "tests_collected" in truth["tests"]:
            print(f"Tests collected: {truth['tests']['tests_collected']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
