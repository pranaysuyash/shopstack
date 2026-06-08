from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Generator

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.providers.registry import ProviderRegistry
from shopstack.schemas.models import InventoryLot, PriceObservation
from shopstack.tools.registry import ToolRegistry


SEED_ITEMS = [
    ("rice", "Basmati Rice", "grains", 5.0, "kg", "pantry", 450.0),
    ("wheat_flour", "Aashirvaad Atta", "grains", 10.0, "kg", "pantry", 380.0),
    ("toor_dal", "Toor Dal", "pulses", 2.0, "kg", "pantry", 180.0),
    ("moong_dal", "Moong Dal", "pulses", 1.0, "kg", "pantry", 150.0),
    ("chana_dal", "Chana Dal", "pulses", 1.5, "kg", "pantry", 120.0),
    ("mustard_oil", "Fortune Mustard Oil", "oils", 1.0, "L", "pantry", 185.0),
    ("sunflower_oil", "Sunflower Oil", "oils", 1.0, "L", "pantry", 140.0),
    ("salt", "Tata Salt", "spices", 1.0, "kg", "spice_box", 25.0),
    ("turmeric", "Turmeric Powder", "spices", 0.2, "kg", "spice_box", 80.0),
    ("red_chilli", "Red Chilli Powder", "spices", 0.2, "kg", "spice_box", 90.0),
    ("cumin", "Jeera", "spices", 0.1, "kg", "spice_box", 120.0),
    ("coriander_powder", "Dhania Powder", "spices", 0.2, "kg", "spice_box", 60.0),
    ("garam_masala", "MDH Garam Masala", "spices", 0.1, "kg", "spice_box", 150.0),
    ("milk", "Amul Taaza", "dairy", 2.0, "L", "fridge", 64.0),
    ("curd", "Amul Curd", "dairy", 0.5, "kg", "fridge", 40.0),
    ("paneer", "Amul Paneer", "dairy", 0.2, "kg", "fridge", 90.0),
    ("butter", "Amul Butter", "dairy", 0.1, "kg", "fridge", 56.0),
    ("onion", "Onion", "vegetables", 2.0, "kg", "fridge_drawer", 40.0),
    ("tomato", "Tomato", "vegetables", 1.0, "kg", "fridge_drawer", 30.0),
    ("potato", "Potato", "vegetables", 3.0, "kg", "fridge_drawer", 45.0),
    ("green_chilli", "Green Chilli", "vegetables", 0.1, "kg", "fridge_drawer", 15.0),
    ("ginger", "Ginger", "vegetables", 0.2, "kg", "fridge_drawer", 30.0),
    ("garlic", "Garlic", "vegetables", 0.2, "kg", "fridge_drawer", 40.0),
    ("capsicum", "Capsicum", "vegetables", 0.5, "kg", "fridge_drawer", 50.0),
    ("coriander", "Coriander Leaves", "vegetables", 0.1, "kg", "fridge_drawer", 10.0),
    ("spinach", "Palak", "vegetables", 0.5, "kg", "fridge_drawer", 20.0),
    ("banana", "Banana", "fruits", 1.0, "dozen", "kitchen", 50.0),
    ("apple", "Apple", "fruits", 1.0, "kg", "kitchen", 180.0),
    ("lemon", "Lemon", "fruits", 0.5, "kg", "kitchen", 60.0),
    ("sugar", "Sugar", "staples", 2.0, "kg", "pantry", 90.0),
    ("tea", "Tata Tea Gold", "beverages", 0.5, "kg", "pantry", 220.0),
    ("coffee", "Nescafe Classic", "beverages", 0.2, "kg", "pantry", 200.0),
    ("biscuit", "Parle-G", "snacks", 1.0, "kg", "pantry", 80.0),
    ("bread", "Britannia Bread", "bakery", 1.0, "unit", "pantry", 40.0),
    ("egg", "Eggs", "protein", 1.0, "dozen", "fridge", 80.0),
    ("chicken", "Chicken Breast", "protein", 1.0, "kg", "freezer", 250.0),
    ("soap", "Dettol Soap", "hygiene", 3.0, "unit", "bathroom_cabinet", 45.0),
    ("shampoo", "Head & Shoulders", "hygiene", 1.0, "unit", "bathroom_cabinet", 200.0),
    ("toothpaste", "Colgate", "hygiene", 1.0, "unit", "bathroom_cabinet", 95.0),
    ("detergent", "Surf Excel", "cleaning", 2.0, "kg", "cleaning_shelf", 280.0),
    ("dish_soap", "Vim Liquid", "cleaning", 1.0, "unit", "cleaning_shelf", 110.0),
    ("floor_cleaner", "Lizol", "cleaning", 1.0, "L", "cleaning_shelf", 150.0),
    ("mosquito_repellent", "Good Knight", "household", 1.0, "unit", "bedroom", 85.0),
    ("paratha", "Frozen Paratha", "frozen", 1.0, "unit", "freezer", 120.0),
    ("peas", "Frozen Peas", "frozen", 0.5, "kg", "freezer", 70.0),
    ("cornflour", "Cornflour", "thickener", 0.5, "kg", "pantry", 50.0),
    ("baking_soda", "Baking Soda", "baking", 0.1, "kg", "pantry", 25.0),
    ("vinegar", "Synthetic Vinegar", "condiment", 1.0, "L", "pantry", 35.0),
    ("soy_sauce", "Ching's Soy Sauce", "condiment", 0.2, "L", "pantry", 55.0),
    ("honey", "Dabur Honey", "condiment", 0.5, "kg", "pantry", 200.0),
]

SEED_STORES = [
    ("store_dmart", "DMart", "Koramangala", "supermarket"),
    ("store_bigbazaar", "Big Bazaar", "HSR Layout", "supermarket"),
    ("store_sharma", "Sharma Kirana", "12th Main", "kirana"),
    ("store_more", "More Supermarket", "Indiranagar", "supermarket"),
    ("store_local", "Local Vendor", "Roadside", "pushcart"),
]


SAMPLE_RECEIPT_TEXT = """Sharma General Store
Date: 08/06/2026
Bill No: 1247

ONION 2 KG 64.00
TOMATO 1 KG 35.00
POTATO 3 KG 75.00
GREEN CHILLI 100 G 12.00
GINGER 200 GM 28.00
CORIANDER LEAVES 1 BUNCH 10.00
AMUL TAAZA MILK 2 L 128.00
BREAD 1 PCS 42.00
EGG 12 PCS 85.00
SURF EXCEL 1 KG 145.00
VIM LIQUID 1 PCS 110.00
TATA SALT 1 KG 25.00
TURMERIC POWDER 200 GM 78.00

Total: Rs. 837.00
GST: 0.00
Cash Paid: 900.00
Change: 63.00
"""


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(_env_file=None, db_path=":memory:", off_the_grid=True)


@pytest.fixture(scope="session")
def db(settings: Settings) -> Generator[Database, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = Database(path)
    yield database
    Path(path).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def providers(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry(settings)


@pytest.fixture(scope="session")
def tool_registry(db: Database) -> ToolRegistry:
    return ToolRegistry(db)


@pytest.fixture(scope="session")
def bench_db() -> Generator[Database, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = Database(path)

    today = date.today()
    for i, (cname, dname, cat, qty, unit, loc, price) in enumerate(SEED_ITEMS):
        lot = InventoryLot(
            canonical_name=cname,
            display_name=dname,
            category=cat,
            quantity=qty,
            unit=unit,
            storage_location_id=loc,
            purchase_date=today - timedelta(days=i % 14),
            price_paid=price,
        )
        database.add_inventory_lot(lot)

    stores_map: dict[str, str] = {}
    for sid, sname, sloc, stype in SEED_STORES:
        from shopstack.schemas.models import Store
        store = Store(store_id=sid, name=sname, location=sloc, store_type=stype)
        database.add_store(store)
        stores_map[sname] = sid

    store_names = list(stores_map.keys())
    for i in range(100):
        item = SEED_ITEMS[i % len(SEED_ITEMS)]
        cname = item[0]
        base_price = item[6]
        store_name = store_names[i % len(store_names)]
        variation = base_price * (1 + (i % 7 - 3) * 0.05)
        obs = PriceObservation(
            canonical_name=cname,
            quantity=item[3],
            unit=item[4],
            price=round(variation, 2),
            store_name=store_name,
            store_id=stores_map[store_name],
            observation_date=today - timedelta(days=i),
        )
        database.record_price(obs)

    for i in range(20):
        item = SEED_ITEMS[i % len(SEED_ITEMS)]
        from shopstack.schemas.models import PurchaseEvent
        event = PurchaseEvent(
            canonical_name=item[0],
            quantity=item[3],
            unit=item[4],
            total_price=item[6],
            source_type="manual",
            store_name=store_names[i % len(store_names)],
        )
        database.add_purchase_event(event)

    database.set_config_value("field_notes_markdown", "# Field Notes\n\nWeekly grocery planning notes.\n")

    from shopstack.schemas.models import ShoppingListItem
    sl = database.create_shopping_list(name="Weekly Groceries", goal="Restock essentials")
    for cname, qty, unit, priority in [
        ("milk", 2.0, "L", "must_buy"),
        ("bread", 1.0, "unit", "must_buy"),
        ("tomato", 1.0, "kg", "optional"),
        ("onion", 2.0, "kg", "must_buy"),
        ("egg", 1.0, "dozen", "must_buy"),
    ]:
        sli = ShoppingListItem(
            canonical_name=cname,
            requested_quantity=qty,
            unit=unit,
            priority=priority,
            reason="Benchmark seed",
        )
        database.add_list_item(sl.list_id, sli)

    yield database
    Path(path).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def bench_tools(bench_db: Database) -> ToolRegistry:
    return ToolRegistry(bench_db)


@pytest.fixture(scope="session")
def sample_receipt_text() -> str:
    return SAMPLE_RECEIPT_TEXT


@pytest.fixture()
def fresh_db() -> Generator[Database, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = Database(path)
    yield database
    Path(path).unlink(missing_ok=True)
