"""Temporary, canonical ShopStack worlds for agent evaluation."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from shopstack.persistence.database import Database
from shopstack.repos.shopping_list import ShoppingListRepo
from shopstack.schemas.models import PreferenceSignal, PriceObservation
from shopstack.tools.registry import ToolRegistry


class IsolatedWorld:
    """A file-backed temporary DB, because ShopStack uses per-thread SQLite connections."""

    def __init__(self, initial_state: dict[str, Any] | None = None):
        self.initial_state = initial_state or {}
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.db: Database | None = None
        self.tools: ToolRegistry | None = None
        self.user_id = "default_household"

    def __enter__(self) -> "IsolatedWorld":
        self._tempdir = tempfile.TemporaryDirectory(prefix="shopstack-agent-eval-")
        path = Path(self._tempdir.name) / "world.db"
        self.db = Database(str(path))
        self.tools = ToolRegistry(self.db)
        self._seed(self.initial_state)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.db is not None:
            self.db.force_close_all_connections()
        if self._tempdir is not None:
            self._tempdir.cleanup()

    def _seed(self, state: dict[str, Any]) -> None:
        assert self.tools is not None and self.db is not None
        for item in state.get("inventory", []):
            self.tools.execute("add_inventory_item", **dict(item))
        shopping = state.get("shopping_list")
        if isinstance(shopping, dict):
            ShoppingListRepo(self.db).create_or_update(
                items=list(shopping.get("items", [])),
                goal=str(shopping.get("goal", "")),
                user_id=self.user_id,
            )
        for price in state.get("prices", []):
            self.db.record_price(PriceObservation(**price), user_id=self.user_id)
        for preference in state.get("preferences", []):
            self.db.add_preference_signal(PreferenceSignal(**preference), user_id=self.user_id)

    def snapshot(self) -> dict[str, Any]:
        assert self.db is not None
        inventory = self.db.get_inventory(user_id=self.user_id)
        shopping = self.db.get_active_shopping_list(user_id=self.user_id)
        return {
            "inventory": [lot.model_dump(mode="json") for lot in inventory],
            "shopping_list": shopping.model_dump(mode="json") if shopping else None,
            "prices": [
                price.model_dump(mode="json")
                for name in sorted({lot.canonical_name for lot in inventory})
                for price in self.db.get_price_history(name, user_id=self.user_id)
            ],
        }

    def inventory_for(self, canonical_name: str) -> list[Any]:
        assert self.db is not None
        return [
            lot for lot in self.db.get_inventory(user_id=self.user_id)
            if lot.canonical_name.lower() == canonical_name.lower()
        ]
