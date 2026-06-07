from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry


@pytest.fixture(scope="session")
def settings() -> Settings:
    # Ignore the repo .env file during benchmark tests so provider selection is deterministic.
    return Settings(_env_file=None, database_path=":memory:", off_the_grid=True)


@pytest.fixture(scope="session")
def db() -> Generator[Database, None, None]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = Database(path)
    yield db
    Path(path).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def providers(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry(settings)


@pytest.fixture(scope="session")
def tool_registry(db: Database) -> ToolRegistry:
    return ToolRegistry(db)
