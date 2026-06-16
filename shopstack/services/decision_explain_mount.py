"""Decision explainability + recurring shopping HTTP endpoints.

**Why this exists (motto_v3 §0.10 Observability Is Delivery +
motto_v3 first-principles / mode-portable):**

Per Pass 18, the decision engine produces structured reasons
and evidence on every ``DecisionResult``. The
``shopstack.services.explainability`` module composes these
into a human-readable explanation. Per Pass 19, the
recurring shopping plan surfaces items the user typically
buys on a regular cadence and that are due within a window.

This module mounts the HTTP endpoints for both:
  - ``GET /api/decision/<name>/explain`` (Pass 18)
  - ``GET /api/recurring`` (Pass 19)

Both follow the ``mount_*_endpoint`` pattern from
``shopstack.services.whoami_mount``. They are best-effort:
sub-check failures return 200 with a partial payload
(``error: <code>``) rather than 5xx. This makes the
endpoints useful in degraded states.
"""
from __future__ import annotations

import logging

import gradio as gr

logger = logging.getLogger(__name__)


def mount_decision_explain_endpoint(
    app: gr.Blocks,
    *,
    path: str = "/api/decision",
) -> None:
    """Mount the ``GET /api/decision/<name>/explain`` route.

    Args:
        app: The ``gr.Blocks`` instance returned by ``build_app()``.
        path: Route prefix. Defaults to ``/api/decision``.

    The route is ``GET /api/decision/<name>/explain`` where
    ``<name>`` is the canonical item name. Returns a JSON
    dict with either the ``DecisionExplanation`` shape or an
    ``error`` field.

    Per `motto_v3` §0.10 (Observability Is Delivery), the
    route is best-effort: sub-check failures return a 200
    with a partial payload (``error: no_decision``) rather
    than a 5xx. This makes the endpoint useful in degraded
    states (e.g. when the dashboard state is missing).
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def _explain(request: Request) -> JSONResponse:
        from shopstack.app_context import db as app_db, tools
        from shopstack.services.dashboard import build_dashboard_state
        from shopstack.services.explainability import (
            explain_decision,
            explanation_to_dict,
        )

        # Extract the canonical name from the path:
        # /api/decision/<name>/explain
        path = request.url.path
        # Path-strip logic — Starlette gives us the full path.
        # Expected: /api/decision/<name>/explain
        prefix = "/api/decision/"
        suffix = "/explain"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return JSONResponse(
                {
                    "error": "bad_path",
                    "message": (
                        f"Path must match {prefix}<name>{suffix}. "
                        f"Got: {path}"
                    ),
                },
                status_code=400,
            )
        canonical_name = path[len(prefix):-len(suffix)]
        if not canonical_name:
            return JSONResponse(
                {"error": "missing_name", "message": "canonical name is required"},
                status_code=400,
            )

        uid = None
        try:
            from shopstack.app_context import current_user_id
            uid = current_user_id() or "default_household"
        except Exception:
            uid = "default_household"

        # Build the dashboard state and find the matching decision.
        try:
            state = build_dashboard_state(app_db, tools.inventory, user_id=uid)
            ds = state.decision_set
            all_decisions = (
                list(ds.buy) + list(ds.skip) + list(ds.use_soon)
                + list(ds.compare) + list(ds.substitute) + list(ds.wait)
            )
            matches = [
                d for d in all_decisions if d.canonical_name == canonical_name
            ]
            if not matches:
                return JSONResponse(
                    {
                        "error": "no_decision",
                        "message": (
                            f"No active decision for canonical_name={canonical_name!r}."
                        ),
                        "canonical_name": canonical_name,
                    },
                    status_code=200,
                )
            # Prefer highest-priority / highest-confidence match.
            matches.sort(key=lambda d: (-d.priority, -d.confidence))
            explanation = explain_decision(matches[0])
            return JSONResponse(
                explanation_to_dict(explanation),
                status_code=200,
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning(
                "Could not build decision explanation for %s: %s",
                canonical_name,
                exc,
            )
            return JSONResponse(
                {
                    "error": "explain_failed",
                    "message": f"{type(exc).__name__}: {exc}",
                    "canonical_name": canonical_name,
                },
                status_code=200,
            )

    # The Starlette router expects a path pattern, not a regex
    # by default. ``/api/decision/{name}/explain`` matches the
    # dynamic ``<name>`` segment.
    route = "/api/decision/{name}/explain"
    try:
        app.app.add_route(route, _explain, methods=["GET"])
        logger.info("Decision-explain endpoint mounted at %s", route)
    except Exception as exc:  # noqa: BLE001 — best-effort mount
        logger.warning("Could not mount decision-explain endpoint: %s", exc)


__all__ = ["mount_decision_explain_endpoint"]


# ── Recurring shopping endpoint (Pass 19) ──────────────────────────


def mount_recurring_endpoint(
    app: gr.Blocks,
    *,
    path: str = "/api/recurring",
) -> None:
    """Mount the ``GET /api/recurring`` route.

    Optional query params (parsed from the request URL):
      - ``window`` (int, default 3): days window for the plan.

    Returns a JSON dict with:
      - ``window_days`` (int)
      - ``summary`` (str): one-line summary ("3 items due...")
      - ``count`` (int)
      - ``items`` (list): each item is a ``DecisionExplanation``
        dict (from the explainability service) plus
        ``days_until_next`` and ``typical_interval_days``.

    Per `motto_v3` §0.10 (Observability Is Delivery), the
    route is best-effort: sub-check failures return 200 with
    an ``error: <code>`` field rather than 5xx.
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def _recurring(request: Request) -> JSONResponse:
        from shopstack.app_context import db as app_db
        from shopstack.services.recurring_shopping import (
            build_recurring_shopping_plan,
            summarize_plan,
        )
        from shopstack.services.explainability import (
            explain_decision,
            explanation_to_dict,
        )

        # Parse the window query param (default 3).
        window = 3
        try:
            window_raw = request.query_params.get("window")
            if window_raw is not None:
                window = max(0, int(window_raw))
        except (ValueError, TypeError):
            window = 3

        try:
            plan = build_recurring_shopping_plan(app_db, user_id="", window_days=window)
            items = []
            for d in plan:
                items.append({
                    **explanation_to_dict(explain_decision(d)),
                    "days_until_next": _extract_days_until_next_from_decision(d),
                    "typical_interval_days": _extract_interval_from_decision(d),
                })
            return JSONResponse(
                {
                    "window_days": window,
                    "summary": summarize_plan(plan),
                    "count": len(plan),
                    "items": items,
                },
                status_code=200,
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("Could not build recurring plan: %s", exc)
            return JSONResponse(
                {
                    "error": "recurring_failed",
                    "message": f"{type(exc).__name__}: {exc}",
                    "items": [],
                },
                status_code=200,
            )

    try:
        app.app.add_route(path, _recurring, methods=["GET"])
        logger.info("Recurring endpoint mounted at %s", path)
    except Exception as exc:  # noqa: BLE001 — best-effort mount
        logger.warning("Could not mount recurring endpoint at %s: %s", path, exc)


def _extract_days_until_next_from_decision(d) -> int | None:
    """Pull the days-until-next number from a DecisionResult's reasons."""
    import re
    for r in d.reasons:
        if "due" not in r:
            continue
        if "today" in r:
            return 0
        if "tomorrow" in r:
            return 1
        m = re.search(r"in\s+(\d+)\s+days", r)
        if m:
            return int(m.group(1))
        m = re.search(r"due\s+(\d+)\s+days\s+ago", r)
        if m:
            return -int(m.group(1))
    return None


def _extract_interval_from_decision(d) -> float | None:
    """Pull the avg-interval-days number from a DecisionResult's reasons."""
    import re
    for r in d.reasons:
        m = re.search(r"every\s+([\d.]+)\s+days", r)
        if m:
            return float(m.group(1))
    return None


__all__ = [
    "mount_decision_explain_endpoint",
    "mount_recurring_endpoint",
]


# ── Meal plan endpoint (Pass 21) ──────────────────────────────────


def mount_mealplan_endpoint(
    app: gr.Blocks,
    *,
    path: str = "/api/mealplan",
) -> None:
    """Mount the ``GET /api/mealplan`` route.

    Optional query params (parsed from the request URL):
      - ``days`` (int, default 7): number of days to plan.
      - ``start`` (str, YYYY-MM-DD, default today): start date.

    Returns a JSON dict with:
      - ``summary`` (str): one-line summary
      - ``days`` (int)
      - ``start_date`` (str)
      - ``count`` (int)
      - ``items`` (list): each item is a ``DayPlan`` dict

    Per `motto_v3` §0.10 (Observability Is Delivery), the
    route is best-effort: sub-check failures return 200 with
    an ``error: <code>`` field rather than 5xx.
    """
    from datetime import datetime
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def _mealplan(request: Request) -> JSONResponse:
        from shopstack.app_context import db as app_db
        from shopstack.services.meal_planning import (
            build_weekly_meal_plan,
            summarize_meal_plan,
        )

        # Parse query params with defaults.
        days = 7
        start = None
        try:
            days_raw = request.query_params.get("days")
            if days_raw is not None:
                days = max(1, min(28, int(days_raw)))
            start_raw = request.query_params.get("start")
            if start_raw:
                start = datetime.strptime(start_raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

        try:
            plan = build_weekly_meal_plan(
                app_db, user_id="", start_date=start, days=days,
            )
            return JSONResponse(
                {
                    "summary": summarize_meal_plan(plan),
                    "days": days,
                    "start_date": (start.isoformat() if start else (plan[0].date if plan else None)),
                    "count": len(plan),
                    "items": [d.model_dump(mode="json") for d in plan],
                },
                status_code=200,
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("Could not build meal plan: %s", exc)
            return JSONResponse(
                {
                    "error": "mealplan_failed",
                    "message": f"{type(exc).__name__}: {exc}",
                    "items": [],
                },
                status_code=200,
            )

    try:
        app.app.add_route(path, _mealplan, methods=["GET"])
        logger.info("Meal plan endpoint mounted at %s", path)
    except Exception as exc:  # noqa: BLE001 — best-effort mount
        logger.warning("Could not mount meal plan endpoint at %s: %s", path, exc)
