"""Tests for the Idempotency-Key middleware (v1.1).

Verifies:
  * The middleware intercepts mutating methods (POST, PUT, PATCH, DELETE)
    with an ``Idempotency-Key`` header.
  * A first request with a new key passes through and is cached.
  * A second request with the same key replays the cached response
    (same status code, body, and headers).
  * GET requests are never cached (passed through every time).
  * Requests without an ``Idempotency-Key`` header are passed through.
  * The middleware validates key length (rejects > 256 chars).
  * Expired keys are purged on write.
  * The table bootstrap is idempotent.
  * Multiple concurrent keys are isolated (no cross-contamination).
  * Non-2xx responses are NOT cached (client can retry with same key
    after fixing the error).
  * The middleware does not crash when the DB is unavailable.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Iterator

import pytest


@pytest.fixture
def temp_db() -> Iterator[str]:
    """A fresh SQLite DB per test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def app_with_idempotency(temp_db: str) -> "FastAPI":
    """A bare FastAPI app with the idempotency middleware mounted."""
    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from shopstack import app_context
    from shopstack.api.v1.idempotency import (
        IdempotencyMiddleware,
        ensure_idempotency_table,
    )

    # Bootstrap the DB
    from shopstack.persistence.database import Database

    db = Database(temp_db)
    ensure_idempotency_table(db)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db)

    fastapi_app = FastAPI(title="idempotency-test")

    # Add BEFORE mounting routes
    fastapi_app.add_middleware(IdempotencyMiddleware)

    # A simple mutating endpoint we can test against
    _call_count: dict[str, int] = {}

    @fastapi_app.post("/test/echo")
    async def echo_post(payload: dict):
        _call_count["echo"] = _call_count.get("echo", 0) + 1
        return JSONResponse(
            {"called": _call_count["echo"], "received": payload},
            headers={"X-Test": "echo-header"},
        )

    @fastapi_app.put("/test/put")
    async def test_put(payload: dict):
        _call_count["put"] = _call_count.get("put", 0) + 1
        return JSONResponse(
            {"called": _call_count["put"], "received": payload},
        )

    @fastapi_app.delete("/test/delete/{item_id}")
    async def test_delete(item_id: str):
        _call_count["delete"] = _call_count.get("delete", 0) + 1
        return JSONResponse({"called": _call_count["delete"], "item_id": item_id})

    @fastapi_app.patch("/test/patch")
    async def test_patch(payload: dict):
        _call_count["patch"] = _call_count.get("patch", 0) + 1
        return JSONResponse({"called": _call_count["patch"], "received": payload})

    @fastapi_app.get("/test/get")
    async def test_get():
        _call_count["get"] = _call_count.get("get", 0) + 1
        return JSONResponse({"called": _call_count["get"]})

    @fastapi_app.get("/test/get-with-idem")
    async def test_get_with_idem():
        """GET endpoint that happens to receive an Idempotency-Key header
        but should NOT be cached."""
        _call_count["get_idem"] = _call_count.get("get_idem", 0) + 1
        return JSONResponse({"called": _call_count["get_idem"]})

    yield fastapi_app
    monkey.undo()
    db.close()


@pytest.fixture
def client(app_with_idempotency):
    from fastapi.testclient import TestClient

    return TestClient(app_with_idempotency)


# ── Table bootstrap ────────────────────────────────────────────────


class TestEnsureIdempotencyTable:
    def test_table_created(self, temp_db):
        from shopstack.persistence.database import Database

        db = Database(temp_db)
        from shopstack.api.v1.idempotency import ensure_idempotency_table

        ensure_idempotency_table(db)
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_v1_idempotency_keys'"
        )
        assert cur.fetchone() is not None

    def test_table_idempotent(self, temp_db):
        """Calling ensure_idempotency_table twice is safe."""
        from shopstack.persistence.database import Database

        db = Database(temp_db)
        from shopstack.api.v1.idempotency import ensure_idempotency_table

        ensure_idempotency_table(db)
        ensure_idempotency_table(db)  # second call is no-op
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_v1_idempotency_keys'"
        )
        assert cur.fetchone() is not None

    def test_table_has_index(self, temp_db):
        from shopstack.persistence.database import Database

        db = Database(temp_db)
        from shopstack.api.v1.idempotency import ensure_idempotency_table

        ensure_idempotency_table(db)
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_idempotency_keys_expires'"
        )
        assert cur.fetchone() is not None


# ── First request (cache miss) ──────────────────────────────────────


class TestCacheMiss:
    def test_first_request_passes_through(self, client):
        key = "test-key-001"
        r = client.post(
            "/test/echo",
            json={"item": "milk"},
            headers={"Idempotency-Key": key},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["called"] == 1  # handler executed once
        assert body["received"] == {"item": "milk"}
        assert r.headers.get("X-Test") == "echo-header"

    def test_first_request_stores_response(self, client):
        key = "test-key-store-001"
        r1 = client.post(
            "/test/echo",
            json={"item": "rice"},
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        # Second request with same key should replay, not re-execute
        r2 = client.post(
            "/test/echo",
            json={"item": "rice"},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code == 200
        assert r2.json()["called"] == 1  # still 1 (not 2)


# ── Retry (cache hit) ──────────────────────────────────────────────


class TestCacheHit:
    def test_replay_returns_same_body(self, client):
        key = "test-replay-001"
        r1 = client.post(
            "/test/echo",
            json={"item": "butter"},
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 200
        body1 = r1.json()

        r2 = client.post(
            "/test/echo",
            json={"item": "butter"},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2 == body1  # identical response

    def test_replay_returns_same_status(self, client):
        key = "test-status-001"
        r1 = client.post(
            "/test/echo",
            json={},
            headers={"Idempotency-Key": key},
        )
        r2 = client.post(
            "/test/echo",
            json={},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code == r1.status_code

    def test_replay_returns_same_headers(self, client):
        key = "test-headers-001"
        r1 = client.post(
            "/test/echo",
            json={},
            headers={"Idempotency-Key": key},
        )
        r2 = client.post(
            "/test/echo",
            json={},
            headers={"Idempotency-Key": key},
        )
        # X-Test header should be preserved across replay
        if r1.headers.get("X-Test"):
            assert r2.headers.get("X-Test") == r1.headers["X-Test"]

    def test_second_request_with_different_body_returns_original(self, client):
        """Even if the retry sends a different body, the cached response
        is returned — the key is the only thing that matters."""
        key = "test-body-diff-001"
        r1 = client.post(
            "/test/echo",
            json={"item": "milk"},
            headers={"Idempotency-Key": key},
        )
        body1 = r1.json()

        r2 = client.post(
            "/test/echo",
            json={"item": "DIFFERENT_ITEM"},
            headers={"Idempotency-Key": key},
        )
        body2 = r2.json()
        assert body2 == body1  # cached, not re-executed


# ── Method gating ──────────────────────────────────────────────────


class TestMethodGating:
    def test_get_never_cached(self, client):
        """GET requests are never cached, even with an Idempotency-Key."""
        key = "test-get-001"
        r1 = client.get(
            "/test/get-with-idem",
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        r2 = client.get(
            "/test/get-with-idem",
            headers={"Idempotency-Key": key},
        )
        assert r2.json()["called"] == 2  # incremented

    def test_put_cached(self, client):
        key = "test-put-001"
        r1 = client.put("/test/put", json={"x": 1}, headers={"Idempotency-Key": key})
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        r2 = client.put("/test/put", json={"x": 2}, headers={"Idempotency-Key": key})
        assert r2.json()["called"] == 1  # cached

    def test_delete_cached(self, client):
        key = "test-delete-001"
        r1 = client.delete("/test/delete/item1", headers={"Idempotency-Key": key})
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        r2 = client.delete("/test/delete/item1", headers={"Idempotency-Key": key})
        assert r2.json()["called"] == 1  # cached

    def test_patch_cached(self, client):
        key = "test-patch-001"
        r1 = client.patch("/test/patch", json={"x": 1}, headers={"Idempotency-Key": key})
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        r2 = client.patch("/test/patch", json={"x": 2}, headers={"Idempotency-Key": key})
        assert r2.json()["called"] == 1  # cached

    def test_no_header_passes_through(self, client):
        """Without an Idempotency-Key header, the request is always executed."""
        r1 = client.post("/test/echo", json={"x": 1})
        assert r1.json()["called"] == 1

        r2 = client.post("/test/echo", json={"x": 1})
        assert r2.json()["called"] == 2  # not cached


# ── Key validation ─────────────────────────────────────────────────


class TestKeyValidation:
    def test_empty_key_treated_as_no_key(self, client):
        """An empty Idempotency-Key header is ignored (passed through)."""
        r1 = client.post(
            "/test/echo", json={}, headers={"Idempotency-Key": ""},
        )
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        r2 = client.post(
            "/test/echo", json={}, headers={"Idempotency-Key": ""},
        )
        assert r2.json()["called"] == 2  # not cached

    def test_long_key_rejected(self, client):
        """Keys over 256 chars are rejected with 400."""
        long_key = "k" * 300
        r = client.post(
            "/test/echo", json={}, headers={"Idempotency-Key": long_key},
        )
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "invalid_idempotency_key"

    def test_whitespace_only_key_treated_as_no_key(self, client):
        """A whitespace-only key is ignored (passed through)."""
        r1 = client.post(
            "/test/echo", json={}, headers={"Idempotency-Key": "   "},
        )
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        r2 = client.post(
            "/test/echo", json={}, headers={"Idempotency-Key": "   "},
        )
        assert r2.json()["called"] == 2  # not cached


# ── Non-2xx responses ──────────────────────────────────────────────


class TestNon2xxResponses:
    def test_500_not_cached(self, client):
        """A 5xx response is not cached — retry should re-execute."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.responses import JSONResponse

        from shopstack import app_context
        from shopstack.api.v1.idempotency import (
            IdempotencyMiddleware,
            ensure_idempotency_table,
        )
        from shopstack.persistence.database import Database

        db = Database(tempfile.mkstemp(suffix=".db")[1])
        ensure_idempotency_table(db)
        monkey = pytest.MonkeyPatch()
        monkey.setattr(app_context, "db", db)

        app = FastAPI(title="5xx-test")
        app.add_middleware(IdempotencyMiddleware)

        call_count = 0

        @app.post("/test/error")
        async def error_endpoint(payload: dict):
            nonlocal call_count
            call_count += 1
            return JSONResponse(
                status_code=500,
                content={"error": "simulated failure"},
            )

        c = TestClient(app)
        key = "test-500-key"
        r1 = c.post("/test/error", json={}, headers={"Idempotency-Key": key})
        assert r1.status_code == 500
        assert call_count == 1

        # Retry with same key — should re-execute (5xx not cached)
        r2 = c.post("/test/error", json={}, headers={"Idempotency-Key": key})
        assert r2.status_code == 500
        assert call_count == 2  # re-executed

        monkey.undo()
        db.close()

    def test_201_cached(self, client):
        """A 201 Created response IS cached (2xx)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.responses import JSONResponse

        from shopstack import app_context
        from shopstack.api.v1.idempotency import (
            IdempotencyMiddleware,
            ensure_idempotency_table,
        )
        from shopstack.persistence.database import Database

        db = Database(tempfile.mkstemp(suffix=".db")[1])
        ensure_idempotency_table(db)
        monkey = pytest.MonkeyPatch()
        monkey.setattr(app_context, "db", db)

        app = FastAPI(title="201-test")
        app.add_middleware(IdempotencyMiddleware)

        call_count = 0

        @app.post("/test/created")
        async def created_endpoint(payload: dict):
            nonlocal call_count
            call_count += 1
            return JSONResponse(
                status_code=201,
                content={"id": "new-resource", "count": call_count},
            )

        c = TestClient(app)
        key = "test-201-key"
        r1 = c.post("/test/created", json={}, headers={"Idempotency-Key": key})
        assert r1.status_code == 201
        assert r1.json()["count"] == 1
        assert call_count == 1

        # Retry — should be cached (201 is 2xx)
        r2 = c.post("/test/created", json={}, headers={"Idempotency-Key": key})
        assert r2.status_code == 201
        assert r2.json()["count"] == 1  # cached, not re-executed
        assert call_count == 1

        monkey.undo()
        db.close()


# ── Isolation ──────────────────────────────────────────────────────


class TestKeyIsolation:
    def test_different_keys_are_independent(self, client):
        """Two different keys produce independent cached responses."""
        k1 = "key-1"
        k2 = "key-2"

        r1 = client.post("/test/echo", json={"seq": 1}, headers={"Idempotency-Key": k1})
        assert r1.json()["called"] == 1

        r2 = client.post("/test/echo", json={"seq": 2}, headers={"Idempotency-Key": k2})
        assert r2.json()["called"] == 2  # different key, executes again

        # Replay key-1
        r3 = client.post("/test/echo", json={"seq": 99}, headers={"Idempotency-Key": k1})
        assert r3.json()["called"] == 1  # cached from first call


# ── TTL expiry ────────────────────────────────────────────────────


class TestTtlExpiry:
    def test_expired_key_misses_cache(self, client):
        """An expired key is treated as a cache miss (request passes through)."""
        key = "test-expire-001"
        r1 = client.post("/test/echo", json={"x": 1}, headers={"Idempotency-Key": key})
        assert r1.status_code == 200
        assert r1.json()["called"] == 1

        # Manually expire the key by updating its expires_at
        from shopstack import app_context
        from shopstack.api.v1.idempotency import _lookup_response

        db = app_context.db
        db.conn.execute(
            "UPDATE api_v1_idempotency_keys SET expires_at = ? WHERE idempotency_key = ?",
            (time.time() - 1, key),
        )
        db.conn.commit()

        # Lookup should return None (expired)
        assert _lookup_response(db, key) is None

        # Second request should re-execute
        r2 = client.post("/test/echo", json={"x": 2}, headers={"Idempotency-Key": key})
        assert r2.json()["called"] == 2  # re-executed


# ── Storage helpers (unit-level) ───────────────────────────────────


class TestStorageHelpers:
    def test_store_and_lookup(self, temp_db):
        from starlette.responses import JSONResponse

        from shopstack.api.v1.idempotency import (
            _lookup_response,
            _store_response,
            ensure_idempotency_table,
        )
        from shopstack.persistence.database import Database

        db = Database(temp_db)
        ensure_idempotency_table(db)

        response = JSONResponse(
            content={"ok": True},
            status_code=201,
            headers={"X-Custom": "val"},
        )
        _store_response(db, "my-key", response)

        cached = _lookup_response(db, "my-key")
        assert cached is not None
        assert cached.status_code == 201
        assert json.loads(cached.body) == {"ok": True}
        # X-Custom was stored as a header (may be lowercased by TestClient)
        assert cached.headers.get("x-custom") == "val" or cached.headers.get("X-Custom") == "val"

    def test_lookup_unknown_key_returns_none(self, temp_db):
        from shopstack.api.v1.idempotency import (
            _lookup_response,
            ensure_idempotency_table,
        )
        from shopstack.persistence.database import Database

        db = Database(temp_db)
        ensure_idempotency_table(db)
        assert _lookup_response(db, "unknown-key") is None

    def test_purge_expired(self, temp_db):
        from starlette.responses import JSONResponse

        from shopstack.api.v1.idempotency import (
            _lookup_response,
            _purge_expired_keys,
            _store_response,
            ensure_idempotency_table,
        )
        from shopstack.persistence.database import Database

        db = Database(temp_db)
        ensure_idempotency_table(db)

        # Store two entries: one fresh, one expired
        _store_response(db, "fresh", JSONResponse({"ok": True}), ttl_hours=24)
        _store_response(db, "expired", JSONResponse({"ok": True}), ttl_hours=0)

        n = _purge_expired_keys(db)
        assert n >= 1  # at least the expired one was purged

        assert _lookup_response(db, "expired") is None
        assert _lookup_response(db, "fresh") is not None


# ── Middleware safety ──────────────────────────────────────────────


class TestMiddlewareSafety:
    def test_no_crash_on_unknown_route(self, client):
        """A request to an unknown route returns 404 normally."""
        r = client.post("/api/v1/nonexistent", json={}, headers={"Idempotency-Key": "k"})
        # 404 from FastAPI (the middleware shouldn't interfere)
        assert r.status_code in (404, 405)

    def test_no_crash_on_missing_db(self):
        """The middleware doesn't crash when the DB handle is missing."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.responses import JSONResponse

        from shopstack import app_context
        from shopstack.api.v1.idempotency import IdempotencyMiddleware

        monkey = pytest.MonkeyPatch()
        monkey.setattr(app_context, "db", None, raising=False)

        app = FastAPI(title="no-db-test")
        app.add_middleware(IdempotencyMiddleware)

        @app.post("/test/ping")
        async def ping(payload: dict):
            return JSONResponse({"ok": True})

        c = TestClient(app)
        r = c.post("/test/ping", json={}, headers={"Idempotency-Key": "k"})
        # Should still respond (no crash); the middleware logs and passes through
        assert r.status_code == 200
        monkey.undo()
