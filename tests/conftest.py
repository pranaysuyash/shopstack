from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import pytest
from unittest.mock import patch

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry

# Set environment variables BEFORE any test imports `app`.
# This ensures `from shopstack.config import settings` (at app import time)
# reads these values rather than the heavy real-model defaults.
import os
os.environ.setdefault("SHOPSTACK_PLANNER_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_STT_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_TTS_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_VISION_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_OCR_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_SEGMENTATION_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_EMBEDDINGS_BACKEND", "mock")

# Tables to clear between tests that share the session-scoped app module.
_APP_DATA_TABLES = [
    "inventory_lots",
    "shopping_list_items",
    "shopping_lists",
    "movement_events",
    "price_observations",
    "purchase_events",
    "traces",
    "household_locations",
    "stores",
]


@pytest.fixture(autouse=True)
def _clear_dashboard_cache():
    """Clear the dashboard state cache before every test.

    ``build_dashboard_state`` caches results for 60 s per user_id.
    Tests that call it with different inventory states would see stale
    data without this reset.
    """
    from shopstack.services.dashboard import clear_dashboard_cache
    clear_dashboard_cache()
    yield
    clear_dashboard_cache()


@pytest.fixture(autouse=True)
def _patch_decode_barcode():
    """Patch ``decode_barcode`` to return ``[]`` by default in all tests.

    This prevents real file I/O in mock-only tests (e.g. the barcode scanner
    trying to open ``fake-market-image.jpg``).  Tests that need actual barcode
    behaviour can unpatch by calling ``monkeypatch.undo()`` or applying their
    own patch inside the test body.
    """
    with patch("shopstack.scanner.decode_barcode", return_value=[]):
        yield


@pytest.fixture(scope="session")
def _app_session():
    """Import app module once per session with an in-memory database.

    Importing ``app`` triggers ``shopstack.app_context`` which bootstraps
    the ``ProviderRegistry`` — an expensive operation (~10s per invocation).
    Caching at session scope avoids that cost on every test.
    """
    import os
    os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")
    os.environ.setdefault("SHOPSTACK_PLANNER_BACKEND", "mock")
    import app as _app
    return _app


@pytest.fixture()
def app(_app_session):
    """Return the session-scoped app module, clearing all data tables between tests.

    Resets ``active_household_id`` to the default household ("default_household")
    so household-scoped screens find a valid context. Setting it to "" would
    break every screen that filters by household.
    """
    app_mod = _app_session
    conn = app_mod.db.conn
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in _APP_DATA_TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    app_mod.db._seed_locations()
    app_mod.db._seed_default_household()
    app_mod.db.active_household_id = "default_household"
    return app_mod


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
                    planner_backend="mock",
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
