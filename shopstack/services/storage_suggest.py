"""Storage location auto-suggestion.

When the user adds a new inventory item, they shouldn't have to pick a
storage location from a long list. This service suggests one based on:

1. **Category** if the user (or upstream) provides one.
2. **Canonical name** if the category isn't known — pattern-match on
   the name to infer category, then map to a storage location.

The output is a suggestion, not a mandate. The user can override.

Mapping (in priority order):

- **dairy / milk / curd / paneer / cheese / butter / yogurt** → ``fridge``
  (specifically the door shelf for milk, the main shelf for everything else)
- **leafy / herbs / greens / coriander / mint / spinach** → ``fridge_drawer``
  (vegetable drawer)
- **vegetable / fruit / onion / potato / tomato / carrot / cucumber** →
  ``pantry`` (cool dry storage for hardy produce) or ``fridge_drawer`` for
  leafy items
- **frozen / ice cream / peas (frozen)** → ``freezer``
- **bread / bakery / biscuit** → ``pantry_top`` (cool dry)
- **rice / flour / atta / dal / lentil / pasta / noodle** → ``pantry_mid``
  (middle shelf — bulk dry goods)
- **spice / masala / chili powder / turmeric / cumin / coriander_powder** →
  ``spice_box``
- **oil / ghee / vinegar / sauce / condiment** → ``pantry_mid``
- **snack / chips / biscuit / chocolate** → ``pantry_top``
- **medicine / tablet / capsule / syrup** → ``medicine_drawer``
- **shampoo / soap / toothpaste / detergent / cleaning** → ``bathroom_cabinet``
- **drink / water / juice / soda / beer / wine** → ``fridge_door``
- **default / unknown** → ``pantry`` (safest)

Storage IDs match the seeded locations in
``shopstack/persistence/database.py::_seed_locations``:

    home.kitchen.fridge
    home.kitchen.fridge.door_1
    home.kitchen.fridge.shelf_1
    home.kitchen.fridge.drawer
    home.kitchen.freezer
    home.kitchen.pantry.shelf_1 (etc.)
    home.bedroom.medicine_drawer
    home.bathroom.cabinet
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Default location ID for items we can't classify. The seeded pantry
# shelf is the safest "I don't know where this goes" place.
DEFAULT_LOCATION = "home.kitchen.pantry.shelf_1"


# ── Category → storage location map ───────────────────────────────────
#
# The key is a (case-insensitive) category token. The value is the
# canonical storage_location_id. Order matters only for the
# (deterministic) suggestion — the first match wins.

_CATEGORY_TO_LOCATION: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(medicine|tablet|capsule|syrup|ointment|prescription|paracetamol)\b"), "home.bedroom.medicine_drawer"),
    (re.compile(r"\b(bathroom|toiletries|personal_care|hygiene)\b"), "home.bathroom.cabinet"),
    (re.compile(r"\b(dairy|milk_product|fermented)\b"), "home.kitchen.fridge.shelf_1"),
    (re.compile(r"\b(shampoo|conditioner|soap|toothpaste|toothbrush|deodorant|detergent|bleach|cleaner)\b"), "home.bathroom.cabinet"),
    (re.compile(r"\b(frozen|ice cream|freezer)\b"), "home.kitchen.freezer.shelf_1"),
    (re.compile(r"\b(leafy|greens|spinach|kale|lettuce|coriander|mint|parsley|basil|dill|herbs?)\b"), "home.kitchen.fridge.drawer"),
    (re.compile(r"\b(cheese|butter|yogurt|curd|paneer|ghee|khoa|cream)\b"), "home.kitchen.fridge.shelf_1"),
    (re.compile(r"\b(milk|doodh)\b"), "home.kitchen.fridge.door_1"),
    (re.compile(r"\b(juice|soda|water|drink|cola|beer|wine)\b"), "home.kitchen.fridge.door_1"),
    (re.compile(r"\b(vegetable|veggie|sabzi|sabzii)\b"), "home.kitchen.fridge.drawer"),
    (re.compile(r"\b(fruit|banana|apple|mango|orange|grape|berry|tomato|potato|onion|carrot|cucumber|brinjal|okra|garlic|ginger|lime|lemon)\b"), "home.kitchen.pantry.shelf_1"),
    (re.compile(r"\b(spice|masala|chili powder|turmeric|cumin|coriander powder|garam masala|paprika|cinnamon|cardamom|clove)\b"), "home.kitchen.pantry.spice_box"),
    (re.compile(r"\b(atta|flour|maida|rice|dal|lentil|pasta|noodle|sooji|semolina|besan)\b"), "home.kitchen.pantry.shelf_2"),
    (re.compile(r"\b(oil|ghee|vinegar|sauce|ketchup|mayo|mustard|soy sauce|cooking oil)\b"), "home.kitchen.pantry.shelf_2"),
    (re.compile(r"\b(bread|bakery|bun|roti|chapati|biscuit|cookie|cake|pastry)\b"), "home.kitchen.pantry.shelf_1"),
    (re.compile(r"\b(snack|chips|nuts|chocolate|crackers|popcorn)\b"), "home.kitchen.pantry.shelf_1"),
    (re.compile(r"\b(tea|coffee|sugar|salt|jaggery|honey)\b"), "home.kitchen.pantry.shelf_2"),
    (re.compile(r"\b(beverage|drink|soda|juice)\b"), "home.kitchen.fridge.door_1"),
]


# ── Canonical-name fallback rules ──────────────────────────────────────
#
# Used when no category is given. Same patterns as category but matched
# against the canonical name (which usually has a "kind" embedded).

_NAME_FALLBACK: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(tablet|capsule|syrup)\b"), "home.bedroom.medicine_drawer"),
    (re.compile(r"\b(shampoo|soap|toothpaste)\b"), "home.bathroom.cabinet"),
    (re.compile(r"\b(ice_cream|frozen)\b"), "home.kitchen.freezer.shelf_1"),
    (re.compile(r"\b(coriander|mint|spinach|kale|lettuce|curry_leaves)\b"), "home.kitchen.fridge.drawer"),
    (re.compile(r"\b(cheese|butter|paneer|curd|yogurt|ghee)\b"), "home.kitchen.fridge.shelf_1"),
    (re.compile(r"\b(milk)\b"), "home.kitchen.fridge.door_1"),
    (re.compile(r"\b(juice|soda|water|cola|beer|wine)\b"), "home.kitchen.fridge.door_1"),
    (re.compile(r"\b(tomato|potato|onion|carrot|cucumber|brinjal|okra|garlic|ginger|lime|lemon|chilli|chili|pepper|banana|apple|mango|orange|grape)\b"), "home.kitchen.pantry.shelf_1"),
    (re.compile(r"\b(atta|flour|maida|rice|dal|lentil|pasta|noodle|sooji|semolina|besan|chickpea|chana|urad|moong|toor)\b"), "home.kitchen.pantry.shelf_2"),
    (re.compile(r"\b(turmeric|cumin|coriander_powder|chili_powder|garam_masala|paprika|cinnamon|cardamom|clove|masala|spice)\b"), "home.kitchen.pantry.spice_box"),
    (re.compile(r"\b(oil|ghee|vinegar|sauce|ketchup|mayo|mustard|soy_sauce)\b"), "home.kitchen.pantry.shelf_2"),
    (re.compile(r"\b(bread|bun|roti|chapati|biscuit|cookie|cake|pastry)\b"), "home.kitchen.pantry.shelf_1"),
    (re.compile(r"\b(chips|nuts|chocolate|crackers|popcorn|snack)\b"), "home.kitchen.pantry.shelf_1"),
    (re.compile(r"\b(tea|coffee|sugar|salt|jaggery|honey)\b"), "home.kitchen.pantry.shelf_2"),
]


@dataclass
class StorageSuggestion:
    """Result of a storage location auto-suggestion."""

    storage_location_id: str
    source: str  # "category" | "name" | "default"
    confidence: float  # 0.0–1.0
    reason: str


def suggest_storage_location(
    canonical_name: str = "",
    category: str = "",
) -> StorageSuggestion:
    """Suggest a storage location for a new inventory item.

    Args:
        canonical_name: The canonical product name (e.g. "milk", "tomato").
            Used as a fallback when ``category`` is empty.
        category: Optional explicit category (e.g. "dairy", "vegetable",
            "spice"). When set, takes priority over the name.

    Returns:
        A ``StorageSuggestion`` with the suggested location, the source
        (category / name / default), a confidence score, and a human-readable
        reason. Always returns a suggestion (falls back to ``DEFAULT_LOCATION``).
    """
    cname = (canonical_name or "").lower()
    cat = (category or "").lower().strip()

    # 1) Category-driven (highest confidence)
    if cat:
        for pattern, location in _CATEGORY_TO_LOCATION:
            if pattern.search(cat):
                return StorageSuggestion(
                    storage_location_id=location,
                    source="category",
                    confidence=0.9,
                    reason=f"Category '{cat}' maps to {location}",
                )

    # 2) Canonical-name fallback
    if cname:
        for pattern, location in _NAME_FALLBACK:
            if pattern.search(cname):
                return StorageSuggestion(
                    storage_location_id=location,
                    source="name",
                    confidence=0.65,
                    reason=f"Canonical name '{canonical_name}' matches {location}",
                )

    # 3) Default — pantry shelf, the safest catch-all
    return StorageSuggestion(
        storage_location_id=DEFAULT_LOCATION,
        source="default",
        confidence=0.3,
        reason="No matching pattern; defaulting to pantry shelf",
    )


__all__ = [
    "StorageSuggestion",
    "DEFAULT_LOCATION",
    "suggest_storage_location",
]
