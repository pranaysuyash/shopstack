#!/usr/bin/env python
"""Update stored benchmark baselines after intentional performance changes.

Usage:
    uv run pytest benchmarks/ --benchmark-autosave --no-header -q
    uv run python benchmarks/update_baselines.py

This reads the most recent pytest-benchmark autosave file and stores
the results as the new baseline. Commit the updated baseline files to git.
"""

from benchmarks.baselines import update_baselines_main

if __name__ == "__main__":
    update_baselines_main()
