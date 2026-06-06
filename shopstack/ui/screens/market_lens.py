from __future__ import annotations

import json
import logging
from html import escape
from typing import Any

from shopstack.app_context import db, providers, tools
from shopstack.scanner import decode_barcode, infer_product_from_code
from shopstack.ui.components import render_grouped_cards
from shopstack.traces.export import create_trace, update_trace_confirmation
from shopstack.ui.screens._utils import WORKFLOW_STEPS, normalize_item_name
from shopstack.ui.screens.ask import ask_shopstack

logger = logging.getLogger(__name__)


def market_lens_process(image_path: str | None, audio_path: str | None) -> tuple:
    result_html = "<div style='color:var(--text-dim);'>No input provided.</div>"
    items_found = []
    analysis = ""
    trace_decisions: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    final_text = ""
    barcode_info: list[dict[str, Any]] = []

    barcode_result = ""
    if image_path:
        codes = decode_barcode(image_path)
        if codes:
            barcode_parts = []
            for code in codes:
                info = infer_product_from_code(code["data"])
                barcode_info.append({
                    "label": info["label"],
                    "code": code["data"],
                    "type": code["type"],
                })
                barcode_parts.append(
                    f"<div class='stat-card' style='margin-bottom:8px;'>"
                    f"<div style='font-weight:600;'>{escape(info['label'])}</div>"
                    f"<div style='font-size:11px;color:var(--text-dim);'>Type: {escape(str(code['type']))} | Code: {escape(code['data'])}</div>"
                    f"<div style='margin-top:6px;color:var(--text-dim);font-size:11px;'>Barcode scanned — use the button below to add to inventory.</div>"
                    f"</div>"
                )
            barcode_result = "<div class='home-card'><h3>Barcode detected</h3>" + "".join(barcode_parts) + "</div>"

    if image_path:
        detections = providers.object_detection.detect(image_path)
        ocr_result = providers.ocr.extract(image_path)
        if isinstance(ocr_result, dict):
            raw_product = ocr_result.get("product_name", "")
        else:
            raw_product = ""
        decisions: list[dict[str, Any]] = []
        for d in detections[:8]:
            item_name = normalize_item_name(str(d.get("label", "")))
            comparison = tools.compare_visible_item_to_inventory(item_name, d.get("quantity", 1.0), "unit")
            decisions.append(
                {
                    "canonical_name": item_name.title(),
                    "decision": comparison.get("decision", "maybe"),
                    "reason": comparison.get("reason", ""),
                    "confidence": float(d.get("confidence", 0.0)),
                    "unit": "unit",
                    "quantity": d.get("quantity", 1.0),
                    "suggested_quantity": max(0.0, d.get("quantity", 1.0)),
                    "source": raw_product,
                }
            )
            items_found.append(item_name.title())
        trace_decisions.extend(decisions)

        buys = [d for d in decisions if d["decision"] == "buy"]
        skips = [d for d in decisions if d["decision"] == "skip"]
        maybes = [d for d in decisions if d["decision"] in ("optional", "maybe")]
        analysis = (
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;'>"
            f"{render_grouped_cards('BUY', buys)}"
            f"{render_grouped_cards('SKIP', skips)}"
            f"{render_grouped_cards('MAYBE', maybes)}"
            "</div>"
        )
        barcode_section = barcode_result + "<br>" if barcode_result else ""
        result_html = (
            barcode_section
            + "<div class='home-card'>"
            f"<h3>Market Lens</h3>{analysis}"
            "</div>"
        )
        analysis = json.dumps({"items": decisions}, indent=2)
        tool_calls.append(
            {
                "tool_name": "compare_visible_item_to_inventory",
                "args": {"items": [d.get("canonical_name", "") for d in decisions]},
            }
        )

    if audio_path:
        transcript = providers.stt.transcribe(audio_path)
        if isinstance(transcript, dict):
            transcript_text = transcript.get("text", "")
        else:
            transcript_text = str(transcript)
        result_html += f"<div style='margin-top:12px;'><strong>Heard:</strong> {escape(transcript_text)}</div>"
        if not image_path and transcript_text:
            result_html = ask_shopstack(transcript_text)
            analysis = json.dumps({"audio_query": transcript_text}, indent=2)
            tool_calls.append(
                {
                    "tool_name": "ask_shopstack",
                    "args": {"question": transcript_text},
                }
            )
            trace_decisions.append({"canonical_name": "", "decision": "text_query", "reason": transcript_text})
        else:
            result_html += f"<div style='margin-top:8px;color:var(--text-dim);'>Spoken note processed for context.</div>"
            tool_calls.append(
                {
                    "tool_name": "stt.transcribe",
                    "args": {"audio_path": audio_path or ""},
                }
            )

    ml_trace_id = ""
    if image_path or audio_path:
        final_text = result_html
        try:
            trace = create_trace(
                db,
                input_type="vision" if image_path else "audio",
                user_goal="market_lens",
                redacted_user_request=analysis,
                perception={"items_detected": items_found, "audio": bool(audio_path), "image": bool(image_path)},
                inventory_context={"decision_count": len(trace_decisions)},
                decision={"steps": list(WORKFLOW_STEPS), "items": trace_decisions[:6]},
                proposed_tool_calls=tool_calls,
                final_response=final_text,
                human_confirmation="uncommitted",
            )
            ml_trace_id = trace.trace_id
        except Exception:
            ml_trace_id = ""
    barcode_json_str = json.dumps(barcode_info) if barcode_info else "[]"
    detected_items_json = json.dumps({"items": items_found}, ensure_ascii=False)
    return result_html, detected_items_json, analysis, ml_trace_id, barcode_json_str


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
    tools.create_or_update_shopping_list(items=list_items)
    if ml_trace_id:
        update_trace_confirmation(db, ml_trace_id, "confirmed-buy")
    names = ", ".join(i.get("canonical_name", "") for i in buy_items)
    return f"<div style='color:var(--green);'>Added {len(buy_items)} item(s) to shopping list: {escape(names)}</div>"


def market_lens_skip(ml_analysis_json: str, ml_trace_id: str) -> str:
    if not ml_analysis_json:
        return "<div style='color:var(--text-dim);'>Scan something first.</div>"
    if ml_trace_id:
        update_trace_confirmation(db, ml_trace_id, "skipped")
    return "<div style='color:var(--text-dim);'>Saved skip decision to workflow trace.</div>"


def market_lens_save_trace(ml_analysis_json: str, ml_trace_id: str) -> str:
    if not ml_trace_id:
        return "<div style='color:var(--text-dim);'>No trace to save. Scan something first.</div>"
    update_trace_confirmation(db, ml_trace_id, "saved")
    return f"<div style='color:var(--green);'>Trace {ml_trace_id[:12]} saved to workflow history.</div>"


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
        )
        lot_id = result.get("lot_id", "")
        added.append(f"{label} (lot {lot_id})")
    names = ", ".join(added)
    return f"<div style='color:var(--green);'>Added {len(added)} barcode item(s): {escape(names)}</div>"
