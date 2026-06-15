"""DATA-1 / SEC-4: household-scoping regression guard.

ShopStack data is household-scoped. Every read/write on inventory,
shopping lists, price observations, and traces accepts a ``user_id``
parameter that must be honored — data belonging to household-A must
never be visible to a query scoped to household-B.

This is a *regression guard*, not a rewrite. The DB layer makes
``user_id`` opt-in per method (a design tradeoff for ergonomics). This
test locks in the contract: if a future change drops or ignores the
``user_id`` parameter on any of these core methods, this test fails
loudly. It is the systemic defense against cross-household data leaks.

Scope: the highest-traffic read/write paths. Not exhaustive (every DB
method would be brittle), but covers the methods the planner, SMS
webhook, and UI tabs call most.
"""
from __future__ import annotations

from datetime import date

from shopstack.schemas.models import InventoryLot, PriceObservation, Trace


class TestHouseholdScopingGuard:
    """Verify the core household-isolation invariant holds on key paths."""

    HOUSEHOLD_A = "family-alpha"
    HOUSEHOLD_B = "family-bravo"

    def _ensure_households(self, db) -> None:
        """Register both test households + their owner members.

        The DB layer enforces membership on writes (require_write), so the
        households and an owner member must exist before any scoped write.
        This mirrors what a real deployment does: create household, add
        owner, then the owner can add inventory.
        """
        for hid in (self.HOUSEHOLD_A, self.HOUSEHOLD_B):
            if not any(h["household_id"] == hid for h in db.list_households()):
                db.add_household(hid, hid.replace("-", " ").title())
            try:
                db.add_household_member(hid, hid, role="owner")
            except Exception:
                pass  # already a member

    def _make_lot(self, name: str = "milk") -> InventoryLot:
        return InventoryLot(
            canonical_name=name,
            display_name=name.title(),
            quantity=2.0,
            unit="L",
            storage_location_id="fridge",
        )

    def test_inventory_write_scoped_then_read_isolated(self, db):
        """An item added to household-A is invisible to household-B."""
        self._ensure_households(db)
        db.add_inventory_lot(self._make_lot("rice"), user_id=self.HOUSEHOLD_A)
        db.add_inventory_lot(self._make_lot("bread"), user_id=self.HOUSEHOLD_B)

        a_items = db.get_inventory(user_id=self.HOUSEHOLD_A)
        b_items = db.get_inventory(user_id=self.HOUSEHOLD_B)

        a_names = {lot.canonical_name for lot in a_items}
        b_names = {lot.canonical_name for lot in b_items}
        assert "rice" in a_names and "bread" not in a_names
        assert "bread" in b_names and "rice" not in b_names

    def test_trace_write_scoped_then_read_isolated(self, db):
        """A trace created for household-A is invisible to household-B."""
        trace_a = Trace(input_type="test", user_goal="goal-a", user_id_hint=self.HOUSEHOLD_A)
        trace_b = Trace(input_type="test", user_goal="goal-b", user_id_hint=self.HOUSEHOLD_B)
        db.save_trace(trace_a, user_id=self.HOUSEHOLD_A)
        db.save_trace(trace_b, user_id=self.HOUSEHOLD_B)

        a_traces = db.get_traces(user_id=self.HOUSEHOLD_A)
        b_traces = db.get_traces(user_id=self.HOUSEHOLD_B)

        a_goals = {t.user_goal for t in a_traces}
        b_goals = {t.user_goal for t in b_traces}
        assert "goal-a" in a_goals and "goal-b" not in a_goals
        assert "goal-b" in b_goals and "goal-a" not in b_goals

    def test_price_observation_does_not_cross_households(self, db):
        """Price memory for household-A doesn't pollute household-B's history."""
        self._ensure_households(db)
        obs_a = PriceObservation(
            canonical_name="onion",
            price=40.0,
            quantity=1.0,
            unit="kg",
            observation_date=date.today(),
        )
        db.record_price(obs_a, user_id=self.HOUSEHOLD_A)
        # household-B should see no price history for onion
        b_history = db.get_price_history("onion", user_id=self.HOUSEHOLD_B)
        assert b_history == [] or len(b_history) == 0

    def test_shopping_list_scoped(self, db):
        """Shopping lists are household-isolated."""
        self._ensure_households(db)
        from shopstack.schemas.models import ShoppingListItem
        # Create active lists for each household with distinct items
        list_a = db.create_shopping_list(goal="list-A", user_id=self.HOUSEHOLD_A)
        db.add_list_item(list_a.list_id, ShoppingListItem(canonical_name="apples", requested_quantity=1.0), user_id=self.HOUSEHOLD_A)
        list_b = db.create_shopping_list(goal="list-B", user_id=self.HOUSEHOLD_B)
        db.add_list_item(list_b.list_id, ShoppingListItem(canonical_name="bananas", requested_quantity=1.0), user_id=self.HOUSEHOLD_B)
        a_list = db.get_active_shopping_list(user_id=self.HOUSEHOLD_A)
        b_list = db.get_active_shopping_list(user_id=self.HOUSEHOLD_B)
        if a_list and a_list.items:
            a_names = {item.canonical_name for item in a_list.items}
            assert "bananas" not in a_names
        if b_list and b_list.items:
            b_names = {item.canonical_name for item in b_list.items}
            assert "apples" not in b_names

    def test_unscoped_query_does_not_silently_mix(self, db):
        """A query WITHOUT user_id should not be silently scoped to a
        random household — it returns the default-household partition.

        This documents the current opt-in behavior: forgetting user_id
        returns default-household data (empty here), NOT a cross-household
        dump. If this invariant ever changes, this test surfaces it."""
        self._ensure_households(db)
        db.add_inventory_lot(self._make_lot("secret"), user_id=self.HOUSEHOLD_A)
        # Unscoped query (no user_id) — should not leak household-A data
        # into what callers expect to be the default partition.
        unscoped = db.get_inventory(user_id="")
        scoped_a = db.get_inventory(user_id=self.HOUSEHOLD_A)
        # The scoped query sees the item; the unscoped one must not see
        # household-A's items (it's the default partition, which is empty).
        scoped_a_names = {lot.canonical_name for lot in scoped_a}
        assert "secret" in scoped_a_names
        unscoped_names = {lot.canonical_name for lot in unscoped}
        assert "secret" not in unscoped_names
