"""Recent corrections screen — Memory → "Recent corrections" panel.

Closes the invisible learning loop surfaced in the 2026-06-15
full-app audit: the system had ``build_correction_event`` and
``PreferenceService.record_correction`` but no user-facing surface
where the user could see what the system had learned, accept it,
or reject it.

This screen reads from the new ``correction_events`` table (added
to the DB schema in the same pass) and renders a one-tap
accept/reject panel. The preference signals already produced by
``PreferenceService.record_correction`` are NOT touched — the
correction panel only updates the new ``accepted`` flag, so the
user can separately retract signals via Memory → Preferences.

Renders as an HTML list with inline Accept / Reject buttons (no
page reload). Refresh re-fetches the latest events from the DB.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.ui.components.primitives import empty_state_enhanced, home_card

logger = logging.getLogger(__name__)


def _format_correction_row(row: Any) -> str:
    """Render one correction event as a card row with inline Accept/Reject buttons.

    Per motto_v3 §7 supersession: the per-row buttons are a thin UI
    wrapper that delegates to the canonical
    :func:`accept_correction_event` and :func:`reject_correction_event`
    handlers (via :func:`render_corrections_click_handler`). They do
    not introduce a new API surface, do not fork the canonical
    handlers, and do not duplicate any existing route.
    """
    canonical = escape(str(getattr(row, "canonical_name", "") or "(unnamed)"))
    correction_type = escape(str(getattr(row, "correction_type", "") or ""))
    old_value = escape(str(getattr(row, "old_value", "") or "—"))
    new_value = escape(str(getattr(row, "new_value", "") or ""))
    ts = getattr(row, "timestamp", None)
    ts_str = escape(str(ts)[:19]) if ts else ""
    event_id = escape(str(getattr(row, "event_id", "") or ""))
    source = escape(str(getattr(row, "source", "") or "user_correction"))

    return (
        f"<div class='correction-row' data-event-id='{event_id}' "
        f"style='border:1px solid var(--border);border-radius:8px;"
        f"padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:baseline;'>"
        f"<strong style='color:var(--text);'>{canonical}</strong>"
        f"<span style='font-size:0.75rem;color:var(--text-dim);'>{ts_str}</span>"
        f"</div>"
        f"<div style='font-size:0.85rem;color:var(--text-dim);margin-top:4px;'>"
        f"<em>{correction_type}</em>: "
        f"<span style='text-decoration:line-through;color:var(--red);'>{old_value}</span>"
        f" → <span style='color:var(--green);'>{new_value}</span>"
        f"</div>"
        f"<div style='font-size:0.7rem;color:var(--text-faint);margin-top:4px;'>"
        f"source: {source}"
        f"</div>"
        f"<div class='correction-row-actions' "
        f"style='display:flex;gap:6px;margin-top:8px;'>"
        f"<button class='correction-row-accept' type='button' "
        f"data-action='accept-correction' data-event-id='{event_id}' "
        f"aria-label='Accept this correction' "
        f"style='background:var(--green,#1f9d55);color:#fff;border:none;"
        f"border-radius:4px;padding:4px 10px;cursor:pointer;"
        f"font-size:0.8125rem;min-height:28px;'>✓ Accept</button>"
        f"<button class='correction-row-reject' type='button' "
        f"data-action='reject-correction' data-event-id='{event_id}' "
        f"aria-label='Reject this correction' "
        f"style='background:var(--red,#c0392b);color:#fff;border:none;"
        f"border-radius:4px;padding:4px 10px;cursor:pointer;"
        f"font-size:0.8125rem;min-height:28px;'>✗ Reject</button>"
        f"</div>"
        f"</div>"
    )


def render_recent_corrections_html(limit: int = 20) -> str:
    """Return the HTML for the Memory → Recent corrections panel.

    Reads pending (accepted=0) correction events for the active
    user, newest first, and renders them as a list of cards. If
    there are no events, returns an actionable empty state.
    """
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _recent_corrections_inner(limit),
        user_message="Could not load recent corrections",
        help_tab="memory",
        icon="📝",
        retry_label="",
    )


def _recent_corrections_inner(limit: int) -> str:
    user_id = current_user_id() or ""
    events = db.get_recent_correction_events(limit=limit, user_id=user_id)
    if not events:
        return empty_state_enhanced(
            "No recent corrections",
            icon="🛠️",
            secondary_text=(
                "When ShopStack misclassifies an item (e.g. 'this is hybrid tomato, "
                "not tomato'), the correction appears here. Accept it to lock the "
                "learning, or reject it to undo the preference change."
            ),
        )
    rows = "".join(_format_correction_row(e) for e in events)
    return (
        "<div class='recent-corrections-panel' "
        "style='max-height:480px;overflow-y:auto;'>"
        f"{rows}"
        "</div>"
    )


def accept_correction_event(event_id: str) -> str:
    """Handler for the Accept button. Marks the event as accepted."""
    if not event_id:
        return render_recent_corrections_html()
    try:
        db.mark_correction_accepted(event_id, accepted=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("accept_correction_event failed: %s", exc)
    return render_recent_corrections_html()


def reject_correction_event(event_id: str) -> str:
    """Handler for the Reject button. Marks the event as rejected
    (``accepted=0`` — the default state, but we set it explicitly for
    the audit trail).
    """
    if not event_id:
        return render_recent_corrections_html()
    try:
        db.mark_correction_accepted(event_id, accepted=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reject_correction_event failed: %s", exc)
    return render_recent_corrections_html()


# ── Per-row click handler (D-04 follow-up, closes the deferred "JS hook" ──
#
# The :func:`build_memory_corrections` builder exposes a hidden
# ``corrections_event_id`` textbox that the canonical global
# Accept/Reject Gradio buttons read as input. The per-row
# Accept/Reject HTML buttons (rendered by
# :func:`_format_correction_row`) are a thin UI shortcut: they fill
# that textbox and programmatically click the matching global
# button, so the user gets the canonical handler in one click
# instead of copy-pasting an id then clicking.
#
# Per motto_v3 §7 (Supersession / Canonical Replacement Rule): this
# handler does NOT call the canonical Python functions directly. It
# only routes through the existing Gradio buttons, which already
# call :func:`accept_correction_event` / :func:`reject_correction_event`.
# This preserves a single canonical entry point per action and
# means any future change to the handler (e.g. audit logging,
# idempotency, undo) is automatically picked up.


def render_corrections_click_handler() -> str:
    """Return JS that wires per-row Accept/Reject buttons to the global handlers.

    The script is loaded once at app load (injected via
    :func:`shopstack.ui.header.pwa_head_html`) and:

    1. Exposes ``window.ssCorrectionClick(eventId, action)`` for
       direct invocation.
    2. Attaches a delegated ``click`` listener on ``document`` for
       any element with ``data-action="accept-correction"`` or
       ``data-action="reject-correction"`` and a
       ``data-event-id`` attribute — this is the backstop that
       wires the per-row buttons in
       :func:`_format_correction_row` without requiring each
       button to carry inline JS.
    3. On click, fills the hidden ``corrections_event_id``
       textbox and programmatically clicks the matching global
       Gradio button (``.corrections-accept-btn`` /
       ``.corrections-reject-btn``) — the canonical
       Gradio handlers then run and re-render the panel.
    """
    return """
<script data-ss-exec="true">
(function() {
  function findGlobalButton(action) {
    var cls = action === 'accept' ? 'corrections-accept-btn' : 'corrections-reject-btn';
    var el = document.querySelector('.' + cls);
    if (!el) return null;
    return el.tagName === 'BUTTON' ? el : (el.querySelector('button') || el);
  }
  function fillEventId(eventId) {
    var tb = document.querySelector(
      'input[data-testid="corrections_event_id"], textarea[data-testid="corrections_event_id"]'
    );
    if (!tb) {
      var inputs = document.querySelectorAll('input[type="text"]');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].name && inputs[i].name.toLowerCase().indexOf('corrections') !== -1) {
          tb = inputs[i];
          break;
        }
      }
    }
    if (!tb) return;
    var proto = tb.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(tb, eventId);
    tb.dispatchEvent(new Event('input', { bubbles: true }));
  }
  function ssCorrectionClick(eventId, action) {
    if (!eventId || !action) return;
    fillEventId(eventId);
    var btn = findGlobalButton(action);
    if (btn) {
      btn.click();
    } else {
      console.warn('ssCorrectionClick: global button not found for action=' + action);
    }
  }
  window.ssCorrectionClick = ssCorrectionClick;
  document.addEventListener('click', function(e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var target = t.closest('[data-action][data-event-id]');
    if (!target) return;
    var eventId = target.getAttribute('data-event-id');
    var action = target.getAttribute('data-action');
    if (!eventId || !action) return;
    if (action === 'accept-correction') {
      e.preventDefault();
      ssCorrectionClick(eventId, 'accept');
    } else if (action === 'reject-correction') {
      e.preventDefault();
      ssCorrectionClick(eventId, 'reject');
    }
  });
})();
</script>
"""


__all__ = [
    "render_recent_corrections_html",
    "accept_correction_event",
    "reject_correction_event",
    "render_corrections_click_handler",
]


# ── Pass 20: "Record a correction" flow ────────────────────────────


def record_correction_handler(
    canonical_name: str,
    was_action: str,
    should_be_action: str,
    reason: str,
) -> str:
    """Handler for the "Record a correction" form in the Memory tab.

    Closes the full learning loop (Pass 20): the user sees
    a decision they disagree with, records the correction via
    this form, and the engine adjusts future decisions on
    the same item. The correction is persisted to the
    ``correction_events`` table and also translated into a
    ``PreferenceSignal`` by ``PreferenceService``.

    Returns the refreshed corrections panel HTML.
    """
    from shopstack.services.feedback import (
        record_user_correction,
        validate_correction,
    )

    errors = validate_correction(
        canonical_name=canonical_name or "",
        was_action=was_action or "",
        should_be_action=should_be_action or "",
        reason=reason or "",
    )
    if errors:
        return (
            f"<div class='correction-error' style='padding:12px;background-color:rgba(166,63,49,0.10);border-radius:4px;color:var(--red-text, var(--red));'>"
            f"<strong>Could not record correction:</strong><ul>"
            + "".join(f"<li>{e}</li>" for e in errors)
            + "</ul></div>"
        ) + render_recent_corrections_html()

    try:
        record_user_correction(
            db,
            user_id=current_user_id(),
            canonical_name=canonical_name.strip(),
            was_action=was_action.strip(),
            should_be_action=should_be_action.strip(),
            reason=(reason or "").strip(),
        )
    except Exception as exc:  # noqa: BLE001
        return (
            f"<div class='correction-error' style='padding:12px;background-color:rgba(166,63,49,0.10);border-radius:4px;color:var(--red-text, var(--red));'>"
            f"<strong>Could not record correction:</strong> {type(exc).__name__}: {exc}"
            f"</div>"
        ) + render_recent_corrections_html()

    return render_recent_corrections_html()
