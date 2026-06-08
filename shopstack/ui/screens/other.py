"""Backward-compatibility re-exports from the now-split screen modules.

This module previously contained 540+ lines with 14+ functions spanning
price memory, household map, field notes, and Swiggy market screens.

Implementation lives in dedicated modules:
  - shopstack.ui.screens.price_memory   (price_memory_view, price_intelligence_view, seed_swiggy_prices)
  - shopstack.ui.screens.household_map  (household_map_view, move_inventory_to_location)
  - shopstack.ui.screens.field_notes    (field_notes_view, field_notes_save)
  - shopstack.ui.screens.swiggy_market  (swiggy_market_view, swiggy_basket_estimate)

This file remains for backward-compatibility. New imports should use the
canonical modules above.
"""

from __future__ import annotations

from shopstack.ui.screens.price_memory import (
    price_memory_view,
    price_intelligence_view,
    seed_swiggy_prices,
)
from shopstack.ui.screens.household_map import (
    household_map_view,
    create_household_location,
    inventory_alerts,
    move_inventory_to_location,
    what_is_in_fridge_now,
)
from shopstack.ui.screens.field_notes import (
    field_notes_view,
    field_notes_save,
)
from shopstack.ui.screens.swiggy_market import (
    swiggy_market_view,
    swiggy_basket_estimate,
)

__all__ = [
    "create_household_location",
    "field_notes_save",
    "field_notes_view",
    "household_map_view",
    "inventory_alerts",
    "move_inventory_to_location",
    "price_intelligence_view",
    "price_memory_view",
    "seed_swiggy_prices",
    "swiggy_basket_estimate",
    "swiggy_market_view",
    "what_is_in_fridge_now",
]
