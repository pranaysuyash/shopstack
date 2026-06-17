"""FastAPI ``Depends()`` helpers for the ``/api/v1/*`` surface.

These dependencies are the **request-scoped identity** layer.
Every protected endpoint declares ``household: HouseholdContext =
Depends(require_household)`` and gets a verified, household-scoped
context — no manual token parsing, no manual DB lookups, no
forgetting the auth check.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Reuses :mod:`shopstack.api.v1.auth` for token storage.
* Reuses :func:`shopstack.app_context.db` for the DB handle
  (avoids a second connection pool).

**The Gradio-compat shim:**

``app_context.current_user_id()`` is the synchronous helper the
Gradio screens use. The FastAPI layer is async, so we cannot
*replace* it — but the v1 surface must NOT cause the Gradio
helper to return a different value. The shim lives in
``shopstack.app_context`` (added separately, additively) and
checks the request-scoped state first, falling back to
``db.active_household_id`` for Gradio calls.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)


#: ``HTTPBearer`` does the standard ``Authorization: Bearer <token>``
#: parsing. ``auto_error=False`` so we can emit a custom 401 with our
#: error code (see ``ApiError.code``) rather than FastAPI's default.
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class HouseholdContext:
    """Verified, request-scoped identity.

    The mobile app (and any other external client) calls an
    endpoint with an ``Authorization: Bearer <token>`` header.
    The token is verified against ``api_v1_auth_tokens``; on
    success, the resolver returns this dataclass, and the
    endpoint reads ``ctx.household_id`` to scope its DB calls.

    The dataclass is frozen because it represents a verified
    identity and should not be mutated downstream. If an
    endpoint needs to add metadata, it composes its own
    dataclass with ``HouseholdContext`` as a field.
    """

    household_id: str
    device_id: str
    scopes: str
    raw_token: str  # held so logout can revoke by token


# ── Dependencies ──────────────────────────────────────────────


def _extract_bearer(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Pull the bearer token out of the request, or raise 401.

    Order of resolution:
    1. ``Authorization: Bearer <token>`` header (the standard)
    2. ``?token=...`` query string (escape hatch for the
       Gradio-rendered client when JS isn't available)

    The query-string path is documented in the OpenAPI and
    logged at INFO so we can spot misuse.
    """
    if creds is not None and creds.scheme.lower() == "bearer" and creds.credentials:
        return creds.credentials
    qs = request.query_params.get("token", "").strip()
    if qs:
        logger.info(
            "Query-string bearer token used for %s %s",
            request.method,
            request.url.path,
        )
        return qs
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "missing_bearer_token",
            "message": "Authorization: Bearer <token> header is required.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_household(
    request: Request,
    token: str = Depends(_extract_bearer),
) -> HouseholdContext:
    """Resolve the bearer token to a verified ``HouseholdContext``.

    Raises 401 on missing/expired/invalid token. Raises 500 only
    on a DB catastrophe (which we cannot recover from).

    The resolved context is stashed on ``request.state`` and the
    household_id is also pushed into the app_context ContextVar
    so that ``current_user_id()`` returns the per-request value
    for the duration of the request. We use a try/finally reset
    in the calling endpoint OR a FastAPI dependency that runs
    on response — for now we set the ContextVar here and rely
    on Starlette's per-task isolation to clean it up.
    """
    # Lazy import to avoid a hard dep on shopstack.app_context at
    # module import time (lets tests instantiate the schema layer
    # without booting the DB).
    from shopstack.api.v1 import auth as auth_mod
    from shopstack.app_context import db, set_request_household

    row = auth_mod.verify_token(db, token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_or_expired_token",
                "message": "The bearer token is invalid, expired, or revoked.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    ctx = HouseholdContext(
        household_id=row["household_id"],
        device_id=row["device_id"],
        scopes=row["scopes"],
        raw_token=token,
    )
    request.state.household_ctx = ctx

    # Push the household_id into the request-scoped ContextVar
    # so that any downstream ``current_user_id()`` call returns
    # the token's household, not the persistent
    # db.active_household_id. Starlette tasks are isolated, so
    # this setting does not leak across concurrent requests.
    set_request_household(ctx.household_id)
    return ctx


__all__ = ["HouseholdContext", "require_household"]
