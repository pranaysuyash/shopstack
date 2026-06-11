from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)

def compute_waste_pattern(database: Database, canonical_name: str) -> dict[str, Any]:
    """Compute how often an item is wasted vs consumed."""
    try:
        movements = database.get_movement_history(canonical_name=canonical_name, limit=100)
    except Exception:
        # If get_movement_history does not support canonical_name filter, just query DB directly
        return {"wasted_qty": 0, "consumed_qty": 0, "waste_rate": 0.0}

    # Fallback to direct DB query if needed
    try:
        rows = database.conn.execute(
            """
            SELECT m.to_location_id, l.quantity, l.unit
            FROM inventory_movements m
            JOIN inventory_lots l ON m.lot_id = l.lot_id
            WHERE l.canonical_name = ? AND m.to_location_id IN ('trash', 'consumed')
            """,
            (canonical_name,)
        ).fetchall()
        
        wasted = 0.0
        consumed = 0.0
        for r in rows:
            qty = r["quantity"] or 1.0
            if r["to_location_id"] == "trash":
                wasted += qty
            elif r["to_location_id"] == "consumed":
                consumed += qty
                
        total = wasted + consumed
        waste_rate = wasted / total if total > 0 else 0.0
        return {
            "wasted_qty": wasted,
            "consumed_qty": consumed,
            "waste_rate": waste_rate,
            "total_resolved": total,
        }
    except Exception as e:
        logger.warning("Waste pattern compute failed: %s", e)
        return {"wasted_qty": 0, "consumed_qty": 0, "waste_rate": 0.0}

def get_waste_insights(database: Database) -> list[dict[str, Any]]:
    """Return top wasted items."""
    try:
        rows = database.conn.execute(
            """
            SELECT l.canonical_name, m.to_location_id, SUM(l.quantity) as total_qty
            FROM inventory_movements m
            JOIN inventory_lots l ON m.lot_id = l.lot_id
            WHERE m.to_location_id IN ('trash', 'consumed')
            GROUP BY l.canonical_name, m.to_location_id
            """
        ).fetchall()
        
        stats: dict[str, dict[str, float]] = {}
        for r in rows:
            name = r["canonical_name"]
            loc = r["to_location_id"]
            qty = r["total_qty"] or 0.0
            if name not in stats:
                stats[name] = {"wasted": 0.0, "consumed": 0.0}
            if loc == "trash":
                stats[name]["wasted"] += qty
            elif loc == "consumed":
                stats[name]["consumed"] += qty
                
        results = []
        for name, data in stats.items():
            total = data["wasted"] + data["consumed"]
            if total > 0:
                rate = data["wasted"] / total
                if data["wasted"] > 0:
                    results.append({
                        "canonical_name": name,
                        "wasted_qty": data["wasted"],
                        "consumed_qty": data["consumed"],
                        "waste_rate": rate,
                    })
                    
        results.sort(key=lambda x: x["waste_rate"], reverse=True)
        return results
    except Exception as e:
        logger.warning("Waste insights failed: %s", e)
        return []
