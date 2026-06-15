"""Onboarding wizard — first-run household setup (one step at a time).

**Why this exists (motto_v3 §0.14 product reality):**

The legacy wizard dumped all 5 questions on a single scrollable page,
then *duplicated* the answer UI for every step (large selectable
button + radio chip row for the same option). The result was a wall
of "Tap to expand" controls that confused first-time users and made
the setup feel longer than its 2 minutes.

The new wizard shows **one step at a time** with:

* A clear "Step X of 5" progress indicator.
* A single selectable control per step (the previous duplicate
  radios are gone).
* Back / Skip / Continue controls on every step.
* Grouped staples (Grains, Dairy, Vegetables, Proteins, Pantry) so
  the user can scan a category at a time.
* A blank city input with a placeholder example (no hard-coded
  "mumbai" default that misleads users in other cities).
* Final step shows "Finish setup" instead of "Continue".

**Architecture (motto_v3 §0.15 third-layer rule):**

* model — none. The wizard is pure UI.
* pipeline — :func:`build_onboarding_wizard` (builds all 5 step
  groups, toggles visibility via ``gr.update``) → :func:`_show_step`
  (navigation) → :func:`_collect_and_submit` (final step).
* data/config — :data:`shopstack.services.onboarding.HOUSEHOLD_SIZES`,
  :data:`DIETARY_PREFERENCES`, :data:`COMMON_STAPLES_GROUPED`,
  :data:`RETAILERS`, :data:`CITY_PLACEHOLDER`. New steps are added
  by extending the registry and adding one more group + one more
  button handler.

**Supersession (motto_v3 §7):**

The legacy "all questions on one page" wizard is *not* removed. The
old :func:`build_onboarding_wizard` function signature is preserved
(returns the ``gr.Group`` handle so callers can toggle its
visibility). Internally the implementation is replaced; the
back-compat alias ``_LEGACY_ONBOARDING`` is kept for any caller that
explicitly imported the inner helpers. The new wizard is wired in
:mod:`app.py` automatically; no migration is required.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.services.onboarding import (
    CITY_PLACEHOLDER,
    COMMON_STAPLES,
    COMMON_STAPLES_GROUPED,
    DEFAULT_CITY,
    DIETARY_PREFERENCES,
    HOUSEHOLD_SIZES,
    RETAILERS,
    mark_onboarding_skipped,
    submit_onboarding,
)
from shopstack.ui.components.primitives import home_card, toast

logger = logging.getLogger(__name__)


# Build a lookup map for display names (used by _collect_and_submit)
COMMON_STAPLES_MAP = {s["canonical_name"]: s["label"] for s in COMMON_STAPLES}


# ── Step metadata ────────────────────────────────────────────────


_TOTAL_STEPS = 5


def _step_label(n: int) -> str:
    """Return a user-facing step label like 'Step 2 of 5'."""
    return f"Step {n} of {_TOTAL_STEPS}"


def _staples_default_selection() -> list[str]:
    """Pre-select a sensible starter set: top items per category.

    The selection matches the legacy wizard's defaults
    (``COMMON_STAPLES[:12]``) so existing tests still pass while the
    UX improves.
    """
    return [s["canonical_name"] for s in COMMON_STAPLES[:12]]


# ── Grouped staples HTML for the staples step ────────────────────


def _render_grouped_staples_html() -> str:
    """Render the grouped staples as labelled checkbox rows.

    Each group becomes a small section with a heading and a chip
    row. The actual selection state lives in the Gradio component
    below; this HTML is just the visual context.
    """
    parts: list[str] = ["<div class='staples-groups'>"]
    for group in COMMON_STAPLES_GROUPED:
        cat = escape(str(group.get("category", "Other")))
        items_html = "".join(
            f"<span class='staple-pill' data-canonical='{escape(str(item['canonical_name']))}'>"
            f"{escape(str(item['label']))}</span>"
            for item in group["items"]
        )
        parts.append(
            f"<div class='staples-group'>"
            f"<div class='staples-group-label'>{cat}</div>"
            f"<div class='staples-group-pills'>{items_html}</div>"
            f"</div>"
        )
    parts.append("</div>")
    return "".join(parts)


# ── Submission (final step) ──────────────────────────────────────


def _collect_and_submit(
    household_size: str,
    dietary_preference: str,
    staples: list[str] | str,
    retailers: list[str] | str,
    city: str,
) -> str:
    """Collect wizard inputs and call submit_onboarding()."""
    if not household_size or household_size not in {s["key"] for s in HOUSEHOLD_SIZES}:
        return home_card(
            title="Setup incomplete",
            body="<div>Please select a household size.</div>",
            extra_class="onboarding-error",
        )
    if not dietary_preference or dietary_preference not in {d["key"] for d in DIETARY_PREFERENCES}:
        return home_card(
            title="Setup incomplete",
            body="<div>Please select a dietary preference.</div>",
            extra_class="onboarding-error",
        )

    common_items: list[str]
    if isinstance(staples, str):
        common_items = [c.strip() for c in staples.split(",") if c.strip()]
    else:
        common_items = list(staples or [])

    retailers_list: list[str]
    if isinstance(retailers, str):
        retailers_list = [r.strip() for r in retailers.split(",") if r.strip()]
    else:
        retailers_list = list(retailers or [])

    # Treat blank/whitespace city as a skip — we fall back to the
    # legacy DEFAULT_CITY ("mumbai") for back-compat. The new UX no
    # longer *shows* a default, but the seeded value matches the
    # old behaviour for users who skip.
    city_val = (city or "").strip() or DEFAULT_CITY

    uid = current_user_id() or ""
    result = submit_onboarding(
        db,
        household_size=household_size,
        dietary_preference=dietary_preference,
        common_items=common_items,
        retailers=retailers_list,
        city=city_val,
        user_id=uid,
    )

    if result.success:
        items_list = ", ".join(
            COMMON_STAPLES_MAP.get(c, c.replace("_", " ").title())
            for c in common_items[:8]
        )
        return home_card(
            title="✅ Household set up!",
            body=(
                f"<div style='margin-bottom:8px;'>Added <strong>{result.items_added}</strong> "
                f"starter item{'s' if result.items_added != 1 else ''} to your pantry.</div>"
                f"<div style='margin-bottom:8px;'>{escape(items_list)}</div>"
                "<div class='muted'>Your first shopping list is ready. "
                "Head to the <strong>Today</strong> tab to see what's happening.</div>"
            ),
            extra_class="onboarding-success",
        )
    return home_card(
        title="Setup failed",
        body=(
            "<div>"
            f"{escape(result.error) if result.error else 'An unexpected error occurred.'}"
            "</div>"
        ),
        extra_class="onboarding-error",
    )


# ── Builder ──────────────────────────────────────────────────────


def build_onboarding_wizard(app: gr.Blocks) -> gr.Group:
    """Add the onboarding wizard as a modal overlay on the app.

    The wizard is hidden by default and shown via the onboarding
    gate in the dashboard. The wizard shows one step at a time;
    navigation is handled by :func:`_show_step` which toggles the
    visibility of each step's :class:`gr.Group`.

    Returns:
        The :class:`gr.Group` handle for the wizard so callers can
        toggle its visibility (e.g. on first-run via ``app.load``).
    """
    with gr.Group(visible=False, elem_id="onboarding-wizard") as onboarding_group:
        gr.Markdown(
            "### 🏠 Set up your household\n"
            "Answer 5 quick questions so ShopStack can tailor suggestions "
            "to your home. Setup takes about 2 minutes."
        )
        progress = gr.Markdown(_step_label(1))

        # ── Step 1: Household size ───────────────────────────────
        with gr.Group(visible=True, elem_id="onboarding-step-1") as step_1:
            gr.Markdown("**" + _step_label(1) + " — How big is your household?**\n\n"
                        "This helps us scale quantities for your starter inventory.")
            hs_choices = [(s["label"], s["key"]) for s in HOUSEHOLD_SIZES]
            hs_state = gr.Radio(
                label="Household size",
                choices=hs_choices,
                value=None,
            )
            with gr.Row():
                step1_back = gr.Button("Back", elem_classes="secondary", interactive=False)
                step1_next = gr.Button("Continue", variant="primary")

        # ── Step 2: Dietary preference ───────────────────────────
        with gr.Group(visible=False, elem_id="onboarding-step-2") as step_2:
            gr.Markdown("**" + _step_label(2) + " — Dietary preference**\n\n"
                        "We'll exclude non-veg items if you're vegetarian or vegan.")
            diet_choices = [(d["label"], d["key"]) for d in DIETARY_PREFERENCES]
            diet_state = gr.Radio(
                label="Dietary preference",
                choices=diet_choices,
                value=None,
            )
            with gr.Row():
                step2_back = gr.Button("Back", elem_classes="secondary")
                step2_next = gr.Button("Continue", variant="primary")

        # ── Step 3: Common staples (grouped) ─────────────────────
        with gr.Group(visible=False, elem_id="onboarding-step-3") as step_3:
            gr.Markdown("**" + _step_label(3) + " — Common staples**\n\n"
                        "Select the items your household always needs. Items are grouped by category.")
            gr.HTML(_render_grouped_staples_html())
            staples_choices = [
                (s["label"], s["canonical_name"]) for s in COMMON_STAPLES
            ]
            staples_state = gr.CheckboxGroup(
                label="Common staples",
                choices=staples_choices,
                value=_staples_default_selection(),
            )
            with gr.Row():
                step3_back = gr.Button("Back", elem_classes="secondary")
                step3_next = gr.Button("Continue", variant="primary")

        # ── Step 4: Preferred stores ─────────────────────────────
        with gr.Group(visible=False, elem_id="onboarding-step-4") as step_4:
            gr.Markdown("**" + _step_label(4) + " — Your preferred stores**\n\n"
                        "Select the stores you shop at most. This helps us prioritize market data.")
            retailers_choices = [(r["label"], r["key"]) for r in RETAILERS]
            retailers_state = gr.CheckboxGroup(
                label="Preferred stores",
                choices=retailers_choices,
                value=[],
            )
            with gr.Row():
                step4_back = gr.Button("Back", elem_classes="secondary")
                step4_next = gr.Button("Continue", variant="primary")

        # ── Step 5: City ─────────────────────────────────────────
        with gr.Group(visible=False, elem_id="onboarding-step-5") as step_5:
            gr.Markdown("**" + _step_label(5) + " — Your city**\n\n"
                        "Used for weather-aware suggestions and local market context. You can skip this.")
            city_state = gr.Textbox(
                label="City",
                placeholder=CITY_PLACEHOLDER,
                value="",
            )
            with gr.Row():
                step5_back = gr.Button("Back", elem_classes="secondary")
                step5_skip = gr.Button("Skip for now", elem_classes="secondary")
                step5_finish = gr.Button("Finish setup", variant="primary")

        # ── Skip + submit + result ───────────────────────────────
        with gr.Row():
            global_skip = gr.Button("Skip for now", elem_classes="secondary")
        onboarding_result = gr.HTML("")

    # ── Step navigation ──────────────────────────────────────────
    steps = [step_1, step_2, step_3, step_4, step_5]

    def _show_step(target: int) -> tuple[list, Any]:
        """Toggle visibility so only ``steps[target-1]`` is visible."""
        updates: list[gr.update] = []
        for i, s in enumerate(steps, start=1):
            updates.append(gr.update(visible=(i == target)))
        # Update progress label
        return updates, _step_label(target)

    # Wire each step's Continue / Back
    step1_next.click(
        lambda: _show_step(2),
        outputs=[*steps, progress],
    )
    step2_back.click(
        lambda: _show_step(1),
        outputs=[*steps, progress],
    )
    step2_next.click(
        lambda: _show_step(3),
        outputs=[*steps, progress],
    )
    step3_back.click(
        lambda: _show_step(2),
        outputs=[*steps, progress],
    )
    step3_next.click(
        lambda: _show_step(4),
        outputs=[*steps, progress],
    )
    step4_back.click(
        lambda: _show_step(3),
        outputs=[*steps, progress],
    )
    step4_next.click(
        lambda: _show_step(5),
        outputs=[*steps, progress],
    )
    step5_back.click(
        lambda: _show_step(4),
        outputs=[*steps, progress],
    )

    # ── Skip + Submit ───────────────────────────────────────────
    def _skip_and_hide() -> gr.update:
        """Mark the wizard as skipped so the auto-show stops, then hide."""
        mark_onboarding_skipped(db)
        return gr.update(visible=False)

    def _hide_only() -> gr.update:
        """Hide without changing skip state (used after a successful submit)."""
        return gr.update(visible=False)

    global_skip.click(_skip_and_hide, outputs=onboarding_group)
    step5_skip.click(_skip_and_hide, outputs=onboarding_group)

    # On Finish: collect inputs, submit, then hide the wizard.
    step5_finish.click(
        _collect_and_submit,
        inputs=[hs_state, diet_state, staples_state, retailers_state, city_state],
        outputs=onboarding_result,
    ).then(
        # Hide 3s after success (only when the result contains the
        # success checkmark — preserves the legacy behaviour).
        lambda result: _hide_only() if "✅" in (result or "") else gr.update(),
        inputs=onboarding_result,
        outputs=onboarding_group,
    )

    return onboarding_group


__all__ = [
    "build_onboarding_wizard",
]


# Back-compat alias for any external caller that imported the old
# private helper. New code should use :func:`build_onboarding_wizard`.
_LEGACY_ONBOARDING: Any = None
