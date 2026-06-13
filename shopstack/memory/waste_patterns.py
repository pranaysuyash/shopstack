from __future__ import annotations

import logging
from typing import Any

from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)


def compute_waste_pattern(database: Database, canonical_name: str) -> dict[str, Any]:
    """Compute how often an item is wasted vs consumed.

    Uses the real ``inventory_events`` table. "Wasted" is recorded as
    ``action = 'discarded'`` and "consumed" as ``action = 'consumed'``;
    quantity is read from the absolute value of ``quantity_delta``.
    """
    try:
        rows = database.conn.execute(
            """
            SELECT action,
                   COALESCE(SUM(ABS(quantity_delta)), 0.0) AS total_qty
            FROM inventory_events
            WHERE canonical_name = ?
              AND action IN ('discarded', 'consumed')
              AND quantity_delta IS NOT NULL
            GROUP BY action
            """,
            (canonical_name.lower(),),
        ).fetchall()
    except Exception as e:
        logger.warning("Waste pattern compute failed: %s", e)
        return {"wasted_qty": 0, "consumed_qty": 0, "waste_rate": 0.0, "total_resolved": 0.0}

    wasted = 0.0
    consumed = 0.0
    for r in rows:
        qty = float(r["total_qty"] or 0.0)
        if r["action"] == "discarded":
            wasted = qty
        elif r["action"] == "consumed":
            consumed = qty

    total = wasted + consumed
    waste_rate = (wasted / total) if total > 0 else 0.0
    return {
        "wasted_qty": wasted,
        "consumed_qty": consumed,
        "waste_rate": waste_rate,
        "total_resolved": total,
    }


def get_waste_insights(database: Database) -> list[dict[str, Any]]:
    """Return per-item waste insights aggregated across the whole inventory.

    Scopes the result to items the household has actually moved through
    the inventory events table.
    """
    try:
        rows = database.conn.execute(
            """
            SELECT canonical_name,
                   action,
                   COALESCE(SUM(ABS(quantity_delta)), 0.0) AS total_qty
            FROM inventory_events
            WHERE action IN ('discarded', 'consumed')
              AND quantity_delta IS NOT NULL
              AND canonical_name <> ''
            GROUP BY canonical_name, action
            """,
        ).fetchall()
    except Exception as e:
        logger.warning("Waste insights failed: %s", e)
        return []

    stats: dict[str, dict[str, float]] = {}
    for r in rows:
        name = r["canonical_name"]
        action = r["action"]
        qty = float(r["total_qty"] or 0.0)
        bucket = stats.setdefault(name, {"wasted": 0.0, "consumed": 0.0})
        if action == "discarded":
            bucket["wasted"] += qty
        elif action == "consumed":
            bucket["consumed"] += qty

    results: list[dict[str, Any]] = []
    for name, data in stats.items():
        wasted = data["wasted"]
        consumed = data["consumed"]
        total = wasted + consumed
        if total <= 0:
            continue
        results.append({
            "canonical_name": name,
            "wasted_qty": wasted,
            "consumed_qty": consumed,
            "waste_rate": wasted / total,
            "total_resolved": total,
        })

    results.sort(key=lambda r: r["waste_rate"], reverse=True)
    return results
