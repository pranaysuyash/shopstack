"""Domain operations for shopping list management."""

from __future__ import annotations

from typing import Any

from shopstack.persistence.database import Database
from shopstack.schemas.models import ShoppingListItem


class ShoppingListRepo:
    def __init__(self, db: Database):
        self.db = db

    def create_or_update(
        self,
        items: list[dict[str, Any]] | None = None,
        goal: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        # Validate the complete batch before creating a list or adding any
        # item. A dependent planner value may have the wrong type even when
        # its reference path resolved successfully; that must fail closed
        # without leaving an empty list or a partial batch behind.
        validated_items = [
            ShoppingListItem(
                canonical_name=item_data.get("canonical_name", ""),
                requested_quantity=item_data.get("requested_quantity"),
                unit=item_data.get("unit"),
                priority=item_data.get("priority", "optional"),
                reason=item_data.get("reason", ""),
            )
            for item_data in (items or [])
        ]
        existing = self.db.get_active_shopping_list(user_id=user_id)
        if existing:
            sl = existing
            sl.goal = goal or sl.goal
        else:
            sl = self.db.create_shopping_list(goal=goal, user_id=user_id)

        if validated_items:
            for sl_item in validated_items:
                self.db.add_list_item(sl.list_id, sl_item, user_id=user_id)

        return {"list": self._load_list(sl.list_id)}

    def _load_list(self, list_id: str) -> dict[str, Any]:
        row = self.db.conn.execute(
            "SELECT * FROM shopping_lists WHERE list_id = ?", (list_id,)
        ).fetchone()
        if not row:
            return {}
        from shopstack.persistence.database import _row_to_list
        sl = _row_to_list(row, self.db.conn)
        return sl.model_dump()
