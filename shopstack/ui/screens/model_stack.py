from __future__ import annotations

from html import escape
from typing import Any

from shopstack.app_context import db, providers, current_user_id
from shopstack.config import settings
from shopstack.model_registry import (
    MAX_ACTIVE_MODEL_PARAMS_B,
    get_registry,
    total_candidate_params,
    validate_active_model_budget,
)
from shopstack.providers.runtime import collect_runtime_diagnostics, diagnostics_to_rows
from shopstack.ui.components.cards import badge_html, card as ui_card, render_metric
from shopstack.ui.screens._utils import rows_to_html


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
    backend = str(provider_info.get("backend", "")).lower()
    if backend and backend not in {"", "mock", "mocked"}:
        return False
    provider_type = str(provider_info.get("type", "")).lower()
    return provider_type.startswith("mock") or provider_type == ""


def _provider_is_blocked(provider_info: dict[str, Any]) -> bool:
    return str(provider_info.get("status", "")).lower() == "blocked_off_grid"


def provider_status_badge() -> str:
    provider_rows = providers.list_providers()
    runtime_rows = [
        row
        for row in provider_rows
        if row.get("name") in {"stt", "tts", "vision", "object_detection", "ocr", "planner", "embeddings"}
    ]
    real_rows = [row for row in runtime_rows if not _provider_is_mock(row)]
    loaded_real_rows = [row for row in real_rows if bool(row.get("available"))]
    blocked_rows = [row for row in runtime_rows if _provider_is_blocked(row)]

    if not real_rows:
        status = "Mock"
        cls = "badge-amber"
    elif blocked_rows and not loaded_real_rows:
        status = "Off-grid"
        cls = "badge-blue"
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


def _runtime_mode(runtime_rows: list[dict[str, Any]]) -> str:
    loaded = [row for row in runtime_rows if row.get("available") and not _provider_is_mock(row)]
    cloud = [row for row in loaded if str(row.get("backend", "")).lower() in {"openai", "huggingface", "whisper"}]
    blocked = [row for row in runtime_rows if _provider_is_blocked(row)]
    if loaded and cloud:
        return "mixed"
    if loaded:
        return "cloud" if cloud else "local"
    if blocked:
        return "off-grid / mock"
    return "mock"


def _pick_runtime_sample(runtime_rows: list[dict[str, Any]], key: str) -> str:
    preferred_order = ("planner", "vision", "ocr", "embeddings", "stt", "tts")
    for preferred in preferred_order:
        for row in runtime_rows:
            if row.get("name") == preferred:
                value = row.get(key, "")
                if value not in {"", None}:
                    return str(value)
    for row in runtime_rows:
        value = row.get(key, "")
        if value not in {"", None}:
            return str(value)
    return ""


def runtime_proof_view() -> str:
    diag = collect_runtime_diagnostics(providers)
    runtime_rows = [
        row
        for row in providers.list_providers()
        if row.get("name") in {"stt", "tts", "vision", "object_detection", "grounding", "segmentation", "ocr", "planner", "tool_call_parser", "embeddings", "image_edit", "image_gen"}
    ]
    planner_backend = next((row.get("backend", "") for row in runtime_rows if row.get("name") == "planner"), "")
    vision_backend = next((row.get("backend", "") for row in runtime_rows if row.get("name") == "vision"), "")
    ocr_backend = next((row.get("backend", "") for row in runtime_rows if row.get("name") == "ocr"), "")
    embeddings_backend = next((row.get("backend", "") for row in runtime_rows if row.get("name") == "embeddings"), "")
    cloud_apis = any(
        str(row.get("backend", "")).lower() in {"openai", "huggingface", "whisper"} and bool(row.get("available"))
        for row in runtime_rows
    )
    latest_trace = ""
    try:
        traces = db.get_traces(limit=1, user_id=current_user_id())
        latest_trace = traces[0].trace_id if traces else ""
    except Exception as exc:
        logger.debug("Failed to load latest trace: %s", exc)
        latest_trace = ""

    badge_parts = [provider_status_badge()]
    if settings.model_stack != "default":
        badge_parts.append(badge_html(settings.model_stack.replace("_", " ").title(), "blue"))
    badges_html = " ".join(badge_parts)

    cards_html = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:12px;'>"
        f"{render_metric('Planner', planner_backend or 'mock')}"
        f"{render_metric('Vision', vision_backend or 'mock')}"
        f"{render_metric('OCR', ocr_backend or 'mock')}"
        f"{render_metric('Embeddings', embeddings_backend or 'mock')}"
        f"{render_metric('Mode', _runtime_mode(runtime_rows))}"
        f"{render_metric('Cloud APIs', 'yes' if cloud_apis else 'no')}"
        f"{render_metric('Active Params', f'{diag.active_total_params_b:.2f} B')}"
        f"{render_metric('Budget', 'within' if diag.within_budget else 'over')}"
        f"{render_metric('Last Latency', _pick_runtime_sample(runtime_rows, 'latency_ms') or 'n/a')}"
        f"{render_metric('Last Tokens', _pick_runtime_sample(runtime_rows, 'tokens') or 'n/a')}"
        f"{render_metric('Last Trace', latest_trace[:12] or 'n/a')}"
        "</div>"
    )

    status_line = (
        "<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:8px;'>"
        "Off-grid policy blocks cloud backends; local models remain eligible. "
        "Cloud use is shown honestly, not hidden behind mock routing."
        "</div>"
    )
    if any(row.get("status") == "blocked_off_grid" for row in runtime_rows):
        status_line += (
            "<div style='font-size: 0.75rem;color:var(--amber);margin-top:6px;'>"
            "Some requested backends are blocked by off-grid policy and are shown as unavailable."
            "</div>"
        )

    table_html = (
        rows_to_html(
            runtime_rows,
            ["name", "backend", "status", "available", "blocked", "capabilities"],
        )
        if runtime_rows
        else "<div style='color:var(--text-dim);margin-top:12px;'>No runtime rows available.</div>"
    )

    return ui_card(
        "Runtime Proof",
        f"<div style='display:flex;gap:8px;flex-wrap:wrap;align-items:center;'>{badges_html}</div>"
        f"{status_line}"
        f"{cards_html}"
        f"<div style='margin-top:12px;'>{table_html}</div>",
    )


def model_budget_view() -> str:
    provider_badge = provider_status_badge()
    
    diag = collect_runtime_diagnostics(providers)
    diag_rows = diagnostics_to_rows(diag)
    
    active_rows = _active_model_rows()
    candidate_rows = _candidate_model_rows()
    if not candidate_rows:
        candidate_html = "<div style='color:var(--text-dim);'>No candidate entries yet.</div>"
    else:
        candidate_html = rows_to_html(
            candidate_rows,
            ["Provider Group", "Model", "Runtime", "Params (B)", "License", "Status"],
        )

    status_badge = badge_html("Under budget", "green") if diag.within_budget else badge_html("Over budget", "red")
    
    if not diag_rows:
        diag_html = "<div style='color:var(--text-dim);'>No runtime diagnostics available.</div>"
    else:
        diag_html = rows_to_html(
            diag_rows,
            ["provider", "backend", "model", "loaded", "status", "blocked", "params_b", "latency_ms", "tokens"]
        )

    budget_pct = min(100.0, max(0.0, (diag.active_total_params_b / diag.budget_limit_b) * 100)) if diag.budget_limit_b > 0 else 0
    budget_color = "var(--green)" if diag.within_budget else "var(--red)"
    progress_bar = (
        f"<div style='width:100%;height:8px;background:var(--border);border-radius:4px;margin-top:8px;overflow:hidden;'>"
        f"<div style='width:{budget_pct:.1f}%;height:100%;background:{budget_color};'></div>"
        f"</div>"
        f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-top:4px;text-align:right;'>{budget_pct:.1f}% of {diag.budget_limit_b:.1f} B budget used</div>"
    )

    return (
        "<div style='margin-bottom:10px;color:var(--text-dim);font-size: 0.8125rem;'>"
        "System status, runtime budget, and candidate model overview."
        "</div>"
        + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:12px 0;'>"
        f"{render_metric('Active / Loaded', f'{diag.active_total_params_b:.2f} B')}"
        f"{render_metric('Candidate Pool', f'{total_candidate_params():.2f} B')}"
        f"{render_metric('Max Budget', f'{diag.budget_limit_b:.2f} B')}"
        "</div>"
        + ui_card(
            "Runtime Diagnostics",
            f"<div style='margin-bottom:8px;display:flex;gap:8px;align-items:center;'>{status_badge}"
            f"<span style='font-size: 0.75rem;color:var(--text-dim);'>Live memory stack tracker</span></div>"
            + progress_bar
            + diag_html,
        )
        + ui_card(
            "Selected Runtime Stack",
            rows_to_html(
                active_rows,
                ["Provider Group", "Model", "Runtime", "Params (B)", "License", "Status"],
            ),
        )
        + ui_card("Candidate Models", candidate_html)
        + f"<div style='margin-top:12px;font-size: 0.6875rem;color:var(--text-dim);display:flex;gap:8px;align-items:center;'>{provider_badge} <span>Runtime status displayed above.</span></div>"
    )
