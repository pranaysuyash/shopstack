"""Today Intelligence UI screen — Phase 9 wiring.

Thin server-rendered panel that pulls the household's
DashboardState, the community pool, and the trip advisor
into a single "what should I do right now?" block.

Wired into the top of the Today tab.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.services.community_price_map import community_median
from shopstack.services.dashboard import build_dashboard_state
from shopstack.services.today_intelligence import (
    build_today_intelligence,
    render_today_intelligence_html,
)
from shopstack.services.trip_advisor import advise_trip, _build_use_soon_count
from shopstack.services.weather import get_weather

logger = logging.getLogger(__name__)


def _gather_community_medians(items: list[dict[str, Any]], city: str = "") -> dict[str, float]:
    """Return {canonical_name: community_median_price} for a small set of items.

    Used to feed the "overpriced vs community" action into the
    Today intelligence view. We cap at 10 items to keep the
    per-render cost bounded.
    """
    out: dict[str, float] = {}
    for it in items[:10]:
        cname = str(it.get("canonical_name") or "")
        if not cname:
            continue
        try:
            summary = community_median(cname, city=city, days=30)
        except Exception:
            summary = None
        if summary is None:
            continue
        out[cname] = float(summary.get("median_price", 0) or 0)
    return out


def today_intelligence_screen(
    city: str = "mumbai",
    max_top: int = 5,
) -> str:
    """Render the unified Today intelligence block for the active household.

    Composes:
    - The dashboard's restock / use-soon / price-drops signals.
    - A small slice of the community pool (top 10 items the
      household has in inventory with a community median).
    - The trip advisor's go/deliver/delay call.
    """
    try:
        user_id = current_user_id() or ""
        state = build_dashboard_state(db, [], user_id=user_id, city=city)
        # Use-soon items for community lookup
        use_soon = _safe_get(state, "use_soon_items", default=[]) or []
        restock = _safe_get(state, "restock_predictions", default=[]) or []
        # Build a small set of canonical names to consult the
        # community pool for. Use-soon + restock is a tight
        # 10-item cap, which is well-bounded.
        cnames: list[dict[str, Any]] = []
        for it in use_soon:
            cname = str(it.get("canonical_name") or "")
            if cname:
                cnames.append({"canonical_name": cname})
        for r in restock:
            cname = str(r.get("canonical_name") or "")
            if cname:
                cnames.append({"canonical_name": cname})
        medians = _gather_community_medians(cnames, city=city)
        # Trip advisor
        try:
            use_soon_count = _build_use_soon_count(db, user_id)
        except Exception:
            use_soon_count = 0
        try:
            weather = get_weather(city=city)
        except Exception:
            weather = None
        trip = advise_trip(
            city=city,
            use_soon_count=use_soon_count,
            price_drop_count=0,
            active_list_size=0,
            weather=weather,
        )
        intel = build_today_intelligence(
            state,
            community_medians=medians,
            trip_advice=trip,
            max_top=max_top,
        )
        return render_today_intelligence_html(intel)
    except Exception as exc:
        logger.warning("today_intelligence_screen failed: %s", exc)
        return (
            "<div class='home-card' style='text-align:center;padding:12px;'>"
            "<div style='color:var(--amber);font-weight:600;'>Could not load today's intelligence</div>"
            f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:4px;'>{escape(str(exc)[:120])}</div>"
            "</div>"
        )


def _safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if obj is None:
            return default
        if isinstance(obj, dict):
            obj = obj.get(k, default)
        else:
            obj = getattr(obj, k, default)
    return obj


__all__ = ["today_intelligence_screen"]
