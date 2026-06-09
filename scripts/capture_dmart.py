#!/usr/bin/env python3
"""DMart market snapshot capture script.

Captures fresh vegetable pricing data from DMart by loading existing
snapshot files from the data/ directory. Full automated web capture
requires Playwright-based scraping (not included in this script).

Usage:
    uv run python scripts/capture_dmart.py           # Show latest snapshot info
    uv run python scripts/capture_dmart.py --list     # List all available snapshots

Snapshot format (expected):
    data/dmart_fresh_vegetables_<date>.json

Expected JSON schema:
    [
        {
            "product": "Fresh Tomato",
            "size": "500 g",
            "current_price": 24.0,
            "listed_price": 34.0,
            "discount_percent": 29,
            "availability": "available",
            "brand": "",
            "delivery_time": "",
            "tag": "",
            "card_index": 0
        },
        ...
    ]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def find_snapshots() -> list[Path]:
    return sorted(DATA_DIR.glob("dmart_fresh_vegetables_*.json"))


def show_latest() -> None:
    snapshots = find_snapshots()
    if not snapshots:
        print("No DMart snapshots found in data/.")
        print(f"Expected: {DATA_DIR}/dmart_fresh_vegetables_*.json")
        print()
        print("To capture a fresh snapshot:")
        print("  1. Visit https://www.dmart.in/cn/fresh-vegetables/")
        print("  2. Save the product cards as JSON")
        print(f"  3. Place in {DATA_DIR}/")
        return

    latest = snapshots[-1]
    print(f"Latest DMart snapshot: {latest.name}")
    print(f"  Path: {latest}")
    print(f"  Size: {latest.stat().st_size:,} bytes")

    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        print(f"  Records: {len(data)}")
        if data:
            sample = data[0]
            print(f"  Sample keys: {list(sample.keys())}")
    except Exception as e:
        print(f"  Error reading: {e}")


def list_all() -> None:
    snapshots = find_snapshots()
    if not snapshots:
        print("No DMart snapshots found.")
        return
    print(f"Found {len(snapshots)} DMart snapshot(s):")
    for s in snapshots:
        try:
            data = json.loads(s.read_text(encoding="utf-8"))
            print(f"  {s.name} — {len(data)} records")
        except Exception:
            print(f"  {s.name} — (unreadable)")


def main() -> None:
    if "--list" in sys.argv:
        list_all()
    else:
        show_latest()


if __name__ == "__main__":
    main()
