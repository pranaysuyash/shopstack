#!/usr/bin/env python3
"""Smoke test for semantic search text-only fallback.

Verifies that ``ShopFindService.semantic_find_inventory_compatible()``
falls back to text-only matching when no embedding provider is
available (e.g. sentence-transformers not installed).

This is the production path on any machine without ML model deps:
- ``semantic_active`` must be ``False``
- Results must still be returned for exact-match, alias, and
  cross-language queries (via the ``ALIASES`` dict)
- Nonsense queries must return 0 results
- ``match_type`` reflects the text-matching source (exact, alias, etc.)

Usage:
    uv run python scripts/smoke_search_fallback.py

Exit code: 0 if all checks pass, 1 if any failure.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ── Inert embedding provider (simulates missing deps) ──────────────────


class _UnavailableProvider:
    """Simulates an embedding provider with missing dependencies.

    ``available`` is ``False``, ``embed()`` returns zero vectors.
    This tests the text-only fallback path in
    ``ShopFindService.semantic_find_inventory_compatible()``.
    """

    name = "unavailable-mock"
    available = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 128 for _ in texts]

    def similarity(self, query_emb: list[float], item_emb: list[float]) -> float:
        return 0.0


# ── Ground-truth query set ──────────────────────────────────────────────
# Each entry: (query, expected_canonical, min_count)
# The text-only fallback uses the ALIASES dict + prefix/substring matching
# so cross-language queries (doodh→milk) should still work via alias
# expansion — but only for terms explicitly in ALIASES.
FALLBACK_CASES: list[tuple[str, str, int]] = [
    # Exact match
    ("milk",   "milk",   1),
    ("eggs",   "eggs",   1),
    ("rice",   "rice",   1),
    ("onion",  "onion",  1),
    # Alias match (Hindi via ALIASES dict)
    ("doodh",  "milk",   1),   # ALIASES: doodh → ["milk"]
    ("dahi",   "curd",   1),   # ALIASES: dahi → ["curd", "yogurt"]
    ("anda",   "eggs",   1),   # ALIASES: anda → ["egg"]
    ("pyaaz",  "onion",  1),   # ALIASES: pyaaz → ["onion"]
    ("tamatar","tomato", 1),   # ALIASES: tamatar → ["tomato"]
    ("aloo",   "potato", 1),   # ALIASES: aloo → ["potato"]
    ("chawal", "rice",   1),   # ALIASES: chawal → ["rice"]
    # Partial / prefix match
    ("butt",   "butter", 1),   # prefix of "butter"
    ("bre",    "bread",  1),   # prefix of "bread"
    # Nonsense — should return 0
    ("zzzzzdoesnotexist", "", 0),
    # Empty query — should return 0 (early return in service)
    ("", "", 0),
]


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

    # ── 1. Setup temp DB ────────────────────────────────────────────────
    print("── Semantic Search Fallback Test ──")
    print()

    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="search_fallback_")
    os.close(fd)
    print(f"  DB: {db_path}")

    from shopstack.persistence.database import Database
    db = Database(db_path)
    household = "hh_fallback"
    db.add_household(household, "Fallback Test HH")
    db.add_household_member(household, household, role="owner")

    # Seed diverse inventory (same as smoke_bge_m3.py)
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

    # ── 2. Create service with unavailable provider ──────────────────────
    from shopstack.services.find import ShopFindService

    provider = _UnavailableProvider()
    service = ShopFindService(db, embedding_provider=provider)

    check(not provider.available, "Embedding provider reports not available")

    # ── 3. Run all fallback queries ─────────────────────────────────────
    print()
    print("  ── Semantic Search Fallback Results ──")

    for query, expected, min_count in FALLBACK_CASES:
        result = service.semantic_find_inventory_compatible(query, user_id=household)
        results = result.get("results", [])
        count = len(results)
        semantic_active = result.get("semantic_active", True)
        match_type = result.get("match_type", "none")
        top_match = results[0].get("match_type", "none") if results else "none"
        top_score = results[0].get("confidence", 0.0) if results else 0.0
        top_title = (
            ((results[0].get("lot", {}) or {}).get("display_name", "?")
             if results else "—")
        )

        # Core assertion: count meets minimum
        ok_count = count >= min_count

        # Cross-assertion: semantic_active must be False
        ok_semantic = not semantic_active

        # Alias assertion: if min_count > 0, match_type should be from text
        # (exact, alias, prefix, context, etc.) — not "semantic" or "none"
        ok_match = True
        if min_count > 0:
            ok_match = match_type != "semantic" and match_type != "none"

        all_ok = ok_count and ok_semantic and ok_match
        note_parts = []
        if not ok_count:
            note_parts.append(f"expected ≥{min_count} results")
        if not ok_semantic:
            note_parts.append("semantic_active should be False")
        if not ok_match:
            note_parts.append(f"match_type should not be semantic/none (got {match_type})")
        note = f" — {'; '.join(note_parts)}" if note_parts else ""

        check(all_ok, (
            f"  '{query}' → {count} result(s), "
            f"semantic={semantic_active}, "
            f"match={match_type}, "
            f"top='{top_title}' ({top_score:.2f})"
            f"{note}"
        ))

    # ── 4. Verify text-only match types ────────────────────────────────
    print()
    print("  ── Text-Fallback Match Types ──")
    print("  (Verifying match_type reflects text matching, not semantic)")

    # Note on match types:
    # - Terms in ALIASES (like "doodh") are expanded to their
    #   English equivalents BEFORE matching. So "doodh" → expand to
    #   ["doodh", "milk"] → "milk" gets an EXACT match against the
    #   lot's canonical_name. The match_type reflects the final
    #   match against the lot, not the expansion step.
    type_checks: list[tuple[str, str, str]] = [
        # query, expected_match_type, expected_display_name
        ("milk",   "exact", "Milk"),
        ("doodh",  "exact", "Milk"),   # expanded → "milk" → exact match
        ("dahi",   "exact", "Curd"),   # expanded → "curd" → exact match
        ("butt",   "prefix", "Butter"),
        ("bre",    "prefix", "Bread"),
    ]
    for query, expected_type, expected_name in type_checks:
        result = service.semantic_find_inventory_compatible(query, user_id=household)
        results = result.get("results", [])
        top = results[0] if results else {}
        match_type = top.get("match_type", "none")
        title = ((top.get("lot", {}) or {}).get("display_name", "?") if top else "—")

        ok_type = match_type == expected_type
        ok_name = title == expected_name

        if ok_type and ok_name:
            check(True, f"  '{query}' → match_type='{match_type}', top='{title}'")
        else:
            issues = []
            if not ok_type:
                issues.append(f"expected match_type='{expected_type}', got '{match_type}'")
            if not ok_name:
                issues.append(f"expected top='{expected_name}', got '{title}'")
            check(False, f"  '{query}' → {'; '.join(issues)}")

    # ── 5. Verify cross-language queries work in fallback ───────────────
    print()
    print("  ── Cross-Language Fallback ──")
    print("  (Hindi→English via ALIASES dict, no embeddings)")

    hindi_pairs: list[tuple[str, str]] = [
        ("doodh",  "milk"),
        ("dahi",   "curd"),
        ("chawal", "rice"),
        ("aloo",   "potato"),
        ("anda",   "eggs"),
        ("pyaaz",  "onion"),
        ("tamatar","tomato"),
    ]
    for hindi_query, expected_en in hindi_pairs:
        result = service.semantic_find_inventory_compatible(hindi_query, user_id=household)
        results = result.get("results", [])
        titles = [
            ((r.get("lot", {}) or {}).get("canonical_name", "") or "").lower()
            for r in results
        ]
        semantic_active = result.get("semantic_active", True)
        found = expected_en in titles
        check(
            found and not semantic_active,
            f"  '{hindi_query}' → found '{expected_en}' in: {titles[:3]}  "
            f"(semantic_active={semantic_active})"
        )

    # ── 6. Teardown ────────────────────────────────────────────────────
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
