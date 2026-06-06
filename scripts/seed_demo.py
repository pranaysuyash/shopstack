#!/usr/bin/env python3
"""Seed ShopStack with realistic Indian household demo data.

Usage:
    uv run python scripts/seed_demo.py [--db PATH]

Seeds:
    - 30+ inventory items across all locations (fridge, pantry, spice box, etc.)
    - 5 stores (Reliance Fresh, DMart, local kirana, etc.)
    - 20+ price observations across stores for price intelligence
    - Active shopping list with mixed priorities
    - 10+ purchase events
    - 5+ agent traces (market lens, shopping list, ask)
    - Low-stock and expiring-soon items for dashboard alerts
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shopstack.config import settings
from shopstack.persistence.database import Database
from shopstack.schemas.models import (
    InventoryLot,
    PriceObservation,
    PurchaseEvent,
    ShoppingListItem,
    Store,
)
from shopstack.traces.export import create_trace


def seed_stores(db: Database) -> int:
    stores = [
        Store(store_id="reliance_fresh", name="Reliance Fresh", location="Koramangala", store_type="supermarket"),
        Store(store_id="dmart", name="DMart", location="HSR Layout", store_type="supermarket"),
        Store(store_id="kirana_1", name="Sharma Kirana", location="5th Block", store_type="kirana"),
        Store(store_id="big_basket", name="BigBasket", location="Online", store_type="online"),
        Store(store_id="local_vendor", name="Green Vegetable Cart", location="Street Corner", store_type="vendor"),
    ]
    for s in stores:
        existing = db.conn.execute("SELECT 1 FROM stores WHERE store_id = ?", (s.store_id,)).fetchone()
        if not existing:
            db.add_store(s)
    return len(stores)


def seed_inventory(db: Database) -> int:
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)

    items = [
        # --- Fridge ---
        {"canonical_name": "milk", "display_name": "Amul Taaza Milk", "quantity": 1.5, "unit": "L",
         "location": "fridge", "category": "dairy", "price": 64.0, "store": "kirana_1",
         "purchase_date": yesterday, "expiry": today + timedelta(days=3)},
        {"canonical_name": "curd", "display_name": "Nestle Curd", "quantity": 0.4, "unit": "kg",
         "location": "fridge", "category": "dairy", "price": 45.0, "store": "reliance_fresh",
         "purchase_date": yesterday, "expiry": today + timedelta(days=2)},
        {"canonical_name": "eggs", "display_name": "Country Eggs", "quantity": 8.0, "unit": "pieces",
         "location": "fridge_top", "category": "protein", "price": 84.0, "store": "kirana_1",
         "purchase_date": last_week},
        {"canonical_name": "cheese", "display_name": "Amul Cheese Slices", "quantity": 1.0, "unit": "pack",
         "location": "fridge", "category": "dairy", "price": 135.0, "store": "dmart",
         "purchase_date": last_week, "expiry": today + timedelta(days=30)},
        {"canonical_name": "butter", "display_name": "Amul Butter", "quantity": 0.5, "unit": "kg",
         "location": "fridge", "category": "dairy", "price": 235.0, "store": "reliance_fresh",
         "purchase_date": last_week},
        {"canonical_name": "coriander", "display_name": "Fresh Coriander", "quantity": 1.0, "unit": "bunch",
         "location": "fridge_drawer", "category": "vegetable", "price": 10.0, "store": "local_vendor",
         "purchase_date": yesterday, "expiry": today + timedelta(days=2)},
        {"canonical_name": "ginger", "display_name": "Ginger", "quantity": 0.2, "unit": "kg",
         "location": "fridge_drawer", "category": "vegetable", "price": 12.0, "store": "local_vendor",
         "purchase_date": last_week},
        {"canonical_name": "green_chili", "display_name": "Green Chilies", "quantity": 0.1, "unit": "kg",
         "location": "fridge_drawer", "category": "vegetable", "price": 8.0, "store": "local_vendor",
         "purchase_date": yesterday},
        {"canonical_name": "bread", "display_name": "Britannia Brown Bread", "quantity": 1.0, "unit": "loaf",
         "location": "fridge_top", "category": "bakery", "price": 55.0, "store": "kirana_1",
         "purchase_date": yesterday, "expiry": today + timedelta(days=4)},

        # --- Pantry ---
        {"canonical_name": "rice", "display_name": "India Gate Basmati", "quantity": 8.0, "unit": "kg",
         "location": "pantry_mid", "category": "grains", "price": 680.0, "store": "dmart",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "wheat_flour", "display_name": "Aashirvaad Atta", "quantity": 4.5, "unit": "kg",
         "location": "pantry_mid", "category": "grains", "price": 295.0, "store": "reliance_fresh",
         "purchase_date": last_week},
        {"canonical_name": "toor_dal", "display_name": "Tata Toor Dal", "quantity": 0.8, "unit": "kg",
         "location": "pantry_top", "category": "pulses", "price": 165.0, "store": "dmart",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "moong_dal", "display_name": "Organic Moong Dal", "quantity": 0.5, "unit": "kg",
         "location": "pantry_top", "category": "pulses", "price": 120.0, "store": "big_basket",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "onion", "display_name": "Onion", "quantity": 2.0, "unit": "kg",
         "location": "pantry_mid", "category": "vegetable", "price": 40.0, "store": "local_vendor",
         "purchase_date": last_week},
        {"canonical_name": "potato", "display_name": "Potato", "quantity": 1.5, "unit": "kg",
         "location": "pantry_mid", "category": "vegetable", "price": 30.0, "store": "local_vendor",
         "purchase_date": last_week},
        {"canonical_name": "garlic", "display_name": "Garlic", "quantity": 0.3, "unit": "kg",
         "location": "pantry", "category": "vegetable", "price": 35.0, "store": "local_vendor",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "cooking_oil", "display_name": "Fortune Sunflower Oil", "quantity": 0.8, "unit": "L",
         "location": "pantry_mid", "category": "cooking", "price": 165.0, "store": "dmart",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "salt", "display_name": "Tata Salt", "quantity": 0.9, "unit": "kg",
         "location": "pantry_top", "category": "staples", "price": 28.0, "store": "kirana_1",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "sugar", "display_name": "Madhur Sugar", "quantity": 1.8, "unit": "kg",
         "location": "pantry_top", "category": "staples", "price": 90.0, "store": "kirana_1",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "tea_leaves", "display_name": "Tata Premium Tea", "quantity": 0.2, "unit": "kg",
         "location": "pantry_top", "category": "beverage", "price": 160.0, "store": "reliance_fresh",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "biscuits", "display_name": "Parle-G Biscuits", "quantity": 2.0, "unit": "pack",
         "location": "pantry", "category": "snacks", "price": 20.0, "store": "kirana_1",
         "purchase_date": last_week},

        # --- Spice Box ---
        {"canonical_name": "turmeric_powder", "display_name": "Turmeric Powder", "quantity": 0.1, "unit": "kg",
         "location": "spice_box", "category": "spice", "price": 18.0, "store": "kirana_1",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "chili_powder", "display_name": "Red Chili Powder", "quantity": 0.1, "unit": "kg",
         "location": "spice_box", "category": "spice", "price": 22.0, "store": "kirana_1",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "garam_masala", "display_name": "MDH Garam Masala", "quantity": 0.05, "unit": "kg",
         "location": "spice_box", "category": "spice", "price": 55.0, "store": "reliance_fresh",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "mustard_seeds", "display_name": "Mustard Seeds", "quantity": 0.05, "unit": "kg",
         "location": "spice_box", "category": "spice", "price": 15.0, "store": "kirana_1",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "cumin_seeds", "display_name": "Cumin Seeds (Jeera)", "quantity": 0.05, "unit": "kg",
         "location": "spice_box", "category": "spice", "price": 20.0, "store": "kirana_1",
         "purchase_date": two_weeks_ago},

        # --- Bathroom ---
        {"canonical_name": "toothpaste", "display_name": "Colgate Strong Teeth", "quantity": 1.0, "unit": "tube",
         "location": "bathroom_cabinet", "category": "personal_care", "price": 99.0, "store": "dmart",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "soap", "display_name": "Dove Cream Bar", "quantity": 3.0, "unit": "bar",
         "location": "bathroom_cabinet", "category": "personal_care", "price": 42.0, "store": "dmart",
         "purchase_date": two_weeks_ago},
        {"canonical_name": "shampoo", "display_name": "Head & Shoulders", "quantity": 0.34, "unit": "L",
         "location": "bathroom_cabinet", "category": "personal_care", "price": 185.0, "store": "reliance_fresh",
         "purchase_date": two_weeks_ago},

        # --- Low stock / expiring for dashboard alerts ---
        {"canonical_name": "tomato", "display_name": "Tomato", "quantity": 0.3, "unit": "kg",
         "location": "fridge_drawer", "category": "vegetable", "price": 18.0, "store": "local_vendor",
         "purchase_date": last_week, "expiry": today + timedelta(days=1)},
        {"canonical_name": "lemon", "display_name": "Lemon", "quantity": 2.0, "unit": "pieces",
         "location": "fridge_drawer", "category": "vegetable", "price": 6.0, "store": "local_vendor",
         "purchase_date": yesterday, "expiry": today + timedelta(days=5)},
    ]

    existing = db.get_inventory()
    if existing:
        return 0

    added = 0
    for item in items:
        lot = InventoryLot(
            canonical_name=item["canonical_name"],
            display_name=item["display_name"],
            quantity=item["quantity"],
            unit=item["unit"],
            storage_location_id=item["location"],
            purchase_date=item.get("purchase_date", today),
            estimated_use_by_date=item.get("expiry"),
            price_paid=item.get("price"),
            category=item.get("category", ""),
            source_event_id="demo_seed",
        )
        db.add_inventory_lot(lot)
        added += 1

    return added


def seed_prices(db: Database) -> int:
    today = date.today()
    last_week = today - timedelta(days=7)
    two_weeks = today - timedelta(days=14)
    three_weeks = today - timedelta(days=21)

    prices = [
        # Milk - price comparison across stores
        ("milk", 64.0, 1.0, "L", "kirana_1", "Sharma Kirana", today),
        ("milk", 68.0, 1.0, "L", "reliance_fresh", "Reliance Fresh", today),
        ("milk", 62.0, 1.0, "L", "dmart", "DMart", last_week),
        ("milk", 66.0, 1.0, "L", "big_basket", "BigBasket", last_week),
        ("milk", 60.0, 1.0, "L", "kirana_1", "Sharma Kirana", two_weeks),
        ("milk", 63.0, 1.0, "L", "dmart", "DMart", three_weeks),

        # Rice - showing price trend
        ("rice", 680.0, 5.0, "kg", "dmart", "DMart", today),
        ("rice", 720.0, 5.0, "kg", "reliance_fresh", "Reliance Fresh", last_week),
        ("rice", 695.0, 5.0, "kg", "big_basket", "BigBasket", last_week),
        ("rice", 710.0, 5.0, "kg", "dmart", "DMart", two_weeks),
        ("rice", 730.0, 5.0, "kg", "reliance_fresh", "Reliance Fresh", three_weeks),

        # Onion - volatile pricing
        ("onion", 40.0, 1.0, "kg", "local_vendor", "Green Vegetable Cart", today),
        ("onion", 35.0, 1.0, "kg", "dmart", "DMart", today),
        ("onion", 38.0, 1.0, "kg", "reliance_fresh", "Reliance Fresh", last_week),
        ("onion", 28.0, 1.0, "kg", "local_vendor", "Green Vegetable Cart", two_weeks),
        ("onion", 22.0, 1.0, "kg", "dmart", "DMart", three_weeks),

        # Other items
        ("eggs", 84.0, 12.0, "pieces", "kirana_1", "Sharma Kirana", today),
        ("eggs", 90.0, 12.0, "pieces", "reliance_fresh", "Reliance Fresh", last_week),
        ("wheat_flour", 295.0, 5.0, "kg", "reliance_fresh", "Reliance Fresh", today),
        ("wheat_flour", 280.0, 5.0, "kg", "dmart", "DMart", last_week),
        ("cooking_oil", 165.0, 1.0, "L", "dmart", "DMart", today),
        ("cooking_oil", 175.0, 1.0, "L", "kirana_1", "Sharma Kirana", last_week),
        ("toor_dal", 165.0, 1.0, "kg", "dmart", "DMart", today),
        ("toor_dal", 180.0, 1.0, "kg", "big_basket", "BigBasket", last_week),
        ("tomato", 18.0, 1.0, "kg", "local_vendor", "Green Vegetable Cart", today),
        ("tomato", 22.0, 1.0, "kg", "reliance_fresh", "Reliance Fresh", last_week),
        ("potato", 30.0, 1.0, "kg", "local_vendor", "Green Vegetable Cart", today),
        ("potato", 28.0, 1.0, "kg", "dmart", "DMart", last_week),
    ]

    added = 0
    for canonical, price, qty, unit, store_id, store_name, obs_date in prices:
        obs = PriceObservation(
            canonical_name=canonical,
            price=price,
            quantity=qty,
            unit=unit,
            store_id=store_id,
            store_name=store_name,
            observation_date=obs_date,
            notes="demo_seed",
        )
        db.record_price(obs)
        added += 1

    return added


def seed_shopping_list(db: Database) -> int:
    existing = db.get_active_shopping_list()
    if existing:
        return 0

    sl = db.create_shopping_list(name="Weekly Grocery Run", goal="Stock up for the week")

    items = [
        ("milk", 2.0, "L", "must_buy", "Only 1.5L left, family uses 0.5L/day"),
        ("coriander", 2.0, "bunch", "must_buy", "Need fresh for weekend cooking"),
        ("tomato", 1.0, "kg", "must_buy", "Almost out, 0.3kg left"),
        ("bread", 1.0, "loaf", "optional", "Current loaf expires in 4 days"),
        ("toor_dal", 1.0, "kg", "must_buy", "Running low on dal"),
        ("biscuits", 3.0, "pack", "optional", "Kids want Parle-G"),
        ("toothpaste", 1.0, "tube", "must_buy", "Colgate almost empty"),
    ]

    for canonical, qty, unit, priority, reason in items:
        item = ShoppingListItem(
            canonical_name=canonical,
            requested_quantity=qty,
            unit=unit,
            priority=priority,
            reason=reason,
        )
        db.add_list_item(sl.list_id, item)

    return len(items)


def seed_purchase_events(db: Database) -> int:
    today = datetime.now()
    events = [
        ("milk", 1.0, "L", 64.0, "kirana_1", "Sharma Kirana", today - timedelta(days=1)),
        ("rice", 5.0, "kg", 680.0, "dmart", "DMart", today - timedelta(days=7)),
        ("eggs", 12.0, "pieces", 84.0, "kirana_1", "Sharma Kirana", today - timedelta(days=7)),
        ("onion", 2.0, "kg", 40.0, "local_vendor", "Green Vegetable Cart", today - timedelta(days=7)),
        ("wheat_flour", 5.0, "kg", 295.0, "reliance_fresh", "Reliance Fresh", today - timedelta(days=7)),
        ("cooking_oil", 1.0, "L", 165.0, "dmart", "DMart", today - timedelta(days=14)),
        ("toor_dal", 1.0, "kg", 165.0, "dmart", "DMart", today - timedelta(days=14)),
        ("toothpaste", 1.0, "tube", 99.0, "dmart", "DMart", today - timedelta(days=14)),
        ("butter", 0.5, "kg", 235.0, "reliance_fresh", "Reliance Fresh", today - timedelta(days=7)),
        ("bread", 1.0, "loaf", 55.0, "kirana_1", "Sharma Kirana", today - timedelta(days=1)),
    ]

    added = 0
    for canonical, qty, unit, price, store_id, store_name, ts in events:
        event = PurchaseEvent(
            canonical_name=canonical,
            quantity=qty,
            unit=unit,
            total_price=price,
            currency="INR",
            source_type="manual",
            store_name=store_name,
            confirmed=True,
            timestamp=ts,
        )
        db.add_purchase_event(event)
        added += 1

    return added


def seed_traces(db: Database) -> int:
    traces_data = [
        {
            "input_type": "vision",
            "user_goal": "market_lens",
            "perception": {"items_detected": ["milk", "bread", "eggs"], "image": True, "audio": False},
            "decision": {"decision_count": 3, "items": ["milk:buy", "bread:optional", "eggs:skip"]},
            "tool_calls": [{"tool_name": "compare_visible_item_to_inventory", "args": {"items": ["milk", "bread", "eggs"]}}],
            "response": "<div>Market Lens: 1 buy, 1 optional, 1 skip</div>",
            "confirmation": "confirmed-buy",
        },
        {
            "input_type": "text",
            "user_goal": "Plan shopping for the week",
            "perception": {"goal": "Weekly grocery run", "item_count": 7},
            "decision": {"must_buy": 5, "optional": 2, "skip": 0},
            "tool_calls": [{"tool_name": "create_or_update_shopping_list", "args": {"items": 7}}],
            "response": "<div>Created shopping list with 7 items</div>",
            "confirmation": "auto-summarized",
        },
        {
            "input_type": "text",
            "user_goal": "ask_shopstack",
            "perception": {"query": "Do we have milk?"},
            "decision": {"response_type": "ask_shopstack", "found": True},
            "tool_calls": [{"tool_name": "find_item", "args": {"query": "milk"}}],
            "response": "<div>Found Amul Taaza Milk (1.5L) in Fridge</div>",
            "confirmation": "responded",
        },
        {
            "input_type": "form",
            "user_goal": "add_purchase",
            "perception": {"item": "rice", "quantity": 8, "store": "DMart"},
            "decision": {"action": "add_inventory_item", "lot_id": "demo_lot"},
            "tool_calls": [{"tool_name": "add_inventory_item", "args": {"name": "rice", "qty": 8}}],
            "response": "<div>Added India Gate Basmati (8kg)</div>",
            "confirmation": "confirmed-by-user",
        },
        {
            "input_type": "form",
            "user_goal": "complete_shopping_list",
            "perception": {"goal": "Weekly Grocery Run", "item_count": 7, "added_count": 5},
            "decision": {"action": "mark_list_complete"},
            "tool_calls": [],
            "response": "<div>Completed list with 5 items added to inventory</div>",
            "confirmation": "auto-confirmed",
        },
    ]

    added = 0
    for t in traces_data:
        create_trace(
            db,
            input_type=t["input_type"],
            user_goal=t["user_goal"],
            redacted_user_request=t["user_goal"],
            perception=t["perception"],
            inventory_context={},
            decision=t["decision"],
            proposed_tool_calls=t["tool_calls"],
            final_response=t["response"],
            human_confirmation=t["confirmation"],
        )
        added += 1

    return added


def seed_field_notes(db: Database) -> None:
    notes = """## Kitchen Notes

- Milk delivery: Sharma Kirana delivers by 7 AM, best to order previous night
- Tomato prices spike on weekends, buy from local vendor on weekdays
- DMart has best prices for staples (rice, dal, oil) but fresh produce is better at the cart

## Price Watch

- Onion prices trending up: ₹22 → ₹40 in 3 weeks
- Rice prices softening: ₹730 → ₹680 in 3 weeks
- Milk stable at ₹60-68 across stores

## Recipes This Week

- Dal chawal (need toor dal + rice)
- Tomato onion sabzi (need more tomatoes)
- Egg curry (eggs expiring soon, use by Thursday)
"""
    db.set_config_value("field_notes_markdown", notes)


def main():
    parser = argparse.ArgumentParser(description="Seed ShopStack demo data")
    parser.add_argument("--db", default=None, help="Database path (default: settings.db_path)")
    parser.add_argument("--reset", action="store_true", help="Clear existing data before seeding")
    args = parser.parse_args()

    db_path = args.db or settings.db_path
    if args.reset:
        for suffix in ("", "-shm", "-wal"):
            f = db_path + suffix
            if os.path.exists(f):
                os.remove(f)
        print(f"Cleared existing database: {db_path}")

    db = Database(db_path)

    print("Seeding ShopStack demo data...")
    stores = seed_stores(db)
    print(f"  Stores: {stores}")

    inv = seed_inventory(db)
    print(f"  Inventory: {inv} items")

    prices = seed_prices(db)
    print(f"  Price observations: {prices}")

    sl = seed_shopping_list(db)
    print(f"  Shopping list items: {sl}")

    purchases = seed_purchase_events(db)
    print(f"  Purchase events: {purchases}")

    traces = seed_traces(db)
    print(f"  Agent traces: {traces}")

    seed_field_notes(db)
    print("  Field notes: configured")

    db.close()
    print(f"\nDone! Database: {db_path}")
    print(f"Run: uv run python app.py")


if __name__ == "__main__":
    main()
