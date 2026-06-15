from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator

# Disable pytest-xdist for the whole test session.
#
# xdist has a known incompatibility with the sys.modules mocking pattern
# used in tests/test_new_providers.py (60+ tests that patch torch and
# transformers to None to simulate missing deps). xdist's module
# isolation loads C-extension modules before the patch runs, so the
# `import torch` inside the provider's _init() succeeds when it should
# fail, and all "test_not_available_when_deps_missing" tests fail.
#
# The fix is to disable xdist: `-p no:xdist` in the test command.
# This is added programmatically below via a pytest plugin.

# Set environment variables BEFORE any shopstack imports.
# ``shopstack.config`` instantiates ``settings = Settings()`` at module
# import time (line 112), so the env vars must be set first or the
# module-level ``settings.db_path`` is locked to ``data/shopstack.db``.
#
# Per motto_v3 §6, all backends are pinned to "mock" via env vars so the
# module-level Settings singleton (used by session-scoped _app_session
# fixture) also gets mock backends. LOCAL_AUTO_DOWNLOAD=False prevents
# test-time model downloads as defense-in-depth.
#
# DB PATH CHOICE (2026-06-14 fix, motto_v3 §0.6 reliability):
# Previously defaulted to ``:memory:``, which is per-connection in SQLite.
# That works for in-process tests (all connections share the main-thread
# connection via threading.local), but it breaks for any test that
# spawns Gradio worker threads — each worker gets a fresh empty
# in-memory DB and fails with "no such table: app_config". The fix is a
# session-scoped temp FILE so all threads see the same schema. The file
# is removed at session exit via the atexit hook below.
import atexit

_SESSION_DB_FD, _SESSION_DB_PATH = tempfile.mkstemp(
    suffix=".db", prefix="shopstack_test_session_"
)
os.close(_SESSION_DB_FD)


@atexit.register
def _cleanup_session_db() -> None:
    """Remove the session DB + WAL/SHM sidecars at process exit."""
    base = Path(_SESSION_DB_PATH)
    for suffix in ("", "-wal", "-shm"):
        base.with_suffix(base.suffix + suffix).unlink(missing_ok=True)


os.environ.setdefault("SHOPSTACK_DB_PATH", _SESSION_DB_PATH)
os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")
os.environ.setdefault("SHOPSTACK_OFF_THE_GRID", "true")
os.environ.setdefault("SHOPSTACK_PLANNER_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_STT_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_TTS_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_VISION_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_OBJECT_DETECTION_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_GROUNDING_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_SEGMENTATION_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_OCR_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_TOOL_CALL_PARSER_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_EMBEDDINGS_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_IMAGE_EDIT_BACKEND", "mock")
os.environ.setdefault("SHOPSTACK_IMAGE_GEN_BACKEND", "mock")

import pytest
from unittest.mock import patch

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry

# ── Stale __pycache__ reset ───────────────────────────────────────────
# Drift across passes can leave ``__pycache__/`` directories out of sync
# with the source files (e.g. when a module is extracted in the same pass
# that edited it, or when ``app.py`` is rewritten and other modules
# import from it). pytest's mtime check is reliable *within* a session
# but a stale cache from a prior session can leak into the first
# import of this session, producing transient ImportError failures
# that vanish on the second run.
#
# Clearing the project ``__pycache__/`` at conftest load time (before
# any fixture or test imports anything) guarantees a fresh compile
# on the first import. We skip ``.venv/`` (provider wheels) and
# ``node_modules/`` (we don't have any, but defensive).
#
# This is a one-time cost: ``find . -name __pycache__`` over the
# project takes ~50ms; the recompile cost is amortized because the
# existing fixtures re-import anyway.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _cache_dir in _PROJECT_ROOT.rglob("__pycache__"):
    if ".venv" in _cache_dir.parts or "node_modules" in _cache_dir.parts:
        continue
    shutil.rmtree(_cache_dir, ignore_errors=True)
del _cache_dir
del _PROJECT_ROOT

# Tables to clear between tests that share the session-scoped app module.
# Includes every household-scoped data table so preference signals, market
# snapshots, reconciliation events, etc. cannot leak across tests. The
# ``households``, ``household_members``, and ``app_config`` tables are
# intentionally preserved (the default household and the active_household_id
# key are reset explicitly in the ``app`` fixture below).
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
    "market_snapshots",
    "market_records",
    "market_record_components",
    "reconciliation_events",
    "preference_signals",
    "inventory_events",
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
            base = Path(path)
            # SQLite WAL mode creates sidecar files (.db-wal, .db-shm);
            # remove them all to prevent disk pressure from orphan files.
            for suffix in ("", "-wal", "-shm"):
                base.with_suffix(base.suffix + suffix).unlink(missing_ok=True)


@pytest.fixture()
def settings(db_path: str) -> Settings:
    # The project Settings API uses `db_path`, not the older `database_path` name.
    # Ignore the repo .env file during tests so defaults are deterministic.
    #
    # Per motto_v3 §6: tests must be deterministic. When real backend deps
    # are installed (funasr, torch, sentence-transformers, etc.) the
    # ProviderRegistry loads real providers that fail at model-weight-download
    # time (local_auto_download=False), producing empty/error results that
    # make tests non-deterministic. Pinning all backends to "mock" ensures
    # every unit test exercises the mock contract with known outputs.
    # Real-provider validation happens via Modal Tier 4 benches, not unit tests.
    return Settings(
        _env_file=None,
        db_path=db_path,
        off_the_grid=True,
        local_auto_download=False,
        planner_backend="mock",
        stt_backend="mock",
        tts_backend="mock",
        vision_backend="mock",
        object_detection_backend="mock",
        grounding_backend="mock",
        segmentation_backend="mock",
        ocr_backend="mock",
        tool_call_parser_backend="mock",
        embeddings_backend="mock",
        image_edit_backend="mock",
        image_gen_backend="mock",
    )


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


# ── Pytest hooks ──────────────────────────────────────────────────────
# The "cache issue" that recurred across multiple passes turned out to be
# drift-introduced import-time errors hidden by stale ``__pycache__``
# bytecode. The module-level cache clear at the top of this conftest
# surfaces those errors on the first test run of a fresh checkout.
# The two hooks below are defense-in-depth + future diagnostics.

def pytest_configure(config):
    """Re-clear ``__pycache__`` AFTER pytest's collection phase and
    disable pytest-xdist.

    The module-level clear at the top of this file runs before any
    tests are collected. This hook re-clears after collection but
    before test execution — catches any bytecode that pytest's
    collection phase may have generated by importing test files
    early (e.g., for parametrize IDs).

    xdist is also blocked here because of a known incompatibility
    with the sys.modules mocking pattern in tests/test_new_providers.py
    (60+ tests that patch torch/transformers to None to simulate
    missing deps). xdist's module isolation loads C-extension modules
    before the patch runs, so the `import torch` inside the provider's
    _init() succeeds when it should fail. See the module-level comment
    at the top of this file for the full rationale.
    """
    project_root = Path(__file__).resolve().parent.parent
    cleared = 0
    for cache_dir in project_root.rglob("__pycache__"):
        if ".venv" in cache_dir.parts or "node_modules" in cache_dir.parts:
            continue
        shutil.rmtree(cache_dir, ignore_errors=True)
        cleared += 1
    if cleared:
        logging.getLogger(__name__).debug(
            "pytest_configure: cleared %d __pycache__ directories", cleared
        )

    # Disable xdist for this session
    try:
        import xdist  # noqa: F401
        config.pluginmanager.set_blocked("xdist")
        logging.getLogger(__name__).debug(
            "pytest_configure: blocked pytest-xdist plugin (incompatible with sys.modules mocking in test_new_providers.py)"
        )
    except ImportError:
        pass


def pytest_unconfigure(config):
    """Diagnostic: log session-level state on shutdown.

    If the "cache issue" ever recurs, this is the place to add
    introspection (e.g., ``sys.modules`` contents, ``app_context``
    global state, dashboard cache size, etc.). For now it just
    logs a marker so we can correlate the cache-clear event with
    test pass/fail events.
    """
    logging.getLogger(__name__).debug(
        "pytest_unconfigure: session ended; cache state preserved for next invocation"
    )
