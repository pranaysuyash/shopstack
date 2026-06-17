"""Shared command execution helpers for the unified command surface.

This module holds the real mutation logic behind the "ask or add"
input so both the Gradio command surface and the new v1 API can call
the same handlers.
"""
from __future__ import annotations

import logging
from typing import Any

from shopstack import app_context
from shopstack.services.command_surface import CommandResult
from shopstack.services.dashboard import clear_dashboard_cache
from shopstack.services.restock_action import add_prediction_to_list
from shopstack.traces.export import create_trace

logger = logging.getLogger(__name__)


def _resolve_user_id(user_id: str | None = None) -> str:
    return (user_id or app_context.current_user_id() or "").strip()


def add_to_list(
    canonical_name: str,
    *,
    intent: Any = None,
    user_id: str | None = None,
) -> CommandResult:
    """Add an item to the active shopping list."""
    if not canonical_name:
        return CommandResult(
            success=False,
            action="add_to_list",
            message="Item name is required.",
        )
    try:
        prediction = {
            "canonical_name": canonical_name,
            "typical_qty": 1.0,
            "typical_unit": "unit",
            "urgency": "due_soon",
            "reason": "Quick add from command surface",
        }
        uid = _resolve_user_id(user_id)
        result = add_prediction_to_list(app_context.db, prediction, user_id=uid)
        clear_dashboard_cache(uid or None)
        if not result.get("added"):
            return CommandResult(
                success=False,
                action="add_to_list",
                canonical_name=canonical_name,
                message=result.get("reason", "Could not add to list."),
            )
        return CommandResult(
            success=True,
            action="add_to_list",
            canonical_name=canonical_name,
            message=f"Added {canonical_name.replace('_', ' ')} to your shopping list.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("add_to_list failed: %s", exc, exc_info=True)
        return CommandResult(
            success=False,
            action="add_to_list",
            canonical_name=canonical_name,
            message=(
                f"Could not add {canonical_name.replace('_', ' ')} to your list. "
                "Please try again."
            ),
        )


def log_purchase(
    canonical_name: str,
    *,
    intent: Any = None,
    user_id: str | None = None,
) -> CommandResult:
    """Log a newly purchased item into inventory."""
    if not canonical_name:
        return CommandResult(
            success=False,
            action="log_purchase",
            message="Item name is required.",
        )
    try:
        _tools = app_context.tools
        _tools.inventory.add_item(
            canonical_name=canonical_name,
            display_name=canonical_name.replace("_", " ").title(),
            quantity=1.0,
            unit="unit",
            user_id=_resolve_user_id(user_id),
        )
        clear_dashboard_cache(_resolve_user_id(user_id) or None)
        return CommandResult(
            success=True,
            action="log_purchase",
            canonical_name=canonical_name,
            message=f"Logged purchase of {canonical_name.replace('_', ' ')}.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("log_purchase failed: %s", exc, exc_info=True)
        return CommandResult(
            success=False,
            action="log_purchase",
            canonical_name=canonical_name,
            message="Could not log that purchase. Please try again.",
        )


def add_stock(
    canonical_name: str,
    *,
    intent: Any = None,
    user_id: str | None = None,
) -> CommandResult:
    """Record that an item is already in stock."""
    base = log_purchase(canonical_name, intent=intent, user_id=user_id)
    return CommandResult(
        success=base.success,
        action="add_stock",
        canonical_name=base.canonical_name,
        message=(
            f"Added {base.canonical_name.replace('_', ' ')} to your pantry."
            if base.success
            else base.message
        ),
    )


def mark_consumed(
    canonical_name: str,
    *,
    intent: Any = None,
    user_id: str | None = None,
) -> CommandResult:
    """Consume one unit from the most recent active matching lot."""
    if not canonical_name:
        return CommandResult(
            success=False,
            action="mark_consumed",
            message="Item name is required.",
        )
    try:
        _tools = app_context.tools
        uid = _resolve_user_id(user_id)
        inventory = app_context.db.get_inventory(user_id=uid)
        candidates = [
            lot for lot in inventory
            if lot.canonical_name.lower() == canonical_name.lower()
            and getattr(lot, "status", "active") == "active"
            and (lot.quantity or 0) > 0
        ]
        if not candidates:
            return CommandResult(
                success=False,
                action="mark_consumed",
                canonical_name=canonical_name,
                message=f"No active stock of {canonical_name.replace('_', ' ')} to consume.",
            )
        candidates.sort(
            key=lambda lot: getattr(lot, "purchase_date", None) or getattr(lot, "added_at", None) or "",
            reverse=True,
        )
        lot = candidates[0]
        result = _tools.inventory.consume_item(
            lot_id=lot.lot_id,
            quantity=min(1.0, lot.quantity),
            user_id=uid,
        )
        clear_dashboard_cache(uid or None)
        if not result:
            return CommandResult(
                success=False,
                action="mark_consumed",
                canonical_name=canonical_name,
                message=(
                    f"Could not mark {canonical_name.replace('_', ' ')} as used. "
                    "Please try again."
                ),
            )
        return CommandResult(
            success=True,
            action="mark_consumed",
            canonical_name=canonical_name,
            message=f"Marked 1 {lot.unit} of {canonical_name.replace('_', ' ')} as used.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("mark_consumed failed: %s", exc, exc_info=True)
        return CommandResult(
            success=False,
            action="mark_consumed",
            canonical_name=canonical_name,
            message=(
                f"Could not mark {canonical_name.replace('_', ' ')} as used. "
                "Please try again."
            ),
        )


def ask(
    canonical_name: str,
    *,
    intent: Any = None,
    user_id: str | None = None,
) -> CommandResult:
    """Fall through to the Ask ShopStack planner."""
    try:
        from shopstack.ui.screens import ask_shopstack

        answer = ask_shopstack(intent.raw if intent is not None else canonical_name)
        summary = _summarise_answer(answer)
        return CommandResult(
            success=True,
            action="ask",
            canonical_name=canonical_name,
            message=summary,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ask handler failed: %s", exc, exc_info=True)
        return CommandResult(
            success=False,
            action="ask",
            canonical_name=canonical_name,
            message="Couldn't answer that just now. Please try again.",
        )


def register_default_handlers() -> None:
    """Register the canonical command handlers with the dispatcher."""
    from shopstack.services import command_surface as _cs

    _cs.register_handler("add_to_list", add_to_list)
    _cs.register_handler("log_purchase", log_purchase)
    _cs.register_handler("add_stock", add_stock)
    _cs.register_handler("mark_consumed", mark_consumed)
    _cs.register_handler("ask", ask)


def record_command_trace(
    *,
    text: str,
    intent: Any,
    result: CommandResult,
    user_id: str | None = None,
) -> None:
    """Persist a command execution trace for recent-history screens.

    This is best-effort observability. A trace write failure should never
    break the user-visible command response.
    """
    try:
        uid = _resolve_user_id(user_id)
        create_trace(
            app_context.db,
            input_type="command",
            user_goal=f"command:{intent.action}",
            redacted_user_request=text,
            perception={
                "canonical_name": intent.canonical_name,
                "action": intent.action,
                "household_id": uid,
            },
            decision={
                "action": intent.action,
                "canonical_name": intent.canonical_name,
                "success": result.success,
                "message": result.message,
            },
            proposed_tool_calls=[
                {
                    "tool_name": intent.action,
                    "args": {"canonical_name": intent.canonical_name, "text": text},
                    "success": result.success,
                    "error": None if result.success else result.message,
                    "requires_confirmation": intent.action in {"add_to_list", "log_purchase", "add_stock", "mark_consumed"},
                    "confirmed": result.success,
                }
            ],
            final_response=result.message,
            user_id=uid,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_command_trace failed: %s", exc)


def _summarise_answer(answer: Any) -> str:
    try:
        if isinstance(answer, dict):
            text = answer.get("text") or answer.get("summary") or answer.get("answer")
            if text:
                return str(text)[:160]
            tool_calls = answer.get("tool_calls") or []
            if tool_calls:
                return f"Ran {len(tool_calls)} tool call{'s' if len(tool_calls) != 1 else ''}."
        if isinstance(answer, str):
            return answer[:160]
    except Exception:  # noqa: BLE001
        pass
    return "Answered."


__all__ = [
    "add_stock",
    "add_to_list",
    "ask",
    "log_purchase",
    "mark_consumed",
    "register_default_handlers",
    "record_command_trace",
]
