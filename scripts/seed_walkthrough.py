import os
import sys
from datetime import datetime, timedelta

# Ensure shopstack is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shopstack.persistence.database import Database
from shopstack.schemas.models import (
    InventoryLot,
    PurchaseEvent,
    ShoppingList,
    ShoppingListItem,
    Trace,
    ToolCall,
    HouseholdLocation,
    MovementEvent
)

def seed():
    print("Seeding ShopStack Database for Demo Walkthrough...")
    db = Database()
    
    # 1. Typical Indian Household Locations
    # _seed_locations already adds basics, but we can add specifics
    locs = [
        HouseholdLocation(location_id="rice_drum", name="Rice Drum", parent_location_id="kitchen", location_type="cabinet"),
        HouseholdLocation(location_id="atta_bin", name="Atta Bin", parent_location_id="kitchen", location_type="cabinet"),
        HouseholdLocation(location_id="onion_basket", name="Onion Basket", parent_location_id="kitchen", location_type="shelf"),
    ]
    for loc in locs:
        try:
            db.conn.execute(
                "INSERT INTO household_locations (location_id, name, parent_location_id, location_type) VALUES (?, ?, ?, ?)",
                (loc.location_id, loc.name, loc.parent_location_id, loc.location_type),
            )
        except Exception:
            pass # ignore duplicates if run twice
    db.conn.commit()
    print("✅ Locations seeded.")

    # 2. Previous purchase history & waste calculation
    now = datetime.now()
    
    # Milk - wasted
    lot_milk = InventoryLot(
        canonical_name="milk_full_cream",
        display_name="Full Cream Milk",
        category="Dairy",
        quantity=2,
        unit="L",
        status="discarded",
        storage_location_id="fridge_door",
        purchase_date=(now - timedelta(days=10)).date()
    )
    db.add_inventory_lot(lot_milk)
    db.conn.execute("INSERT INTO movement_events (movement_id, lot_id, to_location_id, timestamp) VALUES (?, ?, ?, ?)",
                    ("mov_1", lot_milk.lot_id, "trash", now.isoformat()))
    
    # Spinach - wasted
    lot_spinach = InventoryLot(
        canonical_name="spinach",
        display_name="Palak (Spinach)",
        category="Vegetables",
        quantity=500,
        unit="g",
        status="discarded",
        storage_location_id="fridge_drawer",
        purchase_date=(now - timedelta(days=5)).date()
    )
    db.add_inventory_lot(lot_spinach)
    db.conn.execute("INSERT INTO movement_events (movement_id, lot_id, to_location_id, timestamp) VALUES (?, ?, ?, ?)",
                    ("mov_2", lot_spinach.lot_id, "trash", now.isoformat()))
                    
    # Rice - consumed
    lot_rice = InventoryLot(
        canonical_name="basmati_rice",
        display_name="Basmati Rice",
        category="Grains",
        quantity=5,
        unit="kg",
        status="used",
        storage_location_id="rice_drum",
        purchase_date=(now - timedelta(days=30)).date()
    )
    db.add_inventory_lot(lot_rice)
    db.conn.execute("INSERT INTO movement_events (movement_id, lot_id, to_location_id, timestamp) VALUES (?, ?, ?, ?)",
                    ("mov_3", lot_rice.lot_id, "consumed", now.isoformat()))
                    
    db.conn.commit()
    print("✅ Purchase history & waste patterns seeded.")

    # 3. Active Shopping List showing off Decision Engine Confidence Levels
    sl = db.create_shopping_list(name="Weekend Grocery", goal="Prep for next week")
    items = [
        ShoppingListItem(canonical_name="milk_full_cream", requested_quantity=2, unit="L", priority="must_buy", reason="Staple, running out.", status="pending"),
        ShoppingListItem(canonical_name="spinach", requested_quantity=500, unit="g", priority="avoid_buying", reason="Wasted often in recent history. Suggest substituting.", status="pending"),
        ShoppingListItem(canonical_name="basmati_rice", requested_quantity=5, unit="kg", priority="optional", reason="Prices are high this week, wait if possible.", status="pending"),
        ShoppingListItem(canonical_name="maggi_noodles", requested_quantity=4, unit="pack", priority="must_buy", reason="User preference learned.", status="pending"),
        ShoppingListItem(canonical_name="onions", requested_quantity=2, unit="kg", priority="must_buy", reason="Staple ingredient.", status="pending"),
    ]
    for item in items:
        db.add_list_item(sl.list_id, item)

    print("✅ Active shopping list seeded.")

    # 4. Traces for the Trace Viewer
    t = Trace(
        input_type="voice",
        user_goal="Add milk to list",
        redacted_user_request="Hey, we are out of milk.",
        perception={"intent": "add_to_list", "entities": ["milk_full_cream"]},
        inventory_context={"milk_full_cream": {"in_stock": 0, "wasted_often": True}},
        decision={"action": "add_with_warning", "confidence": 0.85},
        proposed_tool_calls=[
            ToolCall(tool_name="add_to_shopping_list", args={"items": ["milk_full_cream"]}, success=True)
        ],
        final_response="Added Full Cream Milk to your shopping list. Note: You've discarded this twice recently."
    )
    db.save_trace(t)

    db.close()
    print("✅ Seed complete! Run 'uv run python app.py' to explore the demo state.")

if __name__ == '__main__':
    seed()
