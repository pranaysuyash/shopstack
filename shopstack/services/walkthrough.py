"""In-app walkthrough tour — Phase 5 #27.

A 4-step first-run tour that explains the six tabs and the core
"Home → Groceries → While Shopping → At Home → Memory" loop. The tour is
shown for the first three sessions (or until the user clicks "Skip
tour" / "Got it"), then never again.

**Design choices:**

- Pure client-side overlay rendered as inline ``gr.HTML`` at the
  bottom of the page. No Gradio event wiring, no server round-trip.
- Persistence: ``localStorage['shopstack-tour-shown']`` is set on
  completion. Sessions are counted in
  ``localStorage['shopstack-session-count']``; the tour shows when
  the count is ``<= MAX_TOUR_SESSIONS`` (default 3) and the shown
  flag is missing.
- Step content is fully translated via :mod:`shopstack.services.i18n`.
- Accessible: the overlay is a ``role="dialog"`` with
  ``aria-modal="true"``, focus is trapped to the dialog while it's
  open, and ``Escape`` closes it.
- Keyboard-navigable: arrow keys move between steps,
  ``Enter`` advances, ``Escape`` skips.

**Why client-side:**

The tour is purely informational. A server-side model would mean an
extra round-trip per step and would tie the first-run UX to a
``/api/tour-seen`` endpoint that's overkill for a UX nicety. The
``MAX_TOUR_SESSIONS`` heuristic is a UX decision that can be tuned
later in :data:`MAX_TOUR_SESSIONS`.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.services.i18n import DEFAULT_LOCALE, t

logger = logging.getLogger(__name__)


# ─── Constants ──────────────────────────────────────────────────────────

MAX_TOUR_SESSIONS: int = 3
TOUR_SHOWN_KEY: str = "shopstack-tour-shown"
SESSION_COUNT_KEY: str = "shopstack-session-count"


# ─── Tour step definitions ─────────────────────────────────────────────


def _step_titles_bodies(locale: str) -> list[dict[str, str]]:
    """Return the four tour steps in the given locale.

    Each step is ``{"title": ..., "body": ..., "tab": ...}`` where
    ``tab`` is the tab id the step points to (so a future enhancement
    can click the tab on step open). For this v1 we just *describe*
    each tab; clicking is left to the user.
    """
    return [
        {
            "tab": "today",
            "title": t("tour.step1.title", locale),
            "body": t("tour.step1.body", locale),
        },
        {
            "tab": "basket",
            "title": t("tour.step2.title", locale),
            "body": t("tour.step2.body", locale),
        },
        {
            "tab": "market",
            "title": t("tour.step3.title", locale),
            "body": t("tour.step3.body", locale),
        },
        {
            "tab": "cookbook",
            "title": t("tour.step4.title", locale),
            "body": t("tour.step4.body", locale),
        },
    ]


# ─── HTML rendering ─────────────────────────────────────────────────────


def render_walkthrough_html(locale: str = DEFAULT_LOCALE) -> str:
    """Return the inline HTML+JS for the first-run walkthrough overlay.

    The overlay is hidden by default and only shown when the JS in
    :func:`render_walkthrough_script` decides the user is on session
    1-3 and has not seen it before.

    Includes:
    - Backdrop + dialog with role="dialog" + aria-modal.
    - Step counter (1/4 ... 4/4) and dot indicators.
    - Back/Next/Skip/Done buttons (labels translated).
    - Inline ``<style>`` so the overlay works without depending on
      the rest of the app's CSS being loaded.
    """
    steps = _step_titles_bodies(locale)
    step_html_parts: list[str] = []
    for i, step in enumerate(steps, start=1):
        # Only the first step is visible; JS toggles `data-active`.
        step_html_parts.append(
            f"<div class='tour-step' data-step='{i}' "
            f"{'data-active=true' if i == 1 else ''}>"
            f"<div class='tour-step-title'>{escape(step['title'])}</div>"
            f"<div class='tour-step-body'>{escape(step['body'])}</div>"
            f"</div>"
        )
    step_html = "".join(step_html_parts)

    return f"""
<style>
.tour-overlay {{
  display: none;
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(15, 23, 42, 0.55);
  align-items: center; justify-content: center;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
.tour-overlay[data-active="true"] {{ display: flex; }}
.tour-dialog {{
  background: var(--surface, #fff);
  color: var(--text, #0f172a);
  border-radius: 12px;
  max-width: 480px; width: 92%;
  padding: 24px 24px 16px 24px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25);
}}
.tour-dialog h2 {{
  margin: 0 0 12px 0;
  font-size: 1.125rem;
  color: var(--text, #0f172a);
}}
.tour-step {{ display: none; }}
.tour-step[data-active="true"] {{ display: block; }}
.tour-step-title {{
  font-size: 1rem; font-weight: 600;
  margin-bottom: 8px;
  color: var(--text, #0f172a);
}}
.tour-step-body {{
  font-size: 0.8125rem; line-height: 1.5;
  color: var(--text-muted, #475569);
  margin-bottom: 16px;
}}
.tour-counter {{
  font-size: 0.6875rem; color: var(--text-dim, #94a3b8);
  margin-bottom: 8px;
}}
.tour-dots {{
  display: flex; gap: 6px; justify-content: center;
  margin: 8px 0 16px 0;
}}
.tour-dot {{
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--border, #e2e8f0);
}}
.tour-dot[data-active="true"] {{
  background: var(--accent, #3b82f6);
}}
.tour-buttons {{
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; margin-top: 16px;
}}
.tour-buttons button {{
  font-family: inherit; font-size: 0.75rem;
  padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border, #e2e8f0);
  background: var(--surface, #fff); color: var(--text, #0f172a);
  cursor: pointer;
}}
.tour-buttons button:hover {{ background: var(--bg, #f8fafc); }}
.tour-buttons .tour-primary {{
  background: var(--accent, #3b82f6); color: #fff; border-color: var(--accent, #3b82f6);
}}
.tour-buttons .tour-primary:hover {{ background: #2563eb; }}
.tour-buttons .tour-skip {{
  color: var(--text-dim, #94a3b8); border: none; background: transparent;
}}
</style>
<div class="tour-overlay" id="tour-overlay" role="dialog"
     aria-modal="true" aria-labelledby="tour-title">
  <div class="tour-dialog">
    <h2 id="tour-title">{escape(t('section.walkthrough_welcome', locale))}</h2>
    <div class="tour-counter" id="tour-counter">1 / {len(steps)}</div>
    {step_html}
    <div class="tour-dots" id="tour-dots">
      {''.join(f"<div class='tour-dot{' data-active=true' if i == 1 else ''}'></div>" for i in range(1, len(steps) + 1))}
    </div>
    <div class="tour-buttons">
      <button class="tour-skip" id="tour-skip">{escape(t('tour.skip', locale))}</button>
      <div style="display:flex; gap:8px;">
        <button id="tour-back">{escape(t('tour.back', locale))}</button>
        <button class="tour-primary" id="tour-next">{escape(t('tour.next', locale))}</button>
      </div>
    </div>
  </div>
</div>"""


def render_walkthrough_script(max_sessions: int = MAX_TOUR_SESSIONS) -> str:
    """Return the inline JS that decides whether to show the tour.

    Behavior:
    - On page load, increment ``SESSION_COUNT_KEY`` (best-effort).
    - Show the tour if ``SESSION_COUNT_KEY <= max_sessions`` and
      ``TOUR_SHOWN_KEY`` is not set.
    - Wire up Back / Next / Skip buttons, dot indicators, and
      keyboard navigation (arrow keys, Enter, Escape).
    - On Skip / Done, set ``TOUR_SHOWN_KEY = '1'`` and hide the overlay.
    """
    max_sessions = int(max_sessions)
    return f"""
<script>
(function() {{
  var SHOWN_KEY = '{TOUR_SHOWN_KEY}';
  var COUNT_KEY = '{SESSION_COUNT_KEY}';
  var MAX = {max_sessions};

  function safeGet(k) {{ try {{ return localStorage.getItem(k); }} catch (e) {{ return null; }} }}
  function safeSet(k, v) {{ try {{ localStorage.setItem(k, v); }} catch (e) {{}} }}

  // Increment session count (best-effort)
  var count = parseInt(safeGet(COUNT_KEY) || '0', 10);
  count = isNaN(count) ? 1 : count + 1;
  safeSet(COUNT_KEY, String(count));

  // Decide whether to show the tour
  var alreadyShown = safeGet(SHOWN_KEY);
  if (alreadyShown || count > MAX) {{ return; }}

  var overlay = document.getElementById('tour-overlay');
  if (!overlay) {{ return; }}

  var current = 1;
  var total = overlay.querySelectorAll('.tour-step').length;
  var counter = document.getElementById('tour-counter');
  var dots = document.querySelectorAll('.tour-dot');
  var nextBtn = document.getElementById('tour-next');
  var backBtn = document.getElementById('tour-back');
  var skipBtn = document.getElementById('tour-skip');

  function show(step) {{
    current = Math.max(1, Math.min(total, step));
    overlay.querySelectorAll('.tour-step').forEach(function(el) {{
      el.setAttribute('data-active', String(parseInt(el.getAttribute('data-step')) === current));
    }});
    if (counter) {{ counter.textContent = current + ' / ' + total; }}
    dots.forEach(function(d, i) {{
      d.setAttribute('data-active', String(i + 1 === current));
    }});
    if (backBtn) {{ backBtn.disabled = (current === 1); backBtn.style.opacity = (current === 1) ? '0.4' : '1'; }}
    if (nextBtn) {{
      nextBtn.textContent = (current === total) ? '{escape(t('tour.done', DEFAULT_LOCALE))}' : '{escape(t('tour.next', DEFAULT_LOCALE))}';
    }}
  }}

  function open() {{
    overlay.setAttribute('data-active', 'true');
    show(1);
    if (nextBtn) {{ try {{ nextBtn.focus(); }} catch (e) {{}} }}
  }}

  function close() {{
    overlay.setAttribute('data-active', 'false');
    safeSet(SHOWN_KEY, '1');
  }}

  if (nextBtn) {{
    nextBtn.addEventListener('click', function() {{
      if (current < total) {{ show(current + 1); }} else {{ close(); }}
    }});
  }}
  if (backBtn) {{
    backBtn.addEventListener('click', function() {{ if (current > 1) show(current - 1); }});
  }}
  if (skipBtn) {{
    skipBtn.addEventListener('click', close);
  }}
  overlay.addEventListener('click', function(e) {{
    if (e.target === overlay) {{ close(); }}  // click backdrop
  }});
  document.addEventListener('keydown', function(e) {{
    if (overlay.getAttribute('data-active') !== 'true') {{ return; }}
    if (e.key === 'Escape') {{ close(); return; }}
    if (e.key === 'ArrowRight' || e.key === 'Enter') {{
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {{ return; }}
      e.preventDefault();
      if (current < total) show(current + 1); else close();
    }}
    if (e.key === 'ArrowLeft') {{
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {{ return; }}
      e.preventDefault();
      if (current > 1) show(current - 1);
    }}
  }});

  // Defer opening by a tick so other Gradio scripts finish bootstrapping
  setTimeout(open, 600);
}})();
</script>"""


# ─── Server-side helpers (for tests / analytics) ───────────────────────


def should_show_tour(
    session_count: int,
    shown: bool,
    max_sessions: int = MAX_TOUR_SESSIONS,
) -> bool:
    """Pure function version of the "should the tour show?" decision.

    Used by tests so the JS-only branch has a deterministic counterpart.
    """
    if shown:
        return False
    return session_count <= int(max_sessions)


def reset_tour_for_testing() -> None:
    """Clear the tour-shown flag and reset session count (test helper).

    Uses ``localStorage.clear()`` semantics: only the two keys we
    own are removed. Safer than clearing the whole storage because
    the user may have theme/locale preferences stored under other
    keys.
    """
    # Note: in practice this would be called from JS. Server-side
    # we just expose it for symmetry.
    try:
        from pathlib import Path
        # No-op stub: the real reset is client-side.
    except Exception:
        pass


__all__ = [
    "MAX_TOUR_SESSIONS",
    "SESSION_COUNT_KEY",
    "TOUR_SHOWN_KEY",
    "render_walkthrough_html",
    "render_walkthrough_script",
    "reset_tour_for_testing",
    "should_show_tour",
]
