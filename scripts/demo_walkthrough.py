"""ShopStack demo walkthrough — stepwise narration of household data flow.

Canonical run path (preferred):
    uv run python scripts/demo_walkthrough.py
    .venv/bin/python scripts/demo_walkthrough.py

The ``shopstack`` package is importable directly because the project
is installed in editable mode (``pip install -e .`` / ``uv sync``).
No ``sys.path`` manipulation is required.

Walks the user through inventory → market lens → shopping list →
classification → output, exercising the same code paths the Gradio
app uses in production.
"""
from __future__ import annotations

from shopstack.config import settings
from shopstack.decisions import classify_all
from shopstack.persistence.database import Database
from shopstack.tools.registry import ToolRegistry

DEMO_ITEMS = [
    {"canonical_name": "milk", "display_name": "Milk", "quantity": 2.0, "unit": "liter", "price": 74.0, "store": "local milk booth", "location": "fridge", "category": "dairy"},
    {"canonical_name": "rice", "display_name": "Basmati Rice", "quantity": 5.0, "unit": "kg", "price": 410.0, "store": "Big Bazaar", "location": "pantry", "category": "grains"},
    {"canonical_name": "eggs", "display_name": "Eggs", "quantity": 12.0, "unit": "pieces", "price": 96.0, "store": "Morning Eggstop", "location": "fridge_top", "category": "protein"},
    {"canonical_name": "onion", "display_name": "Onion", "quantity": 1.5, "unit": "kg", "price": 32.0, "store": "Local Vendor", "location": "pantry_mid", "category": "vegetable"},
    {"canonical_name": "toothpaste", "display_name": "Toothpaste", "quantity": 1.0, "unit": "unit", "price": 129.0, "store": "Apna Store", "location": "bathroom_cabinet", "category": "personal care"},
    {"canonical_name": "olive oil", "display_name": "Olive Oil", "quantity": 1.0, "unit": "L", "price": 690.0, "store": "Supermart", "location": "pantry_mid", "category": "cooking"},
    {"canonical_name": "curd", "display_name": "Curd", "quantity": 0.5, "unit": "kg", "price": 48.0, "store": "Fresh Dairy", "location": "fridge", "category": "dairy"},
    {"canonical_name": "bread", "display_name": "Whole Wheat Bread", "quantity": 1.0, "unit": "loaf", "price": 55.0, "store": "Apna Store", "location": "fridge_top", "category": "bakery"},
    {"canonical_name": "potato", "display_name": "Potato", "quantity": 2.0, "unit": "kg", "price": 30.0, "store": "Local Vendor", "location": "pantry_mid", "category": "vegetable"},
    {"canonical_name": "butter", "display_name": "Butter", "quantity": 0.25, "unit": "kg", "price": 120.0, "store": "Big Bazaar", "location": "fridge", "category": "dairy"},
]

PRICE_OBSERVATIONS = [
    ("milk", 74.0, 1.0, "liter", "local milk booth"),
    ("milk", 72.0, 1.0, "liter", "Big Bazaar"),
    ("rice", 410.0, 5.0, "kg", "Big Bazaar"),
    ("rice", 425.0, 5.0, "kg", "Supermart"),
    ("eggs", 96.0, 12.0, "pieces", "Morning Eggstop"),
    ("eggs", 102.0, 12.0, "pieces", "Big Bazaar"),
    ("onion", 32.0, 1.0, "kg", "Local Vendor"),
    ("onion", 35.0, 1.0, "kg", "Big Bazaar"),
    ("toothpaste", 129.0, 1.0, "unit", "Apna Store"),
    ("olive oil", 690.0, 1.0, "L", "Supermart"),
    ("curd", 48.0, 0.5, "kg", "Fresh Dairy"),
    ("bread", 55.0, 1.0, "loaf", "Apna Store"),
    ("potato", 30.0, 1.0, "kg", "Local Vendor"),
    ("butter", 120.0, 0.25, "kg", "Big Bazaar"),
    ("milk", 76.0, 1.0, "liter", "Fresh Dairy"),
    ("eggs", 88.0, 6.0, "pieces", "Local Vendor"),
]

SHOPPING_LIST_ITEMS = [
    {"canonical_name": "eggs", "requested_quantity": 6, "unit": "pieces", "priority": "must_buy", "reason": "Only a few left, need for weekend cooking"},
    {"canonical_name": "bread", "requested_quantity": 1, "unit": "loaf", "priority": "must_buy", "reason": "Almost finished"},
    {"canonical_name": "milk", "requested_quantity": 2, "unit": "liter", "priority": "must_buy", "reason": "Running low, 2L for the week"},
    {"canonical_name": "tomato", "requested_quantity": 1, "unit": "kg", "priority": "must_buy", "reason": "No tomatoes in stock"},
    {"canonical_name": "cheese", "requested_quantity": 1, "unit": "pack", "priority": "optional", "reason": "Nice to have for sandwiches"},
    {"canonical_name": "coriander", "requested_quantity": 1, "unit": "bunch", "priority": "optional", "reason": "Fresh garnish for dinner"},
]


def seed_inventory(db: Database, tools: ToolRegistry) -> int:
    existing = db.get_inventory()
    if existing:
        return 0
    count = 0
    for item in DEMO_ITEMS:
        tools.add_inventory_item(
            canonical_name=item["canonical_name"],
            display_name=item["display_name"],
            quantity=item["quantity"],
            unit=item["unit"],
            storage_location_id=item["location"],
            category=item["category"],
            price_paid=item["price"],
            source_event_id="demo_walkthrough",
        )
        count += 1
    return count


def seed_prices(db: Database, tools: ToolRegistry) -> int:
    count = 0
    for canonical, price, qty, unit, store in PRICE_OBSERVATIONS:
        tools.record_price_observation(
            canonical_name=canonical,
            price=price,
            quantity=qty,
            unit=unit,
            store_name=store,
        )
        count += 1
    return count


def create_shopping_list(db: Database, tools: ToolRegistry) -> str | None:
    existing = db.get_active_shopping_list()
    if existing:
        return existing.list_id
    result = tools.create_or_update_shopping_list(
        goal="Weekly grocery restock",
        items=SHOPPING_LIST_ITEMS,
    )
    return result["list"]["list_id"]


def show_classification(db: Database, tools: ToolRegistry) -> None:
    decision_set = classify_all(db, tools)

    buy = len(decision_set.buy)
    skip = len(decision_set.skip)
    optional = len(decision_set.optional)
    use_soon = len(decision_set.use_soon)

    print(f"    Total items evaluated: {len(decision_set.decisions)}")
    print(f"    {'Buy':12s}{buy}")
    print(f"    {'Skip':12s}{skip}")
    print(f"    {'Optional':12s}{optional}")
    print(f"    {'Use Soon':12s}{use_soon}")

    relevant = [d for d in decision_set.decisions if d.shopping_list_status == "on_list"]
    if relevant:
        print()
        for d in relevant:
            icon = {"buy": "✓", "skip": "–", "optional": "?"}.get(d.action, " ")
            print(f"    [{icon}] {d.display_name:25s} → {d.action:10s}  {d.reason[:65]}")


def show_inventory_summary(db: Database) -> None:
    all_inv = db.get_inventory()
    active = [lot for lot in all_inv if lot.status == "active"]
    total_qty = sum(lot.quantity for lot in active)
    categories = sorted({lot.category for lot in active if lot.category})
    locations = sorted({lot.storage_location_id for lot in active if lot.storage_location_id})
    print(f"    Active lots: {len(active)}")
    print(f"    Total units: {total_qty:.1f}")
    print(f"    Categories:  {', '.join(categories) if categories else 'none'}")
    print(f"    Locations:   {', '.join(locations) if locations else 'none'}")

    price_count = db.conn.execute("SELECT COUNT(*) FROM price_observations").fetchone()[0]
    print(f"    Price obs:   {price_count}")


def show_shopping_list_summary(db: Database) -> None:
    active = db.get_active_shopping_list()
    if not active:
        print("    No active shopping list.")
        return
    pending = [i for i in active.items if i.status == "pending"]
    must_buy = [i for i in pending if i.priority == "must_buy"]
    optional = [i for i in pending if i.priority == "optional"]
    print(f"    Goal: {active.goal or '(none)'}")
    print(f"    Items: {len(active.items)} total, {len(pending)} pending")
    print(f"    Must-buy: {len(must_buy)}  |  Optional: {len(optional)}")

    for item in pending:
        qty_s = f"{item.requested_quantity} {item.unit}" if item.requested_quantity and item.unit else ""
        pri = {"must_buy": "!", "optional": "?"}.get(item.priority, " ")
        print(f"    [{pri}] {item.canonical_name:25s} {qty_s:15s}  {item.reason[:40]}")


def main() -> None:
    db = Database(settings.db_path)
    tools = ToolRegistry(db)

    section_gap = "  " + "─" * 56

    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║        ShopStack  —  Demo Walkthrough               ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    print("  Step 1  │  Seed demo inventory")
    print(section_gap)
    inv_count = seed_inventory(db, tools)
    if inv_count:
        print(f"  Added {inv_count} items (milk, rice, eggs, onion, ...)")
    else:
        print("  Inventory already populated — reusing existing data")
    print()

    print("  Step 2  │  Seed price observations")
    print(section_gap)
    price_count = seed_prices(db, tools)
    print(f"  Recorded {price_count} price observations across stores")
    print()

    print("  Step 3  │  Create shopping list")
    print(section_gap)
    list_id = create_shopping_list(db, tools)
    active = db.get_active_shopping_list()
    item_count = len(active.items) if active and active.items else 0
    print(f"  Active shopping list ({list_id[:8]}...) with {item_count} items")
    if active and active.items:
        for item in active.items:
            pri = "⚡" if item.priority == "must_buy" else "·"
            qty_s = f"{item.requested_quantity} {item.unit}" if item.requested_quantity and item.unit else ""
            print(f"    {pri} {item.canonical_name:22s} {qty_s:12s}")
    print()

    print("  Step 4  │  Classify list against inventory")
    print(section_gap)
    show_classification(db, tools)
    print()

    print("  Step 5  │  Summary")
    print(section_gap)
    show_inventory_summary(db)
    print()
    show_shopping_list_summary(db)
    print()
    print("  " + "─" * 56)
    print("  Demo walkthrough complete.")
    print(f"  Database: {db.db_path}")
    print()

    db.close()


if __name__ == "__main__":
    main()
