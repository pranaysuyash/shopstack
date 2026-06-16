"""Decision explainability HTTP endpoint — ``/api/decision/<name>/explain``.

**Why this exists (motto_v3 §0.10 Observability Is Delivery +
motto_v3 first-principles / mode-portable):**

Per Pass 18, the decision engine produces structured reasons
and evidence on every ``DecisionResult``. The
``shopstack.services.explainability`` module composes these
into a human-readable explanation. The CLI surfaces it
(``shopstack cli explain <name>``); this endpoint surfaces it
to any HTTP consumer (the Gradio UI's "Why?" button, a mobile
app, a third-party dashboard).

Mirrors the ``/api/whoami`` mount pattern (see
``shopstack.services.whoami_mount``): a thin FastAPI route
on the Gradio app's underlying app, with best-effort error
handling per `motto_v3` §0.10.

**Mode portability:** the endpoint returns the same
JSON-serializable dict as the CLI's ``explain`` subcommand
and the ``DecisionExplanation`` Pydantic model. Any consumer
that can hit HTTP can use it.
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
