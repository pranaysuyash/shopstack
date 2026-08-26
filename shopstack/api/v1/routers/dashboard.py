"""``/api/v1/dashboard/*`` — the Today dashboard data snapshot.

The legacy dashboard builder returns **rendered HTML** (six
panel strings). That is the wrong layer for an API contract — a mobile
client cannot cache or diff HTML. This router exposes the underlying
*data* state via :func:`shopstack.services.dashboard.build_dashboard_state`,
so the mobile app can draw its own home screen and cache the snapshot
for offline use.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Reuses :func:`build_dashboard_state` — the exact same assembly the
  dashboard uses (motto_v3 §6 + §7: no parallel truth source).
* Projects the rich ``DashboardState`` dataclass down to a small,
  stable wire shape (``DashboardSnapshot``): counts + the three
  highest-value item lists. Extra fields are added to the wire schema
  in a later pass; the underlying state already has them.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import DashboardSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/today",
    response_model=DashboardSnapshot,
    summary="Today dashboard data snapshot (offline-cacheable)",
)
def today(
    ctx: HouseholdContext = Depends(require_household),
) -> DashboardSnapshot:
    """Return a data snapshot of the caller's Today dashboard.

Fields mirror the top panels of the web home screen:
    pantry count, use-first count, need-shopping count, just-bought
    count, plus the underlying item lists. The mobile app caches
    this to render offline and refreshes on app foreground.
    """
    from shopstack.app_context import db, tools
    from shopstack.services.dashboard import build_dashboard_state

    try:
        state = build_dashboard_state(db, tools.inventory, user_id=ctx.household_id)
    except Exception as exc:  # noqa: BLE001 — never 500 the home screen
        logger.warning("dashboard state build failed: %s", exc)
        return DashboardSnapshot(household_id=ctx.household_id)

    return DashboardSnapshot(
        household_id=ctx.household_id,
        pantry_count=len(state.active_inventory),
        use_soon_count=state.use_soon_count,
        low_items_count=len(state.low_items),
        recent_purchases_count=len(state.recent_purchases),
        use_soon_items=_safe_items(state.use_soon_items),
        low_items=_safe_items(state.low_items),
        recent_purchases=_safe_items(state.recent_purchases),
        has_trip_recommendation=bool(state.has_trip_recommendation),
    )


def _safe_items(items: Any) -> list[dict[str, Any]]:
    """Coerce a list of models/dicts into JSON-serialisable dicts.

    DashboardState holds a mix of Pydantic models, dataclasses, and
    plain dicts. Pydantic v2 model_dump handles models; ``vars()``
    handles dataclasses; dicts pass through. Anything that fails
    serialisation is stringified so the snapshot never 500s on a
    single bad row.
    """
    out: list[dict[str, Any]] = []
    if not items:
        return out
    for it in items:
        try:
            if hasattr(it, "model_dump"):
                out.append(it.model_dump())
            elif isinstance(it, dict):
                out.append(it)
            elif hasattr(it, "__dict__"):
                out.append(vars(it))
            else:
                out.append({"value": str(it)})
        except Exception:  # noqa: BLE001
            out.append({"value": str(it)})
    return out


__all__ = ["router"]
