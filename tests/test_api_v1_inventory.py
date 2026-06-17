"""Contract tests for ``/api/v1/inventory`` endpoints.

Coverage:
  * Auth-gating: all four endpoints require a bearer token.
  * GET list returns paginated inventory with correct shape.
  * GET list supports limit, offset, and status_filter params.
  * GET list is household-scoped (no cross-household leakage).
  * GET one returns a single lot by id.
  * GET one returns 404 for unknown lot or wrong household.
  * POST consume decrements quantity and returns updated lot.
  * POST consume returns 404 for unknown lot.
  * POST consume returns 409 when consuming more than available.
  * POST create returns 201 with correct shape and fields.
  * POST create persists the lot and it appears in GET list.
  * POST create accepts optional metadata fields.
  * POST create rejects missing canonical_name with 422.
  * POST create is household-scoped.
  * Response shapes match wire schemas (ListResponse[InventoryLot], InventoryLot).
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
    from shopstack.api.v1.routers.inventory import router as inventory_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)
    # The consume endpoint reaches for tools.inventory; mount ToolRegistry
    # so the service-layer delegation works (matches pattern in test_api_v1.py).
    try:
        from shopstack.tools.registry import ToolRegistry
        monkey.setattr(app_context, "tools", ToolRegistry(db_handle), raising=False)
    except Exception:
        pass

    fastapi_app = FastAPI(title="shopstack-test-inventory")
    fastapi_app.include_router(inventory_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_inv") -> str:
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    # Ensure the household exists and is writable (permission gate).
    db_handle.add_household(household, household)
    try:
        db_handle.add_household_member(household, household, role="owner")
    except Exception:
        pass
    return auth_mod.issue_token(
        db_handle, device_id="dev_inv", household_id=household,
    )["token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_lot(
    db_handle,
    lot_id: str = "lot1",
    canonical_name: str = "milk",
    display_name: str = "Milk",
    category: str = "Dairy",
    quantity: float = 2.0,
    unit: str = "L",
    location: str = "fridge",
    status: str = "active",
    household: str = "hh_inv",
) -> None:
    """Insert an inventory lot directly for test seeding."""
    db_handle.conn.execute(
        """INSERT INTO inventory_lots (
            lot_id, canonical_name, display_name, category, quantity,
            unit, storage_location_id, status, user_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lot_id, canonical_name, display_name, category, quantity,
         unit, location, status, household,
         "2026-06-17T00:00:00Z", "2026-06-17T00:00:00Z"),
    )
    db_handle.conn.commit()


# ── Auth gating ──────────────────────────────────────────────────


class TestInventoryAuth:
    def test_list_requires_token(self, client):
        assert client.get("/api/v1/inventory/lots").status_code == 401

    def test_get_one_requires_token(self, client):
        assert client.get("/api/v1/inventory/lots/lot1").status_code == 401

    def test_consume_requires_token(self, client):
        assert client.post(
            "/api/v1/inventory/lots/lot1/consume", json={"quantity": 1.0},
        ).status_code == 401


# ── GET /api/v1/inventory/lots ───────────────────────────────────


class TestListLots:
    def test_empty_list_returns_empty(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["has_more"] is False

    def test_response_shape_matches_list_response(self, client, db_handle):
        _seed_lot(db_handle)
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert isinstance(body["has_more"], bool)

    def test_item_shape_matches_inventory_lot(self, client, db_handle):
        _seed_lot(db_handle)
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots", headers=_hdr(token))
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert "lot_id" in item
        assert "canonical_name" in item
        assert "display_name" in item
        assert "category" in item
        assert "quantity" in item
        assert "unit" in item
        assert "storage_location_id" in item
        assert "status" in item

    def test_returns_seeded_lots(self, client, db_handle):
        _seed_lot(db_handle, "lot_a", "milk")
        _seed_lot(db_handle, "lot_b", "eggs")
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        names = {it["canonical_name"] for it in body["items"]}
        assert names == {"milk", "eggs"}

    def test_household_scoped(self, client, db_handle):
        _seed_lot(db_handle, "lot_a", "milk", household="hh_inv")
        _seed_lot(db_handle, "lot_b", "rice", household="hh_other")
        token = _issue(db_handle, "hh_inv")
        r = client.get("/api/v1/inventory/lots", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["canonical_name"] == "milk"

    def test_respects_limit_param(self, client, db_handle):
        for i in range(5):
            _seed_lot(db_handle, f"lot_{i}", f"item_{i}")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/inventory/lots",
            params={"limit": 3},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["limit"] == 3
        assert len(body["items"]) == 3

    def test_respects_offset_param(self, client, db_handle):
        for i in range(5):
            _seed_lot(db_handle, f"lot_{i}", f"item_{i}")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/inventory/lots",
            params={"limit": 10, "offset": 3},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["offset"] == 3
        assert len(body["items"]) == 2  # 5 total, offset 3 → 2 remaining

    def test_respects_status_filter(self, client, db_handle):
        _seed_lot(db_handle, "lot_active", "active_item", status="active")
        _seed_lot(db_handle, "lot_used", "used_item", status="used")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/inventory/lots",
            params={"status_filter": "used"},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["canonical_name"] == "used_item"

    def test_query_string_token_works(self, client, db_handle):
        _seed_lot(db_handle, "lot_qs", "query_item")
        token = _issue(db_handle)
        r = client.get(f"/api/v1/inventory/lots?token={token}")
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_lot_fields_have_correct_types(self, client, db_handle):
        _seed_lot(db_handle)
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots", headers=_hdr(token))
        item = r.json()["items"][0]
        assert isinstance(item["lot_id"], str)
        assert isinstance(item["quantity"], (int, float))
        assert isinstance(item["status"], str)
        assert isinstance(item["category"], str)
        assert item["quantity"] == 2.0
        assert item["unit"] == "L"


# ── GET /api/v1/inventory/lots/{lot_id} ──────────────────────────


class TestGetLot:
    def test_returns_lot_by_id(self, client, db_handle):
        _seed_lot(db_handle, "lot_get", "get_item", display_name="Get Item")
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots/lot_get", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["lot_id"] == "lot_get"
        assert body["canonical_name"] == "get_item"
        assert body["display_name"] == "Get Item"

    def test_unknown_lot_returns_404(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots/no_such_lot", headers=_hdr(token))
        assert r.status_code == 404
        body = r.json()
        assert body["detail"]["code"] == "lot_not_found"

    def test_wrong_household_returns_404(self, client, db_handle):
        _seed_lot(db_handle, "lot_other", "other_item", household="hh_other")
        token = _issue(db_handle, "hh_inv")
        r = client.get("/api/v1/inventory/lots/lot_other", headers=_hdr(token))
        assert r.status_code == 404

    def test_response_shape(self, client, db_handle):
        _seed_lot(db_handle, "lot_shape", "shape_item")
        token = _issue(db_handle)
        r = client.get("/api/v1/inventory/lots/lot_shape", headers=_hdr(token))
        body = r.json()
        assert "lot_id" in body
        assert "canonical_name" in body
        assert "display_name" in body
        assert "quantity" in body
        assert "unit" in body
        assert "status" in body
        assert body["lot_id"] == "lot_shape"
        assert body["canonical_name"] == "shape_item"


# ── POST /api/v1/inventory/lots/{lot_id}/consume ─────────────────


class TestConsumeLot:
    def test_consume_decrements_quantity(self, client, db_handle):
        _seed_lot(db_handle, "lot_con", "milk", quantity=5.0)
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots/lot_con/consume",
            json={"quantity": 2.0},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["lot_id"] == "lot_con"
        assert body["quantity"] == 3.0  # 5.0 - 2.0

    def test_consume_all_returns_zero(self, client, db_handle):
        _seed_lot(db_handle, "lot_all", "eggs", quantity=1.0)
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots/lot_all/consume",
            json={"quantity": 1.0},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        assert r.json()["quantity"] == 0.0

    def test_consume_more_than_available_returns_409(self, client, db_handle):
        _seed_lot(db_handle, "lot_short", "butter", quantity=1.0)
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots/lot_short/consume",
            json={"quantity": 5.0},
            headers=_hdr(token),
        )
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["code"] == "insufficient_quantity"

    def test_consume_unknown_lot_returns_404(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots/no_such/consume",
            json={"quantity": 1.0},
            headers=_hdr(token),
        )
        assert r.status_code == 404

    def test_consume_wrong_household_returns_404(self, client, db_handle):
        _seed_lot(db_handle, "lot_other_con", "rice", household="hh_other")
        token = _issue(db_handle, "hh_inv")
        r = client.post(
            "/api/v1/inventory/lots/lot_other_con/consume",
            json={"quantity": 1.0},
            headers=_hdr(token),
        )
        assert r.status_code == 404

    def test_consume_response_shape(self, client, db_handle):
        _seed_lot(db_handle, "lot_resp", "pasta", quantity=4.0)
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots/lot_resp/consume",
            json={"quantity": 1.0},
            headers=_hdr(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert "lot_id" in body
        assert "canonical_name" in body
        assert "quantity" in body
        assert "unit" in body
        assert "status" in body
        assert body["lot_id"] == "lot_resp"
        assert body["quantity"] == 3.0

    def test_consume_zero_rejected_by_schema(self, client, db_handle):
        """quantity=0 is rejected by the schema (gt=0 constraint)."""
        _seed_lot(db_handle, "lot_zero", "sugar", quantity=5.0)
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots/lot_zero/consume",
            json={"quantity": 0},
            headers=_hdr(token),
        )
        assert r.status_code == 422

    def test_consume_with_query_string_token(self, client, db_handle):
        """POST consume works with ?token=xxx query-string auth (Gradio compat)."""
        _seed_lot(db_handle, "lot_qs_con", "cheese", quantity=3.0)
        token = _issue(db_handle)
        r = client.post(
            f"/api/v1/inventory/lots/lot_qs_con/consume?token={token}",
            json={"quantity": 1.0},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["lot_id"] == "lot_qs_con"
        assert body["quantity"] == 2.0
        assert body["canonical_name"] == "cheese"
        assert body["status"] == "active"

    def test_consume_query_string_rejected_when_invalid(self, client, db_handle):
        """Invalid query-string token returns 401."""
        _seed_lot(db_handle, "lot_bad_qs", "butter", quantity=3.0)
        r = client.post(
            "/api/v1/inventory/lots/lot_bad_qs/consume?token=bad_token",
            json={"quantity": 1.0},
        )
        assert r.status_code == 401
        body = r.json()
        assert body["detail"]["code"] == "invalid_or_expired_token"

    def test_header_takes_priority_over_query_string(self, client, db_handle):
        """When both Authorization header and ?token= are provided, header wins."""
        _seed_lot(db_handle, "lot_prio", "yogurt", quantity=3.0)
        valid_token = _issue(db_handle)
        # Provide a valid header token AND an invalid query-string token.
        # The header should win, so the request succeeds.
        r = client.post(
            f"/api/v1/inventory/lots/lot_prio/consume?token=invalid_qs_token",
            json={"quantity": 1.0},
            headers=_hdr(valid_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["lot_id"] == "lot_prio"
        assert body["quantity"] == 2.0


# ── POST /api/v1/inventory/lots (create) ─────────────────────────


class TestAddLot:
    def test_create_requires_token(self, client):
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "milk"},
        )
        assert r.status_code == 401

    def test_create_returns_201_and_lot_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "milk"},
            headers=_hdr(token),
        )
        assert r.status_code == 201
        body = r.json()
        assert "lot_id" in body
        assert body["canonical_name"] == "milk"
        assert body["display_name"] == "milk"  # defaults to canonical_name
        assert body["quantity"] == 1.0
        assert body["unit"] == "unit"
        assert body["status"] == "active"

    def test_create_with_all_optional_fields(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={
                "canonical_name": "basmati rice",
                "display_name": "Basmati Rice",
                "quantity": 5.0,
                "unit": "kg",
                "storage_location_id": "pantry",
                "category": "Grains",
                "purchase_date": "2026-06-15",
                "estimated_use_by_date": "2027-06-15",
                "label_expiry_date": "2027-06-15",
                "price_paid": 450.0,
                "currency": "INR",
                "confidence": 0.95,
            },
            headers=_hdr(token),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["lot_id"] != ""
        assert body["canonical_name"] == "basmati rice"
        assert body["display_name"] == "Basmati Rice"
        assert body["quantity"] == 5.0
        assert body["unit"] == "kg"
        assert body["storage_location_id"] == "pantry"
        assert body["category"] == "Grains"
        assert body["purchase_date"] is not None
        assert body["price_paid"] == 450.0
        assert body["confidence"] == 0.95

    def test_create_persists_lot_in_list(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "eggs"},
            headers=_hdr(token),
        )
        assert r.status_code == 201
        new_lot_id = r.json()["lot_id"]
        # GET list should include the new lot.
        r2 = client.get("/api/v1/inventory/lots", headers=_hdr(token))
        ids = {it["lot_id"] for it in r2.json()["items"]}
        assert new_lot_id in ids

    def test_create_rejects_missing_name(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={},
            headers=_hdr(token),
        )
        assert r.status_code == 422

    def test_create_household_scoped(self, client, db_handle):
        token_a = _issue(db_handle, "hh_a")
        token_b = _issue(db_handle, "hh_b")
        # hh_a creates a lot.
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "hh_a_item"},
            headers=_hdr(token_a),
        )
        assert r.status_code == 201
        # hh_b should not see it.
        r2 = client.get("/api/v1/inventory/lots", headers=_hdr(token_b))
        assert r2.json()["total"] == 0

    def test_create_accepts_zero_price(self, client, db_handle):
        """price_paid=0 is valid (free items, gifts)."""
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "free sample", "price_paid": 0},
            headers=_hdr(token),
        )
        assert r.status_code == 201
        assert r.json()["price_paid"] == 0

    def test_create_rejects_negative_price(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "test", "price_paid": -1},
            headers=_hdr(token),
        )
        assert r.status_code == 422

    def test_create_auto_generates_id(self, client, db_handle):
        """lot_id is auto-generated, not derived from the name."""
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "auto-id"},
            headers=_hdr(token),
        )
        assert r.status_code == 201
        lot_id = r.json()["lot_id"]
        assert isinstance(lot_id, str) and len(lot_id) > 0
        # lot_id should not be predictable from the canonical_name
        assert lot_id != "auto-id"

    def test_create_sets_default_status(self, client, db_handle):
        """New lots have status=active."""
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/inventory/lots",
            json={"canonical_name": "fresh item"},
            headers=_hdr(token),
        )
        assert r.status_code == 201
        assert r.json()["status"] == "active"
