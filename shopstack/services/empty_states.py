"""Better empty states with onboarding hints.

The default "no data yet" empty state is a teachable moment. A user who
hits a fresh screen and sees only a placeholder will close the tab;
a user who sees "Add your first 5 pantry staples — or import a Swiggy
receipt" is one click away from activation.

**Why this exists (motto_v3 §0.14 product reality):**

The previous empty states across the app were generic one-liners
(`"Fridge is empty right now."`, `"List is empty."`, etc.). Each screen
invented its own copy. The result was inconsistent voice and a missed
opportunity: a new user doesn't know what to do *next*.

This module centralises the "what to do" copy per screen/section, with:

- A canonical registry of empty-state presets (title, body, optional
  primary/secondary CTAs).
- Per-locale rendering through the existing ``shopstack.services.i18n``
  layer (additive — reuses the same translation tables).
- A "smart" mode that picks different copy when the household has some
  history vs. when it's truly empty (e.g., a household with 200 items
  and no list sees a *different* empty state than a brand-new household
  with zero items).
- A small `render()` helper that produces the HTML for a given preset,
  with the existing `.empty-state` CSS class so the visual style is
  consistent.

**Long-term:** the registry is the *only* place empty-state copy
should be defined. When a screen needs a new empty state, add a
preset here, then call ``empty_state.render(preset_id)``. When
untranslated, the preset falls back to English.

**Supersession rule (motto_v3 §7):** the existing one-liner empty
states in `shopstack/ui/screens/*` are *not deleted* — they stay as
the legacy fallback. The new helper is additive: each screen can
opt in by calling ``render_empty_state(...)`` instead of returning
its hand-rolled HTML. Old screens continue to work; new screens use
the helper.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

from shopstack.services.i18n import get_translation

logger = logging.getLogger(__name__)


# ── Data model ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmptyStateCTA:
    """A single call-to-action rendered below the empty-state body.

    Attributes:
        label: The visible text (will be translated via i18n if it
            matches a registered key like ``empty.cta.add_items``).
        target_id: The ``elem_id`` of the Gradio component to click.
            The empty-state HTML wraps the label in a button that
            calls ``document.getElementById(target_id).click()`` — so
            the CTA activates an existing component on the page
            rather than introducing a new one.
        target_tab: Optional tab slug to switch to (one of the
            ``TAB_ORDER`` keys). When set, the CTA switches the
            top-level tab *and* optionally clicks the target.
    """

    label: str
    target_id: str = ""
    target_tab: str = ""


@dataclass(frozen=True)
class EmptyStatePreset:
    """A single empty-state definition.

    A preset binds together: a stable ID (so screens can reference it),
    a translatable title, a translatable body, and 0-2 optional CTAs.
    Presets live in :data:`PRESETS` and are immutable.

    The ``tier`` field distinguishes "first-time" empty states (a
    brand-new household, zero history) from "transient" empty states
    (a household that *has* data but the *current view* is empty).
    The smart renderer picks the right tier based on what the
    household has, so the copy is contextual.
    """

    preset_id: str
    tier: str  # "first_time" | "transient"
    title_key: str  # i18n key, falls back to title_key text if untranslated
    body_key: str
    primary_cta: EmptyStateCTA | None = None
    secondary_cta: EmptyStateCTA | None = None
    icon: str = ""  # decorative emoji/symbol; not the meaning


# ── Preset registry ────────────────────────────────────────────────


PRESETS: dict[str, EmptyStatePreset] = {
    "home.dashboard": EmptyStatePreset(
        preset_id="home.dashboard",
        tier="first_time",
        title_key="empty.dashboard.title",
        body_key="empty.dashboard.body",
        primary_cta=EmptyStateCTA(
            label="empty.cta.add_first_items",
            target_id="add-first-items-btn",
        ),
        secondary_cta=EmptyStateCTA(
            label="empty.cta.import_receipt",
            target_id="reconcile-import-receipt-btn",
            target_tab="reconcile",
        ),
        icon="🏠",
    ),
    "pantry.inventory": EmptyStatePreset(
        preset_id="pantry.inventory",
        tier="first_time",
        title_key="empty.inventory.title",
        body_key="empty.inventory.body",
        primary_cta=EmptyStateCTA(
            label="empty.cta.add_items",
            target_id="add-items-btn",
        ),
        secondary_cta=EmptyStateCTA(
            label="empty.cta.scan_receipt",
            target_id="scan-receipt-btn",
            target_tab="reconcile",
        ),
        icon="🛒",
    ),
    "groceries.basket": EmptyStatePreset(
        preset_id="groceries.basket",
        tier="first_time",
        title_key="empty.basket.title",
        body_key="empty.basket.body",
        primary_cta=EmptyStateCTA(
            label="empty.cta.create_list",
            target_id="create-list-btn",
        ),
        icon="🧺",
    ),
    "groceries.basket.no_active_list": EmptyStatePreset(
        preset_id="groceries.basket.no_active_list",
        tier="transient",
        title_key="empty.basket.no_active.title",
        body_key="empty.basket.no_active.body",
        primary_cta=EmptyStateCTA(
            label="empty.cta.create_list",
            target_id="create-list-btn",
        ),
        icon="📝",
    ),
    "memory.recent": EmptyStatePreset(
        preset_id="memory.recent",
        tier="first_time",
        title_key="empty.memory.title",
        body_key="empty.memory.body",
        primary_cta=EmptyStateCTA(
            label="empty.cta.add_items",
            target_id="add-items-btn",
        ),
        icon="📓",
    ),
    "memory.what_changed": EmptyStatePreset(
        preset_id="memory.what_changed",
        tier="transient",
        title_key="empty.memory.no_changes.title",
        body_key="empty.memory.no_changes.body",
        icon="🔍",
    ),
    "memory.find_trail": EmptyStatePreset(
        preset_id="memory.find_trail",
        tier="transient",
        title_key="empty.find_trail.title",
        body_key="empty.find_trail.body",
        icon="🧭",
    ),
    # Pass 15 §2.5: tab-level empty state for the Find Trail tab before
    # the user enters a query. Different from ``memory.find_trail``
    # (which fires when the user has searched but found no trail) — this
    # fires on first tab visit with no input.
    "find_trail.no_query": EmptyStatePreset(
        preset_id="find_trail.no_query",
        tier="transient",
        title_key="empty.find_trail.no_query.title",
        body_key="empty.find_trail.no_query.body",
        icon="🔍",
    ),
    "while_shopping.manual_add": EmptyStatePreset(
        preset_id="while_shopping.manual_add",
        tier="transient",
        title_key="empty.manual_add.title",
        body_key="empty.manual_add.body",
        icon="📷",
    ),
    "at_home.reconcile": EmptyStatePreset(
        preset_id="at_home.reconcile",
        tier="transient",
        title_key="empty.reconcile.title",
        body_key="empty.reconcile.body",
        primary_cta=EmptyStateCTA(
            label="empty.cta.scan_receipt",
            target_id="scan-receipt-btn",
        ),
        icon="🏡",
    ),
    "household.fridge": EmptyStatePreset(
        preset_id="household.fridge",
        tier="transient",
        title_key="empty.fridge.title",
        body_key="empty.fridge.body",
        primary_cta=EmptyStateCTA(
            label="empty.cta.add_items",
            target_id="add-items-btn",
        ),
        icon="❄️",
    ),
    "recipes.cookbook": EmptyStatePreset(
        preset_id="recipes.cookbook",
        tier="transient",
        title_key="empty.cookbook.title",
        body_key="empty.cookbook.body",
        icon="🍳",
    ),
    "global_search.no_results": EmptyStatePreset(
        preset_id="global_search.no_results",
        tier="transient",
        title_key="empty.search.title",
        body_key="empty.search.body",
        icon="🔎",
    ),
    # Generic catch-all for legacy call sites. The renderer
    # accepts overrides for title/body/icon so the old
    # `empty_state_enhanced(message, icon=...)` pattern maps
    # cleanly to this preset. New screens should prefer the
    # named presets above.
    "generic": EmptyStatePreset(
        preset_id="generic",
        tier="transient",
        title_key="",  # empty → renderer uses override_title
        body_key="",   # empty → renderer uses override_body
        icon="",       # empty → renderer uses override_icon
    ),
}


# ── Smart context (so presets adapt to household history) ─────────


@dataclass
class HouseholdContext:
    """Lightweight summary of a household used to pick the right tier.

    Smart mode: a household with 0 items / 0 lists is "first_time" and
    gets the heavy onboarding copy. A household with data but no list
    is "transient" and gets a lighter "no list right now" copy.

    This is intentionally cheap to compute: a single COUNT query per
    subsystem, not a full snapshot. Callers (the empty-state renderer)
    use it to choose a tier, not to render data.
    """

    item_count: int = 0
    list_count: int = 0
    trace_count: int = 0
    recipe_count: int = 0
    has_any_data: bool = False


def build_household_context(database: Any, user_id: str = "") -> HouseholdContext:
    """Build a :class:`HouseholdContext` for ``user_id``.

    Best-effort: any exception (e.g. missing tables) returns an empty
    context (i.e. ``first_time`` tier). This is the correct failure
    mode for an empty-state renderer — we never want a missing
    context to crash the page render.
    """
    try:
        items = database.get_inventory(user_id=user_id) if database else []
        lists = (
            [database.get_active_shopping_list(user_id=user_id)]
            if database
            else []
        )
        active_lists = [l for l in lists if l]
        # Traces and recipes are best-effort — the count API differs
        # across service versions. We use getattr to skip on missing.
        traces = (
            database.get_traces(limit=1, user_id=user_id)
            if database and hasattr(database, "get_traces")
            else []
        )
        ctx = HouseholdContext(
            item_count=len(items) if items is not None else 0,
            list_count=len(active_lists),
            trace_count=len(traces) if traces is not None else 0,
            recipe_count=0,  # not in DB; recipes come from cookbook service
            has_any_data=bool(items) or bool(active_lists) or bool(traces),
        )
        return ctx
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_household_context failed: %s", exc)
        return HouseholdContext()


# ── Renderer ───────────────────────────────────────────────────────


@dataclass
class RenderOptions:
    """Options for the empty-state HTML renderer.

    Attributes:
        locale: Locale code (default "en"). The i18n layer is the
            source of truth; we never bake language into the preset.
        compact: When ``True``, render a one-liner (used in tooltips
            and the global search). When ``False`` (default), render
            the full card with title, body, icon, and CTA buttons.
        extra_class: Optional extra CSS class for the wrapper
            (e.g. ``"empty-state--wide"`` to opt into a wider layout).
    """

    locale: str = "en"
    compact: bool = False
    extra_class: str = ""


def render(
    preset_id: str,
    *,
    options: RenderOptions | None = None,
    household: HouseholdContext | None = None,
    override_title: str | None = None,
    override_body: str | None = None,
    override_icon: str | None = None,
) -> str:
    """Render the HTML for ``preset_id``.

    Args:
        preset_id: The preset to render. If unknown, a safe fallback
            ("No data yet.") is returned (we never crash the page).
        options: Render options. Defaults to RenderOptions().
        household: Optional household context. If provided and the
            preset has tier "first_time" but the household already
            has data, the renderer falls through to the matching
            "transient" preset (e.g. ``home.dashboard`` -> a
            generic "all caught up" placeholder).
        override_title: When the preset has no title_key (the
            ``"generic"`` preset), this string is used as the
            title verbatim.
        override_body: Same for the body.
        override_icon: Same for the icon.

    Returns:
        An HTML string. Inject into the page via ``gr.HTML`` or any
        ``innerHTML`` write.

    Example::

        from shopstack.services.empty_states import render, build_household_context
        ctx = build_household_context(db, current_user_id())
        html = render("home.dashboard", household=ctx)
    """
    options = options or RenderOptions()
    preset = PRESETS.get(preset_id)
    if preset is None:
        return _fallback_html(options)

    # Smart mode: if the preset is "first_time" but the household has
    # data, downgrade to a transient placeholder.
    effective_preset = preset
    if preset.tier == "first_time" and household is not None and household.has_any_data:
        # Map each first_time preset to a transient sibling
        sibling = _TRANSIENT_SIBLINGS.get(preset.preset_id)
        if sibling and sibling in PRESETS:
            effective_preset = PRESETS[sibling]

    # Resolve title/body/icon: preset keys first, then overrides.
    if effective_preset.title_key:
        title = get_translation(options.locale, effective_preset.title_key)
    else:
        title = override_title or ""
    if effective_preset.body_key:
        body = get_translation(options.locale, effective_preset.body_key)
    else:
        body = override_body or ""
    icon = effective_preset.icon or (override_icon or "")

    if options.compact:
        return _render_compact(title, body, effective_preset, options)
    return _render_full(title, body, effective_preset, icon, options)


def _render_compact(
    title: str,
    body: str,
    preset: EmptyStatePreset,
    options: RenderOptions,
) -> str:
    """One-line empty state, used in tooltips and global-search results."""
    return (
        f'<div class="empty-state empty-state--compact {escape(options.extra_class)}" '
        f'role="status">'
        f'<strong>{escape(title)}</strong> '
        f'<span class="empty-state-body">{escape(body)}</span>'
        f'</div>'
    )


def _render_full(
    title: str,
    body: str,
    preset: EmptyStatePreset,
    icon: str,
    options: RenderOptions,
) -> str:
    """Card-style empty state with icon, body, and CTAs.

    The preset provides the CTAs; the icon is resolved (preset
    icon wins unless empty, then override_icon is used). This
    split lets the ``"generic"`` preset work: it has no icon
    in the registry, so the caller's override_icon is used.
    """
    resolved_icon = preset.icon or icon
    icon_html = (
        f'<div class="empty-state-icon" aria-hidden="true">{escape(resolved_icon)}</div>'
        if resolved_icon
        else ""
    )
    cta_html = _render_ctas(preset, options)
    return (
        f'<div class="empty-state {escape(options.extra_class)}" '
        f'role="status" aria-live="polite">'
        f'{icon_html}'
        f'<h3 class="empty-state-title">{escape(title)}</h3>'
        f'<p class="empty-state-body">{escape(body)}</p>'
        f'{cta_html}'
        f'</div>'
    )


def _render_ctas(preset: EmptyStatePreset, options: RenderOptions) -> str:
    if preset.primary_cta is None and preset.secondary_cta is None:
        return ""
    buttons: list[str] = []
    if preset.primary_cta:
        buttons.append(
            f'<button type="button" class="empty-state-cta empty-state-cta--primary" '
            f'onclick="ssEmptyStateCta({_cta_json(preset.primary_cta)})">'
            f'{escape(get_translation(options.locale, preset.primary_cta.label))}'
            f'</button>'
        )
    if preset.secondary_cta:
        buttons.append(
            f'<button type="button" class="empty-state-cta empty-state-cta--secondary" '
            f'onclick="ssEmptyStateCta({_cta_json(preset.secondary_cta)})">'
            f'{escape(get_translation(options.locale, preset.secondary_cta.label))}'
            f'</button>'
        )
    return '<div class="empty-state-ctas">' + "".join(buttons) + "</div>"


def _cta_json(cta: EmptyStateCTA) -> str:
    """Render the CTA as a JSON object literal for the JS handler."""
    return json.dumps(
        {"targetId": cta.target_id, "targetTab": cta.target_tab},
        separators=(",", ":"),
    )


def _fallback_html(options: RenderOptions) -> str:
    """Return a safe HTML fallback when a preset id is unknown."""
    msg = get_translation(options.locale, "empty.fallback")
    return f'<div class="empty-state" role="status">{escape(msg)}</div>'


# Map first_time presets to their transient siblings for smart-mode
# downgrade. Screens register transient siblings for the same
# screen/section when they exist.
_TRANSIENT_SIBLINGS: dict[str, str] = {
    "home.dashboard": "memory.what_changed",
    "pantry.inventory": "household.fridge",
    "groceries.basket": "groceries.basket.no_active_list",
    "memory.recent": "memory.what_changed",
}


# ── Public API for the JS CTA handler ─────────────────────────────


# The empty-state CTAs are just buttons that delegate to a global JS
# function. The function is registered by `render_empty_state_script()`
# below, which the Gradio header can include via `app.load(None, js=...)`
# or by being injected into the page through `gr.HTML(...)`.
EMPTY_STATE_SCRIPT_HTML: str = """
<script data-ss-exec="true">
function ssEmptyStateCta(cta) {
  try {
    if (cta && cta.targetTab) {
      var tabBtn = document.querySelector('[data-testid="tab-' + cta.targetTab + '"]');
      if (tabBtn) tabBtn.click();
    }
    if (cta && cta.targetId) {
      // Defer past any tab-switch animation
      setTimeout(function() {
        var el = document.getElementById(cta.targetId);
        if (el) el.click();
      }, cta.targetTab ? 80 : 0);
    }
  } catch (e) {
    console.warn('ssEmptyStateCta failed', e);
  }
}
</script>
"""


def render_empty_state_script() -> str:
    """Return the inline JS handler for empty-state CTAs.

    Pass to ``gr.HTML(empty_states.render_empty_state_script())`` or
    include in the header block. The handler delegates to whichever
    element/tab the CTA references.
    """
    return EMPTY_STATE_SCRIPT_HTML


__all__ = [
    "EmptyStateCTA",
    "EmptyStatePreset",
    "EmptyStatePreset",
    "HouseholdContext",
    "PRESETS",
    "RenderOptions",
    "build_household_context",
    "render",
    "render_empty_state_script",
]
