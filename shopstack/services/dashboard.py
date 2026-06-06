from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.decisions import DecisionSet, classify_all
from shopstack.persistence.database import Database
from shopstack.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class DashboardState:
    decision_set: DecisionSet
    market_snapshot: Any | None
    use_soon: dict[str, Any]
    active_list: Any | None
    all_inventory: list[Any] = field(default_factory=list)
    active_inventory: list[Any] = field(default_factory=list)
    low_items: list[Any] = field(default_factory=list)
    recent_purchases: list[Any] = field(default_factory=list)

    @property
    def use_soon_count(self) -> int:
        return int(self.use_soon.get("count", len(self.use_soon.get("items", []))))

    @property
    def use_soon_items(self) -> list[dict[str, Any]]:
        return list(self.use_soon.get("items", []))


def build_dashboard_state(db: Database, tools: ToolRegistry) -> DashboardState:
    """Assemble Today dashboard product state without rendering HTML."""
    market_snapshot = _load_market_snapshot()
    decision_set = classify_all(db, tools, market_snapshot)
    use_soon = tools.get_use_soon_items(days=3)
    active_list = db.get_active_shopping_list()
    all_inventory = db.get_inventory()
    active_inventory = [lot for lot in all_inventory if lot.status == "active"]
    low_items = [lot for lot in active_inventory if lot.quantity <= 0.5 or lot.status == "low"]
    recent_purchases = db.get_purchase_events(limit=5)

    return DashboardState(
        decision_set=decision_set,
        market_snapshot=market_snapshot,
        use_soon=use_soon,
        active_list=active_list,
        all_inventory=all_inventory,
        active_inventory=active_inventory,
        low_items=low_items,
        recent_purchases=recent_purchases,
    )


def _load_market_snapshot():
    try:
        from shopstack.market.sources.swiggy import load_snapshot
        return load_snapshot()
    except Exception as exc:
        logger.info("Swiggy market data unavailable: %s", exc)
        return None
