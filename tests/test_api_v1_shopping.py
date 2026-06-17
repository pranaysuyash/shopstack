"""Contract tests for ``/api/v1/shopping`` endpoints.

Coverage:
  * Auth-gating: all five endpoints require a bearer token.
  * GET active returns placeholder when no list exists.
  * GET active returns the current active list with items.
  * GET active response shape matches ShoppingListWire.
  * POST lists creates a new list with seed items.
  * POST lists returns 201 with correct shape.
  * POST lists with empty items creates an empty active list.
  * POST items appends to an existing list.
  * POST items response includes all items (old + new).
  * POST items to wrong household returns 404.
  * POST complete closes a list and returns added items.
  * POST complete with avoid_buying items skips them.
  * POST complete returns 404 for unknown/wrong household.
  * POST mark-purchased adds selected items to inventory.
  * POST mark-purchased returns 404 for unknown list.
  * POST mark-purchased rejects empty item_ids with 422.
  * Household scoping: one household's list doesn't leak to another.
"""
from __future__ import annotations

import os
import tempfile
from typing import Iterator

import pytest


@pytest.fixture
def temp_db(monkeypatch) -> Iterator[str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from shopstack.persistence.database import Database

    db = Database(path)
    yield path
    db.close()
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def db_handle(temp_db: str):
    from shopstack.persistence.database import Database

    db = Database(temp_db)
    yield db
    db.close()


@pytest.fixture
def v1_app(db_handle):
    from fastapi import FastAPI

    from shopstack import app_context
    from shopstack.api.v1.routers.shopping import router as shopping_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)
    # The shopping router reaches for tools.inventory via app_context.tools
    # when completing/purchasing. For basic list/create tests the ToolRegistry
    # is not needed, but we mount it for consistency.
    try:
        from shopstack.tools.registry import ToolRegistry
        monkey.setattr(app_context, "tools", ToolRegistry(db_handle), raising=False)
    except Exception:
        pass

    fastapi_app = FastAPI(title="shopstack-test-shopping")
    fastapi_app.include_router(shopping_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_shop") -> str:
    """Issue a bearer token and ensure the household exists + is writable."""
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    db_handle.add_household(household, household)
    # Writable households need an owner member (mirrors the production
    # create path). Without this, add_list_item's permission gate denies.
    try:
        db_handle.add_household_member(household, household, role="owner")
    except Exception:
        pass  # Idempotent if already exists
    return auth_mod.issue_token(
        db_handle, device_id="dev_shop", household_id=household,
    )["token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_list(client, token: str, items: list[dict] | None = None,
                 goal: str = "") -> dict:
    """Helper: POST /api/v1/shopping/lists and return the JSON body."""
    body = {"goal": goal}
    if items:
        body["items"] = items
    r = client.post("/api/v1/shopping/lists", json=body, headers=_hdr(token))
    assert r.status_code == 201, r.text
    return r.json()


# ── Auth gating ──────────────────────────────────────────────────


class TestShoppingAuth:
    def test_active_requires_token(self, client):
        assert client.get("/api/v1/shopping/active").status_code == 401

    def test_create_requires_token(self, client):
        assert client.post(
            "/api/v1/shopping/lists", json={},
        ).status_code == 401

    def test_add_items_requires_token(self, client):
        assert client.post(
            "/api/v1/shopping/lists/some_id/items",
            json={"items": [{"canonical_name": "milk"}]},
        ).status_code == 401

    def test_complete_requires_token(self, client):
        assert client.post(
            "/api/v1/shopping/lists/some_id/complete",
        ).status_code == 401

    def test_mark_purchased_requires_token(self, client):
        assert client.post(
            "/api/v1/shopping/lists/some_id/mark-purchased",
            json={"item_ids": ["abc"]},
        ).status_code == 401


# ── GET /api/v1/shopping/active ─────────────────────────────────


class TestGetActiveList:
    def test_no_active_list_returns_placeholder(self, client, db_handle):
        """When no list exists, returns empty placeholder with list_id=\"\". """
        token = _issue(db_handle)
        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["list_id"] == ""
        assert body["items"] == []
        assert body["is_active"] is True
        assert body["name"] == "Shopping List"

    def test_placeholder_shape_matches_schema(self, client, db_handle):
        """Placeholder response matches ShoppingListWire schema keys."""
        token = _issue(db_handle)
        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert "list_id" in body
        assert "name" in body
        assert "created_at" in body
        assert "updated_at" in body
        assert "goal" in body
        assert "is_active" in body
        assert "items" in body

    def test_after_create_returns_list(self, client, db_handle):
        """After creating a list, GET active returns it with items."""
        token = _issue(db_handle)
        created = _create_list(client, token, items=[{"canonical_name": "milk"}])
        list_id = created["list_id"]

        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["list_id"] == list_id
        assert len(body["items"]) == 1
        assert body["items"][0]["canonical_name"] == "milk"
        assert body["items"][0]["status"] == "pending"

    def test_active_list_shape(self, client, db_handle):
        """Active list response matches ShoppingListWire schema."""
        token = _issue(db_handle)
        _create_list(client, token, items=[{"canonical_name": "eggs"}])

        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert "list_id" in body
        assert body["is_active"] is True
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert "item_id" in item
        assert "canonical_name" in item
        assert "status" in item
        assert item["canonical_name"] == "eggs"
        assert item["status"] == "pending"

    def test_household_scoped(self, client, db_handle):
        """One household's active list is not visible to another."""
        token_a = _issue(db_handle, "hh_a")
        _create_list(client, token_a, items=[{"canonical_name": "milk"}])

        token_b = _issue(db_handle, "hh_b")
        r = client.get("/api/v1/shopping/active", headers=_hdr(token_b))
        assert r.status_code == 200
        body = r.json()
        # hh_b should see no active list (placeholder)
        assert body["list_id"] == ""
        assert body["items"] == []

    def test_multiple_creates_returns_most_recent(self, client, db_handle):
        """Creating multiple lists makes the most recent one active."""
        token = _issue(db_handle)
        first = _create_list(client, token)
        second = _create_list(client, token)

        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        # The most recently created list should be the active one.
        assert body["list_id"] == second["list_id"]


# ── POST /api/v1/shopping/lists ──────────────────────────────────


class TestCreateList:
    def test_create_empty_list(self, client, db_handle):
        """Creating a list with no items returns a valid list with empty items."""
        token = _issue(db_handle)
        body = _create_list(client, token)
        assert body["list_id"]
        assert body["items"] == []
        assert body["goal"] == ""
        assert body["is_active"] is True

    def test_create_with_items(self, client, db_handle):
        """Creating a list with seed items includes them in the response."""
        token = _issue(db_handle)
        body = _create_list(
            client, token,
            items=[
                {"canonical_name": "milk", "requested_quantity": 2, "unit": "L"},
                {"canonical_name": "bread"},
            ],
        )
        assert body["list_id"]
        names = {it["canonical_name"] for it in body["items"]}
        assert names == {"milk", "bread"}
        # Verify quantities
        milk = next(it for it in body["items"] if it["canonical_name"] == "milk")
        assert milk["requested_quantity"] == 2.0
        assert milk["unit"] == "L"

    def test_create_with_goal(self, client, db_handle):
        token = _issue(db_handle)
        body = _create_list(client, token, goal="Weekend groceries")
        assert body["goal"] == "Weekend groceries"

    def test_create_response_shape(self, client, db_handle):
        """Response matches ShoppingListWire schema."""
        token = _issue(db_handle)
        body = _create_list(client, token, items=[{"canonical_name": "test"}])
        assert "list_id" in body
        assert "name" in body
        assert "created_at" in body
        assert "updated_at" in body
        assert "goal" in body
        assert "is_active" in body
        assert "items" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["is_active"], bool)

    def test_create_list_then_active_returns_same_id(self, client, db_handle):
        """After creating a list, GET /active returns the same list_id."""
        token = _issue(db_handle)
        created = _create_list(client, token)
        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        assert r.json()["list_id"] == created["list_id"]


# ── POST /api/v1/shopping/lists/{id}/items ──────────────────────


class TestAddItems:
    def test_add_items_appends(self, client, db_handle):
        """Adding items to an existing list appends them."""
        token = _issue(db_handle)
        created = _create_list(client, token, items=[{"canonical_name": "milk"}])
        list_id = created["list_id"]

        r = client.post(
            f"/api/v1/shopping/lists/{list_id}/items",
            json={"items": [{"canonical_name": "butter"}, {"canonical_name": "cheese"}]},
            headers=_hdr(token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        names = {it["canonical_name"] for it in body["items"]}
        assert "milk" in names
        assert "butter" in names
        assert "cheese" in names

    def test_add_items_response_includes_all(self, client, db_handle):
        """The response includes the full list (not just new items)."""
        token = _issue(db_handle)
        created = _create_list(client, token, items=[{"canonical_name": "a"}])
        list_id = created["list_id"]

        r = client.post(
            f"/api/v1/shopping/lists/{list_id}/items",
            json={"items": [{"canonical_name": "b"}]},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_add_items_response_shape(self, client, db_handle):
        """Response matches ShoppingListWire schema."""
        token = _issue(db_handle)
        created = _create_list(client, token, items=[{"canonical_name": "x"}])
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/items",
            json={"items": [{"canonical_name": "y"}]},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert "list_id" in body
        assert "items" in body
        assert isinstance(body["items"], list)
        assert len(body["items"]) == 2
        item = body["items"][0]
        assert "item_id" in item
        assert "canonical_name" in item
        assert "status" in item

    def test_add_items_empty_list_returns_422(self, client, db_handle):
        """Empty items array should be rejected (min_length=1)."""
        token = _issue(db_handle)
        created = _create_list(client, token)
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/items",
            json={"items": []},
            headers=_hdr(token),
        )
        assert r.status_code == 422

    def test_add_items_wrong_household_is_404(self, client, db_handle):
        """A caller from a different household cannot add to a list."""
        token_a = _issue(db_handle, "hh_a")
        created = _create_list(client, token_a, items=[{"canonical_name": "milk"}])

        token_b = _issue(db_handle, "hh_b")
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/items",
            json={"items": [{"canonical_name": "butter"}]},
            headers=_hdr(token_b),
        )
        assert r.status_code == 404
        body = r.json()
        assert body["detail"]["code"] == "list_not_found"

    def test_add_items_to_nonexistent_list_returns_404(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/shopping/lists/no_such_list/items",
            json={"items": [{"canonical_name": "milk"}]},
            headers=_hdr(token),
        )
        assert r.status_code == 404


# ── POST /api/v1/shopping/lists/{list_id}/complete ───────────────


class TestCompleteList:
    def test_complete_empty_list_returns_success(self, client, db_handle):
        """Completing an empty list returns success with no items added."""
        token = _issue(db_handle)
        created = _create_list(client, token)
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/complete",
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["list_id"] == created["list_id"]
        assert body["items_added"] == []
        assert body["items_skipped"] == 0

    def test_complete_with_must_buy_adds_items(self, client, db_handle):
        """Must-buy items are added to inventory at full quantity."""
        token = _issue(db_handle)
        created = _create_list(
            client, token,
            items=[
                {"canonical_name": "milk", "requested_quantity": 2, "unit": "L",
                 "priority": "must_buy"},
                {"canonical_name": "eggs", "requested_quantity": 12, "unit": "unit",
                 "priority": "must_buy"},
            ],
        )
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/complete",
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert len(body["items_added"]) == 2
        names = {i["canonical_name"] for i in body["items_added"]}
        assert names == {"milk", "eggs"}
        # Verify milk was added at full quantity 2.0
        milk = next(i for i in body["items_added"] if i["canonical_name"] == "milk")
        assert milk["quantity"] == 2.0
        assert milk["unit"] == "L"

    def test_complete_skips_avoid_buying(self, client, db_handle):
        """Items with priority avoid_buying are skipped, not added."""
        token = _issue(db_handle)
        created = _create_list(
            client, token,
            items=[
                {"canonical_name": "milk", "priority": "must_buy"},
                {"canonical_name": "chips", "priority": "avoid_buying"},
            ],
        )
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/complete",
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        added_names = {i["canonical_name"] for i in body["items_added"]}
        assert "milk" in added_names
        assert "chips" not in added_names
        assert body["items_skipped"] >= 1

    def test_complete_response_shape(self, client, db_handle):
        """Response matches CompleteShoppingListResponse schema."""
        token = _issue(db_handle)
        created = _create_list(
            client, token,
            items=[{"canonical_name": "butter", "priority": "must_buy"}],
        )
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/complete",
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert "success" in body
        assert "list_id" in body
        assert "items_added" in body
        assert "items_skipped" in body
        assert "goal" in body
        assert "message" in body
        assert isinstance(body["success"], bool)
        assert isinstance(body["items_added"], list)
        assert isinstance(body["items_skipped"], int)

    def test_complete_unknown_list_returns_404(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/shopping/lists/no_such_list/complete",
            headers=_hdr(token),
        )
        assert r.status_code == 404

    def test_complete_wrong_household_returns_404(self, client, db_handle):
        """A caller from a different household cannot complete a list."""
        token_a = _issue(db_handle, "hh_a")
        created = _create_list(
            client, token_a,
            items=[{"canonical_name": "milk", "priority": "must_buy"}],
        )
        token_b = _issue(db_handle, "hh_b")
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/complete",
            headers=_hdr(token_b),
        )
        assert r.status_code == 404


# ── POST /api/v1/shopping/lists/{list_id}/mark-purchased ─────────


class TestMarkPurchased:
    def test_mark_purchased_returns_success(self, client, db_handle):
        """Marking purchased items returns success with items_added."""
        token = _issue(db_handle)
        created = _create_list(
            client, token,
            items=[
                {"canonical_name": "milk", "requested_quantity": 2, "priority": "must_buy"},
                {"canonical_name": "eggs", "priority": "must_buy"},
            ],
        )
        list_id = created["list_id"]
        # Get the item_ids from the created list.
        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        items = r.json()["items"]
        item_ids = [it["item_id"] for it in items[:2]]

        r = client.post(
            f"/api/v1/shopping/lists/{list_id}/mark-purchased",
            json={"item_ids": item_ids},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert len(body["items_added"]) == 2
        names = {i["canonical_name"] for i in body["items_added"]}
        assert names == {"milk", "eggs"}

    def test_mark_purchased_response_shape(self, client, db_handle):
        """Response matches MarkPurchasedResponse schema."""
        token = _issue(db_handle)
        created = _create_list(
            client, token,
            items=[{"canonical_name": "butter", "priority": "must_buy"}],
        )
        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        item_id = r.json()["items"][0]["item_id"]

        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/mark-purchased",
            json={"item_ids": [item_id]},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert "success" in body
        assert "items_added" in body
        assert "message" in body
        assert isinstance(body["success"], bool)
        assert isinstance(body["items_added"], list)
        assert len(body["items_added"]) == 1
        item = body["items_added"][0]
        assert "canonical_name" in item
        assert "lot_id" in item
        assert "quantity" in item
        assert item["canonical_name"] == "butter"

    def test_mark_purchased_unknown_list_returns_404(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/shopping/lists/no_such_list/mark-purchased",
            json={"item_ids": ["abc"]},
            headers=_hdr(token),
        )
        assert r.status_code == 404

    def test_mark_purchased_wrong_household_returns_404(self, client, db_handle):
        """A caller from a different household cannot mark items purchased."""
        token_a = _issue(db_handle, "hh_a")
        created = _create_list(
            client, token_a,
            items=[{"canonical_name": "milk", "priority": "must_buy"}],
        )
        r = client.get("/api/v1/shopping/active", headers=_hdr(token_a))
        item_id = r.json()["items"][0]["item_id"]

        token_b = _issue(db_handle, "hh_b")
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/mark-purchased",
            json={"item_ids": [item_id]},
            headers=_hdr(token_b),
        )
        assert r.status_code == 404

    def test_mark_purchased_empty_ids_returns_422(self, client, db_handle):
        """Empty item_ids is rejected by schema (min_length=1)."""
        token = _issue(db_handle)
        created = _create_list(client, token)
        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/mark-purchased",
            json={"item_ids": []},
            headers=_hdr(token),
        )
        assert r.status_code == 422

    def test_mark_purchased_updates_item_status(self, client, db_handle):
        """After marking items purchased, the item status changes."""
        token = _issue(db_handle)
        created = _create_list(
            client, token,
            items=[
                {"canonical_name": "milk", "priority": "must_buy"},
                {"canonical_name": "eggs", "priority": "must_buy"},
            ],
        )
        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        items = r.json()["items"]
        # Mark only milk as purchased.
        milk_id = next(it["item_id"] for it in items if it["canonical_name"] == "milk")

        r = client.post(
            f"/api/v1/shopping/lists/{created['list_id']}/mark-purchased",
            json={"item_ids": [milk_id]},
            headers=_hdr(token),
        )
        assert r.status_code == 200

        # Verify milk is no longer pending.
        r = client.get("/api/v1/shopping/active", headers=_hdr(token))
        items = r.json()["items"]
        milk = next(it for it in items if it["canonical_name"] == "milk")
        assert milk["status"] == "bought"
        eggs = next(it for it in items if it["canonical_name"] == "eggs")
        assert eggs["status"] == "pending"
