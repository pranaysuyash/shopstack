"""Onboarding quiz — first-run experience for new households.

When a fresh ShopStack DB has no inventory and no shopping list, the
Today dashboard is dead — no stats, no restocks, no substitutions.
This service runs a 5-question wizard that auto-seeds the household with
a sensible starter inventory based on the answers, marks onboarding as
complete, and creates an initial shopping list.

**The 5 questions:**

1. **Household size** — 1 / 2-3 / 4-5 / 6+
2. **Dietary preference** — vegetarian / vegan / omnivore
3. **Common items to stock** — multi-select from a curated list of
   Indian household staples (rice, atta, dal, onion, tomato, milk, …)
4. **Top retailers in your area** — multi-select (Swiggy, Blinkit, Zepto, DMart)
5. **City for weather-aware suggestions** — free text (default: mumbai)

**Seeding rules:**

- Household size scales quantities (1 → 1×, 6+ → 2.5×)
- Diet excludes meat/fish/egg items from the default seed
- Common items are added to inventory (one lot per item, with
  typical_quantity for the household size)
- Retailers are saved as preferences (used to prioritise market snapshots)
- City is saved as a config value (used for weather context)

The seed is **idempotent** — re-running onboarding (or the wizard
hitting a glitch mid-way) won't double-add. We check for existing
canonical names before inserting.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.persistence.database import Database
from shopstack.repos.inventory import InventoryRepo
from shopstack.repos.shopping_list import ShoppingListRepo
from shopstack.schemas.models import (
    InventoryLot,
    PreferenceSignal,
    ShoppingListItem,
)
from shopstack.services.storage_suggest import suggest_storage_location

logger = logging.getLogger(__name__)


# ── Question schema ────────────────────────────────────────────────────────

HOUSEHOLD_SIZES: list[dict[str, Any]] = [
    {"key": "1", "label": "Just me", "scale": 1.0},
    {"key": "2-3", "label": "2-3 people", "scale": 1.5},
    {"key": "4-5", "label": "4-5 people", "scale": 2.0},
    {"key": "6+", "label": "6 or more", "scale": 2.5},
]

DIETARY_PREFERENCES: list[dict[str, str]] = [
    {"key": "vegetarian", "label": "Vegetarian"},
    {"key": "vegan", "label": "Vegan"},
    {"key": "omnivore", "label": "Omnivore (eats everything)"},
]

# Curated list of Indian household staples. Multi-select. Items are
# paired with a default storage category so the auto-categorize service
# can place them.
COMMON_STAPLES: list[dict[str, str]] = [
    {"canonical_name": "rice", "label": "Rice", "category": "staple"},
    {"canonical_name": "wheat_flour", "label": "Wheat flour (atta)", "category": "staple"},
    {"canonical_name": "toor_dal", "label": "Toor dal", "category": "staple"},
    {"canonical_name": "onion", "label": "Onion", "category": "vegetable"},
    {"canonical_name": "tomato", "label": "Tomato", "category": "vegetable"},
    {"canonical_name": "potato", "label": "Potato", "category": "vegetable"},
    {"canonical_name": "green_chilli", "label": "Green chilli", "category": "vegetable"},
    {"canonical_name": "ginger", "label": "Ginger", "category": "vegetable"},
    {"canonical_name": "garlic", "label": "Garlic", "category": "vegetable"},
    {"canonical_name": "coriander", "label": "Coriander (dhania)", "category": "herb"},
    {"canonical_name": "milk", "label": "Milk", "category": "dairy"},
    {"canonical_name": "curd", "label": "Curd (dahi)", "category": "dairy"},
    {"canonical_name": "paneer", "label": "Paneer", "category": "dairy"},
    {"canonical_name": "salt", "label": "Salt", "category": "staple"},
    {"canonical_name": "turmeric", "label": "Turmeric", "category": "spice"},
    {"canonical_name": "cooking_oil", "label": "Cooking oil", "category": "staple"},
    {"canonical_name": "tea", "label": "Tea", "category": "staple"},
    {"canonical_name": "sugar", "label": "Sugar", "category": "staple"},
    # Non-veg (only seeded for omnivore)
    {"canonical_name": "egg", "label": "Eggs", "category": "dairy_alt"},
    {"canonical_name": "chicken", "label": "Chicken", "category": "meat"},
    {"canonical_name": "fish", "label": "Fish", "category": "meat"},
]

NON_VEG_CANONICALS = {"egg", "chicken", "fish"}

RETAILERS: list[dict[str, str]] = [
    {"key": "swiggy", "label": "Swiggy Instamart"},
    {"key": "blinkit", "label": "Blinkit"},
    {"key": "zepto", "label": "Zepto"},
    {"key": "dmart", "label": "DMart"},
]

# Default city for weather-aware suggestions if the user skips the input.
DEFAULT_CITY = "mumbai"


@dataclass
class OnboardingResult:
    """Result of running the onboarding wizard."""

    success: bool
    was_already_complete: bool
    items_added: int = 0
    retailers_added: int = 0
    list_created: bool = False
    city_saved: str = ""
    notes: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "was_already_complete": self.was_already_complete,
            "items_added": self.items_added,
            "retailers_added": self.retailers_added,
            "list_created": self.list_created,
            "city_saved": self.city_saved,
            "notes": self.notes,
            "error": self.error,
        }


# ── State queries ────────────────────────────────────────────────────────


def is_onboarding_complete(db: Database) -> bool:
    """True when the user has previously completed onboarding."""
    return db.get_config_value("onboarding_complete", "0") == "1"


# ── Sub-routines ────────────────────────────────────────────────────────


def _household_scale(household_key: str) -> float:
    for size in HOUSEHOLD_SIZES:
        if size["key"] == household_key:
            return float(size["scale"])
    return 1.0


def _default_quantities(household_key: str) -> dict[str, float]:
    """Return per-item default quantities (in the unit they should be stored)."""
    scale = _household_scale(household_key)
    base = {
        "rice": 5.0,
        "wheat_flour": 5.0,
        "toor_dal": 1.0,
        "onion": 2.0,
        "tomato": 2.0,
        "potato": 2.0,
        "green_chilli": 0.25,
        "ginger": 0.1,
        "garlic": 0.1,
        "coriander": 0.1,
        "milk": 1.0,
        "curd": 0.5,
        "paneer": 0.2,
        "salt": 1.0,
        "turmeric": 0.2,
        "cooking_oil": 1.0,
        "tea": 0.5,
        "sugar": 1.0,
        "egg": 12.0,
        "chicken": 1.0,
        "fish": 0.5,
    }
    return {cname: qty * scale for cname, qty in base.items()}


def _default_units() -> dict[str, str]:
    return {
        "rice": "kg",
        "wheat_flour": "kg",
        "toor_dal": "kg",
        "onion": "kg",
        "tomato": "kg",
        "potato": "kg",
        "green_chilli": "kg",
        "ginger": "kg",
        "garlic": "kg",
        "coriander": "kg",
        "milk": "L",
        "curd": "kg",
        "paneer": "kg",
        "salt": "kg",
        "turmeric": "kg",
        "cooking_oil": "L",
        "tea": "kg",
        "sugar": "kg",
        "egg": "pieces",
        "chicken": "kg",
        "fish": "kg",
    }


def _filter_by_diet(items: list[str], dietary_key: str) -> list[str]:
    """Remove non-vegetarian items if the user is vegetarian or vegan."""
    if dietary_key in ("vegetarian", "vegan"):
        return [c for c in items if c not in NON_VEG_CANONICALS]
    return items


# ── Public API ───────────────────────────────────────────────────────────


def submit_onboarding(
    db: Database,
    *,
    household_size: str,
    dietary_preference: str,
    common_items: list[str] | str,
    retailers: list[str] | str,
    city: str = "",
    user_id: str | None = None,
) -> OnboardingResult:
    """Run the onboarding wizard and seed the household.

    Args:
        db: Database.
        household_size: One of "1", "2-3", "4-5", "6+".
        dietary_preference: One of "vegetarian", "vegan", "omnivore".
        common_items: List of canonical names from ``COMMON_STAPLES`` (or
            a comma-separated string).
        retailers: List of retailer keys from ``RETAILERS``.
        city: City name for weather context. Empty → ``DEFAULT_CITY``.
        user_id: Household ID. Defaults to ``db.active_household_id``.

    Returns:
        ``OnboardingResult`` with item counts and notes.
    """
    if user_id is None:
        user_id = getattr(db, "active_household_id", "") or ""

    result = OnboardingResult(
        success=False,
        was_already_complete=is_onboarding_complete(db),
        city_saved=(city or DEFAULT_CITY).strip(),
    )

    if result.was_already_complete:
        result.notes.append(
            "Onboarding was already complete for this household; re-running is a no-op for items/retailers (idempotent)."
        )
        # Still update city + retailers in case the user wants to change them.
    if household_size not in {s["key"] for s in HOUSEHOLD_SIZES}:
        result.error = f"Invalid household size: {household_size!r}"
        return result
    if dietary_preference not in {d["key"] for d in DIETARY_PREFERENCES}:
        result.error = f"Invalid dietary preference: {dietary_preference!r}"
        return result

    # Normalise inputs
    if isinstance(common_items, str):
        common_items = [
            c.strip().lower().replace(" ", "_")
            for c in common_items.split(",")
            if c.strip()
        ]
    if isinstance(retailers, str):
        retailers = [r.strip().lower() for r in retailers.split(",") if r.strip()]
    valid_retailer_keys = {r["key"] for r in RETAILERS}
    retailers = [r for r in retailers if r in valid_retailer_keys]

    # Apply dietary filter
    common_items = _filter_by_diet(common_items, dietary_preference)

    quantities = _default_quantities(household_size)
    units = _default_units()

    # 1) Seed inventory via the existing repo (so events get recorded).
    inventory_repo = InventoryRepo(db)
    existing_canonicals = {
        (lot.canonical_name or "").lower().strip()
        for lot in db.get_inventory(user_id=user_id)
    }

    items_added = 0
    for cname in common_items:
        if cname in existing_canonicals:
            continue
        qty = quantities.get(cname)
        unit = units.get(cname, "unit")
        if qty is None:
            # Unknown item; still add with default 1.0 / unit
            qty, unit = 1.0, "unit"
        suggestion = suggest_storage_location(canonical_name=cname)
        try:
            inventory_repo.add_item(
                canonical_name=cname,
                display_name=cname.replace("_", " ").title(),
                quantity=qty,
                unit=unit,
                storage_location_id=suggestion.storage_location_id,
                category=next(
                    (s["category"] for s in COMMON_STAPLES if s["canonical_name"] == cname),
                    "",
                ),
                user_id=user_id,
            )
            items_added += 1
        except Exception as exc:
            logger.warning("Onboarding: failed to add %s: %s", cname, exc)

    # 2) Save retailers as preference signals (so the engine knows what
    # the user uses). The signal_type="brand_preferred" and value=retailer
    # key is the schema's documented way to record a preferred source.
    retailers_added = 0
    for rkey in retailers:
        try:
            db.add_preference_signal(
                PreferenceSignal(
                    canonical_name=f"_retailer:{rkey}",
                    signal_type="brand_preferred",
                    value=rkey,
                    confidence=1.0,
                    source=f"onboarding:{user_id}",
                ),
                user_id=user_id,
            )
            retailers_added += 1
        except Exception as exc:
            logger.warning("Onboarding: failed to add retailer %s: %s", rkey, exc)

    # 3) Create the initial shopping list (only if none exists)
    list_repo = ShoppingListRepo(db)
    existing_list = db.get_active_shopping_list(user_id=user_id)
    if existing_list is None:
        try:
            list_repo.create_or_update(
                goal="Welcome to ShopStack — your first shopping list",
                user_id=user_id,
            )
            result.list_created = True
        except Exception as exc:
            logger.warning("Onboarding: failed to create initial list: %s", exc)

    # 4) Save the city for weather context
    try:
        db.set_config_value("weather_city", result.city_saved)
    except Exception as exc:
        logger.debug("Onboarding: failed to save weather city: %s", exc)

    # 5) Mark complete
    try:
        db.set_config_value("onboarding_complete", "1")
    except Exception as exc:
        logger.debug("Onboarding: failed to mark complete: %s", exc)

    result.success = True
    result.items_added = items_added
    result.retailers_added = retailers_added
    result.notes.extend([
        f"Added {items_added} starter item(s) to inventory.",
        f"Saved {retailers_added} preferred retailer(s).",
        f"City set to: {result.city_saved}",
        f"Household size: {household_size} (scale {_household_scale(household_size)}x).",
        f"Dietary preference: {dietary_preference}.",
    ])
    return result


__all__ = [
    "HOUSEHOLD_SIZES",
    "DIETARY_PREFERENCES",
    "COMMON_STAPLES",
    "RETAILERS",
    "DEFAULT_CITY",
    "OnboardingResult",
    "is_onboarding_complete",
    "submit_onboarding",
]
