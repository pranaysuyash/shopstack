"""ShopStack CLI consumer — mode-portability proof.

**Why this exists (motto_v3 §0.10 Observability Is Delivery +
motto_v3 first-principles / mode-agnostic):**

The ShopStack app has a Gradio UI for end-users. But the
*concepts* (Home / Pantry / Shopping / Recipes / Trips / Memory)
are not bound to Gradio — they're domain concepts that should
be consumable from any front-end (Gradio today, Streamlit /
Next.js / React Native / CLI tomorrow).

This CLI is the smallest possible proof that the public service
API (``shopstack.app_context.tools``) can be consumed from a
non-Gradio mode. It:

  1. Imports ``shopstack.app_context`` (NOT ``app.py``).
  2. Calls the same public service methods the Gradio UI calls.
  3. Outputs JSON to stdout by default (programmatic consumers).
  4. Has a ``--human`` flag for terminal-friendly output.

The CLI itself is intentionally minimal — 5 subcommands covering
the most common operator questions:
  - ``inventory`` : what do I have at home?
  - ``shopping``  : what's on my shopping list?
  - ``find NAME`` : where is item X in inventory?
  - ``use-soon``  : what expires next?
  - ``next-buy``  : what should I buy next?
  - ``tools``     : what services does the API expose?
  - ``whoami``    : which household / DB am I in?

Per motto_v3 §0.14 (product reality), the operator's actual jobs
are: "did the latest deploy break anything?", "what's in the
test household's pantry?", "can I trigger a function without
launching Gradio?" This CLI answers those without a Gradio boot
(``build_app()`` takes ~5-10s; this CLI cold-starts in <2s).

**Architectural contract:**

This module MUST NOT import ``app`` or ``gradio`` (other than
indirectly via ``app_context``). The whole point of the CLI is
to prove the public service API works without the UI layer.

If you need to add a UI-specific feature, add it to
``shopstack.ui.*`` and the CLI exposes the underlying public
service method.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

# Import only the public service layer — NOT app.py or gradio.
# This is the contract: the CLI is mode-portable.
from shopstack.app_context import current_user_id, db, tools


def _serialize(obj: Any) -> Any:
    """Best-effort JSON serializer for domain objects.

    Falls back to ``str(obj)`` if the object isn't natively
    JSON-serializable. The point is to give operators *something*
    readable, not to enforce a strict schema.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(_serialize(v) for v in obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _serialize(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return _serialize({k: v for k, v in obj.__dict__.items() if not k.startswith("_")})
    return str(obj)


def cmd_inventory(args: argparse.Namespace) -> dict[str, Any]:
    """Return the active household's inventory as JSON.

    Reads via ``db.get_inventory(user_id=current_user_id())`` —
    the same accessor the Gradio dashboard calls. Capped at
    ``args.limit`` rows to keep the response bounded.
    """
    uid = current_user_id() or "default_household"
    lots = db.get_inventory(user_id=uid)
    if args.limit:
        lots = lots[: args.limit]
    return {
        "household": uid,
        "count": len(lots),
        "items": _serialize(lots),
    }


def cmd_shopping(args: argparse.Namespace) -> dict[str, Any]:
    """Return the active household's shopping list as JSON."""
    uid = current_user_id() or "default_household"
    repo = tools.shopping_list
    # ShoppingListRepo is mode-portable; the public surface is the
    # methods that work without Gradio context. ``list_active`` /
    # ``list_for_user`` are the canonical accessors.
    if hasattr(repo, "list_for_user"):
        items = repo.list_for_user(uid)
    elif hasattr(repo, "list_active"):
        items = repo.list_active()
    else:
        items = []
    return {
        "household": uid,
        "count": len(items) if isinstance(items, list) else 0,
        "items": _serialize(items),
    }


def cmd_find(args: argparse.Namespace) -> dict[str, Any]:
    """Search inventory for ``args.name``.

    Uses ``tools.find_item(name)`` (the same method the Ask
    ShopStack service uses). Returns ranked matches.
    """
    result = tools.find_item(args.name)
    return _serialize(result)


def cmd_use_soon(args: argparse.Namespace) -> dict[str, Any]:
    """List items expiring within ``args.days`` days (default 7).

    Uses ``tools.get_use_soon_items(days=N)`` (the same method
    the Pantry card on the dashboard uses).
    """
    days = args.days or 7
    # ``get_use_soon_items`` is a thin wrapper that accepts ``*a, **kw``
    # and forwards to ``tools.inventory.get_use_soon(days=...)``. Pass
    # the ``days`` kwarg explicitly to keep the contract clear.
    result = tools.get_use_soon_items(days=days)
    # ``get_use_soon`` returns a dict like ``{"items": [...], "count": N}``
    # rather than a bare list. Normalize the contract here.
    if isinstance(result, dict):
        items = result.get("items", [])
        return {
            "days_threshold": days,
            "count": len(items),
            "items": _serialize(items),
        }
    return {
        "days_threshold": days,
        "count": len(result) if isinstance(result, list) else 0,
        "items": _serialize(result),
    }


def cmd_next_buy(args: argparse.Namespace) -> dict[str, Any]:
    """Return the next-buy suggestions.

    Uses ``tools.get_next_buy_suggestions()`` (the same method
    the Trips tab calls). The result may be either a list of
    items or a dict with a ``suggestions`` key (depending on
    the service layer version) — normalize to a consistent
    shape here.
    """
    result = tools.get_next_buy_suggestions()
    if isinstance(result, dict):
        items = result.get("suggestions", result.get("items", []))
        return {
            "count": len(items) if isinstance(items, list) else 0,
            "items": _serialize(items),
        }
    return {
        "count": len(result) if isinstance(result, list) else 0,
        "items": _serialize(result),
    }


def cmd_tools(args: argparse.Namespace) -> dict[str, Any]:
    """List the public service API surface.

    Uses ``tools.tool_specs()`` (the same method the planner
    uses to discover which tools it can call). This is the
    mode-portability proof: the same surface that powers the
    Gradio UI powers this CLI.
    """
    specs = tools.tool_specs()
    out = []
    for s in specs:
        out.append({
            "name": s.name,
            "description": s.description,
        })
    return {"count": len(out), "tools": out}


def cmd_whoami(args: argparse.Namespace) -> dict[str, Any]:
    """Return the operator's context: active household + DB path + pid.

    This is the CLI counterpart of the ``/api/whoami`` HTTP
    endpoint (added in Pass 17). Operators running this CLI
    from a shell get the same introspection data.
    """
    import logging
    from datetime import datetime, timezone
    logger = logging.getLogger(__name__)

    uid = current_user_id() or "default_household"
    db_path = getattr(db, "db_path", None)
    size_bytes = None
    if db_path:
        try:
            size_bytes = os.path.getsize(db_path)
        except OSError as exc:
            logger.debug("whoami: could not stat db: %s", exc)

    table_count = None
    try:
        cur = db.conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'")
        table_count = cur.fetchone()[0]
    except Exception:
        pass

    return {
        "household": uid,
        "database": {
            "path": db_path,
            "size_bytes": size_bytes,
            "table_count": table_count,
        },
        "runtime": {
            "pid": os.getpid(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def cmd_explain(args: argparse.Namespace) -> dict[str, Any]:
    """Explain the decision for ``args.canonical_name``.

    Per Pass 18, the decision engine produces a
    ``DecisionResult`` with structured reasons and evidence
    for every recommendation. This subcommand surfaces that
    explanation to the operator without launching the Gradio
    UI.

    The result is a JSON-serializable dict (the same shape
    the HTTP ``/api/decision/{name}/explain`` endpoint
    returns). The ``--human`` flag renders the explanation
    as plain text for terminal consumption.
    """
    from shopstack.services.explainability import (
        explain_decision,
        explanation_to_dict,
    )
    from shopstack.services.dashboard import build_dashboard_state
    from shopstack.app_context import tools

    uid = current_user_id() or "default_household"
    # Build the dashboard state and find the matching decision.
    state = build_dashboard_state(db, tools.inventory, user_id=uid)
    ds = state.decision_set
    all_decisions = (
        list(ds.buy) + list(ds.skip) + list(ds.use_soon)
        + list(ds.compare) + list(ds.substitute) + list(ds.wait)
    )
    matches = [d for d in all_decisions if d.canonical_name == args.canonical_name]
    if not matches:
        return {
            "error": "no_decision",
            "message": (
                f"No active decision for canonical_name={args.canonical_name!r}. "
                f"The item may not need a decision right now (e.g. well-stocked), "
                f"or the name may not match what ShopStack uses."
            ),
            "canonical_name": args.canonical_name,
        }
    # Prefer the highest-priority / highest-confidence match.
    matches.sort(key=lambda d: (-d.priority, -d.confidence))
    explanation = explain_decision(matches[0])
    return explanation_to_dict(explanation)


def cmd_recurring(args: argparse.Namespace) -> dict[str, Any]:
    """Show items due in the user's shopping rhythm.

    Per Pass 19, the recurring shopping plan surfaces the
    items the user typically buys on a regular cadence and
    that are due within ``--window`` days (default 3). The
    output is the same data the dashboard's "shopping
    rhythm" card shows.

    The result is a JSON-serializable dict. With ``--human``,
    it's a plain-text summary.
    """
    from shopstack.services.recurring_shopping import (
        build_recurring_shopping_plan,
        summarize_plan,
    )
    from shopstack.services.explainability import (
        explain_decision,
        explanation_to_dict,
    )

    window = args.window or 3
    plan = build_recurring_shopping_plan(db, user_id="", window_days=window)
    return {
        "window_days": window,
        "summary": summarize_plan(plan),
        "count": len(plan),
        "items": [
            {
                **explanation_to_dict(explain_decision(d)),
                "days_until_next": _extract_days_until_next(d),
                "typical_interval_days": _extract_interval(d),
            }
            for d in plan
        ],
    }


def _extract_days_until_next(d) -> int | None:
    """Pull the days-until-next number from a DecisionResult's reasons.

    The recurring-shopping plan embeds the days-until-next
    in a reason like "is due in 2 days" or "is due today" or
    "was due 1 day ago". This helper extracts the number.
    """
    for r in d.reasons:
        if "due" not in r:
            continue
        # "is due today" → 0
        if "today" in r:
            return 0
        # "is due tomorrow" → 1
        if "tomorrow" in r:
            return 1
        # "is due in N days" → N
        m = re.search(r"in\s+(\d+)\s+days", r)
        if m:
            return int(m.group(1))
        # "was due N days ago" → -N
        m = re.search(r"due\s+(\d+)\s+days\s+ago", r)
        if m:
            return -int(m.group(1))
    return None


def _extract_interval(d) -> float | None:
    """Pull the avg-interval-days number from a DecisionResult's reasons."""
    for r in d.reasons:
        # "you buy Milk every 3 days" → 3
        m = re.search(r"every\s+([\d.]+)\s+days", r)
        if m:
            return float(m.group(1))
    return None


# ── Subcommand dispatch ─────────────────────────────────────────────


SUBCOMMANDS = {
    "inventory": cmd_inventory,
    "shopping": cmd_shopping,
    "find": cmd_find,
    "use-soon": cmd_use_soon,
    "next-buy": cmd_next_buy,
    "tools": cmd_tools,
    "whoami": cmd_whoami,
    "explain": cmd_explain,
    "recurring": cmd_recurring,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Kept separate from ``main()`` so tests can exercise the
    parser without invoking ``sys.argv``.
    """
    parser = argparse.ArgumentParser(
        prog="shopstack-cli",
        description=(
            "ShopStack CLI consumer — public service API access "
            "without launching the Gradio UI. See "
            "shopstack/cli/__init__.py for the architecture."
        ),
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Pretty-print output (default: JSON for programmatic consumers).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Cap on rows returned (default 50; 0 = no cap).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory", help="List household inventory")
    sub.add_parser("shopping", help="Show current shopping list")
    p_find = sub.add_parser("find", help="Search inventory for an item")
    p_find.add_argument("name", help="Item name to search for")
    p_use_soon = sub.add_parser("use-soon", help="List items expiring soon")
    p_use_soon.add_argument(
        "--days", type=int, default=7, help="Days threshold (default 7)"
    )
    sub.add_parser("next-buy", help="Show next-buy suggestions")
    sub.add_parser("tools", help="List the public service API surface")
    sub.add_parser("whoami", help="Show operator context (household, DB, pid)")
    p_explain = sub.add_parser(
        "explain",
        help="Explain the decision for a canonical item name (Pass 18)",
    )
    p_explain.add_argument(
        "canonical_name",
        help="The canonical item name (e.g. 'milk', 'rice', 'toothpaste')",
    )
    p_recurring = sub.add_parser(
        "recurring",
        help="Show items due in your shopping rhythm (Pass 19)",
    )
    p_recurring.add_argument(
        "--window",
        type=int,
        default=3,
        help="Days window for the plan (default 3)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code (0 = success)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = SUBCOMMANDS.get(args.cmd)
    if handler is None:
        parser.error(f"Unknown command: {args.cmd}")
        return 2
    try:
        payload = handler(args)
    except Exception as exc:  # noqa: BLE001 — operator-friendly trace
        sys.stderr.write(f"error: {type(exc).__name__}: {exc}\n")
        return 1
    if args.human:
        sys.stdout.write(_humanize(args.cmd, payload))
    else:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    return 0


def _humanize(cmd: str, payload: dict[str, Any]) -> str:
    """Best-effort human-readable rendering of a command's payload.

    Falls back to JSON if we don't know how to render a particular
    command's output. The CLI's primary contract is JSON (for
    programmatic consumers); the human rendering is a convenience.
    """
    if cmd == "whoami":
        return (
            f"household: {payload.get('household', 'unknown')}\n"
            f"db.path: {payload.get('database', {}).get('path', 'unknown')}\n"
            f"db.size_bytes: {payload.get('database', {}).get('size_bytes', 'unknown')}\n"
            f"db.table_count: {payload.get('database', {}).get('table_count', 'unknown')}\n"
            f"pid: {payload.get('runtime', {}).get('pid', 'unknown')}\n"
        )
    if cmd == "tools":
        lines = [f"Available tools ({payload.get('count', 0)}):"]
        for t in payload.get("tools", []):
            lines.append(f"  - {t['name']}: {t.get('description', '')[:60]}")
        return "\n".join(lines) + "\n"
    if cmd == "inventory":
        items = payload.get("items", [])
        lines = [f"Inventory ({payload.get('count', 0)} items, household={payload.get('household', '?')}):"]
        for lot in items[:20]:
            if isinstance(lot, dict):
                name = lot.get("canonical_name") or lot.get("display_name") or "?"
                qty = lot.get("quantity", "?")
                unit = lot.get("unit", "")
                lines.append(f"  - {name}: {qty} {unit}")
            else:
                lines.append(f"  - {lot}")
        return "\n".join(lines) + "\n"
    return json.dumps(payload, indent=2, default=str) + "\n"


if __name__ == "__main__":
    sys.exit(main())
