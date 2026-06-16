"""Auth tokens for ``/api/v1/*``.

This module is the **storage + verification** layer for opaque
bearer tokens. It does **not** ship a login UI; the v1 login
endpoint lives in ``routers/auth_router.py`` and uses
:func:`issue_token` here.

**Design choices (per the decision doc):**

* **Opaque tokens, not JWT.** A random 32-byte token, base64url-
  encoded. The server stores ``sha256(token)`` as the primary key;
  the plaintext token is given to the client once and never
  stored server-side. Revocation is a row delete.
* **No password flow in v1.** v1 trusts the local-first premise:
  the mobile app and the backend share a device. A device-level
  shared secret (``device_secret``) gates ``POST /api/v1/auth/login``.
  A future ``v2/auth/sso`` adds a real identity provider.
* **Tokens are household-scoped.** Each token row carries the
  ``household_id`` it was issued for. Cross-household access
  requires issuing a new token.
* **TTL.** 30 days. Refresh extends the expiry without rotating
  the token (rotation can be added in v1.1 if mobile wants
  short-lived tokens).

**DB schema (added at boot by ``ensure_auth_table``):**

.. code-block:: sql

    CREATE TABLE IF NOT EXISTS api_v1_auth_tokens (
        token_hash BLOB PRIMARY KEY,    -- sha256(token), 32 bytes
        device_id TEXT NOT NULL,
        household_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        last_used_at TEXT,
        scopes TEXT DEFAULT ''         -- comma-separated; '' == all
    );

    CREATE INDEX IF NOT EXISTS idx_api_v1_auth_tokens_device
        ON api_v1_auth_tokens(device_id);
    CREATE INDEX IF NOT EXISTS idx_api_v1_auth_tokens_household
        ON api_v1_auth_tokens(household_id);
    CREATE INDEX IF NOT EXISTS idx_api_v1_auth_tokens_expires
        ON api_v1_auth_tokens(expires_at);
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────

#: Token TTL: 30 days. Mobile clients are expected to refresh
#: silently on each app start; rotation is a v1.1 concern.
TOKEN_TTL_DAYS = 30

#: Used to hash tokens at rest. SHA-256 is the standard choice
#: for non-password secrets (OWASP recommends a slow KDF like
#: bcrypt for passwords; tokens are already 32 bytes of entropy
#: from secrets.token_bytes, so no KDF stretch is needed).
_HASH_ALGO = hashlib.sha256


# ── Token format ──────────────────────────────────────────────────


def _new_token() -> str:
    """Generate a fresh opaque token.

    32 bytes of entropy → 43 base64url chars (no padding). The
    token is what the client stores; the server only sees
    ``sha256(token)``.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def _hash_token(token: str) -> bytes:
    """Hash a token for at-rest storage and lookup."""
    return _HASH_ALGO(token.encode("utf-8")).digest()


# ── DB schema bootstrap ──────────────────────────────────────────


def ensure_auth_table(db: Any) -> None:
    """Create the ``api_v1_auth_tokens`` table if missing.

    Idempotent. Called from :func:`shopstack.api.v1.mount.mount_v1_routes`
    on every startup so a fresh DB is ready before the first
    request. Uses the same per-thread connection the rest of the
    app uses (``db.conn``).
    """
    c = db.conn
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_v1_auth_tokens (
            token_hash BLOB PRIMARY KEY,
            device_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_used_at TEXT,
            scopes TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_api_v1_auth_tokens_device
            ON api_v1_auth_tokens(device_id);
        CREATE INDEX IF NOT EXISTS idx_api_v1_auth_tokens_household
            ON api_v1_auth_tokens(household_id);
        CREATE INDEX IF NOT EXISTS idx_api_v1_auth_tokens_expires
            ON api_v1_auth_tokens(expires_at);
        """
    )
    c.commit()


# ── Issue / verify / revoke ──────────────────────────────────────


def issue_token(
    db: Any,
    *,
    device_id: str,
    household_id: str,
    scopes: str = "",
    ttl_days: int = TOKEN_TTL_DAYS,
) -> dict[str, str]:
    """Mint a new token and persist its hash.

    Returns the wire shape ``{token, expires_at, household_id}``
    (the household name is added by the router, which has the
    context to look it up).

    Best-effort: a DB failure raises; the caller decides whether
    to surface a 500 or a 503. Per the v1 contract, we always
    surface 500 because the client cannot recover from a write
    failure.
    """
    if not device_id or not household_id:
        raise ValueError("device_id and household_id are required")

    token = _new_token()
    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=ttl_days)

    db.conn.execute(
        """
        INSERT INTO api_v1_auth_tokens (
            token_hash, device_id, household_id,
            created_at, expires_at, last_used_at, scopes
        ) VALUES (?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            token_hash,
            device_id,
            household_id,
            now.isoformat(),
            expires.isoformat(),
            scopes,
        ),
    )
    db.conn.commit()

    logger.info(
        "Issued v1 auth token for device=%s household=%s expires=%s",
        device_id[:8] + "...",  # never log the full device_id
        household_id,
        expires.isoformat(),
    )

    return {
        "token": token,
        "expires_at": expires.isoformat(),
        "household_id": household_id,
    }


def verify_token(db: Any, token: str) -> dict[str, Any] | None:
    """Look up a token; return the row or ``None`` if missing/expired.

    Side effect: updates ``last_used_at`` for the token (best-effort;
    a write failure here does not invalidate the token, since the
    read already succeeded).
    """
    if not token:
        return None
    token_hash = _hash_token(token)
    cur = db.conn.execute(
        """
        SELECT token_hash, device_id, household_id, created_at,
               expires_at, last_used_at, scopes
        FROM api_v1_auth_tokens
        WHERE token_hash = ?
        """,
        (token_hash,),
    )
    row = cur.fetchone()
    if row is None:
        return None

    # Expired?
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except (ValueError, TypeError):
        return None
    if expires < datetime.now(timezone.utc):
        return None

    # Touch last_used_at (best-effort, do not raise).
    try:
        db.conn.execute(
            "UPDATE api_v1_auth_tokens SET last_used_at = ? WHERE token_hash = ?",
            (datetime.now(timezone.utc).isoformat(), token_hash),
        )
        db.conn.commit()
    except sqlite3.OperationalError as exc:
        # Locked DB; do not invalidate the read result.
        logger.debug("last_used_at update failed: %s", exc)

    return {
        "device_id": row["device_id"],
        "household_id": row["household_id"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "scopes": row["scopes"] or "",
    }


def revoke_token(db: Any, token: str) -> bool:
    """Delete a token. Returns True if a row was removed."""
    if not token:
        return False
    token_hash = _hash_token(token)
    cur = db.conn.execute(
        "DELETE FROM api_v1_auth_tokens WHERE token_hash = ?",
        (token_hash,),
    )
    db.conn.commit()
    return cur.rowcount > 0


def revoke_all_for_device(db: Any, device_id: str) -> int:
    """Delete every token issued for a device. Returns row count.

    Used by ``POST /api/v1/auth/logout`` when the client wants a
    full sign-out across all households.
    """
    if not device_id:
        return 0
    cur = db.conn.execute(
        "DELETE FROM api_v1_auth_tokens WHERE device_id = ?",
        (device_id,),
    )
    db.conn.commit()
    return cur.rowcount


# ── Device-secret verification ───────────────────────────────────


def verify_device_secret(stored: str, presented: str) -> bool:
    """Constant-time compare of two device secrets.

    Per OWASP, string comparison must use ``hmac.compare_digest``
    rather than ``==`` to avoid timing-leak attacks. The
    secrets here are device-level, not user-level, so the
    threat model is low — but the cost of doing it right is
    one import, so we always do it right.
    """
    if not stored or not presented:
        return False
    return hmac.compare_digest(stored.encode("utf-8"), presented.encode("utf-8"))


# ── Cleanup helper ──────────────────────────────────────────────


def purge_expired_tokens(db: Any) -> int:
    """Delete tokens past their expiry. Returns row count.

    Intended to be called from a periodic background task
    (the existing ``data_retention`` service is the right
    home — wiring it is a v1.1 concern). Provided here so
    tests can exercise the path without a background task.
    """
    now = datetime.now(timezone.utc).isoformat()
    cur = db.conn.execute(
        "DELETE FROM api_v1_auth_tokens WHERE expires_at < ?",
        (now,),
    )
    db.conn.commit()
    return cur.rowcount


__all__ = [
    "TOKEN_TTL_DAYS",
    "ensure_auth_table",
    "issue_token",
    "verify_token",
    "revoke_token",
    "revoke_all_for_device",
    "verify_device_secret",
    "purge_expired_tokens",
]
