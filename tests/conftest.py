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
