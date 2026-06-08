from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry


@pytest.fixture()
def db_path() -> Generator[str, None, None]:
    path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        yield path
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


@pytest.fixture()
def settings(db_path: str) -> Settings:
    # The project Settings API uses `db_path`, not the older `database_path` name.
    # Ignore the repo .env file during tests so defaults are deterministic.
    return Settings(_env_file=None, db_path=db_path, off_the_grid=True,
                    stt_backend="mock", tts_backend="mock")


@pytest.fixture()
def db(settings: Settings) -> Database:
    return Database(settings.db_path)


@pytest.fixture()
def providers(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry(settings)


@pytest.fixture()
def tool_registry(db: Database) -> ToolRegistry:
    return ToolRegistry(db)


@pytest.fixture()
def planner(db: Database, tool_registry: ToolRegistry, providers: ProviderRegistry) -> PlannerEngine:
    return PlannerEngine(db, tool_registry, providers)


# Seeded fixtures for workflow tests
@pytest.fixture()
def seeded_inventory(db: Database, tool_registry: ToolRegistry):
    """Seed demo inventory for testing workflows."""
    from shopstack.ui.screens.inventory import DEMO_SEED_INVENTORY
    for item in DEMO_SEED_INVENTORY:
        name = item.get("display_name", item.get("canonical_name", ""))
        tool_registry.add_inventory_item(
            canonical_name=str(item.get("canonical_name")).strip(),
            display_name=str(name).strip(),
            quantity=float(item.get("quantity", 1.0)),
            unit=str(item.get("unit", "unit")),
            storage_location_id=str(item.get("location", "kitchen")),
            category=str(item.get("category", "")),
            price_paid=float(item.get("price", 0.0) or 0.0),
            source_event_id="test_seed",
        )
        if item.get("price") and item.get("store"):
            tool_registry.record_price_observation(
                canonical_name=item.get("canonical_name", ""),
                price=float(item.get("price", 0.0)),
                quantity=float(item.get("quantity", 1.0)),
                unit=str(item.get("unit", "unit")),
                store_name=str(item.get("store", "")),
            )
    return db


@pytest.fixture()
def seeded_shopping_list(db: Database, tool_registry: ToolRegistry):
    """Create a sample shopping list for testing."""
    items = [
        {"canonical_name": "milk", "requested_quantity": 2.0, "unit": "L", "priority": "must_buy", "reason": "Low stock"},
        {"canonical_name": "bread", "requested_quantity": 1.0, "unit": "loaf", "priority": "must_buy", "reason": "Weekly staple"},
        {"canonical_name": "tomato", "requested_quantity": 1.0, "unit": "kg", "priority": "optional", "reason": "Nice to have"},
    ]
    result = tool_registry.create_or_update_shopping_list(items=items, goal="Weekly Groceries")
    return db, result.get("list", {}).get("list_id", "")


@pytest.fixture()
def seeded_price_history(db: Database, tool_registry: ToolRegistry):
    """Seed price observations for testing."""
    observations = [
        ("milk", 64.0, 2.0, "L", "Sharma Kirana"),
        ("milk", 70.0, 2.0, "L", "DMart"),
        ("rice", 680.0, 5.0, "kg", "Big Bazaar"),
        ("rice", 650.0, 5.0, "kg", "Local Vendor"),
        ("onion", 32.0, 1.0, "kg", "Local Vendor"),
    ]
    for canonical, price, qty, unit, store in observations:
        tool_registry.record_price_observation(
            canonical_name=canonical,
            price=price,
            quantity=qty,
            unit=unit,
            store_name=store,
        )
    return db


@pytest.fixture()
def seeded_traces(db: Database):
    """Seed workflow traces for testing."""
    from shopstack.traces.export import create_trace
    trace_ids = []
    for i in range(3):
        trace = create_trace(
            db,
            input_type="text" if i % 2 == 0 else "voice",
            user_goal=f"test_workflow_{i}",
            redacted_user_request=f"test request {i}",
            perception={"items": [f"item_{i}"]},
            inventory_context={"total_items": i + 1},
            decision={"action": "test", "items": [f"item_{i}"]},
            proposed_tool_calls=[{"tool_name": "test_tool", "args": {}}],
            final_response=f"Test response {i}",
            human_confirmation="auto-confirmed",
        )
        trace_ids.append(trace.trace_id)
    return db, trace_ids