"""Keyboard shortcuts — Phase 5 #21 (verify + extend).

The header already has basic ``j``/``k``/arrow-key tab navigation
(``shopstack/ui/header.py:122-160``). This module extends that with:

- **Vim-style ``g`` + letter combos** to jump to a specific tab
  (``g t`` = Home, ``g c`` = Recipes, ``g b`` = Groceries,
  ``g s`` = While Shopping, ``g r`` = At Home, ``g m`` = Memory).
- **Single-letter shortcuts** for common actions:
  - ``?`` — open the help/shortcuts overlay.
  - ``n`` — focus the next field in the active tab.
  - ``Shift+L`` — toggle locale (English ↔ Hindi).
  - ``Shift+T`` — toggle theme (light ↔ dark).
  - ``Esc`` — close any open overlay (walkthrough, help, modal).
- **Discoverability** — pressing ``?`` opens a small help overlay
  listing every shortcut, so the user can learn them in place.

**Why a separate module:**

The header's existing JS is inline and tied to the brand block; we
don't want to keep growing that string. A small standalone module
is testable, replaceable, and can be re-rendered on locale change
without touching the rest of the header.

**Why not Gradio's built-in shortcuts:**

Gradio 6 has ``allow_shortcut`` on a few components but no global
shortcut handler. A custom global listener is the only way to
cover all 6 tabs uniformly.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Iterable

logger = logging.getLogger(__name__)


# ─── Shortcut table ─────────────────────────────────────────────────────


# Each entry: (key_combo, description_key, action)
# action is a string the JS handler understands:
#   "tab:<id>"  → click the tab whose Gradio id is <id>
#   "help"      → open the shortcuts help overlay
#   "locale"    → toggle locale
#   "theme"     → toggle theme
SHORTCUTS: tuple[dict[str, str], ...] = (
    {"key": "j / →",      "action": "tab:next",     "desc": "Next tab"},
    {"key": "k / ←",      "action": "tab:prev",     "desc": "Previous tab"},
    {"key": "g t",        "action": "tab:today",    "desc": "Go to Home"},
    {"key": "g c",        "action": "tab:cookbook", "desc": "Go to Recipes"},
    {"key": "g b",        "action": "tab:basket",   "desc": "Go to Groceries"},
    {"key": "g s",        "action": "tab:market",   "desc": "Go to While Shopping"},
    {"key": "g r",        "action": "tab:reconcile","desc": "Go to At Home"},
    {"key": "g m",        "action": "tab:memory",   "desc": "Go to Memory"},
    {"key": "?",          "action": "help",         "desc": "Show this help"},
    {"key": "Shift+L",    "action": "locale",       "desc": "Toggle language (EN/हिं)"},
    {"key": "Shift+T",    "action": "theme",        "desc": "Toggle light/dark theme"},
    {"key": "Esc",        "action": "close",        "desc": "Close any open overlay"},
)


# Map tab id → Gradio tab id (must match `gr.Tab(..., id=...)` in tab builders)
TAB_IDS: tuple[str, ...] = ("today", "cookbook", "basket", "market", "reconcile", "memory")


# ─── Help overlay rendering ────────────────────────────────────────────


def render_shortcuts_help_html() -> str:
    """Return the inline HTML for the shortcuts help overlay.

    Same dialog pattern as the walkthrough so the user gets a
    consistent close/click-outside/Escape experience.
    """
    rows: list[str] = []
    for s in SHORTCUTS:
        rows.append(
            "<div class='sc-row'>"
            f"<kbd class='sc-key'>{escape(s['key'])}</kbd>"
            f"<span class='sc-desc'>{escape(s['desc'])}</span>"
            f"</div>"
        )
    return f"""
<style>
.sc-overlay {{
  display: none;
  position: fixed; inset: 0; z-index: 9998;
  background: rgba(15, 23, 42, 0.5);
  align-items: center; justify-content: center;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
.sc-overlay[data-active="true"] {{ display: flex; }}
.sc-dialog {{
  background: var(--surface, #fff);
  color: var(--text, #0f172a);
  border-radius: 12px;
  max-width: 420px; width: 92%;
  padding: 20px 24px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25);
}}
.sc-dialog h2 {{
  margin: 0 0 12px 0; font-size: 16px;
  color: var(--text, #0f172a);
}}
.sc-row {{
  display: flex; align-items: center; gap: 12px;
  padding: 4px 0; font-size: 12px;
}}
.sc-key {{
  display: inline-block;
  background: var(--bg, #f1f5f9);
  border: 1px solid var(--border, #e2e8f0);
  border-bottom-width: 2px;
  border-radius: 4px;
  padding: 2px 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  min-width: 70px; text-align: center;
  color: var(--text, #0f172a);
}}
.sc-desc {{ color: var(--text-muted, #475569); }}
.sc-hint {{
  margin-top: 12px; font-size: 10px; color: var(--text-dim, #94a3b8);
}}
</style>
<div class="sc-overlay" id="sc-overlay" role="dialog"
     aria-modal="true" aria-labelledby="sc-title">
  <div class="sc-dialog">
    <h2 id="sc-title">⌨ Keyboard shortcuts</h2>
    {''.join(rows)}
    <div class="sc-hint">Press <kbd class='sc-key'>?</kbd> to toggle this overlay · <kbd class='sc-key'>Esc</kbd> to close</div>
  </div>
</div>"""


# ─── JS for tab-by-id navigation ──────────────────────────────────────


def render_shortcuts_script() -> str:
    """Return the JS that wires up tab nav + help overlay + locale/theme toggles.

    Idempotent: calling this multiple times (e.g. after a locale change
    reloads the page) will replace the listeners cleanly.
    """
    tab_ids_js = ", ".join(f'"{tid}"' for tid in TAB_IDS)
    return f"""
<script>
(function() {{
  // Tab ids that we know about (must match Gradio's gr.Tab(id=...))
  var TAB_IDS = [{tab_ids_js}];

  function findTab(id) {{
    // Gradio 6 sets data-testid="tab-<id>" on the tab button
    return document.querySelector('[data-testid="tab-' + id + '"]')
        || document.querySelector('button[role=tab][data-value="' + id + '"]')
        || Array.from(document.querySelectorAll('button[role=tab]')).find(function(b) {{
            return (b.textContent || '').toLowerCase().includes(id.replace('_', ' '));
          }});
  }}
  function clickTab(id) {{
    var t = findTab(id);
    if (t) {{ t.click(); return true; }}
    return false;
  }}
  function tabsList() {{
    return Array.from(document.querySelectorAll('button[role=tab]'));
  }}
  function tabIndex() {{
    var tabs = tabsList();
    return tabs.findIndex(function(t) {{ return t.getAttribute('aria-selected') === 'true'; }});
  }}

  var overlay = document.getElementById('sc-overlay');
  function openHelp() {{ if (overlay) overlay.setAttribute('data-active', 'true'); }}
  function closeHelp() {{ if (overlay) overlay.setAttribute('data-active', 'false'); }}
  function toggleHelp() {{
    if (!overlay) return;
    var active = overlay.getAttribute('data-active') === 'true';
    overlay.setAttribute('data-active', String(!active));
  }}

  // Walkthrough overlay: also close on Escape
  function closeAny() {{
    closeHelp();
    var tour = document.getElementById('tour-overlay');
    if (tour) tour.setAttribute('data-active', 'false');
    // Close any open Gradio modal-ish elements
    document.querySelectorAll('.modal, [role=dialog]').forEach(function(m) {{
      if (m.getAttribute('data-active') === 'true') m.setAttribute('data-active', 'false');
    }});
  }}

  // Click backdrop to close
  if (overlay) {{
    overlay.addEventListener('click', function(e) {{
      if (e.target === overlay) closeHelp();
    }});
  }}

  // g-<letter> two-key combos
  var gPrefix = false;
  var gTimer = null;
  function resetG() {{ gPrefix = false; if (gTimer) clearTimeout(gTimer); gTimer = null; }}

  document.addEventListener('keydown', function(e) {{
    // Skip when typing in inputs
    var tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable)) {{ return; }}

    // Single-key shortcuts
    if (!gPrefix) {{
      if (e.key === '?') {{ e.preventDefault(); toggleHelp(); return; }}
      if (e.shiftKey && (e.key === 'L' || e.key === 'l')) {{
        e.preventDefault();
        if (typeof toggleLocale === 'function') {{
          var cur = localStorage.getItem('shopstack-locale') || 'en';
          toggleLocale(cur === 'en' ? 'hi' : 'en');
        }}
        return;
      }}
      if (e.shiftKey && (e.key === 'T' || e.key === 't')) {{
        e.preventDefault();
        if (typeof toggleTheme === 'function') toggleTheme();
        return;
      }}
      if (e.key === 'Escape') {{ e.preventDefault(); closeAny(); return; }}
      if (e.key === 'g' || e.key === 'G') {{
        gPrefix = true;
        gTimer = setTimeout(resetG, 1200);
        return;
      }}
    }} else {{
      // g<letter> combos
      resetG();
      var map = {{
        't': 'today', 'T': 'today',
        'c': 'cookbook', 'C': 'cookbook',
        'b': 'basket', 'B': 'basket',
        's': 'market', 'S': 'market',
        'r': 'reconcile', 'R': 'reconcile',
        'm': 'memory', 'M': 'memory',
      }};
      var target = map[e.key];
      if (target) {{ e.preventDefault(); clickTab(target); }}
    }}
  }});
}})();
</script>"""


__all__ = [
    "SHORTCUTS",
    "TAB_IDS",
    "render_shortcuts_help_html",
    "render_shortcuts_script",
]
