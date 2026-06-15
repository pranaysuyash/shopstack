from __future__ import annotations

import gradio as gr

from shopstack.basket.service import optimize_baskets
from shopstack.app_context import db, tools, current_user_id
from shopstack.services.dashboard import build_dashboard_state
from shopstack.ui.components.primitives import home_card

def get_basket_ui_html() -> str:
    state = build_dashboard_state(db, tools.inventory, user_id=current_user_id())
    decision_set = state.decision_set

    from shopstack.services.market_sources import load_market_registry
    registry, _ = load_market_registry(db=db, force=False)

    candidates = optimize_baskets(decision_set, registry)
    
    if not candidates:
        from shopstack.services.empty_states import render as _es_render
        return _es_render("groceries.basket")

    html_parts = []
    for idx, c in enumerate(candidates):
        is_best = idx == 0
        badge = "<span class='badge badge-green' style='margin-left:8px;'>Best Value</span>" if is_best else ""
        border = "border:2px solid var(--green);" if is_best else "border:1px solid var(--border);"
        
        items_html = ""
        for i in c.items:
            if getattr(i, "price_status", "known") == "unavailable":
                price_str = "<span style='color:var(--text-dim);font-size: 0.75rem;'>Price pending</span>"
                status_note = "<span style='font-size: 0.6875rem;color:var(--amber);'>(point-in-time)</span>"
            else:
                price_str = f"&#8377;{i.price_inr:.0f}"
                status_note = ""
            stale_warning = f" <span style='color:var(--amber);font-size: 0.6875rem;'>(Stale)</span>" if i.freshness == "stale" else ""
            ad_warning = f" <span style='color:var(--text-dim);font-size: 0.6875rem;'>(Ad)</span>" if i.is_ad else ""
            row_note = ""
            if getattr(i, "notes", None):
                row_note = f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>{i.notes}</div>"
            items_html += (
                f"<div style='display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px dashed var(--border);'><div>"
                f"<span>{i.display_name}{stale_warning}{ad_warning}{status_note}</span>{row_note}"
                f"</div><span style='font-weight:600;'>{price_str}</span>"
                f"</div>"
            )
            
        missing_html = ""
        if c.missing_items:
            missing_html = f"<div style='margin-top:8px;font-size: 0.6875rem;color:var(--red);'>Missing: {', '.join(c.missing_items)}</div>"

        card = home_card(
            style=f"margin-bottom:16px;{border}",
            body=(
                f"  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>"
                f"    <h3 style='margin:0;display:flex;align-items:center;'>{c.source_name.replace('_', ' ').title()} Basket {badge}</h3>    <div style='font-size: 1.25rem;font-weight:bold;'>{'--' if c.source_name == 'decision_only' else f'&#8377;{c.total_cost:.0f}'}</div>"
                f"  </div>  <div style='margin-bottom:12px;'>{items_html}</div>"
                f"  {missing_html}  <div style='display:flex;gap:12px;font-size: 0.75rem;color:var(--text-dim);border-top:1px solid var(--border);padding-top:8px;margin-top:8px;'>"
                f"    <span>Score: {c.overall_score:.1f}</span>    <span>Freshness: {c.freshness_score:.0f}</span>"
                f"    <span>Waste Risk: {c.waste_risk_score:.0f}</span>  </div>"
            ),
        )
        html_parts.append(card)
        
    return f"<div style='max-width:800px;margin:0 auto;'>{''.join(html_parts)}</div>"


def build_basket_screen():
    with gr.Column():
        gr.Markdown("## Multi-Source Basket Optimizer")
        gr.Markdown("Ranks baskets by usefulness, cost, freshness, waste risk, and user preference across available snapshots.")
        
        refresh_btn = gr.Button("Optimize Baskets", variant="primary")
        basket_html = gr.HTML(home_card(
            style="text-align:center;padding:40px;color:var(--text-dim);",
            body="Click 'Optimize Baskets' to generate multi-source candidates.",
        ))
        
        refresh_btn.click(
            fn=get_basket_ui_html,
            inputs=[],
            outputs=[basket_html]
        )
