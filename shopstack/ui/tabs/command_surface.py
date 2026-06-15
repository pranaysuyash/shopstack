"""Command surface sub-builder — the unified input for the Today tab.

**Why this exists (motto_v3 §0.14 product reality):**

The legacy Today tab had two near-duplicate inputs:

* "Quick add" — a small textbox + a primary "Add to my shopping list"
  button that called :func:`shopstack.services.restock_card.add_restock_to_list`.
* "Ask ShopStack" — a textbox + button pair that routed natural-language
  questions through the AI planner.

For the user, these were the same job ("tell ShopStack something").
For us, they were two surfaces to maintain, two event wirings, and
two ways to forget which one does what.

The command surface merges both. One input, one button, one Enter
handler. The :mod:`shopstack.services.command_surface` service parses
the typed text into a :class:`CommandIntent` (deterministic, no
LLM roundtrip for the common cases) and dispatches to the matching
inventory or shopping-list action. If nothing matches, the input
falls through to the Ask ShopStack planner so the user always gets
an answer.

The chip row below the input shows the 10 most common Indian
household staples — clicking a chip prefills the input with
``"add <staple>"`` and focuses it.

**Supersession (motto_v3 §7):**

The Quick-add row in :mod:`shopstack.ui.tabs.today` and the Ask
panel in :mod:`shopstack.ui.tabs.ask_panel` are *not* deleted. They
are deprecated (kept for back-compat) and the new command surface
is wired as the primary input. The chip-row, JS shim, and
"register_handler" pattern are the canonical surface for new code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.services.command_surface import (
    COMMAND_SURFACE_SCRIPT_HTML,
    CommandResult,
    parse_intent,
    render_command_surface_html,
)
from shopstack.services.intelligence_cards import INTELLIGENCE_CARD_SCRIPT_HTML
from shopstack.services.dashboard import clear_dashboard_cache
from shopstack.services.restock_action import add_prediction_to_list
from shopstack.ui.components.primitives import toast as _toast
from shopstack.ui.tabs.context import TabContext

logger = logging.getLogger(__name__)


# ── Result toast HTML used to give immediate feedback ───────────────


def _toast_for_result(result: CommandResult) -> str:
    """Wrap a :class:`CommandResult` in the inline feedback div."""
    return result.to_toast()


# ── Dispatch handlers (registered with command_surface at build) ───


def _add_to_list_handler(canonical_name: str) -> CommandResult:
    """Handler for ``add_to_list`` — adds the item to the active list."""
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
        result = add_prediction_to_list(db, prediction, user_id=current_user_id() or "")
        clear_dashboard_cache(current_user_id() or None)
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


def _log_purchase_handler(canonical_name: str) -> CommandResult:
    """Handler for ``log_purchase`` — adds a fresh lot to inventory.

    Treats the purchase as a typical purchase of 1.0 unit. The user
    can refine qty/unit in the At Home tab; the command surface
    optimises for low friction over completeness.
    """
    if not canonical_name:
        return CommandResult(
            success=False,
            action="log_purchase",
            message="Item name is required.",
        )
    try:
        from shopstack.app_context import tools as _tools

        _tools.inventory.add_item(
            canonical_name=canonical_name,
            display_name=canonical_name.replace("_", " ").title(),
            quantity=1.0,
            unit="unit",
            user_id=current_user_id() or "",
        )
        clear_dashboard_cache(current_user_id() or None)
        return CommandResult(
            success=True,
            action="log_purchase",
            canonical_name=canonical_name,
            message=(
                f"Logged purchase of {canonical_name.replace('_', ' ')}."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("log_purchase failed: %s", exc, exc_info=True)
        return CommandResult(
            success=False,
            action="log_purchase",
            canonical_name=canonical_name,
            message=(
                f"Could not log that purchase. "
                "Please try again."
            ),
        )


def _add_stock_handler(canonical_name: str) -> CommandResult:
    """Handler for ``add_stock`` — same as log_purchase for now.

    Both actions add to inventory. The distinction is preserved in
    the *intent* so future rendering can highlight one as a
    purchase-log and the other as a pantry-restock.
    """
    base = _log_purchase_handler(canonical_name)
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


def _mark_consumed_handler(canonical_name: str) -> CommandResult:
    """Handler for ``mark_consumed`` — consumes 1 unit of the matching
    lot, prefer the most-recent active lot with quantity > 0."""
    if not canonical_name:
        return CommandResult(
            success=False,
            action="mark_consumed",
            message="Item name is required.",
        )
    try:
        from shopstack.app_context import tools as _tools

        # Find the most recent active lot for this canonical name.
        uid = current_user_id() or ""
        inventory = db.get_inventory(user_id=uid)
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
                message=(
                    f"No active stock of {canonical_name.replace('_', ' ')} to consume."
                ),
            )
        # Most recent first (by purchase_date if available)
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
            message=(
                f"Marked 1 {lot.unit} of {canonical_name.replace('_', ' ')} as used."
            ),
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


def _ask_handler(canonical_name: str, *, intent: Any = None) -> CommandResult:
    """Handler for ``ask`` — falls through to the Ask ShopStack planner.

    Returns a CommandResult with the rendered answer so the inline
    feedback div surfaces the assistant's reply. (We render a brief
    summary; the full Ask panel below shows the detailed JSON output.)
    """
    try:
        from shopstack.ui.screens import ask_shopstack

        answer = ask_shopstack(intent.raw if intent is not None else canonical_name)
        # Try to extract a short summary line from the structured
        # answer. The full structured answer is shown in the Ask
        # panel below; here we want a 1-2 line toast.
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
            message=(
                "Couldn't answer that just now. "
                "Please try again."
            ),
        )


def _summarise_answer(answer: Any) -> str:
    """Pull a 1-2 line user-facing summary from the Ask ShopStack result."""
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


# ── Sub-builder handles ────────────────────────────────────────────


@dataclass
class CommandSurfaceHandles:
    """Components the parent Today tab references after building.

    Exposed (a) so the legacy Quick-add row in :mod:`shopstack.ui.tabs.today`
    can still be queried for back-compat and (b) so the household-switch
    wiring in ``app.py`` can refresh the surface on household change.
    """

    prompt_html: gr.HTML
    input_textbox: gr.Textbox
    submit_btn: gr.Button
    feedback_html: gr.HTML
    js_shim: gr.HTML


# ── Builder ────────────────────────────────────────────────────────


def build_command_surface(
    blocks: gr.Blocks,
    app: gr.Blocks,
    ctx: TabContext,
) -> CommandSurfaceHandles:
    """Add the unified command surface to the parent ``gr.Blocks`` context.

    Registers handlers for the four inventory actions and the Ask
    fall-through. The chip-row is rendered as part of ``prompt_html``
    (HTML produced by :func:`render_command_surface_html`) so the
    :class:`gr.HTML` for the prompt doubles as the chip container.
    """
    from shopstack.services import command_surface as _cs

    # Register handlers (idempotent — registering twice is a no-op
    # because we check identity).
    _cs.register_handler("add_to_list", _add_to_list_handler)
    _cs.register_handler("log_purchase", _log_purchase_handler)
    _cs.register_handler("add_stock", _add_stock_handler)
    _cs.register_handler("mark_consumed", _mark_consumed_handler)
    _cs.register_handler("ask", _ask_handler)

    # Description / chip row (HTML)
    prompt_html = gr.HTML(
        render_command_surface_html(),
        elem_classes="command-surface-prompt",
    )

    # JS shim (chip → input fill helper + intelligence card dispatcher)
    js_shim = gr.HTML(
        _cs.COMMAND_SURFACE_SCRIPT_HTML + INTELLIGENCE_CARD_SCRIPT_HTML,
        elem_id="command-surface-shim",
        visible=True,
    )

    # Input + button in a single row (the unified CTA)
    with gr.Row(elem_classes="command-surface-row"):
        input_textbox = gr.Textbox(
            label="",
            placeholder=(
                "Add milk · I bought bread · We finished eggs · Do we have rice?"
            ),
            scale=4,
            elem_id="command-surface-input",
            show_label=False,
        )
        submit_btn = gr.Button("Submit", variant="primary", scale=1)

    feedback_html = gr.HTML("", elem_id="command-surface-feedback")

    def _on_submit(text: str) -> str:
        intent = parse_intent(text or "")
        result = _cs.dispatch(intent)
        return result.to_toast()

    submit_btn.click(_on_submit, inputs=input_textbox, outputs=feedback_html)
    input_textbox.submit(_on_submit, inputs=input_textbox, outputs=feedback_html)

    return CommandSurfaceHandles(
        prompt_html=prompt_html,
        input_textbox=input_textbox,
        submit_btn=submit_btn,
        feedback_html=feedback_html,
        js_shim=js_shim,
    )


__all__ = [
    "CommandSurfaceHandles",
    "build_command_surface",
]
