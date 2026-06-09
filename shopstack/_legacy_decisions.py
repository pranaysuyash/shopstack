"""DB-aware render wrappers for decision dashboard cards.

These functions combine data fetching (from Database) with HTML rendering
(from ui.renderers.decision_cards). They exist here because the decisions
package cannot import from UI without creating circular imports.

New code should call renderers directly with pre-fetched data rather than
using these wrappers.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)


# --- Render wrappers (backward-compatible with old db-based signatures) ---


def render_market_basket(ds) -> str:
    from shopstack.ui.renderers.decision_cards import render_market_basket
    return render_market_basket(ds)


def render_inventory_overview(all_inv: list[Any]) -> str:
    from shopstack.ui.renderers.decision_cards import render_inventory_overview
    return render_inventory_overview(all_inv)


def render_my_list_panel(ds, active_list: Any) -> str:
    from shopstack.ui.renderers.decision_cards import render_my_list_panel
    return render_my_list_panel(ds, active_list)


def render_compare_panel(ds) -> str:
    from shopstack.ui.renderers.decision_cards import render_compare_panel
    return render_compare_panel(ds)


def render_decision_panel(ds) -> str:
    from shopstack.ui.renderers.decision_cards import render_decision_panel
    return render_decision_panel(ds)


def render_what_changed(db: Database) -> str:
    from shopstack.ui.renderers.decision_cards import render_what_changed
    purchases = db.get_purchase_events(limit=5)
    traces = db.get_traces(limit=5)
    return render_what_changed(purchases, traces)


def render_cadence_insights(db: Database) -> str:
    from shopstack.decisions import detect_purchase_cadence
    from shopstack.ui.renderers.decision_cards import render_cadence_insights
    cadence = detect_purchase_cadence(db)
    return render_cadence_insights(cadence)


def render_waste_warnings(db: Database) -> str:
    from shopstack.decisions import detect_waste_patterns
    from shopstack.ui.renderers.decision_cards import render_waste_warnings
    signals = detect_waste_patterns(db)
    return render_waste_warnings(signals)


def render_swiggy_soldout_warning(shopping_list_names: list[str]) -> str:
    from shopstack.decisions import check_swiggy_availability
    from shopstack.ui.renderers.decision_cards import render_swiggy_soldout_warning
    avail = check_swiggy_availability(shopping_list_names)
    return render_swiggy_soldout_warning(avail)


def render_needs_confirmation(db: Database) -> str:
    from shopstack.ui.renderers.decision_cards import render_needs_confirmation
    all_inv = db.get_inventory()
    uncertain = [
        lot for lot in all_inv
        if lot.status == "active" and lot.quantity > 0 and (
            not lot.purchase_date
            or (date.today() - lot.purchase_date).days > 14
        )
    ]
    return render_needs_confirmation(uncertain)
