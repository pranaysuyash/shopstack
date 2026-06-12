from __future__ import annotations

import gradio as gr
import json
import logging
from html import escape
from typing import Any
import sys

from shopstack.config import settings

# Use TraceService from app_context for all trace CRUD operations.
# The service wraps shopstack.traces.export with a clean class interface
# following the service boundary pattern.
from shopstack.app_context import get_trace_service

logger = logging.getLogger(__name__)


def _current_db():
    # Prefer the process-level `app` module singleton first.
    # Test suites occasionally reload `shopstack.app_context`, and we must not
    # drift to a different `db` object when existing tests keep using the same app
    # instance.
    app_module = sys.modules.get("app")
    if app_module is not None and hasattr(app_module, "db"):
        return app_module.db

    # Compatibility fallback for direct package imports that only touch
    # `shopstack.app_context`.
    try:
        from shopstack import app as _app
    except Exception:
        _app = None
    if _app is not None and hasattr(_app, "db"):
        return _app.db

    # Fallback to app_context for call-sites that import traces without the app
    # module loaded (for example, lower-level unit tests).
    from shopstack import app_context
    return app_context.db


def _safe_trace_id(trace_id: str) -> str:
    return trace_id.strip().split()[0]


def _find_trace_by_id(trace_id: str):
    db = _current_db()
    from shopstack.app_context import current_user_id
    user_id = current_user_id()
    if not trace_id:
        traces = db.get_traces(limit=1, user_id=user_id)
        return traces[0] if traces else None
    target = _safe_trace_id(trace_id)
    return db.get_trace_by_id(target, user_id=user_id)


def _filter_traces(search: str = "", input_type_filter: str = "") -> list:
    db = _current_db()
    from shopstack.app_context import current_user_id
    user_id = current_user_id()
    traces = db.get_traces(limit=max(1, min(settings.trace_max_rows, 500)), user_id=user_id)
    needle = (search or "").strip().lower()
    selected = (input_type_filter or "").strip().lower()
    if selected:
        traces = [t for t in traces if (t.input_type or "").lower() == selected]
    if needle:
        traces = [
            t for t in traces
            if needle in (t.user_goal or "").lower()
            or needle in (t.trace_id or "").lower()
            or needle in (t.input_type or "").lower()
        ]
    return traces


def _trace_timeline_html(trace) -> str:
    if not trace:
        return "<div style='color:var(--text-dim);'>No activity selected yet.</div>"
    
    # Extract structured decision data if available
    d_dict = trace.decision or {}
    if not isinstance(d_dict, dict):
        d_dict = {}
    
    final_action = d_dict.get("action", "No decision recorded")
    confidence = d_dict.get("confidence", 0.0)
    rule_path = d_dict.get("source_trace", "Unknown rule path")
    
    evidence_list = d_dict.get("evidence", [])
    inventory_ev = [e.get("value") for e in evidence_list if e.get("source") == "inventory"]
    market_ev = [e.get("value") for e in evidence_list if e.get("source") == "market"]
    price_ev = [e.get("value") for e in evidence_list if e.get("source") == "price"]
    preference_ev = [e.get("value") for e in evidence_list if e.get("source") == "preference"]
    
    warnings_list = d_dict.get("warnings", [])
    warnings_str = ", ".join([w.get("message", "") for w in warnings_list]) if warnings_list else "None"

    steps = [
        ("Input Facts", trace.redacted_user_request or str(trace.perception or {})),
        ("Inventory Evidence", ", ".join(inventory_ev) if inventory_ev else "None"),
        ("Market Evidence", ", ".join(market_ev) if market_ev else "None"),
        ("Price Evidence", ", ".join(price_ev) if price_ev else "None"),
        ("Preference Evidence", ", ".join(preference_ev) if preference_ev else "None"),
        ("Rule Path", rule_path),
        ("Final Action", final_action.upper()),
        ("Confidence", f"{confidence:.0%}"),
        ("Warnings", warnings_str),
        ("Actions Proposed", f"{len(trace.proposed_tool_calls or [])} actions"),
        ("Recorded ID", trace.trace_id[:12] if trace.trace_id else "No"),
    ]
    
    rows_html = "".join(
        f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);'>"
        f"<strong style='min-width:140px;color:var(--text-dim);'>{label}</strong>"
        f"<span style='text-align:right;'>{escape(str(value))}</span></div>"
        for label, value in steps
    )
    return (
        "<div class='home-card' style='text-align:left;'>"
        "<h3>Decision Trace Details</h3>"
        f"{rows_html}"
        "</div>"
    )


def _format_trace_selector_label(trace) -> str:
    goal = (trace.user_goal or "").strip() or "activity"
    return f"{goal[:40]} \xb7 {trace.input_type} \xb7 {trace.timestamp.strftime('%m-%d %H:%M') if trace.timestamp else 'no time'}"


def agent_trace_choices(search: str = "", input_type_filter: str = "") -> tuple[list[tuple[str, str]], str]:
    traces = _filter_traces(search, input_type_filter)
    if not traces:
        return [("No activity yet", "")], ""
    choices = [(f"{_format_trace_selector_label(t)} | {t.trace_id[:12]}", t.trace_id) for t in traces]
    default = traces[0].trace_id
    return choices, default


def _trace_bundle(trace_id: str) -> tuple[str, str]:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        no_trace = "<div style='color:var(--text-dim);'>No activity selected yet.</div>"
        return no_trace, no_trace
    timeline_html = _trace_timeline_html(trace)
    service = get_trace_service()
    raw_json = json.dumps(service.trace_payload(trace), indent=2, default=str)
    return timeline_html, f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{raw_json}</pre>"


def agent_trace_bootstrap(search: str = "", input_type_filter: str = "") -> tuple:
    traces = _filter_traces(search, input_type_filter)
    if not traces:
        no_data = "<div style='color:var(--text-dim);'>No activity recorded yet.</div>"
        return gr.update(choices=[("No activity yet", "")], value=""), "", no_data, no_data
    first = traces[0]
    timeline, raw = _trace_bundle(first.trace_id)
    choices = [(f"{_format_trace_selector_label(t)} | {t.trace_id[:12]}", t.trace_id) for t in traces]
    return gr.update(choices=choices, value=first.trace_id), first.trace_id, timeline, raw


def agent_trace_view(search: str = "", input_type_filter: str = "") -> tuple:
    traces = _filter_traces(search, input_type_filter)
    if not traces:
        return [["No activity yet"]], ""
    tbl = _traces_to_table(traces)
    return tbl, traces[0].trace_id if traces else ""


def _traces_to_table(traces) -> list[list[str]]:
    headers = ["activity_id", "type", "time", "goal", "actions"]
    table = [headers]
    for t in traces:
        table.append([
            t.trace_id[:12],
            t.input_type,
            t.timestamp.strftime("%Y-%m-%d %H:%M") if t.timestamp else "",
            (t.user_goal or "")[:40],
            str(len(t.proposed_tool_calls or [])),
        ])
    return table


def agent_trace_detail(trace_id: str) -> str:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        return "<div style='color:var(--text-dim);'>Activity not found.</div>"
    timeline = _trace_timeline_html(trace)
    service = get_trace_service()
    raw = json.dumps(service.trace_payload(trace), indent=2, default=str)
    return timeline + (
        "<div class='home-card' style='text-align:left;margin-top:12px;'>"
        "<h3>Raw activity record</h3>"
        f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{raw}</pre>"
        "</div>"
    )


def agent_trace_export_file(trace_id: str) -> str:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        return ""
    service = get_trace_service()
    from shopstack.app_context import current_user_id
    return service.export_trace_to_jsonl(trace.trace_id, redact=True, user_id=current_user_id())



def record_workflow_trace(
    input_type: str,
    user_goal: str,
    redacted_user_request: str,
    perception: dict[str, Any],
    inventory_context: dict[str, Any],
    decision: dict[str, Any],
    proposed_tool_calls: list[dict[str, Any]],
    final_response: str,
    human_confirmation: str | None = None,
    user_id: str = "",
) -> str:
    try:
        service = get_trace_service()
        trace = service.create_trace(
            input_type=input_type,
            user_goal=user_goal,
            redacted_user_request=redacted_user_request,
            perception=perception,
            inventory_context=inventory_context,
            decision=decision,
            proposed_tool_calls=proposed_tool_calls,
            human_confirmation=human_confirmation,
            final_response=final_response,
            user_id=user_id,
        )
        return trace.trace_id
    except Exception:
        return ""


# Public handler for Gradio composition layer
def trace_bundle(trace_id: str) -> tuple[str, str]:
    """Public handler for getting trace timeline and raw JSON."""
    return _trace_bundle(trace_id)


def agent_trace_refresh() -> tuple:
    """Refresh trace selector, timeline, raw, state, and table.

    Returns 5 values matching Gradio's [trace_selector, trace_bootstrap_state,
    trace_timeline, trace_raw, trace_table] outputs.
    """
    selector, trace_id, timeline_html, raw_html = agent_trace_bootstrap()
    tbl, _ = agent_trace_view()
    return selector, trace_id, timeline_html, raw_html, tbl


def agent_trace_search_filter(search: str, type_filter: str) -> tuple:
    """Filter traces by search and type, return updated selector, timeline, raw.

    Returns 3 values matching Gradio's [trace_selector, trace_timeline, trace_raw] outputs.
    """
    boot = agent_trace_bootstrap(search, type_filter)
    return boot[0], boot[2], boot[3]
