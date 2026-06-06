from __future__ import annotations

from shopstack.config import settings
from shopstack.model_registry import get_registry
from shopstack.persistence.database import Database
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry

db = Database(settings.db_path)
providers = ProviderRegistry(settings)
tools = ToolRegistry(db)
planner = PlannerEngine(db, tools, providers)
model_registry = get_registry()
