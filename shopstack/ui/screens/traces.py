from __future__ import annotations

import json
import logging
import os
import tempfile
from html import escape
from typing import Any

from shopstack.app_context import db
from shopstack.traces.export import export_trace_by_id, trace_payload_for_export, create_trace

logger = logging.getLogger(__name__)


def _safe_trace_id(trace_id: str) -> str:
    return trace_id.strip().split()[0]


def _find_trace_by_id(trace_id: str):
    if not trace_id:
        traces = db.get_traces(limit=1)
        return traces[0] if traces else None
    target = _safe_trace_id(trace_id)
    for trace in db.get_traces(limit=100):
        if trace.trace_id == target:
            return trace
    return None


def _filter_traces(search: str = "", input_type_filter: str = "") -> list:
    traces = db.get_traces(limit=200)
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
        return "<div style='color:var(--text-dim);'>No workflow trace selected yet.</div>"
    steps = [
        ("Input", trace.input_type or "unknown"),
        ("Perception", trace.redacted_user_request or str(trace.perception or {})),
        (
            "Inventory Context",
            (str(trace.inventory_context) if trace.inventory_context else "Using live household state"),
        ),
        ("Decision", str(trace.decision) if trace.decision else "Decision not stored"),
        ("Proposed Actions", f"{len(trace.proposed_tool_calls or [])} tool calls suggested"),
        (
            "Human Confirmation",
            trace.human_confirmation or "No confirmation recorded yet",
        ),
        ("Saved Trace", "Yes" if trace.trace_id else "No"),
    ]
    rows_html = "".join(
        f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);'>"
        f"<strong>{label}</strong><span>{escape(str(value))}</span></div>"
        for label, value in steps
    )
    return (
        "<div class='home-card' style='text-align:left;'>"
        "<h3>Workflow evidence timeline</h3>"
        f"{rows_html}"
        "</div>"
    )


def _format_trace_selector_label(trace) -> str:
    goal = (trace.user_goal or "").strip() or "workflow run"
    return f"{goal[:40]} \xb7 {trace.input_type} \xb7 {trace.timestamp.strftime('%m-%d %H:%M') if trace.timestamp else 'no time'}"


def agent_trace_choices(search: str = "", input_type_filter: str = "") -> tuple[list[tuple[str, str]], str]:
    traces = _filter_traces(search, input_type_filter)
    if not traces:
        return [("No traces yet", "")], ""
    choices = [(f"{_format_trace_selector_label(t)} | {t.trace_id[:12]}", t.trace_id) for t in traces]
    default = traces[0].trace_id
    return choices, default


def _trace_bundle(trace_id: str) -> tuple[str, str]:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        no_trace = "<div style='color:var(--text-dim);'>No workflow trace selected yet.</div>"
        return no_trace, no_trace
    timeline_html = _trace_timeline_html(trace)
    raw_json = json.dumps(trace_payload_for_export(trace), indent=2, default=str)
    return timeline_html, f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{raw_json}</pre>"


def agent_trace_bootstrap(search: str = "", input_type_filter: str = "") -> tuple:
    traces = _filter_traces(search, input_type_filter)
    if not traces:
        no_data = "<div style='color:var(--text-dim);'>No workflow traces recorded yet.</div>"
        return {"choices": [("No traces yet", "")], "value": ""}, "", no_data, no_data
    first = traces[0]
    timeline, raw = _trace_bundle(first.trace_id)
    choices = [(f"{_format_trace_selector_label(t)} | {t.trace_id[:12]}", t.trace_id) for t in traces]
    return {"choices": choices, "value": first.trace_id}, first.trace_id, timeline, raw


def agent_trace_view(search: str = "", input_type_filter: str = "") -> tuple:
    traces = _filter_traces(search, input_type_filter)
    if not traces:
        return [["No traces yet"]], ""
    tbl = _traces_to_table(traces)
    return tbl, traces[0].trace_id if traces else ""


def _traces_to_table(traces) -> list[list[str]]:
    headers = ["trace_id", "type", "time", "goal", "tool_calls"]
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
        return "<div style='color:var(--text-dim);'>Trace not found.</div>"
    timeline = _trace_timeline_html(trace)
    raw = json.dumps(trace_payload_for_export(trace), indent=2, default=str)
    return timeline + (
        "<div class='home-card' style='text-align:left;margin-top:12px;'>"
        "<h3>Redacted trace payload</h3>"
        f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{raw}</pre>"
        "</div>"
    )


def agent_trace_export_file(trace_id: str) -> str:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        return ""
    fd, out_path = tempfile.mkstemp(suffix=".jsonl")
    try:
        wrote = export_trace_by_id(db, trace.trace_id, out_path, redact=True)
    finally:
        os.close(fd)
    if not wrote:
        return ""
    return out_path


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
) -> str:
    try:
        trace = create_trace(
            db,
            input_type=input_type,
            user_goal=user_goal,
            redacted_user_request=redacted_user_request,
            perception=perception,
            inventory_context=inventory_context,
            decision=decision,
            proposed_tool_calls=proposed_tool_calls,
            human_confirmation=human_confirmation,
            final_response=final_response,
        )
        return trace.trace_id
    except Exception:
        return ""
