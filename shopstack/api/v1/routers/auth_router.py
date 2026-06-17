"""``/api/v1/auth/*`` — token issuance, refresh, logout.

**Flow (v1):**

1. **First launch** (no prior token):

   * Mobile generates a random ``device_secret`` (256 bits) and
     a stable ``device_id`` (iOS identifierForVendor / Android
     ANDROID_ID / browser fingerprint).
   * Mobile calls ``POST /api/v1/auth/register`` with both
     and the household name it wants to bootstrap.
   * Server stores the device_id → device_secret hash, creates
     the household, and returns a token.

2. **Subsequent launches**:

   * Mobile calls ``POST /api/v1/auth/login`` with the same
     ``device_id`` + ``device_secret`` pair.
   * Server verifies the secret, lists the device's known
     households, returns a token scoped to the requested
     household.

3. **Session maintenance**:

   * Mobile calls ``POST /api/v1/auth/refresh`` before the
     token expires (server extends the expiry, same token).
   * Mobile calls ``POST /api/v1/auth/logout`` on explicit
     sign-out (server deletes the token; client discards its
     copy).

**Why v1 does NOT ship a password flow:**

The local-first premise is that the mobile app and the backend
share a device. A device-level secret is sufficient for v1.
A future ``v2/auth/sso`` adds a real identity provider and
multi-device-per-user flows.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from shopstack.api.v1 import auth as auth_mod
from shopstack.api.v1.schemas import ApiError, LoginRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── device-secrets table ──────────────────────────────────────────


def ensure_device_table(db: Any) -> None:
    """Create the device-secrets table if missing.

    Stores ``sha256(device_secret)`` keyed by ``device_id``. The
    plaintext secret is held only by the client.
    """
    db.conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_v1_device_secrets (
            device_id TEXT PRIMARY KEY,
            secret_hash BLOB NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT
        );
        """
    )
    db.conn.commit()


def _hash_secret(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _lookup_device(db: Any, device_id: str) -> dict[str, Any] | None:
    cur = db.conn.execute(
        "SELECT device_id, secret_hash, created_at, last_seen_at "
        "FROM api_v1_device_secrets WHERE device_id = ?",
        (device_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def _register_device(db: Any, device_id: str, secret: str) -> None:
    """Register a device + its secret. Idempotent on device_id."""
    secret_hash = _hash_secret(secret)
    now = datetime.now(timezone.utc).isoformat()
    db.conn.execute(
        """
        INSERT INTO api_v1_device_secrets (device_id, secret_hash, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET secret_hash = excluded.secret_hash
        """,
        (device_id, secret_hash, now),
    )
    db.conn.commit()


def _touch_device(db: Any, device_id: str) -> None:
    """Update last_seen_at for a device. Best-effort."""
    try:
        db.conn.execute(
            "UPDATE api_v1_device_secrets SET last_seen_at = ? WHERE device_id = ?",
            (datetime.now(timezone.utc).isoformat(), device_id),
        )
        db.conn.commit()
    except sqlite3.OperationalError:
        pass


# ── request models ───────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """``POST /api/v1/auth/register`` — first-launch registration.

    The mobile app generates a random 256-bit ``device_secret``,
    sends it once, and stores it in the platform keystore. The
    server stores only the hash.
    """

    device_id: str = Field(..., min_length=8, max_length=128)
    device_secret: str = Field(..., min_length=32, max_length=512)
    household_name: str = Field(..., min_length=1, max_length=80)
    household_id: str | None = Field(
        default=None,
        max_length=80,
        description="Optional explicit household ID. If omitted, "
        "the server derives one from the device_id.",
    )


class RefreshRequest(BaseModel):
    """``POST /api/v1/auth/refresh`` body — same shape as login, but
    used to extend an existing token's lifetime without rotation.
    """

    token: str = Field(..., description="Existing bearer token to refresh.")


class LogoutRequest(BaseModel):
    """``POST /api/v1/auth/logout`` body."""

    token: str = Field(..., description="Bearer token to revoke.")
    all_devices: bool = Field(
        default=False,
        description="If True, revoke every token for the device. "
        "Use this for full sign-out (lost device, account reset).",
    )


# ── helpers ──────────────────────────────────────────────────────


def _resolve_household(db: Any, requested: str | None) -> tuple[str, str]:
    """Resolve a household_id + display name from a request.

    If the requested household exists, use it. Otherwise create
    a new one and return the new id. The (id, name) tuple is
    the source of truth for the token's scope.
    """
    households = db.list_households() or []
    if requested:
        for h in households:
            if h.get("household_id") == requested:
                return h["household_id"], h.get("name") or requested
        # Requested but not found — create.
        name = requested
        db.add_household(requested, name)
        return requested, name

    # No requested: pick the default household if it exists,
    # else create a default. Per the existing ground rule,
    # "default_household" is always present in a fresh DB.
    for h in households:
        if h.get("household_id") == "default_household":
            return "default_household", h.get("name") or "Default"
    db.add_household("default_household", "Default")
    return "default_household", "Default"


# ── endpoints ─────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="First-launch device registration",
)
def register(req: RegisterRequest) -> TokenResponse:
    """Register a new device + bootstrap a household.

    Idempotent on ``device_id``: re-registering replaces the
    stored secret hash (handles the "I reinstalled the app"
    case). The ``household_name`` is only used on the first
    registration; subsequent calls keep the existing
    household scope.
    """
    from shopstack.app_context import db

    ensure_device_table(db)
    auth_mod.ensure_auth_table(db)

    _register_device(db, req.device_id, req.device_secret)

    # On first registration, create the household if absent.
    households = db.list_households() or []
    if not any(h.get("household_id") == req.household_id for h in households if req.household_id):
        # Derive a household_id if not provided.
        if not req.household_id:
            req.household_id = "hh_" + secrets.token_hex(6)
        db.add_household(req.household_id, req.household_name)

    hh_id, hh_name = _resolve_household(db, req.household_id)
    try:
        db.add_household_member(hh_id, hh_id, role="owner")
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth register owner-membership bootstrap failed: %s", exc)
    issued = auth_mod.issue_token(
        db, device_id=req.device_id, household_id=hh_id,
    )
    return TokenResponse(
        token=issued["token"],
        expires_at=issued["expires_at"],
        household_id=hh_id,
        household_name=hh_name,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Device login (subsequent launches)",
)
def login(req: LoginRequest) -> TokenResponse:
    """Re-authenticate a previously registered device.

    Returns a fresh token scoped to ``requested_household_id``
    (or the device's default household if omitted). The old
    tokens are NOT revoked; the device may hold several
    simultaneously.
    """
    from shopstack.app_context import db

    ensure_device_table(db)
    auth_mod.ensure_auth_table(db)

    device = _lookup_device(db, req.device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(
                code="unknown_device",
                message="This device is not registered. Call POST /api/v1/auth/register first.",
            ).model_dump(),
        )

    secret_hash = _hash_secret(req.device_secret)
    if not hmac.compare_digest(secret_hash, device["secret_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(
                code="bad_device_secret",
                message="The device_secret does not match the stored hash.",
            ).model_dump(),
        )

    _touch_device(db, req.device_id)

    hh_id, hh_name = _resolve_household(db, req.requested_household_id)
    issued = auth_mod.issue_token(
        db, device_id=req.device_id, household_id=hh_id,
    )
    return TokenResponse(
        token=issued["token"],
        expires_at=issued["expires_at"],
        household_id=hh_id,
        household_name=hh_name,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Extend an existing token's lifetime",
)
def refresh(req: RefreshRequest) -> TokenResponse:
    """Extend an existing token's ``expires_at`` by 30 days.

    The token itself is not rotated (rotation is a v1.1
    concern). If the token is invalid or expired, this returns
    401 — the client must then call ``/auth/login`` again.
    """
    from shopstack.app_context import db

    auth_mod.ensure_auth_table(db)
    row = auth_mod.verify_token(db, req.token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(
                code="invalid_or_expired_token",
                message="The token is invalid or expired.",
            ).model_dump(),
        )

    # verify_token() also touches last_used_at; we now extend expires_at.
    new_expires = (
        datetime.now(timezone.utc).timestamp() + auth_mod.TOKEN_TTL_DAYS * 86400
    )
    new_expires_iso = datetime.fromtimestamp(
        new_expires, tz=timezone.utc
    ).isoformat()
    db.conn.execute(
        "UPDATE api_v1_auth_tokens SET expires_at = ? WHERE token_hash = ?",
        (new_expires_iso, auth_mod._hash_token(req.token)),
    )
    db.conn.commit()

    hh_id, hh_name = _resolve_household(db, row["household_id"])
    return TokenResponse(
        token=req.token,
        expires_at=new_expires_iso,
        household_id=hh_id,
        household_name=hh_name,
    )


@router.post(
    "/logout",
    summary="Revoke a token (or all tokens for a device)",
)
def logout(req: LogoutRequest) -> dict[str, Any]:
    """Revoke the presented token. If ``all_devices`` is true,
    revoke every token for the device that issued it.
    """
    from shopstack.app_context import db

    auth_mod.ensure_auth_table(db)
    if req.all_devices:
        # Look up the device_id for the presented token first.
        row = auth_mod.verify_token(db, req.token)
        if row is None:
            return {"revoked": 0, "note": "token not found"}
        n = auth_mod.revoke_all_for_device(db, row["device_id"])
        return {"revoked": n, "all_devices": True, "device_id_prefix": row["device_id"][:8] + "..."}

    n = auth_mod.revoke_token(db, req.token)
    return {"revoked": 1 if n else 0}


__all__ = ["router", "ensure_device_table"]
