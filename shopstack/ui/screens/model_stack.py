from __future__ import annotations

from html import escape
from typing import Any

from shopstack.app_context import model_registry, providers
from shopstack.model_registry import (
    MAX_ACTIVE_MODEL_PARAMS_B,
    get_registry,
    total_candidate_params,
    total_loaded_params,
    validate_active_model_budget,
)
from shopstack.ui import badge_html, card as ui_card, render_metric
from shopstack.ui.screens._utils import WORKFLOW_STEPS, workflow_header, rows_to_html


def _active_model_rows() -> list[dict[str, Any]]:
    active = [m for m in get_registry() if m.status == "active"]
    if active:
        return [
            {
                "Provider Group": model.provider_group,
                "Model": model.model_id,
                "Runtime": model.runtime,
                "Params (B)": f"{model.params_b:.2f}",
                "License": model.license_note,
                "Status": model.status,
            }
            for model in active
        ]
    return [
        {
            "Provider Group": "runtime",
            "Model": "Mock providers",
            "Runtime": "mock",
            "Params (B)": "0.00",
            "License": "N/A",
            "Status": "active",
        }
    ]


def _candidate_model_rows() -> list[dict[str, Any]]:
    return [
        {
            "Provider Group": model.provider_group,
            "Model": model.model_id,
            "Runtime": model.runtime,
            "Params (B)": f"{model.params_b:.2f}",
            "License": model.license_note,
            "Status": model.status,
        }
        for model in get_registry()
        if model.status == "candidate"
    ]


def _provider_is_mock(provider_info: dict[str, Any]) -> bool:
    provider_type = str(provider_info.get("type", "")).lower()
    return provider_type.startswith("mock") or provider_type == ""


def provider_status_badge() -> str:
    provider_rows = providers.list_providers()
    runtime_rows = [
        row
        for row in provider_rows
        if row.get("name") in {"stt", "tts", "vision", "object_detection", "ocr", "planner", "embeddings"}
    ]
    real_rows = [row for row in runtime_rows if not _provider_is_mock(row)]
    loaded_real_rows = [row for row in real_rows if bool(row.get("available"))]

    if not real_rows:
        status = "Mock"
        cls = "badge-amber"
    elif loaded_real_rows:
        status = "AI"
        cls = "badge-green"
    else:
        status = "Configured"
        cls = "badge-blue"

    caps = sorted({c for p in provider_rows for c in str(p.get("capabilities", "")).split(", ") if c})
    backend_summary = ", ".join(
        f"{row.get('name')}={row.get('type')}{' loaded' if row.get('available') else ' unavailable'}"
        for row in runtime_rows
    )
    title = f"Capabilities: {', '.join(caps) if caps else 'mock'} | {backend_summary or 'mock runtime'}"
    return f'<span class="badge {cls}" title="{escape(title, quote=True)}">{escape(status)}</span>'


def model_budget_view() -> str:
    provider_badge = provider_status_badge()
    try:
        validate_active_model_budget()
        budget_ok = True
        budget_message = "Active runtime stack is within the 32B cap."
    except ValueError as exc:
        budget_ok = False
        budget_message = str(exc)

    active_rows = _active_model_rows()
    candidate_rows = _candidate_model_rows()
    if not candidate_rows:
        candidate_html = "<div style='color:var(--text-dim);'>No candidate entries yet.</div>"
    else:
        candidate_html = rows_to_html(
            candidate_rows,
            ["Provider Group", "Model", "Runtime", "Params (B)", "License", "Status"],
        )

    status_badge = badge_html("Under budget", "green") if budget_ok else badge_html("Over budget", "red")
    return (
        f"{workflow_header(WORKFLOW_STEPS)}"
        + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:12px 0;'>"
        f"{render_metric('Active / Loaded', f'{total_loaded_params():.2f} B')}"
        f"{render_metric('Candidate Pool', f'{total_candidate_params():.2f} B')}"
        f"{render_metric('Max Budget', f'{MAX_ACTIVE_MODEL_PARAMS_B:.2f} B')}"
        "</div>"
        + ui_card(
            "Selected Runtime Stack",
            f"<div style='margin-bottom:8px;display:flex;gap:8px;align-items:center;'>{status_badge}"
            f"<span style='font-size:12px;color:var(--text-dim);'>{budget_message}</span></div>"
            + rows_to_html(
                active_rows,
                ["Provider Group", "Model", "Runtime", "Params (B)", "License", "Status"],
            ),
        )
        + ui_card("Candidate Models", candidate_html)
        + f"<div style='margin-top:12px;font-size:11px;color:var(--text-dim);display:flex;gap:8px;align-items:center;'>{provider_badge} <span>Runtime status displayed above.</span></div>"
    )
