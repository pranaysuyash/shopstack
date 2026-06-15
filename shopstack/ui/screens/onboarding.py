"""Onboarding wizard screen — first-run household setup.

Renders a 5-step Gradio wizard that collects:
1. Household size (1 / 2-3 / 4-5 / 6+)
2. Dietary preference (vegetarian / vegan / omnivore)
3. Common staples (multi-select from curated list)
4. Top retailers (multi-select)
5. City (free text, default mumbai)

On submit, calls ``submit_onboarding()`` to seed the household
inventory, preferences, and initial shopping list.

This module is the *Gradio UI* layer; all business logic lives in
``shopstack.services.onboarding``.
"""
from __future__ import annotations

import logging
from html import escape

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.services.onboarding import (
    COMMON_STAPLES,
    DEFAULT_CITY,
    DIETARY_PREFERENCES,
    HOUSEHOLD_SIZES,
    RETAILERS,
    mark_onboarding_skipped,
    submit_onboarding,
)
from shopstack.ui.components.primitives import loading_skeleton

logger = logging.getLogger(__name__)


def _step1_household_size() -> str:
    """Render step 1: household size."""
    buttons = []
    for size in HOUSEHOLD_SIZES:
        buttons.append(
            f"<button class='onboarding-btn' data-value='{size['key']}'>"
            f"<strong>{escape(size['label'])}</strong></button>"
        )
    return (
        "home_card(body='"\n        "<h3>Step 1 of 5 — How big is your household?</h3>"\n        "<div class=\'muted\' style=\'margin-bottom:12px;\'>This helps us scale "\n        "quantities for your starter inventory.', style='text-align:left;')"
        f"{''.join(buttons)}"
        "</div>"
    )


def _step2_diet() -> str:
    """Render step 2: dietary preference."""
    buttons = []
    for pref in DIETARY_PREFERENCES:
        buttons.append(
            f"<button class='onboarding-btn' data-value='{pref['key']}'>"
            f"<strong>{escape(pref['label'])}</strong></button>"
        )
    return (
        "home_card(body='"\n        "<h3>Step 2 of 5 — Dietary preference</h3>"\n        "<div class=\'muted\' style=\'margin-bottom:12px;\'>We\'ll exclude "\n        "non-veg items if you\'re vegetarian or vegan.', style='text-align:left;')"
        f"{''.join(buttons)}"
        "</div>"
    )


def _step3_staples() -> str:
    """Render step 3: common staples (checkboxes rendered as Gradio later)."""
    items_html = []
    for item in COMMON_STAPLES:
        items_html.append(
            f"<div style='padding:4px 0;'>"
            f"<label><input type='checkbox' class='staple-cb' "
            f"value='{item['canonical_name']}'> "
            f"{escape(item['label'])} <span class='muted'>({escape(item['category'])})</span></label>"
            f"</div>"
        )
    return (
        "home_card(body='"\n        "<h3>Step 3 of 5 — Common staples</h3>"\n        "<div class=\'muted\' style=\'margin-bottom:12px;\'>Select the items "\n        "your household always needs.', style='text-align:left;')"
        f"{''.join(items_html)}"
        "</div>"
    )


def _step4_retailers() -> str:
    """Render step 4: preferred retailers."""
    buttons = []
    for r in RETAILERS:
        buttons.append(
            f"<button class='onboarding-btn retailer-btn' data-value='{r['key']}'>"
            f"<strong>{escape(r['label'])}</strong></button>"
        )
    return (
        "home_card(body='"\n        "<h3>Step 4 of 5 — Your preferred stores</h3>"\n        "<div class=\'muted\' style=\'margin-bottom:12px;\'>Select the stores "\n        "you shop at most. This helps us prioritize market data.', style='text-align:left;')"
        f"{''.join(buttons)}"
        "</div>"
    )


def _step5_city() -> str:
    """Render step 5: city."""
    return (
        "home_card(body='"\n        "<h3>Step 5 of 5 — Your city</h3>"\n        "<div class=\'muted\' style=\'margin-bottom:12px;\'>Used for weather-aware "\n        "suggestions and local market context.', style='text-align:left;')"
        f"<input type='text' id='onboarding-city' "
        f"placeholder='{DEFAULT_CITY}' class='onboarding-city-input' />"
        "</div>"
    )


def _collect_and_submit(
    household_size: str,
    dietary_preference: str,
    staples_csv: str,
    retailers_csv: str,
    city: str,
) -> str:
    """Collect wizard inputs and call submit_onboarding()."""
    if not household_size or household_size not in {s["key"] for s in HOUSEHOLD_SIZES}:
        return (
            "home_card(body='"\n            "<h3>Setup incomplete</h3>"\n            "<div>Please select a household size.', style='border:2px solid var(--red);')"
            "</div>"
        )
    if not dietary_preference or dietary_preference not in {d["key"] for d in DIETARY_PREFERENCES}:
        return (
            "home_card(body='"\n            "<h3>Setup incomplete</h3>"\n            "<div>Please select a dietary preference.', style='border:2px solid var(--red);')"
            "</div>"
        )

    common_items = [c.strip() for c in staples_csv.split(",") if c.strip()] if staples_csv else []
    retailers = [r.strip() for r in retailers_csv.split(",") if r.strip()] if retailers_csv else []
    city_val = (city or DEFAULT_CITY).strip()

    uid = current_user_id() or ""
    result = submit_onboarding(
        db,
        household_size=household_size,
        dietary_preference=dietary_preference,
        common_items=common_items,
        retailers=retailers,
        city=city_val,
        user_id=uid,
    )

    if result.success:
        items_list = ", ".join(COMMON_STAPLES_MAP.get(c, c.replace("_", " ").title()) for c in common_items[:8])
        return (
            "home_card(body='"\n            "<h3>✅ Household set up!</h3>"\n            f"<div style=\'margin-bottom:8px;\'>Added <strong>{result.items_added}</strong> "\n            f"starter item{\'s\' if result.items_added != 1 else \'\'} to your pantry.', style='border:2px solid var(--green);text-align:left;')"
            f"<div style='margin-bottom:8px;'>{items_list}</div>"
            "<div class='muted'>Your first shopping list is ready. "
            "Head to the <strong>Today</strong> tab to see what's happening.</div>"
            "</div>"
        )
    else:
        return (
            "home_card(body='"\n            "<h3>Setup failed</h3>"\n            f"<div>{escape(result.error) if result.error else \'An unexpected error occurred.\'}', style='border:2px solid var(--red);')"
            "</div>"
        )


# Build a lookup map for display names
COMMON_STAPLES_MAP = {s["canonical_name"]: s["label"] for s in COMMON_STAPLES}


def build_onboarding_wizard(app: gr.Blocks) -> gr.Group:
    """Add the onboarding wizard as a modal overlay on the app.

    This is called once during app construction. The wizard is hidden
    by default and shown via the onboarding gate in the dashboard.

    Returns:
        The :class:`gr.Group` handle for the wizard so callers can
        toggle its visibility (e.g. on first-run via ``app.load``).
    """
    with gr.Group(visible=False, elem_id="onboarding-wizard") as onboarding_group:
        gr.Markdown("### 🏠 Set up your household")
        gr.Markdown(
            "Answer 5 quick questions so " + "ShopStack" + " can tailor "
            "suggestions to your home."
        )

        step1_html = gr.HTML(_step1_household_size())
        hs_radio = gr.Radio(
            label="Household size",
            choices=[(s["label"], s["key"]) for s in HOUSEHOLD_SIZES],
            value=None,
        )

        step2_html = gr.HTML(_step2_diet())
        diet_radio = gr.Radio(
            label="Dietary preference",
            choices=[(p["label"], p["key"]) for p in DIETARY_PREFERENCES],
            value=None,
        )

        step3_html = gr.HTML(_step3_staples())
        staples_checkboxes = gr.CheckboxGroup(
            label="Common staples",
            choices=[(s["label"], s["canonical_name"]) for s in COMMON_STAPLES],
            value=[s["canonical_name"] for s in COMMON_STAPLES[:12]],
        )

        step4_html = gr.HTML(_step4_retailers())
        retailers_checkboxes = gr.CheckboxGroup(
            label="Preferred stores",
            choices=[(r["label"], r["key"]) for r in RETAILERS],
            value=[],
        )

        step5_html = gr.HTML(_step5_city())
        city_input = gr.Textbox(
            label="City",
            placeholder=DEFAULT_CITY,
            value="",
        )

        with gr.Row():
            cancel_btn = gr.Button("Skip for now", elem_classes="secondary")
            submit_btn = gr.Button("Finish setup", variant="primary")

        onboarding_result = gr.HTML("")

    def _hide_wizard():
        return gr.update(visible=False)

    def _skip_and_hide():
        """Mark the wizard as skipped so the auto-show stops, then hide."""
        mark_onboarding_skipped(db)
        return gr.update(visible=False)

    cancel_btn.click(_skip_and_hide, outputs=onboarding_group)
    submit_btn.click(
        _collect_and_submit,
        inputs=[hs_radio, diet_radio, staples_checkboxes, retailers_checkboxes, city_input],
        outputs=onboarding_result,
    ).then(
        # Auto-hide 3 seconds after success
        lambda result: gr.update(visible=False) if "✅" in result else gr.update(),
        inputs=onboarding_result,
        outputs=onboarding_group,
    )

    return onboarding_group
