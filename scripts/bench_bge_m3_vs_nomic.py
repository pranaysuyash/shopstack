#!/usr/bin/env python3
"""Benchmark comparison between BGE-M3 and Nomic embedding providers.

Measures:
- Embedding dimension
- Embed latency per query (average, min, max)
- Top-1 accuracy: does the ground-truth item appear in top semantic results?
- Cross-language (Hindi→English) retrieval accuracy

Usage:
    uv run python scripts/bench_bge_m3_vs_nomic.py

Exit code: 0 if both providers are benchmarked successfully, 1 if any error.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ── Ground-truth query set ──────────────────────────────────────────────
# Each entry: (query, expected_canonical_name, category)
QUERIES: list[tuple[str, str, str]] = [
    # English exact-match queries
    ("milk",   "milk",   "english"),
    ("rice",   "rice",   "english"),
    ("eggs",   "eggs",   "english"),
    ("onion",  "onion",  "english"),
    ("tomato", "tomato", "english"),
    ("potato", "potato", "english"),
    ("curd",   "curd",   "english"),
    ("butter", "butter", "english"),
    ("bread",  "bread",  "english"),
    ("dal",    "dal",    "english"),
    # Cross-language Hindi → English
    ("doodh",   "milk",   "hindi"),
    ("dahi",    "curd",   "hindi"),
    ("chawal",  "rice",   "hindi"),
    ("aloo",    "potato", "hindi"),
    ("anda",    "eggs",   "hindi"),
    ("pyaaz",   "onion",  "hindi"),
    ("tamatar", "tomato", "hindi"),
]


def _seed_db(db_path: str) -> str:
    """Create and seed a temp DB. Returns the household ID."""
    from shopstack.persistence.database import Database

    db = Database(db_path)
    household = "hh_bench"
    db.add_household(household, "Benchmark HH")
    db.add_household_member(household, household, role="owner")

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
    db.close()
    return household


def _bench_provider(
    provider,
    provider_name: str,
    uses_query_prefix: bool,
    db_path: str,
    household: str,
    queries: list[tuple[str, str, str]],
) -> dict:
    """Run all benchmarks for a single provider.

    ``uses_query_prefix``: if True, embed with ``kind="query"`` (Nomic).
    If False, embed with a manual ``search_query:`` prefix (BGE-M3).

    Returns a dict with keys: dim, embed_latencies_ms, top1_accuracy,
    top1_by_category.
    """
    from shopstack.services.find import ShopFindService

    print(f"\n  ── {provider_name} ──")

    # ── Provider info ──────────────────────────────────────────────
    print(f"  Available:  {provider.available}")
    if not provider.available:
        return {
            "dim": 0,
            "embed_latencies_ms": [],
            "top1_accuracy": 0.0,
            "top1_by_category": {"english": 0.0, "hindi": 0.0},
            "available": False,
        }

    # ── Dimension ──────────────────────────────────────────────────
    test_texts = [f"search_query: {queries[0][0]}"]
    sample_emb = provider.embed(test_texts)[0] if not uses_query_prefix else provider.embed([queries[0][0]], kind="query")[0]
    dim = len(sample_emb)
    non_zero = any(v != 0.0 for v in sample_emb)
    print(f"  Dim:        {dim}  (non-zero: {non_zero})")

    # ── Embed latency ──────────────────────────────────────────────
    embed_latencies_ms: list[float] = []
    for q, _expected, _cat in queries:
        if uses_query_prefix:
            texts = [q]
            t0 = time.perf_counter()
            provider.embed(texts, kind="query")
        else:
            texts = [f"search_query: {q}"]
            t0 = time.perf_counter()
            provider.embed(texts)
        elapsed = time.perf_counter() - t0
        embed_latencies_ms.append(elapsed * 1000)

    avg_ms = sum(embed_latencies_ms) / len(embed_latencies_ms)
    min_ms = min(embed_latencies_ms)
    max_ms = max(embed_latencies_ms)
    print(f"  Embed lat:  {avg_ms:.2f}ms avg  ({min_ms:.2f}–{max_ms:.2f}ms)  ({len(embed_latencies_ms)} queries)")

    # ── Semantic search accuracy ───────────────────────────────────
    db = __import__("shopstack.persistence.database").persistence.database.Database(db_path)
    service = ShopFindService(db, embedding_provider=provider)

    correct = 0
    total = len(queries)
    correct_by_cat: dict[str, int] = {"english": 0, "hindi": 0}
    total_by_cat: dict[str, int] = {"english": 0, "hindi": 0}

    for query, expected, category in queries:
        total_by_cat[category] = total_by_cat.get(category, 0) + 1
        result = service.semantic_find_inventory_compatible(query, user_id=household)
        results = result.get("results", [])
        titles = [
            ((r.get("lot", {}) or {}).get("canonical_name", "") or "").lower()
            for r in results
        ]
        top_title = titles[0] if titles else "—"
        top_score = results[0].get("confidence", 0.0) if results else 0.0
        match_type = results[0].get("match_type", "none") if results else "none"

        if expected in titles:
            correct += 1
            correct_by_cat[category] = correct_by_cat.get(category, 0) + 1

        is_correct = expected in titles
        if not is_correct:
            print(f"    ✗  '{query}' → expected '{expected}', top='{top_title}' score={top_score:.2f} — {titles[:3]}")

    db.close()

    accuracy = correct / total * 100 if total > 0 else 0.0
    eng_acc = correct_by_cat.get("english", 0) / max(total_by_cat.get("english", 1), 1) * 100
    hin_acc = correct_by_cat.get("hindi", 0) / max(total_by_cat.get("hindi", 1), 1) * 100

    print(f"  Top-1 acc:  {accuracy:.0f}% ({correct}/{total})")
    print(f"    English:  {eng_acc:.0f}% ({correct_by_cat.get('english', 0)}/{total_by_cat.get('english', 1)})")
    print(f"    Hindi:    {hin_acc:.0f}% ({correct_by_cat.get('hindi', 0)}/{total_by_cat.get('hindi', 1)})")

    return {
        "dim": dim,
        "embed_latencies_ms": embed_latencies_ms,
        "top1_accuracy": accuracy,
        "top1_by_category": {"english": eng_acc, "hindi": hin_acc},
        "available": True,
    }


def _print_summary(results: dict[str, dict], bge_load_s: float, nomic_load_s: float) -> None:
    """Print a comparison table of both providers."""
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║                   BGE-M3  vs  Nomic                         ║")
    print("  ╠══════════════════════════════════════════════════════════════╣")
    print(f"  ║  {'Metric':<30} {'BGE-M3':<18} {'Nomic':<18}║")
    print("  ║  " + "─" * 66 + "║")

    bge = results.get("bge-m3", {})
    nomic = results.get("nomic", {})

    dim_bge = bge.get("dim", "n/a")
    dim_nomic = nomic.get("dim", "n/a")
    print(f"  ║  {'Embedding dim':<30} {str(dim_bge):<18} {str(dim_nomic):<18}║")
    print(f"  ║  {'Parameters (M)':<30} {'600':<18} {'137':<18}║")

    bge_avail = bge.get("available", False)
    nomic_avail = nomic.get("available", False)

    bge_lats = bge.get("embed_latencies_ms", [])
    nomic_lats = nomic.get("embed_latencies_ms", [])
    bge_avg = sum(bge_lats) / len(bge_lats) if bge_lats else None
    nomic_avg = sum(nomic_lats) / len(nomic_lats) if nomic_lats else None

    bge_lat_str = f"{bge_avg:.2f}ms" if bge_avail and bge_avg is not None else "n/a"
    nomic_lat_str = f"{nomic_avg:.2f}ms" if nomic_avail and nomic_avg is not None else "n/a"
    print(f"  ║  {'Avg embed latency (ms)':<30} {bge_lat_str:<18} {nomic_lat_str:<18}║")

    print(f"  ║  {'Model load time (s)':<30} {bge_load_s:<18.1f} {nomic_load_s:<18.1f}║")

    bge_acc = bge.get("top1_accuracy", None)
    nomic_acc = nomic.get("top1_accuracy", None)
    bge_acc_str = f"{bge_acc:.0f}" if bge_avail and bge_acc is not None else "n/a"
    nomic_acc_str = f"{nomic_acc:.0f}" if nomic_avail and nomic_acc is not None else "n/a"
    print(f"  ║  {'Top-1 accuracy (%)':<30} {bge_acc_str:<18} {nomic_acc_str:<18}║")

    bge_eng = bge.get("top1_by_category", {}).get("english", None)
    bge_hin = bge.get("top1_by_category", {}).get("hindi", None)
    nomic_eng = nomic.get("top1_by_category", {}).get("english", None)
    nomic_hin = nomic.get("top1_by_category", {}).get("hindi", None)
    bge_eng_str = f"{bge_eng:.0f}" if bge_avail and bge_eng is not None else "n/a"
    bge_hin_str = f"{bge_hin:.0f}" if bge_avail and bge_hin is not None else "n/a"
    nomic_eng_str = f"{nomic_eng:.0f}" if nomic_avail and nomic_eng is not None else "n/a"
    nomic_hin_str = f"{nomic_hin:.0f}" if nomic_avail and nomic_hin is not None else "n/a"
    print(f"  ║  {'  English subset (%)':<30} {bge_eng_str:<18} {nomic_eng_str:<18}║")
    print(f"  ║  {'  Hindi cross-lang (%)':<30} {bge_hin_str:<18} {nomic_hin_str:<18}║")

    # Winner column
    print("  ║  " + "─" * 66 + "║")
    dim_winner = "Nomic (768)" if isinstance(dim_nomic, int) and isinstance(dim_bge, int) and dim_nomic < dim_bge else "BGE-M3 (1024)" if isinstance(dim_bge, int) else "—"
    if bge_avail and nomic_avail and bge_avg is not None and nomic_avg is not None:
        lat_winner = "Nomic" if nomic_avg < bge_avg else "BGE-M3"
    else:
        lat_winner = "—"
    if bge_avail and nomic_avail and bge_acc is not None and nomic_acc is not None:
        acc_winner = "BGE-M3" if bge_acc > nomic_acc else "Nomic" if nomic_acc > bge_acc else "Tie"
    else:
        acc_winner = "—"
    print(f"  ║  {'Winner (dim)':<30} {'':<18} {dim_winner:<18}║")
    print(f"  ║  {'Winner (latency)':<30} {'':<18} {lat_winner:<18}║")
    print(f"  ║  {'Winner (accuracy)':<30} {'':<18} {acc_winner:<18}║")
    print(f"  ║  {'Winner (load time)':<30} {'':<18} {'Nomic' if nomic_load_s < bge_load_s else 'BGE-M3' if bge_load_s > 0 else '—':<18}║")

    # Caveat
    print("  ║  " + "─" * 66 + "║")
    print(f"  ║  {'Note: Nomic accuracy uses embed() with default':<66} ║")
    print(f"  ║  {'kind=document (match=prod path). kind=query':<66} ║")
    print(f"  ║  {'could improve results (see services/find.py).':<66} ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()


def main() -> int:
    t0 = time.monotonic()

    print("── BGE-M3 vs Nomic Embedding Benchmark ──")
    print()

    # ── Setup temp DB ────────────────────────────────────────────────
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="embed_bench_")
    os.close(fd)
    print(f"  DB: {db_path}")

    household = _seed_db(db_path)

    # ── Load providers ──────────────────────────────────────────────
    from shopstack.providers.embeddings_provider import (
        BGEM3EmbeddingProvider,
        NomicEmbeddingProvider,
    )

    print("  Loading providers...")

    bge_loader_t0 = time.perf_counter()
    provider_bge = BGEM3EmbeddingProvider()
    _ = provider_bge.available  # trigger lazy init
    bge_load_s = time.perf_counter() - bge_loader_t0

    nomic_loader_t0 = time.perf_counter()
    provider_nomic = NomicEmbeddingProvider()
    _ = provider_nomic.available  # trigger lazy init
    nomic_load_s = time.perf_counter() - nomic_loader_t0

    print(f"  BGE-M3 load: {bge_load_s:.1f}s")
    print(f"  Nomic  load: {nomic_load_s:.1f}s")

    # ── Run benchmarks ──────────────────────────────────────────────
    result_bge = _bench_provider(provider_bge, "BGE-M3", False, db_path, household, QUERIES)
    result_nomic = _bench_provider(provider_nomic, "Nomic", True, db_path, household, QUERIES)

    # ── Summary ─────────────────────────────────────────────────────
    _print_summary({"bge-m3": result_bge, "nomic": result_nomic}, bge_load_s, nomic_load_s)

    elapsed = time.monotonic() - t0
    print(f"  Total: {elapsed:.1f}s")
    print()

    # ── Teardown ────────────────────────────────────────────────────
    for suffix in ("", "-wal", "-shm"):
        Path(db_path).with_suffix(Path(db_path).suffix + suffix).unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
