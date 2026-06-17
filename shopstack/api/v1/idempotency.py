"""Idempotency-Key middleware for safe mobile retries (v1.1).

**Why this exists (motto_v3 §0.6 risk-based verification):**

Mobile clients operate on unreliable networks. A POST to ``/api/v1/inventory/lots``
may succeed server-side but the response never reaches the client. Retrying the
same request would create a *second* lot — a double-submission bug.

The Idempotency-Key pattern solves this:

1. The client generates a unique key (UUID v4) for each mutating request
   and sends it as the ``Idempotency-Key`` header.
2. The server stores the response for that key.
3. If the client retries with the same key, the server returns the stored
   response without executing the mutation again.

**Design choices:**

* **Storage:** SQLite table ``api_v1_idempotency_keys``, same DB connection
  the rest of the app uses. This is correct for a single-replica deployment;
  multi-replica deployments would need a shared store (Redis), tracked as
  a future concern.
* **TTL:** 24 hours (``IDEMPOTENCY_TTL_HOURS``). After that, the entry is
  eligible for purging. This is long enough for a client to notice the
  failure and retry, short enough to keep the table small.
* **Scope:** Mutating methods only (POST, PUT, PATCH, DELETE). GET requests
  are never cached — they are idempotent by definition and should not
  be deduplicated.
* **Response storage:** We store the status code, response body (bytes),
  and response headers. On replay, the middleware re-constructs a
  ``Response`` with the original status, body, and headers so the
  client sees exactly what they'd see from a real execution.
* **Idempotent mount:** The middleware is added via ``app.add_middleware``
  which is itself idempotent in production (called once).

**Pattern (motto_v3 §0.15 three-layer rule):**

* HTTP boundary only — this module knows nothing about the domain.
* The ``IdempotencyMiddleware`` class follows the ``BaseHTTPMiddleware``
  pattern used by ``app.py:PermissionsPolicyMiddleware``.
* No business logic leaks into the middleware; it only caches/replays
  responses for mutating requests that carry an ``Idempotency-Key``.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────

#: How long an idempotency-key entry remains valid. 24 hours gives the
#: client a full day to retry after a network failure. Entries older than
#: this are purged on write or by a background task.
IDEMPOTENCY_TTL_HOURS: int = 24

#: Mutating HTTP methods that are candidates for idempotency-key caching.
#: GET, HEAD, OPTIONS, TRACE are never cached.
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: The header name the client uses to send its idempotency key.
IDEMPOTENCY_KEY_HEADER: str = "Idempotency-Key"


# ── DB table bootstrap ────────────────────────────────────────────


def ensure_idempotency_table(db: Any) -> None:
    """Create the ``api_v1_idempotency_keys`` table if missing.

    Idempotent. Called from ``mount_v1_routes`` on startup.
    """
    db.conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_v1_idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            response_status INTEGER NOT NULL,
            response_body BLOB NOT NULL,
            response_headers TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,       -- unix timestamp
            expires_at REAL NOT NULL         -- unix timestamp
        );
        CREATE INDEX IF NOT EXISTS idx_idempotency_keys_expires
            ON api_v1_idempotency_keys(expires_at);
        """
    )
    db.conn.commit()
    logger.info("idempotency_keys table ready")


# ── Storage helpers ───────────────────────────────────────────────


def _store_response(
    db: Any,
    key: str,
    response: Response,
    body: bytes | None = None,
    ttl_hours: int = IDEMPOTENCY_TTL_HOURS,
) -> None:
    """Store a response for a given idempotency key.

    Args:
        db: Database handle with a ``conn`` attribute.
        key: The idempotency key (from the ``Idempotency-Key`` header).
        response: The ``Response`` to cache (used for status/headers).
        body: Pre-extracted response body as bytes. If ``None``, read from
            ``response.body`` (may fail for ``StreamingResponse``).
        ttl_hours: How long the entry lives (default 24h).
    """
    now = time.time()
    expires_at = now + ttl_hours * 3600
    # Serialise headers as JSON so they survive the SQLite round-trip.
    # Exclude server-internal headers (content-length, date, server).
    headers = dict(response.headers)
    for skip in ("content-length", "date", "server"):
        headers.pop(skip, None)
    if body is None:
        body = response.body if isinstance(response.body, bytes) else str(response.body).encode("utf-8")
    db.conn.execute(
        """
        INSERT OR REPLACE INTO api_v1_idempotency_keys
            (idempotency_key, response_status, response_body, response_headers,
             created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (key, response.status_code, body, json.dumps(headers), now, expires_at),
    )
    db.conn.commit()


def _lookup_response(db: Any, key: str) -> Response | None:
    """Look up a cached response for an idempotency key.

    Returns ``None`` if the key is unknown, expired, or the DB is
    unavailable. The caller (middleware) should let the request through
    in that case.
    """
    now = time.time()
    try:
        cur = db.conn.execute(
            "SELECT response_status, response_body, response_headers, expires_at "
            "FROM api_v1_idempotency_keys WHERE idempotency_key = ?",
            (key,),
        )
        row = cur.fetchone()
    except Exception:  # noqa: BLE001
        logger.debug("idempotency lookup failed for key=%s", key[:12])
        return None
    if row is None:
        return None
    if now > row["expires_at"]:
        return None
    # Reconstruct the response. Headers are stored as JSON.
    try:
        headers = json.loads(row["response_headers"]) if row["response_headers"] else {}
    except (json.JSONDecodeError, TypeError):
        headers = {}
    return Response(
        content=row["response_body"],
        status_code=row["response_status"],
        headers=headers,
    )


def _purge_expired_keys(db: Any) -> int:
    """Delete expired idempotency-key entries. Returns row count.

    Called on every write to keep the table from growing unbounded.
    """
    now = time.time()
    cur = db.conn.execute(
        "DELETE FROM api_v1_idempotency_keys WHERE expires_at < ?",
        (now,),
    )
    db.conn.commit()
    return cur.rowcount


# ── Middleware ─────────────────────────────────────────────────────


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that handles ``Idempotency-Key`` headers.

    Usage::

        fastapi_app.add_middleware(IdempotencyMiddleware)

    The middleware intercepts every request, checks for the header,
    and for mutating methods attempts to store/replay the response.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Intercept the request if it carries an ``Idempotency-Key`` header."""
        # Only intercept mutating methods.
        if request.method.upper() not in _MUTATING_METHODS:
            return await call_next(request)

        key = request.headers.get(IDEMPOTENCY_KEY_HEADER, "").strip()
        if not key:
            return await call_next(request)

        # Validate key format (must be a non-empty printable ASCII string,
        # max 256 chars — UUID v4 is the canonical choice).
        if len(key) > 256:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_idempotency_key",
                    "message": "Idempotency-Key must be 256 characters or fewer.",
                },
            )

        # Lazy-import the DB to avoid circular imports at module level.
        try:
            from shopstack.app_context import db
        except Exception:
            # If we can't get the DB, let the request through.
            return await call_next(request)

        # Check for a cached response.
        cached = _lookup_response(db, key)
        if cached is not None:
            logger.debug("idempotency replay: key=%s", key[:12])
            # Preserve the original content-type from the stored response
            # if it was set, otherwise default to application/json.
            return cached

        # No cached response — let the request through.
        response = await call_next(request)

        # Only cache successful responses (2xx). If the upstream
        # returned an error, caching it would make the error
        # permanent for this key — the client should be able to
        # fix the error and retry with the same key (or a new one).
        if 200 <= response.status_code < 300:
            try:
                # Extract body safely. Starlette's BaseHTTPMiddleware may wrap
                # the inner response in a _StreamingResponse which has no .body
                # attribute. We consume the body_iterator in that case.
                if hasattr(response, "body"):
                    body = response.body if isinstance(response.body, bytes) else str(response.body).encode("utf-8")
                else:
                    chunks = [c async for c in response.body_iterator]
                    body = b"".join(chunks)
                    # Reconstruct a sendable response — the original streaming
                    # body is now exhausted.
                    response = Response(
                        content=body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                    )
                _store_response(db, key, response, body)
                _purge_expired_keys(db)
                logger.info("idempotency cached: key=%s status=%d", key[:12], response.status_code)
            except Exception as exc:  # noqa: BLE001
                # If storage fails, the request still succeeded; we just
                # can't guarantee idempotency on retry. Log and continue.
                logger.warning("idempotency store failed for key=%s: %s", key[:12], exc)

        return response


__all__ = [
    "IDEMPOTENCY_TTL_HOURS",
    "IDEMPOTENCY_KEY_HEADER",
    "IdempotencyMiddleware",
    "ensure_idempotency_table",
]
