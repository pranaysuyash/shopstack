from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import db
from shopstack.memory.waste_patterns import get_waste_insights
from shopstack.ui.screens.price_memory import price_intelligence_view
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)

@safe_render
def get_intelligence_dashboard():
    """Return HTML for Waste, Preferences, and Price intelligence."""
    # 1. Waste Patterns
    try:
        waste_data = get_waste_insights(db)
        if waste_data:
            waste_items = []
            for w in waste_data:
                rate = w["waste_rate"] * 100
                if rate > 0:
                    waste_items.append(
                        f"<li><strong>{escape(w['canonical_name'].title())}</strong>: "
                        f"{w['wasted_qty']} wasted out of {w['wasted_qty']+w['consumed_qty']} ({rate:.0f}% waste rate)</li>"
                    )
            
            if waste_items:
                waste_html = "<div class='home-card' style='border-left:4px solid var(--red);'>" \
                             "<h4>High Waste Items</h4><ul>" + "".join(waste_items[:10]) + "</ul></div>"
            else:
                waste_html = "<div class='home-card'>No waste patterns detected yet. Great job!</div>"
        else:
            waste_html = "<div class='home-card'>No waste data available.</div>"
    except Exception as e:
        logger.warning("Error loading waste insights: %s", e)
        waste_html = "<div class='home-card'>Error loading waste insights.</div>"
        
    # 2. Preferences
    try:
        prefs = db.get_preference_signals()
        if prefs:
            pref_items = []
            for p in prefs:
                pref_items.append(
                    f"<li><strong>{escape(p.canonical_name.title())}</strong>: "
                    f"<em>{escape(p.signal_type)}</em> &rarr; {escape(str(p.value))} "
                    f"<span style='color:var(--text-dim);font-size:0.85em;'>(Source: {escape(p.source)})</span></li>"
                )
            pref_html = "<div class='home-card'><h4>Learned Preferences</h4><ul>" + "".join(pref_items[:10]) + "</ul></div>"
        else:
            pref_html = "<div class='home-card'>No preference signals learned yet. Complete more shopping trips!</div>"
    except Exception as e:
        logger.warning("Error loading preferences: %s", e)
        pref_html = "<div class='home-card'>Error loading preferences.</div>"
        
    # 3. Price Intelligence
    try:
        price_html = price_intelligence_view()
    except Exception as e:
        logger.warning("Error loading price intelligence: %s", e)
        price_html = "<div class='home-card'>Error loading price intelligence.</div>"
        
    return waste_html, pref_html, price_html

