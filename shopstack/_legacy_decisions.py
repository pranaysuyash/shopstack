"""Decision engine — backward-compatible re-exports.

New code should import directly from shopstack.decisions (types, rules)
and shopstack.ui.renderers.decision_cards (HTML renderers).

This module remains for backward compatibility — all names delegate to
the canonical implementation in shopstack.decisions.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from shopstack.decisions import (
    DecisionSet,
    check_swiggy_availability,
    detect_purchase_cadence,
    detect_waste_patterns,
)
from shopstack.ui.renderers import decision_cards as _cards
from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)


# --- Render wrappers (backward-compatible with old db-based signatures) ---


def render_market_basket(ds: DecisionSet) -> str:
    return _cards.render_market_basket(ds)


def render_inventory_overview(all_inv: list[Any]) -> str:
    return _cards.render_inventory_overview(all_inv)


def render_my_list_panel(ds: DecisionSet, active_list: Any) -> str:
    return _cards.render_my_list_panel(ds, active_list)


def render_compare_panel(ds: DecisionSet) -> str:
    return _cards.render_compare_panel(ds)


def render_decision_panel(ds: DecisionSet) -> str:
    return _cards.render_decision_panel(ds)


def render_what_changed(db: Database) -> str:
    purchases = db.get_purchase_events(limit=5)
    traces = db.get_traces(limit=5)
    return _cards.render_what_changed(purchases, traces)


def render_cadence_insights(db: Database) -> str:
    cadence = detect_purchase_cadence(db)
    return _cards.render_cadence_insights(cadence)


def render_waste_warnings(db: Database) -> str:
    signals = detect_waste_patterns(db)
    return _cards.render_waste_warnings(signals)


def render_swiggy_soldout_warning(shopping_list_names: list[str]) -> str:
    avail = check_swiggy_availability(shopping_list_names)
    return _cards.render_swiggy_soldout_warning(avail)


def render_needs_confirmation(db: Database) -> str:
    all_inv = db.get_inventory()
    uncertain = [
        lot for lot in all_inv
        if lot.status == "active" and lot.quantity > 0 and (
            not lot.purchase_date
            or (date.today() - lot.purchase_date).days > 14
        )
    ]
    return _cards.render_needs_confirmation(uncertain)
