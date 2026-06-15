from __future__ import annotations

import json
import logging
from html import escape
from typing import Any

from shopstack.app_context import db, providers, tools, current_user_id
from shopstack.services.market_lens import MarketLensResult, analyze_market_lens
from shopstack.ui.components import render_grouped_cards
from shopstack.ui.components.primitives import home_card
from shopstack.traces.export import create_trace, update_trace_confirmation
from shopstack.ui.screens._utils import WORKFLOW_STEPS, source_freshness_html
from shopstack.ui.screens.ask import ask_shopstack, render_ask_response

logger = logging.getLogger(__name__)


def market_lens_process(image_path: str | None, audio_path: str | None) -> tuple:
    result_html = "<div style='color:var(--text-dim);'>No input provided.</div>"
    service_result = analyze_market_lens(image_path, audio_path, providers, tools.inventory)
    analysis = service_result.analysis_json
    source_metadata = _render_market_lens_source_metadata(service_result)

    if image_path:
        swiggy_section = _render_swiggy_section(service_result.decisions)
        buys = [d for d in service_result.decisions if d["decision"] == "buy"]
        skips = [d for d in service_result.decisions if d["decision"] == "skip"]
        maybes = [d for d in service_result.decisions if d["decision"] in ("optional", "maybe")]
        analysis = (
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;'>"
            f"{render_grouped_cards('BUY', buys)}{render_grouped_cards('SKIP', skips)}"
            f"{render_grouped_cards('MAYBE', maybes)}"
            "</div>"
        )
        barcode_result = _render_barcode_section(service_result)
        barcode_section = barcode_result + "<br>" if barcode_result else ""
        result_html = (
            source_metadata
            + barcode_section
            + home_card(body=f"<h3>Market Lens</h3>{analysis}{swiggy_section}")
        )
        analysis = service_result.analysis_json

    if audio_path:
        transcript_text = service_result.transcript_text
        if not image_path:
            result_html = source_metadata
        result_html += f"<div style='margin-top:12px;'><strong>Heard:</strong> {escape(transcript_text)}</div>"
        if not image_path and transcript_text:
            # ``ask_shopstack`` returns a structured dict; render it to HTML
            # via the canonical renderer before assigning to ``result_html``.
            # Assigning the raw dict previously broke ``create_trace`` because
            # ``Trace.final_response`` is typed ``str`` and Pydantic rejected
            # the dict, silently dropping the trace (empty ``ml_trace_id``).
            result_html = render_ask_response(ask_shopstack(transcript_text))
            analysis = service_result.analysis_json
            service_result.decisions.append({"canonical_name": "", "decision": "text_query", "reason": transcript_text})
        else:
            result_html += "<div style='margin-top:8px;color:var(--text-dim);'>Spoken note processed for context.</div>"

    ml_trace_id = ""
    if image_path or audio_path:
        try:
            uid = current_user_id()
            trace = create_trace(
                db,
                input_type="vision" if image_path else "audio",
                user_goal="market_lens",
                redacted_user_request=analysis,
                perception={"items_detected": service_result.items_found, "audio": bool(audio_path), "image": bool(image_path)},
                inventory_context={"decision_count": len(service_result.decisions)},
                decision={"steps": list(WORKFLOW_STEPS), "items": service_result.decisions[:6]},
                proposed_tool_calls=service_result.tool_calls,
                final_response=result_html,
                human_confirmation="uncommitted",
                user_id=uid,
            )
            ml_trace_id = trace.trace_id
        except Exception as exc:
            logger.warning("market_lens: failed to create trace: %s", exc)
            ml_trace_id = ""
    return result_html, service_result.detected_items_json, analysis, ml_trace_id, service_result.barcode_json


def _render_barcode_section(result: MarketLensResult) -> str:
    if not result.barcode_info:
        return ""
    barcode_parts = []
    for code in result.barcode_info:
        barcode_parts.append(
            stat_card(
                style="margin-bottom:8px;",
                body_html=(
                    f"<div style='font-weight:600;'>{escape(code['label'])}</div>"
                    f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>Type: {escape(str(code['type']))} | Code: {escape(code['code'])}</div><div style='margin-top:6px;color:var(--text-dim);font-size: 0.6875rem;'>Barcode scanned — use the button below to add to inventory.</div>"
                ),
            )
        )
    return home_card(body="<h3>Barcode detected</h3>" + "".join(barcode_parts))


def _render_swiggy_section(decisions: list[dict[str, Any]]) -> str:
    swiggy_items = [d for d in decisions if d.get("swiggy_price") is not None or d.get("swiggy_available") is False]
    if not swiggy_items:
        return ""
    swiggy_rows = []
    for d in swiggy_items[:5]:
        name = escape(d["canonical_name"])
        if d.get("swiggy_available") is False:
            swiggy_rows.append(
                f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'><strong>{name}</strong> <span style='color:var(--red);font-size: 0.6875rem;'>Sold out on Swiggy</span>"
                f"</div>"
            )
        elif d.get("swiggy_price"):
            ppk = d.get("swiggy_price_per_kg", 0)
            ppk_str = f" ({ppk:.0f}/kg)" if ppk else ""
            swiggy_rows.append(
                f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'><strong>{name}</strong> <span style='color:var(--green);'>&#8377;{d['swiggy_price']:.0f}{ppk_str}</span>"
                f"</div>"
            )
    return stat_card(
        value="",
        label="",
        body_html=(
            "<h4>Swiggy Instamart Prices</h4>"
            + "".join(swiggy_rows)
            + source_freshness_html("swiggy")
        ),
        style="margin-top:10px;",
    )


def _render_market_lens_source_metadata(result: MarketLensResult) -> str:
    if not result.source_mode and not result.freshness_label and not result.warnings:
        return ""

    warning_html = ""
    if result.warnings:
        warning_rows = [
            f"<li style='margin:4px 0;color:var(--red);'>⚠ {escape(warning)}</li>"
            for warning in result.warnings
        ]
        warning_html = (
            "<ul style='margin:8px 0 0 14px;padding:0;line-height:1.35;'>"
            + "".join(warning_rows)
            + "</ul>"
        )

    return home_card(
        style="margin-bottom:10px;",
        body=(
            f"<h4>Market Lens context</h4><div style='margin-bottom:6px;'><strong>Source mode:</strong> {escape(result.source_mode.title())}</div>"
            f"<div style='font-size: 0.75rem;color:var(--text-dim);'>{escape(result.freshness_label)}</div>{warning_html}"
        ),
    )


def market_lens_confirm_buy(ml_analysis_json: str, ml_trace_id: str) -> str:
    if not ml_analysis_json:
        return "<div style='color:var(--text-dim);'>Scan something first.</div>"
    try:
        data = json.loads(ml_analysis_json)
        items = data.get("items", [])
    except (json.JSONDecodeError, TypeError):
        return "<div style='color:var(--red);'>Could not parse analysis data.</div>"
    buy_items = [i for i in items if i.get("decision") == "buy"]
    if not buy_items:
        return "<div style='color:var(--amber);'>No BUY items found to confirm.</div>"
    list_items = []
    for item in buy_items:
        list_items.append({
            "canonical_name": item.get("canonical_name", "").lower(),
            "requested_quantity": item.get("suggested_quantity", 1.0),
            "unit": item.get("unit", "unit"),
            "priority": "must_buy",
            "reason": item.get("reason", ""),
        })
    tools.create_or_update_shopping_list(items=list_items, user_id=current_user_id())
    if ml_trace_id:
        update_trace_confirmation(db, ml_trace_id, "confirmed-buy", user_id=current_user_id())
    names = ", ".join(i.get("canonical_name", "") for i in buy_items)
    return f"<div style='color:var(--green);'>Added {len(buy_items)} item(s) to shopping list: {escape(names)}</div>"


def market_lens_skip(ml_analysis_json: str, ml_trace_id: str) -> str:
    if not ml_analysis_json:
        return "<div style='color:var(--text-dim);'>Scan something first.</div>"
    if ml_trace_id:
        update_trace_confirmation(db, ml_trace_id, "skipped", user_id=current_user_id())
    return "<div style='color:var(--text-dim);'>Saved skip decision to workflow trace.</div>"


def market_lens_save_trace(ml_analysis_json: str, ml_trace_id: str) -> str:
    if not ml_trace_id:
        return "<div style='color:var(--text-dim);'>No scan to save. Scan something first.</div>"
    update_trace_confirmation(db, ml_trace_id, "saved", user_id=current_user_id())
    return f"<div style='color:var(--green);'>Scan results saved to activity history.</div>"


def market_lens_barcode_add(barcode_json: str) -> str:
    if not barcode_json or barcode_json == "[]":
        return "<div style='color:var(--text-dim);'>No barcode data. Scan an image with a barcode first.</div>"
    try:
        codes = json.loads(barcode_json)
    except (json.JSONDecodeError, TypeError):
        return "<div style='color:var(--red);'>Could not parse barcode data.</div>"
    if not codes:
        return "<div style='color:var(--text-dim);'>No barcode data to add.</div>"
    added = []
    for code in codes:
        label = code.get("label", "").removeprefix("Product code ")
        label = label or f"barcode-item-{code.get('code', 'unknown')[:8]}"
        result = tools.add_inventory_item(
            canonical_name=label.lower().strip(),
            display_name=label.strip(),
            quantity=1.0,
            unit="unit",
            storage_location_id="pantry",
            user_id=current_user_id(),
        )
        lot_id = result.get("lot_id", "")
        added.append(f"{label} (lot {lot_id})")
    names = ", ".join(added)
    return f"<div style='color:var(--green);'>Added {len(added)} barcode item(s): {escape(names)}</div>"
