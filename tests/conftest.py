from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry


@pytest.fixture
def db_path() -> Generator[str, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def db(db_path: str) -> Database:
    return Database(db_path)


@pytest.fixture
def settings() -> Settings:
    return Settings(database_path=":memory:", off_the_grid=True)


@pytest.fixture
def providers(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry(settings)


@pytest.fixture
def tool_registry(db: Database) -> ToolRegistry:
    return ToolRegistry(db)
