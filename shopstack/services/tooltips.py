"""Inline help / tooltip registry.

Many of ShopStack's most powerful features (lot IDs, batch syntax,
scene types, community opt-in, backup restore) are invisible until a
user reads the docs — and a user who has to leave the app to learn
the app will not come back.

This module centralises the inline help for advanced fields, with:

- A canonical registry of (key → HelpEntry) mappings. Each entry has
  a stable id, a translatable title + body, and an optional
  ``learn_more`` URL.
- A renderer that produces the HTML wrapper for any entry. Screens
  call ``render_inline_help("lot_id")`` next to a field, and the
  helper emits the `.help-target`/`.help-tooltip` markup the
  CSS in ``shopstack.ui.theme`` knows how to style.
- A `tooltips_missing()` static check used by the copy audit
  (see ``shopstack.tools.copy_audit``) to flag any new advanced
  field that has no help entry — the long-term direction is that
  every advanced input has a tooltip.
- A lightweight JS click-toggle for the persistent popover: most
  tooltips only need hover/focus, but the longer descriptions need
  a click-toggle so keyboard users can keep them open while they
  read. The JS is self-contained and reuses the existing
  ``data-ss-exec`` pattern (item #99 from the 2026-06-13 review).

**Why this is more than a tooltip library (motto_v3 §0.14 product
reality):**

The first time a user sees "Scene Type: shelf" with no context, they
assume the app is broken. A one-line "What is this?" tooltip next to
the field is the difference between a confused user and an
activated one. The registry is also a *contract* — the doc health
audit and the tests both treat it as such, so adding a new advanced
field is a one-line registry entry plus one test.

**Supersession rule (motto_v3 §7):** no existing inline help is
deleted. The legacy ``title=`` attributes on Gradio components stay;
this registry is additive and only used by screens that opt in.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from shopstack.services.i18n import get_translation

__all__ = [
    "HelpEntry",
    "HELP_REGISTRY",
    "render_inline_help",
    "render_help_for",
    "tooltips_missing",
    "render_help_toggle_script",
]


@dataclass(frozen=True)
class HelpEntry:
    """A single inline-help entry.

    Attributes:
        help_id: Stable id (e.g. ``"lot_id"``). Screens reference
            entries by id, never by title.
        title_key: i18n key for the bold title shown in the tooltip.
        body_key: i18n key for the longer body. If the key is missing
            the renderer falls back to the title.
        learn_more: Optional URL to a docs page. Shown as a small
            "Learn more" link in the tooltip.
        example: Optional example string shown below the body in a
            monospace block — useful for syntax-driven fields like
            ``"lot:qty"`` batch consume.
    """

    help_id: str
    title_key: str
    body_key: str
    learn_more: str = ""
    example: str = ""


# Canonical registry. The order of insertion is the order the help
# audit will iterate. Add new entries here, never at the call site —
# the whole point of the registry is that it is the single source of
# truth for inline help.
HELP_REGISTRY: dict[str, HelpEntry] = {
    # ── Inventory / lot management ─────────────────────────────────
    "lot_id": HelpEntry(
        help_id="lot_id",
        title_key="help.lot_id.title",
        body_key="help.lot_id.body",
        learn_more="Docs/handbook/lots.md",
        example="inv-2025-001 (one batch of milk)",
    ),
    "batch_syntax": HelpEntry(
        help_id="batch_syntax",
        title_key="help.batch_syntax.title",
        body_key="help.batch_syntax.body",
        example="inv-001: 3, inv-002: 1, salt: 0.5kg",
    ),
    "expiry_date": HelpEntry(
        help_id="expiry_date",
        title_key="help.expiry_date.title",
        body_key="help.expiry_date.body",
    ),
    "storage_location": HelpEntry(
        help_id="storage_location",
        title_key="help.storage_location.title",
        body_key="help.storage_location.body",
    ),

    # ── Scanning ──────────────────────────────────────────────────
    "scene_type": HelpEntry(
        help_id="scene_type",
        title_key="help.scene_type.title",
        body_key="help.scene_type.body",
    ),
    "receipt_confidence": HelpEntry(
        help_id="receipt_confidence",
        title_key="help.receipt_confidence.title",
        body_key="help.receipt_confidence.body",
    ),

    # ── Privacy & sharing ─────────────────────────────────────────
    "community_optin": HelpEntry(
        help_id="community_optin",
        title_key="help.community_optin.title",
        body_key="help.community_optin.body",
        learn_more="Docs/PRIVACY.md",
    ),
    "federation_share": HelpEntry(
        help_id="federation_share",
        title_key="help.federation_share.title",
        body_key="help.federation_share.body",
    ),
    "sms_phone_registry": HelpEntry(
        help_id="sms_phone_registry",
        title_key="help.sms_phone_registry.title",
        body_key="help.sms_phone_registry.body",
    ),
    "voice_memo_retention": HelpEntry(
        help_id="voice_memo_retention",
        title_key="help.voice_memo_retention.title",
        body_key="help.voice_memo_retention.body",
    ),

    # ── Backup / restore ──────────────────────────────────────────
    "backup_format": HelpEntry(
        help_id="backup_format",
        title_key="help.backup_format.title",
        body_key="help.backup_format.body",
    ),
    "backup_restore": HelpEntry(
        help_id="backup_restore",
        title_key="help.backup_restore.title",
        body_key="help.backup_restore.body",
    ),
    "trace_retention": HelpEntry(
        help_id="trace_retention",
        title_key="help.trace_retention.title",
        body_key="help.trace_retention.body",
    ),

    # ── Roles & permissions ───────────────────────────────────────
    "household_role": HelpEntry(
        help_id="household_role",
        title_key="help.household_role.title",
        body_key="help.household_role.body",
    ),
    "actor_id": HelpEntry(
        help_id="actor_id",
        title_key="help.actor_id.title",
        body_key="help.actor_id.body",
    ),

    # ── Recipes / cooking ─────────────────────────────────────────
    "cook_tonight": HelpEntry(
        help_id="cook_tonight",
        title_key="help.cook_tonight.title",
        body_key="help.cook_tonight.body",
    ),

    # ── Search ────────────────────────────────────────────────────
    "global_search": HelpEntry(
        help_id="global_search",
        title_key="help.global_search.title",
        body_key="help.global_search.body",
        example="Press ⌘K or Ctrl+K from anywhere.",
    ),
    "search_syntax": HelpEntry(
        help_id="search_syntax",
        title_key="help.search_syntax.title",
        body_key="help.search_syntax.body",
        example="prefix:milk   type:recipe   household:guest",
    ),
}


# ── Renderer ───────────────────────────────────────────────────────


def render_inline_help(
    help_id: str,
    *,
    locale: str = "en",
    icon: str = "?",
) -> str:
    """Render the inline help HTML for ``help_id``.

    The output is a ``.help-target`` wrapper containing an icon
    and a ``.help-tooltip`` element. Hover/focus reveals the tooltip
    (CSS handles this). Click toggles a persistent popover (JS
    handles this). Returns an empty string for unknown help_id —
    safe to drop into a render pipeline.
    """
    entry = HELP_REGISTRY.get(help_id)
    if entry is None:
        return ""
    title = get_translation(locale, entry.title_key)
    body = get_translation(locale, entry.body_key) or title
    # When the body is identical to the title, suppress the body
    # (the i18n key was likely missing and the fallback returned
    # the title).
    if body == title and "?" not in body and len(body) < 30:
        # Title only; emit a one-liner.
        body = ""
    example_html = (
        f'<div class="help-tooltip-example" '
        f'style="margin-top:4px;padding:2px 6px;background:var(--bg-warm,#FFF1D6);'
        f'border-radius:3px;font-family:ui-monospace,Menlo,monospace;'
        f'font-size:0.75rem;">'
        f'{escape(entry.example)}</div>'
        if entry.example
        else ""
    )
    learn_html = (
        f'<a href="{escape(entry.learn_more)}" target="_blank" '
        f'style="color:var(--accent,#B8623F);font-size:0.75rem;'
        f'display:inline-block;margin-top:4px;">'
        f'Learn more →</a>'
        if entry.learn_more
        else ""
    )
    tip_id = f"help-tip-{help_id}"
    return (
        f'<span class="help-target" tabindex="0" role="button" '
        f'aria-label="Help: {escape(title)}" aria-describedby="{tip_id}">'
        f'<span class="help-target-icon" aria-hidden="true">{escape(icon)}</span>'
        f'<span class="help-tooltip" id="{tip_id}" role="tooltip">'
        f'<strong>{escape(title)}</strong>'
        f'{f"<span>{escape(body)}</span>" if body else ""}'
        f'{example_html}'
        f'{learn_html}'
        f'</span>'
        f'</span>'
    )


def render_help_for(
    field_label: str,
    help_id: str,
    *,
    locale: str = "en",
) -> str:
    """Render ``<label> + inline help icon`` for a form field.

    Convenience for fields that pair a label and a help icon on the
    same row. ``field_label`` is the visible label text.
    """
    return (
        f'<label style="display:inline-flex;align-items:center;gap:6px;">'
        f'{escape(field_label)}'
        f'{render_inline_help(help_id, locale=locale)}'
        f'</label>'
    )


# ── Static check: flag advanced fields without tooltips ────────────

# Conservative: only flag fields whose visible label contains an obvious
# "advanced" term. We *don't* flag every label — the audit would be too
# noisy. Each substring maps to its expected HELP_REGISTRY key.
_SUBSTRING_TO_HELP_ID: dict[str, str] = {
    "lot id": "lot_id",
    "batch": "batch_syntax",
    "expiry": "expiry_date",
    "scene": "scene_type",
    "community": "community_optin",
    "federation": "federation_share",
    "sms phone": "sms_phone_registry",
    "voice memo retention": "voice_memo_retention",
    "action history retention": "trace_retention",
    "backup format": "backup_format",
    "actor id": "actor_id",
    "household role": "household_role",
    "search syntax": "search_syntax",
}


def tooltips_missing(
    *,
    fields: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Return help-ids for advanced fields that have no entry.

    The defaults cover the "known advanced" fields — any field whose
    label includes one of these words is treated as advanced and
    should have a help entry. The copy audit (see
    ``shopstack.tools.copy_audit``) calls this with the list of
    labels it has extracted from the codebase.

    Args:
        fields: List of ``(label, context)`` tuples. ``label`` is
            the visible label text; ``context`` is a free-form
            location string (e.g. ``"inventory.py:L102"``).

    Returns:
        List of help-ids that are missing from the registry. The
        caller is expected to format this into a human report.
    """
    if fields is None:
        # When called with no fields, return the registry's own
        # completeness: every key has a non-empty title and body.
        missing: list[str] = []
        for help_id, entry in HELP_REGISTRY.items():
            title = get_translation("en", entry.title_key)
            body = get_translation("en", entry.body_key)
            if not title or title.startswith("??"):
                missing.append(f"{help_id}:title")
            if not body or body.startswith("??"):
                missing.append(f"{help_id}:body")
        return missing
    # When called with a fields list, the audit caller wants a list
    # of fields whose labels match advanced_substrings but have no
    # corresponding help entry. We match labels against the
    # registry's known help_ids and flag any field that looks
    # advanced but hasn't been registered.
    missing = []
    for label, context in fields:
        label_lower = label.lower()
        for substring, expected_help_id in _SUBSTRING_TO_HELP_ID.items():
            if substring in label_lower:
                if expected_help_id not in HELP_REGISTRY:
                    missing.append(f"{expected_help_id} (label={label!r} at {context})")
                break
    return missing


# ── Click-toggle script (for long tooltips) ───────────────────────


def render_help_toggle_script() -> str:
    """Return JS that lets users click a help icon to keep the
    tooltip open while they read.

    The CSS already shows tooltips on hover/focus. For long
    descriptions the click-toggle adds a ``data-pinned="true"``
    attribute on the ``.help-target`` so the tooltip stays visible
    even when the user moves their mouse to read it. A second click
    unpins.
    """
    return """
<script data-ss-exec="true">
(function() {
  function pinTooltip(target) {
    if (!target) return;
    var wasPinned = target.getAttribute('data-pinned') === 'true';
    document.querySelectorAll('.help-target[data-pinned="true"]').forEach(function(t){
      t.removeAttribute('data-pinned');
    });
    if (!wasPinned) target.setAttribute('data-pinned', 'true');
  }
  document.addEventListener('click', function(e) {
    var target = e.target.closest && e.target.closest('.help-target');
    if (!target) return;
    e.preventDefault();
    pinTooltip(target);
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.help-target[data-pinned="true"]').forEach(function(t){
        t.removeAttribute('data-pinned');
      });
    }
  });
})();
</script>
"""
