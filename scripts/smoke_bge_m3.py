#!/usr/bin/env python3
"""BGE-M3 semantic search smoke test.

Verifies that BGE-M3 loads, embeds, and returns semantic matches
via ``ShopFindService.semantic_find_inventory_compatible()``.

Usage:
    uv run python scripts/smoke_bge_m3.py

Exit code: 0 if all checks pass, 1 if any failure.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    t0 = time.monotonic()
    passed = 0
    failed = 0

    def check(ok: bool, msg: str) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"  ✓  {msg}")
        else:
            failed += 1            # noqa: PLW2901
            print(f"  ✗  {msg}")

    # ── 1. Setup temp DB ────────────────────────────────────────────
    print("── BGE-M3 Smoke Test ──")
    print()

    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="bge_m3_smoke_")
    os.close(fd)
    print(f"  DB: {db_path}")

    from shopstack.persistence.database import Database
    db = Database(db_path)
    household = "hh_smoke"
    db.add_household(household, "Smoke Test HH")
    db.add_household_member(household, household, role="owner")

    # Seed diverse inventory across categories
    lots_data = [
        ("lot_milk",    "milk",      2.0, "L",   "fridge"),
        ("lot_rice",    "rice",      5.0, "kg",  "pantry"),
        ("lot_dal",     "dal",       1.0, "kg",  "pantry"),
        ("lot_eggs",    "eggs",     12.0, "unit","fridge"),
        ("lot_onion",   "onion",     2.0, "kg",  "pantry"),
        ("lot_tomato",  "tomato",    1.0, "kg",  "pantry"),
        ("lot_bread",   "bread",     1.0, "loaf","fridge"),
        ("lot_curd",    "curd",      0.5, "kg",  "fridge"),
        ("lot_potato",  "potato",    3.0, "kg",  "pantry"),
        ("lot_butter",  "butter",    0.25,"kg",  "fridge"),
    ]
    for lot_id, cname, qty, unit, loc in lots_data:
        db.conn.execute(
            "INSERT INTO inventory_lots "
            "(lot_id, canonical_name, display_name, quantity, unit, "
            " storage_location_id, status, user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (lot_id, cname, cname.capitalize(), qty, unit, loc, "active", household),
        )
    db.conn.commit()

    lots = db.get_inventory(user_id=household)
    check(len(lots) == len(lots_data), f"Seeded {len(lots)} inventory lots")

    # ── 2. Load BGE-M3 ──────────────────────────────────────────────
    print()
    from shopstack.providers.embeddings_provider import BGEM3EmbeddingProvider
    provider = BGEM3EmbeddingProvider()
    avail = provider.available
    check(avail, f"BGE-M3 available: {avail}")
    if not avail:
        print()
        print("  ⚠  BGE-M3 is not available (sentence-transformers missing?).")
        print("     Skipping embed & semantic-search checks.")
        print()

    # ── 3. Embed & similarity checks ────────────────────────────────
    if avail:
        queries = [
            ("milk",       2),   # exact match plus dairy neighbours
            ("eggs",       2),   # exact match
            ("rice",       2),   # exact match
            ("onion",      2),   # exact match
            ("coriander",  1),   # no lot, but weak semantic to onion/tomato
            ("doodh",      1),   # Hindi → English cross-language
            ("dahi",       1),   # Hindi → English (curd/yogurt)
            ("zzzzzdoesnotexist", 0),  # truly nonexistent → 0
        ]

        for query, min_results in queries:
            texts = [f"search_query: {query}"]
            emb = provider.embed(texts)[0]
            non_zero = any(v != 0.0 for v in emb)
            check(non_zero, f"embed('{query}'): dim={len(emb)}, has_non_zero={non_zero}")

        # ── 4. Semantic search via ShopFindService ───────────────────
        print()
        from shopstack.services.find import ShopFindService

        service = ShopFindService(db, embedding_provider=provider)

        test_cases: list[tuple[str, int]] = [
            ("milk",       1),
            ("eggs",       1),
            ("rice",       1),
            ("onion",      1),
            ("tomato",     1),
            ("doodh",      1),  # cross-language: Hindi milk
            ("dahi",       1),  # cross-language: Hindi curd
            ("zzzzzdoesnotexist", 0),  # nonsense query → 0 semantic matches
        ]

        print("  ── Semantic Search Results ──")
        for query, min_count in test_cases:
            result = service.semantic_find_inventory_compatible(query, user_id=household)
            results = result.get("results", [])
            match_type = result.get("match_type", "none")
            semantic_active = result.get("semantic_active", False)
            count = len(results)
            top_match = results[0].get("match_type", "none") if results else "none"
            top_score = results[0].get("confidence", 0.0) if results else 0.0
            top_title = (
                (results[0].get("lot", {}) or {}).get("display_name", "?")
                if results else "—"
            )
            ok = count >= min_count
            check(ok, f"  '{query}' → {count} result(s), match={top_match}, score={top_score:.2f}, top={top_title}")
            if not ok:
                print(f"           expected ≥ {min_count} results, got {count}")

        # ── 5. Cross-language Hindi → English ────────────────────────
        print()
        print("  ── Cross-Language Verification ──")
        hindi_pairs = [
            ("doodh", "milk"),
            ("dahi",  "curd"),
            ("chawal","rice"),
            ("aloo",  "potato"),
        ]
        for hindi_query, expected_en in hindi_pairs:
            result = service.semantic_find_inventory_compatible(hindi_query, user_id=household)
            results = result.get("results", [])
            titles = [
                ((r.get("lot", {}) or {}).get("canonical_name", "") or "").lower()
                for r in results
            ]
            found = expected_en in titles
            check(found, f"  '{hindi_query}' → found '{expected_en}' in: {titles[:3]}")

    # ── 6. Teardown ─────────────────────────────────────────────────
    db.close()
    for suffix in ("", "-wal", "-shm"):
        Path(db_path).with_suffix(Path(db_path).suffix + suffix).unlink(missing_ok=True)

    elapsed = time.monotonic() - t0
    print()
    print(f"  {'─' * 42}")
    print(f"  Results: {passed} passed, {failed} failed  ({elapsed:.1f}s)")
    print(f"  {'─' * 42}")
    print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
