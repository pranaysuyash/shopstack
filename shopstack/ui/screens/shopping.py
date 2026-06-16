from __future__ import annotations

import json
import logging
import os
import warnings
from html import escape
from typing import Any
from urllib.parse import quote

from shopstack.app_context import APP_NAME, current_user_id, db, providers, tools
from shopstack.services.dashboard import clear_dashboard_cache
from shopstack.services.i18n import load_locale_preference, t
from shopstack.services.shopping import (
    classify_shopping_items,
    enrich_items_with_swiggy,
    normalize_item_name,
    complete_shopping_list_service,
    mark_items_purchased_service,
)
from shopstack.services.shopping_substitutions import (
    get_substitutions_for_list,
    render_substitutions_html,
)
from shopstack.ui.components.cards import list_to_table
from shopstack.ui.components.decorators import aria_live_screen
from shopstack.ui.components.primitives import (
    empty_state_enhanced,
    item_row,
    stat_card,
    toast,
    toast_floating,
    home_card,
)
from shopstack.ui.renderers import render_mark_purchased, render_shopping_completion
from shopstack.traces.export import create_trace
from shopstack.services.reconciliation import reconcile_shopping_trip
from shopstack.ui.screens._utils import (
    parse_shopping_text,
    source_freshness_html,
)

logger = logging.getLogger(__name__)


def shopping_list_view():
    """LEGACY: 4-tuple return. Superseded by `shopping_list_view_with_cards`
    (6-tuple return).

    **STATUS (2026-06-13 supersession audit):** This function is
    deprecated. The canonical path is ``shopping_list_view_with_cards``
    (6-tuple return). Per ``motto_v3`` §7 the deprecation protocol is:
    (1) ``@deprecated`` docstring (this), (2) ``DeprecationWarning``
    emitted on call (next), (3) keep for one release cycle, (4) delete.
    The function is no longer in ``screens/__init__.py:__all__`` as of
    2026-06-13 (audit pass). New code must call
    ``shopping_list_view_with_cards`` instead. See
    ``Docs/HANDOFF_SUPERSESSION_AUDIT_2026-06-13.md``.
    """
    # Emit the deprecation warning. stacklevel=2 so the warning
    # points at the caller's line, not this wrapper.
    warnings.warn(
        "shopping_list_view() is deprecated and will be removed in "
        "the next minor release. Use shopping_list_view_with_cards() "
        "instead. See Docs/HANDOFF_SUPERSESSION_AUDIT_2026-06-13.md.",
        DeprecationWarning,
        stacklevel=2,
    )
    goal_html, tbl, list_id, list_goal, _cards, _share = _shopping_list_payload()
    return goal_html, tbl, list_id, list_goal


def shopping_list_create(goal: str, items_json: str) -> str:
    uid = current_user_id()
    if not items_json:
        items = []
        plan_note = empty_state_enhanced(
            "No items specified yet.",
            icon="📝",
            secondary_text="Add items from Pantry, or use the command input to plan today's shopping.",
        )
    else:
        try:
            parsed_json = json.loads(items_json)
            if isinstance(parsed_json, list):
                items = parsed_json
                plan_note = None
            elif isinstance(parsed_json, dict):
                items = [parsed_json]
                plan_note = None
            else:
                return toast("Input must be a list (or one item).", kind="error")
        except json.JSONDecodeError:
            stripped = items_json.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                return toast("Invalid JSON input.", kind="error")
            items, plan_note = _parse_shopping_items_from_text(goal, items_json)
            if not items:
                return toast(plan_note, kind="warning")
        except TypeError:
            return toast("Unable to parse input.", kind="error")

    if not items:
        items = []
    for item in items:
        if not item.get("canonical_name"):
            item["canonical_name"] = normalize_item_name(str(item.get("name", "")))
            item["canonical_name"] = item["canonical_name"] or "unknown"
    items = [
        {
            "canonical_name": normalize_item_name(item.get("canonical_name") or item.get("item", "")),
            "requested_quantity": item.get("requested_quantity") or 1.0,
            "unit": item.get("unit", "unit"),
            "priority": item.get("priority", "must_buy"),
            "reason": item.get("reason", ""),
        }
        for item in items if isinstance(item, dict)
    ]
    if items:
        must_buy, optional, skipped, use_soon = _classify_shopping_items(items)
        plan_note = _render_shopping_plan_html(must_buy, optional, skipped, use_soon)
        _record_shopping_trace(goal, items_json, items, must_buy, optional, skipped, use_soon, plan_note)
    else:
        plan_note = empty_state_enhanced("Created an empty active list. Add more items anytime.", icon="📋")
    result = tools.create_or_update_shopping_list(items=items, goal=goal, user_id=uid)
    safe_list_id = escape(str(result.get("list", {}).get("list_id", "")))
    return toast_floating(f"Created list: {safe_list_id} with {len(items)} items", kind="success") + plan_note


def _parse_shopping_items_from_text(goal: str, raw: str) -> tuple[list[dict[str, Any]], str]:
    raw = (raw or "").strip()
    parsed = parse_shopping_text(raw)
    if parsed:
        items = []
        for item in parsed:
            if not item:
                continue
            items.append({
                "canonical_name": item,
                "requested_quantity": 1.0,
                "unit": "unit",
                "priority": "must_buy",
            })
        return items, raw

    if raw:
        suggestions = tools.get_next_buy_suggestions().get("suggestions", [])
        fallback_items = []
        for s in suggestions[:5]:
            fallback_items.append({
                "canonical_name": s["canonical_name"],
                "requested_quantity": s.get("suggested_quantity", 1),
                "unit": "unit",
                "priority": s.get("priority", "optional"),
                "reason": s.get("reason", ""),
            })
        if fallback_items:
            return fallback_items, f"Suggested from home memory: {goal}"

    return [], "No clear items were detected. Share a rough list like `milk, bread, tomato`."


def _classify_shopping_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    plan = classify_shopping_items(items, tools.inventory)
    return plan.must_buy, plan.optional, plan.skipped, plan.use_soon


def _enrich_items_with_swiggy(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enrich_items_with_swiggy(items)
    return items



def _render_shopping_plan_html(
    must_buy: list[dict[str, Any]], optional: list[dict[str, Any]], skipped: list[dict[str, Any]], use_soon: list[dict[str, Any]]
) -> str:
    def _swiggy_badge(item: dict[str, Any]) -> str:
        price = item.get("swiggy_price")
        avail = item.get("swiggy_available")
        ppk = item.get("swiggy_price_per_kg")
        if price is None and avail is None:
            return ""
        if avail is False:
            return " <span style='font-size: 0.625rem;color:var(--red);font-weight:600;'>SOLD OUT</span>"
        parts = []
        if price:
            parts.append(f"&#8377;{price:.0f}")
        if ppk:
            parts.append(f"({ppk:.0f}/kg)")
        if parts:
            return f" <span style='font-size: 0.625rem;color:var(--green);font-weight:600;'>Swiggy: {' '.join(parts)}</span>"
        return ""

    def _card_with_badge(group_name: str, items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        color_map = {
            "Must buy": "var(--green)", "Optional": "var(--blue)",
            "Use Soon": "var(--amber)", "Skip": "var(--text-dim)",
        }
        color = color_map.get(group_name, "var(--text-dim)")
        rows = []
        for item in items[:8]:
            name = str(item.get("canonical_name", ""))
            qty = item.get("requested_quantity", 1.0)
            unit = item.get("unit", "unit")
            reason = item.get("reason", "")
            badge_html_str = _swiggy_badge(item)
            extra = f"{escape(str(reason))}{badge_html_str}" if reason or badge_html_str else ""
            rows.append(item_row(
                name=name.replace("_", " ").title(),
                quantity=qty,
                unit=unit,
                status="active",
                extra=extra,
            ))
        heading = f"<h4 style='color:{color};margin-bottom:4px;'>{escape(group_name)} ({len(items)})</h4>"
        return f"<div style='text-align:left;margin-bottom:8px;'>{heading}{''.join(rows)}</div>"

    cards = "".join(
        _card_with_badge(name, items)
        for name, items in [("Must buy", must_buy), ("Optional", optional), ("Use Soon", use_soon), ("Skip", skipped)]
        if items
    )
    return f"<div style='margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;'>{cards}</div>" if cards else ""



def _record_shopping_trace(
    goal: str | None,
    items_json: str,
    items: list[dict[str, Any]],
    must_buy: list[dict[str, Any]],
    optional: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    use_soon: list[dict[str, Any]],
    plan_note: str,
) -> None:
    try:
        create_trace(
            db,
            input_type="text",
            user_goal=(goal or "").strip() or "Plan shopping list",
            redacted_user_request=goal or "",
            perception={"goal": goal or "", "items_text": items_json},
            inventory_context={
                "must_buy": len(must_buy),
                "optional": len(optional),
                "skip": len(skipped),
                "use_soon": len(use_soon),
            },
            decision={"workflow": "plan_shopping", "items": [i["canonical_name"] for i in items]},
            proposed_tool_calls=[
                {
                    "tool_name": "create_or_update_shopping_list",
                    "args": {"goal": goal or "", "items": items},
                    "confirmed": True,
                }
            ],
            final_response=plan_note,
            human_confirmation="auto-summarized",
            user_id=current_user_id(),
        )
    except Exception as exc:
        logger.debug("Failed to record shopping trace: %s", exc)


def _shopping_list_share_text(items: list[dict[str, Any]]) -> str:
    """Plain-text version of the shopping list, grouped by decision.

    Format is plain text (no markdown) so it can be pasted into
    WhatsApp / SMS / email / any other messaging surface without
    formatting issues. Public callers should use
    :func:`shopping_list_share` which wraps this with HTML.
    """
    if not items:
        return (
            f"{APP_NAME} list for today\n"
            "No items in list — add items from Pantry or use the command input to plan today's shopping."
        )
    must_buy: list[str] = []
    optional: list[str] = []
    skipped: list[str] = []
    use_soon: list[str] = []
    for item in items:
        decision = item.get("smart_decision") or item.get("priority") or "must_buy"
        name = item.get("canonical_name", "")
        qty = item.get("requested_quantity")
        unit = item.get("unit", "unit") or "unit"
        reason = (item.get("reason") or "").strip()
        suffix = f" \u2014 {qty} {unit}"
        if reason:
            suffix += f" ({reason})"
        if decision == "skip":
            skipped.append(f"\u2022 {name}{suffix}")
        elif decision == "optional":
            optional.append(f"\u2022 {name}{suffix}")
        elif decision == "use_soon":
            use_soon.append(f"\u2022 {name}{suffix}")
        else:
            must_buy.append(f"\u2022 {name}{suffix}")

    sections: list[str] = [f"{APP_NAME} list for today"]
    if must_buy:
        sections.append("\nMust Buy:\n" + "\n".join(must_buy))
    if optional:
        sections.append("\nOptional:\n" + "\n".join(optional))
    if skipped:
        sections.append("\nSkip:\n" + "\n".join(skipped))
    if use_soon:
        sections.append("\nUse Soon:\n" + "\n".join(use_soon))
    return "\n".join(sections)


def _shopping_list_share_html(share_text: str, locale: str = "en") -> str:
    safe_text = escape(share_text)
    encoded = quote(share_text)
    whatsapp_url = f"https://wa.me/?text={encoded}"
    title = t("button.share_list_title", locale)
    copy_label = t("button.share_list_copy", locale)
    copy_done = t("button.share_list_copy_done", locale)
    whatsapp_label = t("button.share_list_whatsapp", locale)
    return (
        "<div style='margin-top:8px;'>"
        f"<strong>{title}</strong>"
        "<div style='display:flex;gap:8px;margin-top:6px;'>"
        "<textarea readonly rows='6' id='sl-share-text' "
        "style='flex:1;background:var(--bg-input);border:1px solid var(--border);"
        "border-radius:var(--radius-sm);padding:8px;font-size: 0.75rem;color:var(--text);"
        "resize:none;'"
        f">{safe_text}</textarea>"
        "</div>"
        f"<button onclick=\"var t=document.getElementById('sl-share-text');"
        f"t.select();navigator.clipboard.writeText(t.value);"
        f"this.textContent='{copy_done}';setTimeout(function(){{this.textContent='{copy_label}'}}.bind(this),1500);"
        f"\" class='gr-button' style='margin-top:6px;font-size: 0.75rem;'>{copy_label}</button>"
        f"<a class='gr-button' style='margin-top:6px;display:inline-block;text-decoration:none;' href='{whatsapp_url}' target='_blank'>{whatsapp_label}</a>"
        "</div>"
    )


def _shopping_list_payload() -> tuple[str, list[list[str]], str, str, str, str]:
    sl = db.get_active_shopping_list(user_id=current_user_id())
    if not sl:
        return (
            empty_state_enhanced("No active shopping list. Create one with your goal or rough text.", icon="🛒", action_label="Create List", on_click_tab="shopping"),
            [["No items"]],
            "",
            "",
            "",
            _shopping_list_share_html(_shopping_list_share_text([]), load_locale_preference()),
        )

    rows = [
        {
            "canonical_name": lot.canonical_name,
            "requested_quantity": lot.requested_quantity or 1.0,
            "unit": lot.unit or "unit",
            "priority": lot.priority,
            "reason": lot.reason or "",
        }
        for lot in (sl.items or [])
        if lot.status != "bought" and lot.status != "skipped"
    ]
    _classify_shopping_items(rows)
    must_buy = [i for i in rows if i.get("priority") == "must_buy"]
    optional = [i for i in rows if i.get("priority") == "optional"]
    skipped = [i for i in rows if i.get("priority") == "avoid_buying"]
    use_soon = [i for i in rows if i.get("smart_decision") == "use_soon"]

    cards = _render_shopping_plan_html(must_buy, optional, skipped, use_soon)
    if cards and any(item.get("swiggy_available") is not None for item in rows):
        cards += source_freshness_html("swiggy")

    table_rows = []
    for item in rows:
        swiggy_col = ""
        price = item.get("swiggy_price")
        avail = item.get("swiggy_available")
        if avail is False:
            swiggy_col = "SOLD OUT"
        elif price:
            ppk = item.get("swiggy_price_per_kg")
            swiggy_col = f"&#8377;{price:.0f}" + (f" ({ppk:.0f}/kg)" if ppk else "")
        table_rows.append({
            "item": item.get("canonical_name", ""),
            "qty": item.get("requested_quantity", 1.0),
            "unit": item.get("unit", "unit"),
            "priority": item.get("priority", "optional"),
            "swiggy": swiggy_col,
            "reason": item.get("reason", ""),
        })
    tbl = list_to_table(
        table_rows,
        ["item", "qty", "unit", "priority", "swiggy", "reason"],
    )
    goal_html = stat_card(
        style="text-align:left;margin-bottom:8px;",
        body_html=f"<strong>Goal:</strong> {escape(str(sl.goal))}",
    ) if sl.goal else ""
    share_text = _shopping_list_share_text(rows)
    share_html = _shopping_list_share_html(share_text, load_locale_preference())
    return goal_html, tbl, sl.list_id, sl.goal or "", cards, share_html


def generate_shopping_poster() -> tuple[str, str]:
    """Generate a shopping poster from the current shopping list items.

    Returns:
        (file_path_or_empty, status_html)
    """
    sl = db.get_active_shopping_list(user_id=current_user_id())
    if not sl or not sl.items:
        return "", "<div class='muted'>No active shopping list to generate a poster from.</div>"

    items = []
    for lot in sl.items:
        if lot.status in ("bought", "skipped"):
            continue

        decision_map = {
            "must_buy": "buy",
            "optional": "optional",
            "avoid_buying": "skip",
        }
        decision = decision_map.get(lot.priority, "buy")

        confidence_map = {
            "must_buy": 0.85,
            "optional": 0.70,
            "avoid_buying": 0.90,
        }
        confidence = confidence_map.get(lot.priority, 0.80)

        items.append({
            "name": lot.canonical_name,
            "decision": decision,
            "reason": lot.reason or "",
            "confidence": confidence,
        })

    if not items:
        return "", "<div class='muted'>No active items to include in the poster.</div>"

    try:
        provider = providers.image_gen
        if not provider or not getattr(provider, "available", True):
            return "", (
                "<div class='muted' style='color:var(--amber);'>"
                "Image generation provider not available. Install cairosvg or svglib to generate poster images."
                "</div>"
            )

        poster_path = provider.generate_shopping_poster(items)
        if not poster_path or not os.path.isfile(poster_path):
            return "", "<div style='color:var(--red);'>Poster generation returned an invalid file path.</div>"

        return poster_path, f"<div style='color:var(--green);font-weight:600;margin-bottom:8px;'>\u2713 Poster saved: {os.path.basename(poster_path)}</div>"
    except Exception as e:
        logger.warning("Failed to generate shopping poster: %s", e)
        return "", f"<div style='color:var(--red);'>Failed to generate poster: {e}</div>"


def _shopping_list_view_with_cards() -> tuple[str, str, list[list[str]], str, str, str]:
    goal_html, tbl, list_id, list_goal, cards, share = _shopping_list_payload()
    from shopstack.services.empty_states import render as _es_render
    empty_cards = _es_render("groceries.basket")
    card_wrap = home_card(title="Shopping List", body=(cards or empty_cards), style="text-align:left;")
    return card_wrap, goal_html, tbl, list_id, list_goal, share


def shopping_list_item_choices() -> list[tuple[str, str]]:
    sl = db.get_active_shopping_list(user_id=current_user_id())
    if not sl or not sl.items:
        return []
    items = [i for i in sl.items if i.status != "bought" and i.status != "skipped"]
    if not items:
        return []
    return [
        (
            f"{i.canonical_name} ({i.requested_quantity or 1.0} {i.unit or 'unit'})",
            i.list_item_id,
        )
        for i in items
    ]


@aria_live_screen()
def mark_items_purchased(item_ids_json: str | list[str]) -> str:
    if isinstance(item_ids_json, list):
        item_ids = item_ids_json
    else:
        item_ids = item_ids_json
    uid = current_user_id()
    result = mark_items_purchased_service(item_ids, tools.inventory, db, user_id=uid)
    clear_dashboard_cache(uid)
    return render_mark_purchased(result) + toast_floating(f"Marked {len(item_ids)} item(s) as bought", kind="success")


@aria_live_screen()
def complete_shopping_list(list_id: str) -> str:
    uid = current_user_id()
    result = complete_shopping_list_service(list_id, tools.inventory, db, user_id=uid)
    clear_dashboard_cache(uid)
    return render_shopping_completion(result) + toast_floating("Shopping list completed", kind="success")


def _build_shopping_list_and_refresh(
    goal: str, items_text: str
) -> tuple[str, str, str, list[list[str]], str, str, str]:
    create_result = shopping_list_create(goal, items_text)
    cards, goal_html, tbl, list_id, list_goal, share = _shopping_list_view_with_cards()
    return create_result, cards, goal_html, tbl, list_id, list_goal, share


def get_reconciliation_draft() -> tuple[list[list[Any]], str, str]:
    sl = db.get_active_shopping_list(user_id=current_user_id())
    if not sl or not sl.items:
        return [], "", "<div class='muted'>No active shopping list.</div>"
    
    rows = []
    for item in sl.items:
        if item.status == "bought" or item.status == "skipped":
            continue
            
        qty = item.requested_quantity or 1.0
        default_action = "bought"
        if item.priority == "avoid_buying":
            default_action = "skipped"
            
        rows.append([
            item.canonical_name,
            qty,
            item.unit or "unit",
            default_action,
            0.0,
            ""
        ])
    
    if not rows:
        return [], "", "<div class='muted'>All items are already bought or skipped.</div>"
        
    return rows, sl.list_id, ""


def confirm_reconciliation(df_data: Any, list_id: str) -> str:
    if not list_id:
        return "<div style='color:var(--red);'>No active list ID.</div>"
        
    uid = current_user_id()

    if hasattr(df_data, "values"):
        df_list = df_data.values.tolist()
    else:
        df_list = df_data

    if not df_list:
        return (
            "<div style='color:var(--red);'>"
            "No data in reconciliation table. Add a few purchases or import a Swiggy "
            "receipt to start seeing the reconciliation view."
            "</div>"
        )

    sl = db.get_active_shopping_list(user_id=uid)
    if not sl:
        return "<div style='color:var(--red);'>No active shopping list.</div>"

    planned_items: list[dict[str, Any]] = []
    for item in sl.items:
        if item.status in ("bought", "skipped"):
            continue
        planned_items.append({
            "canonical_name": item.canonical_name,
            "requested_quantity": item.requested_quantity,
            "unit": item.unit or "unit",
            "action": item.priority if item.priority in ("must_buy", "optional", "avoid_buying") else "buy",
            "smart_decision": item.priority if item.priority in ("must_buy", "optional", "avoid_buying") else "must_buy",
        })

    actual_items: list[dict[str, Any]] = []

    for row in df_list:
        try:
            if len(row) < 6:
                continue
            name, qty_str, unit, action, price_str, note = row
            name = str(name).strip()
            if not name:
                continue
                
            qty = float(qty_str) if qty_str else 1.0
            price = float(price_str) if price_str else 0.0
            action = str(action).strip().lower()
            note_val = note.strip() if note else None
            actual_items.append({
                "canonical_name": name.lower(),
                "quantity": qty,
                "unit": str(unit) or "unit",
                "action": action,
                "price_paid": price,
                "substituted_with": note_val if action == "substituted" else None,
                "notes": note_val if action not in ("substituted", "") else None,
                "source": "manual",
            })
        except Exception as e:
            logger.warning("Reconciliation row error: %s", e)

    try:
        result = reconcile_shopping_trip(
            planned_items=planned_items,
            actual_items=actual_items,
            tools=tools.inventory,
            database=db,
            user_id=uid,
        )
        db.mark_list_complete(list_id)
        return home_card(body=f"Reconciliation complete. {escape(result.message)}", style="color:var(--green);font-weight:600;")
    except Exception as e:
        logger.warning("Failed to reconcile shopping trip: %s", e)

    return "<div style='color:var(--red);'>Failed to reconcile shopping trip.</div>"


# Public handlers for Gradio composition layer
def shopping_list_view_with_cards() -> tuple[str, str, list[list[str]], str, str, str]:
    """Public handler for refreshing shopping list view with cards."""
    return _shopping_list_view_with_cards()


def shopping_list_substitutions_view() -> str:
    """Render substitution suggestions for the active shopping list.

    Loads the active list, queries the multi-source market registry for
    available snapshots, runs ``find_substitutions`` per item, and returns
    HTML for an inline substitution panel. Returns an empty string when
    there is no active list, no market data, or no sold-out items to
    surface alternatives for.
    """
    sl = db.get_active_shopping_list(user_id=current_user_id())
    if not sl or not sl.items:
        return ""

    rows = [
        {
            "canonical_name": lot.canonical_name,
            "requested_quantity": lot.requested_quantity or 1.0,
            "unit": lot.unit or "unit",
            "display_name": (lot.canonical_name or "").replace("_", " ").title(),
        }
        for lot in sl.items
        if lot.status not in ("bought", "skipped")
    ]
    if not rows:
        return ""

    try:
        from shopstack.services.market_sources import load_market_registry

        registry, _ = load_market_registry(force=False)
    except Exception as exc:
        logger.warning("Could not load market registry for substitutions: %s", exc)
        return ""

    if registry is None:
        return ""

    items = get_substitutions_for_list(rows, registry)
    return render_substitutions_html(items)


def build_shopping_list_and_refresh(
    goal: str, items_text: str
) -> tuple[str, str, str, list[list[str]], str, str, str]:
    """Public handler for building shopping list and refreshing view."""
    return _build_shopping_list_and_refresh(goal, items_text)


def shopping_list_share() -> str:
    """Render the shareable shopping list as HTML (textarea + WhatsApp link).

    The returned HTML includes:
      * A readonly ``<textarea>`` with the plain-text share content
        (so the user can copy it manually if clipboard JS fails).
      * A "Copy" button that copies the textarea's text to the
        clipboard via ``navigator.clipboard.writeText`` (with a
        "Copied!" confirmation that auto-resets).
      * An "Open WhatsApp" link that opens
        ``https://wa.me/?text=<share>`` in a new tab, pre-filled
        with the share text.

    This is the public Gradio adapter (added 2026-06-13). The
    internal ``_shopping_list_share_text`` and
    ``_shopping_list_share_html`` helpers do the real work; this
    function just composes them and is the single entry point
    for the Gradio ``gr.Button.click`` wiring.

    Returns:
        HTML string for the share panel. Empty string if the
        active household has no shopping list.
    """
    try:
        sl = db.get_active_shopping_list(user_id=current_user_id() or "")
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("shopping_list_share: get_active failed: %s", exc)
        return ""
    if not sl:
        return home_card(
            body=(
                "<div style='font-size: 0.75rem;color:var(--text-dim);'>"
                "No active shopping list. Create or activate a list first."
                "</div>"
            ),
        )
    # Build the row dicts the share_text helper expects
    rows: list[dict[str, Any]] = []
    try:
        for lot in sl.items:
            if getattr(lot, "status", "active") in ("bought", "skipped"):
                continue
            rows.append(
                {
                    "canonical_name": lot.canonical_name,
                    "requested_quantity": lot.requested_quantity or 1.0,
                    "unit": lot.unit or "unit",
                    "smart_decision": "must_buy",
                }
            )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("shopping_list_share: build rows failed: %s", exc)
        return ""
    try:
        share_text = _shopping_list_share_text(rows)
        return _shopping_list_share_html(share_text, load_locale_preference())
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("shopping_list_share: render failed: %s", exc)
        return ""
