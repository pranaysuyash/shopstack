from __future__ import annotations

import json
import logging
from html import escape
from typing import Any

from shopstack.app_context import db, providers, tools, current_user_id
from shopstack.schemas.shelf import ProposedInventoryAction, ShelfIntelligenceResult
from shopstack.services.shelf_intelligence import analyze_shelf_scene
from shopstack.traces.export import create_trace, update_trace_confirmation
from shopstack.ui.screens._utils import WORKFLOW_STEPS

logger = logging.getLogger(__name__)


def shelf_scan_process(
    image_path: str | None,
    audio_path: str | None,
    scene_type: str = "auto",
) -> tuple[str, str, str, str]:
    if not image_path and not audio_path:
        return (
            "<div style='color:var(--text-dim);'>No image or audio input provided.</div>",
            "",
            "",
            "",
        )

    result = analyze_shelf_scene(image_path, audio_path, scene_type, providers, tools.inventory, user_id=current_user_id())
    html = _render_shelf_scan(result)
    scan_state = result.model_dump_json()
    trace_id = ""

    try:
        trace = create_trace(
            db,
            input_type="multimodal" if image_path and audio_path else ("vision" if image_path else "audio"),
            user_goal="shelf_scan",
            redacted_user_request=json.dumps(
                {
                    "scene_type": result.scene_type.value,
                    "speech": result.speech_intent.translated_text if result.speech_intent else "",
                    "items": [item.canonical_name for item in result.aggregates],
                },
                ensure_ascii=False,
            ),
            perception={
                "scene_type": result.scene_type.value,
                "perception_mode": result.perception_mode,
                "instances": len(result.instances),
                "aggregates": len(result.aggregates),
                "speech": bool(result.speech_intent and result.speech_intent.original_text),
                "annotated_image": bool(result.annotated_image_path),
            },
            inventory_context={
                "matches": [
                    {
                        "canonical_name": match.canonical_name,
                        "home_quantity": match.total_quantity_at_home,
                        "matched_lots": match.matched_lot_ids,
                    }
                    for match in result.inventory_matches
                ]
            },
            decision={
                "scene_type": result.scene_type.value,
                "actions": [action.model_dump() for action in result.proposed_actions],
                "summary": result.confidence_summary.model_dump(),
            },
            proposed_tool_calls=[
                {
                    "tool_name": action.action,
                    "args": action.field_updates or {
                        "canonical_name": action.canonical_name,
                        "quantity": action.quantity,
                        "unit": action.unit,
                        "target_location_id": action.target_location_id,
                    },
                }
                for action in result.proposed_actions
            ],
            final_response=html,
            human_confirmation="uncommitted",
            user_id=current_user_id(),
        )
        trace_id = trace.trace_id
    except Exception:
        logger.debug("Failed to record shelf scan trace", exc_info=True)

    return html, scan_state, trace_id, result.annotated_image_path or ""


def shelf_scan_confirm(scan_json: str, trace_id: str) -> str:
    result = _load_scan_result(scan_json)
    if result is None:
        return "<div style='color:var(--red);'>Scan something first.</div>"
    applied: list[str] = []
    for action in result.proposed_actions:
        outcome = _apply_action(action)
        if outcome:
            applied.append(outcome)
    if trace_id:
        update_trace_confirmation(db, trace_id, "confirmed-home-scan", user_id=current_user_id())
    if not applied:
        return "<div style='color:var(--text-dim);'>Nothing needed confirmation.</div>"
    return (
        "<div style='color:var(--green);'>Applied "
        f"{len(applied)} update(s): {escape(', '.join(applied))}</div>"
    )


def shelf_scan_skip(scan_json: str, trace_id: str) -> str:
    result = _load_scan_result(scan_json)
    if result is None:
        return "<div style='color:var(--text-dim);'>Scan something first.</div>"
    if trace_id:
        update_trace_confirmation(db, trace_id, "skipped-home-scan", user_id=current_user_id())
    return "<div style='color:var(--text-dim);'>Saved this shelf scan without applying updates.</div>"


def shelf_scan_save_trace(scan_json: str, trace_id: str) -> str:
    if not trace_id:
        return "<div style='color:var(--text-dim);'>No trace to save. Scan something first.</div>"
    update_trace_confirmation(db, trace_id, "saved-home-scan", user_id=current_user_id())
    return f"<div style='color:var(--green);'>Shelf scan trace {trace_id[:12]} saved.</div>"


def _load_scan_result(scan_json: str) -> ShelfIntelligenceResult | None:
    if not scan_json:
        return None
    try:
        return ShelfIntelligenceResult.model_validate_json(scan_json)
    except Exception:
        try:
            payload = json.loads(scan_json)
        except Exception:
            return None
        try:
            return ShelfIntelligenceResult.model_validate(payload)
        except Exception:
            return None


def _apply_action(action: ProposedInventoryAction) -> str:
    if action.action == "add_new_lot":
        result = tools.add_inventory_item(
            canonical_name=action.canonical_name,
            display_name=action.display_name,
            quantity=action.quantity,
            unit=action.unit,
            storage_location_id=action.target_location_id or "kitchen",
            category=action.field_updates.get("category", ""),
            user_id=current_user_id(),
        )
        lot_id = result.get("lot_id", "")
        return f"added {action.display_name} ({lot_id[:8]})"

    if action.action == "update_quantity" and action.lot_id:
        result = tools.update_inventory_item(
            action.lot_id,
            {
                "quantity": action.quantity,
                "unit": action.unit,
            },
        )
        lot = result.get("lot", {}) if isinstance(result, dict) else {}
        return f"updated {action.display_name} ({str(lot.get('lot_id', action.lot_id))[:8]})"

    if action.action == "mark_use_soon" and action.lot_id:
        result = tools.update_inventory_item(
            action.lot_id,
            {
                "status": "low",
            },
        )
        lot = result.get("lot", {}) if isinstance(result, dict) else {}
        return f"marked {action.display_name} use soon ({str(lot.get('lot_id', action.lot_id))[:8]})"

    if action.action == "move_location" and action.lot_id:
        result = tools.move_inventory_item(
            action.lot_id,
            action.target_location_id or "kitchen",
        )
        movement = result.get("movement", {}) if isinstance(result, dict) else {}
        return f"moved {action.display_name} ({str(movement.get('lot_id', action.lot_id))[:8]})"

    if action.action == "confirm":
        return ""

    return ""


def _render_shelf_scan(result: ShelfIntelligenceResult) -> str:
    summary = result.confidence_summary
    speech_html = ""
    if result.speech_intent and result.speech_intent.original_text:
        speech_html = (
            "<div class='home-card' style='margin-top:10px;'>"
            "<h4>Voice note</h4>"
            f"<div style='margin-top:4px;font-size:13px;'><strong>Heard:</strong> {escape(result.speech_intent.original_text)}</div>"
            f"<div style='margin-top:4px;font-size:13px;color:var(--text-dim);'><strong>Translated:</strong> {escape(result.speech_intent.translated_text or result.speech_intent.original_text)}</div>"
            f"<div style='margin-top:4px;font-size:12px;color:var(--text-dim);'>Action: {escape(result.speech_intent.action)} · "
            f"Scene hint: {escape(result.speech_intent.target_scene.value)}</div>"
            "</div>"
        )

    warning_html = ""
    if result.warnings:
        warning_html = (
            "<div class='home-card' style='margin-top:10px;border-left:4px solid var(--amber);'>"
            "<h4>Notes</h4>"
            + "".join(
                f"<div style='font-size:12px;margin-top:4px;color:var(--amber);'>&#9888; {escape(w)}</div>"
                for w in result.warnings
            )
            + "</div>"
        )

    aggregate_cards = "".join(_render_aggregate_card(item) for item in result.aggregates) or _empty_block("No items grouped yet.")
    action_cards = "".join(_render_action_card(item) for item in result.proposed_actions) or _empty_block("No actions proposed.")
    review_cards = "".join(_render_review_card(item) for item in result.corrections_needed[:6]) or _empty_block("Nothing needs review.")
    instance_cards = "".join(_render_instance_card(item) for item in result.instances[:8]) or _empty_block("No visible instances.")

    return (
        "<div class='home-card'>"
        f"<h3>Home Scan · {escape(result.scene_label)}</h3>"
        f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:6px;'>"
        f"{_badge(result.perception_mode, 'var(--blue)')}"
        f"{_badge(f'{summary.items_seen} seen', 'var(--text-dim)')}"
        f"{_badge(f'{summary.items_grouped} grouped', 'var(--text-dim)')}"
        f"{_badge(f'{summary.needs_review_count} review', 'var(--amber)')}"
        f"{_badge(f'{summary.overall_confidence:.0%} overall', 'var(--green)')}"
        "</div>"
        f"<div style='margin-top:8px;color:var(--text-dim);font-size:12px;'>"
        f"Scene: {escape(result.scene_type.value)} · Image confidence {summary.image_confidence:.0%} · Speech confidence {summary.speech_confidence:.0%}</div>"
        f"{warning_html}"
        f"{speech_html}"
        "<div class='home-card' style='margin-top:10px;'><h4>Detected items</h4>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin-top:8px;'>{instance_cards}</div></div>"
        "<div class='home-card' style='margin-top:10px;'><h4>Grouped view</h4>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin-top:8px;'>{aggregate_cards}</div></div>"
        "<div class='home-card' style='margin-top:10px;'><h4>Proposed updates</h4>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin-top:8px;'>{action_cards}</div></div>"
        "<div class='home-card' style='margin-top:10px;'><h4>Review prompts</h4>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin-top:8px;'>{review_cards}</div></div>"
        "</div>"
    )


def _badge(text: str, color: str) -> str:
    return (
        f"<span style='display:inline-block;padding:3px 8px;border-radius:999px;"
        f"background:{color}20;color:{color};font-size:11px;font-weight:600;'>"
        f"{escape(text)}</span>"
    )


def _empty_block(text: str) -> str:
    return (
        "<div style='padding:10px;border:1px dashed var(--border);border-radius:12px;"
        "color:var(--text-dim);font-size:12px;'>"
        f"{escape(text)}</div>"
    )


def _render_instance_card(instance: Any) -> str:
    freshness = ""
    if getattr(instance, "freshness_visual_score", None) is not None:
        freshness = f" · freshness {float(instance.freshness_visual_score):.0%}"
    expiry = ""
    if getattr(instance, "expiry_date", None):
        expiry = f" · expiry {instance.expiry_date.isoformat()}"
    return (
        "<div class='stat-card' style='text-align:left;'>"
        f"<div style='font-weight:600;'>{escape(instance.display_name)}</div>"
        f"<div style='font-size:12px;color:var(--text-dim);margin-top:4px;'>"
        f"{escape(instance.recognition_source)} · {instance.quantity_estimate.value:g} {escape(instance.quantity_estimate.unit)}"
        f"{freshness}{expiry}</div>"
        f"<div style='margin-top:6px;font-size:11px;color:var(--text-dim);'>"
        f"{escape(instance.zone_guess or 'unknown zone')}</div>"
        "</div>"
    )


def _render_aggregate_card(aggregate: Any) -> str:
    return (
        "<div class='stat-card' style='text-align:left;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<strong>{escape(aggregate.display_name)}</strong>"
        f"<span class='badge badge-blue'>{escape(aggregate.recommendation)}</span></div>"
        f"<div style='font-size:12px;color:var(--text-dim);margin-top:4px;'>"
        f"{aggregate.count} instance(s) · {aggregate.estimated_quantity:g} {escape(aggregate.unit)}"
        f" · home {aggregate.matched_home_quantity:g}</div>"
        f"<div style='font-size:11px;color:var(--text-dim);margin-top:4px;'>"
        f"delta {aggregate.delta_from_inventory:+g} · confidence {aggregate.confidence:.0%}</div>"
        + (
            f"<div style='font-size:11px;color:var(--green);margin-top:6px;'>"
            f"Why: {escape('; '.join(aggregate.reasons[:2]))}</div>"
            if aggregate.reasons else ""
        )
        + (
            f"<div style='font-size:11px;color:var(--amber);margin-top:4px;'>"
            f"Warnings: {escape('; '.join(aggregate.warnings[:2]))}</div>"
            if aggregate.warnings else ""
        )
        "</div>"
    )


def _render_action_card(action: ProposedInventoryAction) -> str:
    return (
        "<div class='stat-card' style='text-align:left;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<strong>{escape(action.display_name)}</strong>"
        f"<span class='badge badge-blue'>{escape(action.action)}</span></div>"
        f"<div style='font-size:12px;color:var(--text-dim);margin-top:4px;'>"
        f"{action.quantity:g} {escape(action.unit)} · confidence {action.confidence:.0%}</div>"
        f"<div style='font-size:11px;color:var(--text-dim);margin-top:4px;'>"
        f"Location: {escape(action.target_location_id or 'n/a')} · Lot: {escape(action.lot_id or 'new')}</div>"
        f"<div style='font-size:11px;color:var(--text-dim);margin-top:4px;'>"
        f"{escape(action.reason)}</div>"
        "</div>"
    )


def _render_review_card(text: str) -> str:
    return (
        "<div class='stat-card' style='text-align:left;border-left:3px solid var(--amber);'>"
        f"<div style='font-size:12px;color:var(--text-dim);'>{escape(text)}</div>"
        "</div>"
    )

