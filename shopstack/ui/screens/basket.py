from __future__ import annotations

import gradio as gr
from typing import Any

from shopstack.basket.service import optimize_baskets
from shopstack.schemas.models import DecisionSet
from shopstack.app_context import db, tools
from shopstack.services.dashboard import build_dashboard_state

def get_basket_ui_html() -> str:
    state = build_dashboard_state(db, tools.inventory)
    decision_set = state.decision_set
    
    # We need a source registry for multiple sources. Since we don't have direct access
    # to all snapshots here easily, we will simulate if none exist, or we can use provider_registry if we added it.
    from shopstack.market import swiggy, adapter_zepto, adapter_dmart
    
    candidates = optimize_baskets(decision_set, None)  # Mocked or use actual source registry
    
    if not candidates:
        return "<div class='home-card' style='text-align:center;padding:40px;color:var(--text-dim);'>No items to buy today.</div>"

    html_parts = []
    for idx, c in enumerate(candidates):
        is_best = idx == 0
        badge = "<span class='badge badge-green' style='margin-left:8px;'>Best Value</span>" if is_best else ""
        border = "border:2px solid var(--green);" if is_best else "border:1px solid var(--border);"
        
        items_html = ""
        for i in c.items:
            price_str = f"&#8377;{i.price_inr:.0f}"
            stale_warning = f" <span style='color:var(--amber);font-size:11px;'>(Stale)</span>" if i.freshness == "stale" else ""
            ad_warning = f" <span style='color:var(--text-dim);font-size:11px;'>(Ad)</span>" if i.is_ad else ""
            items_html += (
                f"<div style='display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px dashed var(--border);'>"
                f"<span>{i.display_name}{stale_warning}{ad_warning}</span>"
                f"<span style='font-weight:600;'>{price_str}</span>"
                f"</div>"
            )
            
        missing_html = ""
        if c.missing_items:
            missing_html = f"<div style='margin-top:8px;font-size:11px;color:var(--red);'>Missing: {', '.join(c.missing_items)}</div>"

        card = (
            f"<div class='home-card' style='margin-bottom:16px;{border}'>"
            f"  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>"
            f"    <h3 style='margin:0;display:flex;align-items:center;'>{c.source_name.title()} Basket {badge}</h3>"
            f"    <div style='font-size:20px;font-weight:bold;'>&#8377;{c.total_cost:.0f}</div>"
            f"  </div>"
            f"  <div style='margin-bottom:12px;'>{items_html}</div>"
            f"  {missing_html}"
            f"  <div style='display:flex;gap:12px;font-size:12px;color:var(--text-dim);border-top:1px solid var(--border);padding-top:8px;margin-top:8px;'>"
            f"    <span>Score: {c.overall_score:.1f}</span>"
            f"    <span>Freshness: {c.freshness_score:.0f}</span>"
            f"    <span>Waste Risk: {c.waste_risk_score:.0f}</span>"
            f"  </div>"
            f"</div>"
        )
        html_parts.append(card)
        
    return f"<div style='max-width:800px;margin:0 auto;'>{''.join(html_parts)}</div>"


def build_basket_screen():
    with gr.Column():
        gr.Markdown("## Multi-Source Basket Optimizer")
        gr.Markdown("Ranks baskets by usefulness, cost, freshness, waste risk, and user preference across multiple sources (Swiggy, Zepto, DMart).")
        
        refresh_btn = gr.Button("Optimize Baskets", variant="primary")
        basket_html = gr.HTML("<div class='home-card' style='text-align:center;padding:40px;color:var(--text-dim);'>Click 'Optimize Baskets' to generate multi-source candidates.</div>")
        
        refresh_btn.click(
            fn=get_basket_ui_html,
            inputs=[],
            outputs=[basket_html]
        )
