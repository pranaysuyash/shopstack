"""Header state and rendering for the Gradio app.

The Gradio app's header has three pieces of dynamic state:

1. **Runtime label** — "Local mock mode" / "Local runtime" / "Cloud runtime"
   / "Off-grid mock mode" depending on which providers are loaded.
2. **Model download status** — shows a pending-download hint if the
   configured MLX planner model isn't cached locally.
3. **Theme + keyboard shortcuts** — inline JavaScript for the dark/light
   theme toggle (persisted in localStorage) and `j`/`k` / arrow-key tab
   navigation. Extended in Phase 5 with g<letter> tab jumps, the
   `?` help overlay, and the `Shift+L` / `Shift+T` locale+theme toggles.
4. **Language selector** (Phase 5 #9) — EN/हिं buttons in the header
   that write the new locale to localStorage and reload the page.
5. **Walkthrough overlay** (Phase 5 #27) — first-run 4-step tour that
   shows on sessions 1-3 unless skipped.

This module extracts these from the inline `app.py` header so that:
- The state computation is testable in isolation.
- The header rendering is local to one module.
- Future theme/layout work has a clear home.
"""
from __future__ import annotations

import os
from html import escape
from pathlib import Path

from shopstack.app_context import providers
from shopstack.config import settings
from shopstack.services.i18n import (
    DEFAULT_LOCALE,
    render_language_script,
    render_language_selector_html,
)
from shopstack.services.shortcuts import (
    render_shortcuts_help_html,
    render_shortcuts_script,
)
from shopstack.services.tooltips import render_help_toggle_script
from shopstack.services.global_search import (
    render_palette_html,
    render_palette_script,
)
from shopstack.services.undo_ledger import render_undo_click_handler
from shopstack.services.walkthrough import (
    render_walkthrough_html,
    render_walkthrough_script,
)


# ── Runtime label ──────────────────────────────────────────────────────

def runtime_label() -> str:
    """Return a human-readable label describing the current provider runtime.

    - "Cloud runtime" — a real OpenAI/HuggingFace/Whisper provider is loaded.
    - "Local runtime" — a real local provider (MLX, llama.cpp) is loaded.
    - "Off-grid mock mode" — off-the-grid policy blocked all real providers.
    - "Local mock mode" — all providers are mock (default).

    Falls back to "Local runtime" on any error.
    """
    try:
        runtime = providers.get_runtime_diagnostics()
        loaded_real = [
            r for r in runtime.providers
            if getattr(r, "loaded", False) and getattr(r, "backend", "") != "mock"
        ]
        blocked = [r for r in runtime.providers if getattr(r, "blocked_by_off_grid", False)]
        if loaded_real and any(
            getattr(r, "backend", "") in {"openai", "huggingface", "whisper"}
            for r in loaded_real
        ):
            return "Cloud runtime"
        if loaded_real:
            return "Local runtime"
        if blocked:
            return "Off-grid mock mode"
        return "Local mock mode"
    except Exception:
        return "Local runtime"


# ── Model download status ───────────────────────────────────────────

def model_download_status() -> str:
    """Return an HTML snippet if the configured MLX planner model is uncached.

    The snippet is shown as a hint above the app title; an empty string
    means the model is already cached (no hint needed).

    The check is best-effort: any exception (e.g. read-permission errors)
    returns an empty string rather than crashing the app.
    """
    try:
        mlx_model = settings.local_mlx_model
        if not mlx_model:
            return ""

        # Check HF hub cache
        hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
        hf_cache = Path(hf_home) / "hub"
        model_dir_name = "models--" + mlx_model.replace("/", "--")
        model_cache_dir = hf_cache / model_dir_name

        if model_cache_dir.is_dir():
            snapshots_dir = model_cache_dir / "snapshots"
            if snapshots_dir.is_dir():
                for snap in snapshots_dir.iterdir():
                    if snap.is_dir() and any(
                        f.suffix in (".safetensors", ".gguf")
                        for f in snap.iterdir()
                    ):
                        return ""
            return ""

        return (
            "<div style='font-size: 0.6875rem;color:var(--amber);margin-top:4px;'>"
            f"<span>\u23F3 {mlx_model.split('/')[-1]} download pending (first query triggers it)</span>"
            "</div>"
        )
    except Exception:
        return ""


# ── Header HTML + JS ──────────────────────────────────────────────────

def header_html(brand_title: str, brand_subtitle: str, current_locale: str = DEFAULT_LOCALE) -> str:
    """Return the inline HTML for the app header.

    The header includes:
    - Brand title and subtitle
    - Active household indicator (added 2026-06-13): a small badge
      showing the current household's display name. Helps users
      notice when they're in a different household than they think.
    - Theme toggle button (calls `toggleTheme()` defined in `header_script()`)
    - Language selector (Phase 5 #9): EN/हिं buttons that switch the UI
      language via the `setLocale()` JS helper.
    """
    locale_html = render_language_selector_html(current_locale)
    household_html = household_indicator_html()
    return f"""
<!-- WCAG 2.4.1 Bypass Blocks — skip-to-content link (first focusable element) -->
<a class=\"skip-link\" href=\"#main-content\">Skip to content</a>
<!-- WCAG 4.1.3 Status Messages — live region for dynamic content announcements -->
<div id=\"ss-live-region\" class=\"sr-only-live\" aria-live=\"polite\" aria-atomic=\"true\"></div>
<div class=\"app-header">
  <div>
    <h1 class=\"brand-title\">{escape(brand_title)}</h1>
    <div class=\"brand-subtitle\">{escape(brand_subtitle)}</div>
  </div>
  <div style=\"display:flex;gap:8px;align-items:center;flex-wrap:wrap;\">
    {household_html}
    {locale_html}
    <button onclick="toggleTheme()" aria-label="Toggle light/dark theme" title="Toggle theme" style="background:none;border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 14px;cursor:pointer;font-size: 0.875rem;color:var(--text-muted);min-height:44px;min-width:44px;">🌓</button>
  </div>
</div>"""


def household_indicator_html() -> str:
    """Return a small badge showing the active household's display name.

    Added 2026-06-13 to surface the household context that's otherwise
    buried in the workspace admin accordion. The badge shows the
    *display name* (e.g., "My Home") not the slug (e.g., "default_household").

    Behavior:
    - Looks up the active household via ``list_households()``.
    - Falls back to the household_id if no display name is registered.
    - Returns an empty string if no active household can be resolved
      (defensive: never breaks the page render).
    - Safe to call at import time (no side effects).
    """
    try:
        from shopstack.app_context import current_user_id, list_households
        active_id = current_user_id() or ""
        if not active_id:
            return ""
        # Find the display name for the active household.
        display_name = active_id
        for h in list_households():
            if h.get("household_id") == active_id:
                display_name = h.get("name") or active_id
                break
        return (
            f"<span class=\"hh-indicator\" "
            f"aria-label=\"Active household: {escape(display_name)}\" "
            f"title=\"Active household: {escape(display_name)}\" "
            f"style=\"display:inline-flex;align-items:center;gap:6px;"
            f"padding:6px 10px;border-radius:var(--radius-sm);background:var(--bg-card);border:1px solid var(--border);"
            f"font-size: 0.75rem;color:var(--text-muted);min-height:32px;\">"
            f"🏠&nbsp;{escape(display_name)}</span>"
        )
    except Exception:
        # Never let a household-resolution failure break the page.
        return ""


def header_script() -> str:
    """Return the inline JavaScript for theme persistence + keyboard shortcuts.

    Behavior:
    - On load: read `shopstack-theme` from localStorage and apply.
    - `toggleTheme()`: flip between light/dark and persist to localStorage.
    - `j` / `ArrowRight` (when not in input): move to next tab.
    - `k` / `ArrowLeft` (when not in input): move to previous tab.
    """
    return """
<script data-ss-exec="true">
(function() {
  var t = localStorage.getItem('shopstack-theme');
  if (t) {
    document.documentElement.setAttribute('data-theme', t);
  }
})();
function toggleTheme() {
  var e = document.documentElement;
  var t = e.getAttribute('data-theme');
  var n = (t === 'dark' ? 'light' : 'dark');
  e.setAttribute('data-theme', n);
  localStorage.setItem('shopstack-theme', n);
}
// Explicitly bind to window so the function is globally accessible
// even if the script is re-executed in a context where top-level
// function declarations don't become implicit globals (e.g. some
// module/eval contexts). The onclick="toggleTheme()" attribute on
// the theme button requires window.toggleTheme to exist.
window.toggleTheme = toggleTheme;

/* WCAG 4.1.3 Status Messages — announce to screen readers */
function announceToScreenReader(message) {
  var region = document.getElementById('ss-live-region');
  if (region) {
    region.textContent = '';
    /* Brief delay so the DOM mutation triggers a new announcement */
    setTimeout(function() { region.textContent = message; }, 80);
  }
}

/* Show a toast notification and announce to screen readers.
   Reuses the existing .toast / .toast-{kind} CSS classes from theme.py.
   The container is appended to body and positioned via the fixed toast CSS. */
function showToast(msg, kind, action) {
  kind = kind || 'info';
  var icons = { success: '\u2713', error: '\u2717', info: '\u2139', warning: '\u26A0' };
  var container = document.getElementById('ss-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'ss-toast-container';
    container.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:600;display:flex;flex-direction:column-reverse;gap:8px;';
    document.body.appendChild(container);
  }
  var el = document.createElement('div');
  el.className = 'toast toast-' + kind;
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');
  el.innerHTML = '<span aria-hidden="true">' + (icons[kind] || icons.info) + '</span><span>' + msg + '</span>';
  var dismissTimer = null;
  if (action && action.label && action.targetId) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'toast-action';
    btn.textContent = action.label;
    btn.style.cssText = 'margin-left:10px;background:transparent;border:1px solid currentColor;border-radius:4px;padding:2px 8px;cursor:pointer;color:inherit;font:inherit;font-size:0.8em;';
    btn.addEventListener('click', function() {
      if (action.valueTargetId && action.value !== undefined && action.value !== null) {
        var holder = document.getElementById(action.valueTargetId);
        var input = holder && (holder.querySelector('input, textarea') || holder);
        if (input) {
          input.value = action.value;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      var target = document.getElementById(action.targetId);
      if (target) target.click();
      if (dismissTimer) clearTimeout(dismissTimer);
      el.remove();
    });
    el.appendChild(btn);
  }
  container.appendChild(el);
  announceToScreenReader((kind === 'success' ? 'Success: ' : kind === 'error' ? 'Error: ' : '') + msg);
  dismissTimer = setTimeout(function() {
    el.style.opacity = '0';
    el.style.transform = 'translateY(12px)';
    el.style.transition = 'opacity 200ms, transform 200ms';
    setTimeout(function() { el.remove(); }, 220);
  }, action ? 6000 : 3000);
}

/* Item #99b: toast_floating() emits an inert <script> when rendered via
   gr.HTML(...) dynamic output updates (same "already started script" rule
   as item #99, but for the post-load injection path that the one-shot
   bootstrap re-exec in js_helpers.py doesn't cover). Instead it emits a
   hidden `.ss-toast-trigger` marker element; this observer watches for
   those markers anywhere in the DOM and fires showToast() directly. */
(function() {
  function processTriggers(root) {
    var triggers = root.querySelectorAll ? root.querySelectorAll('.ss-toast-trigger') : [];
    for (var i = 0; i < triggers.length; i++) {
      var trigger = triggers[i];
      if (trigger.hasAttribute('data-ss-toast-shown')) continue;
      trigger.setAttribute('data-ss-toast-shown', 'true');
      var msg = trigger.getAttribute('data-toast-msg') || '';
      var kind = trigger.getAttribute('data-toast-kind') || 'info';
      var action = null;
      var actionLabel = trigger.getAttribute('data-toast-action-label');
      if (actionLabel) {
        action = {
          label: actionLabel,
          targetId: trigger.getAttribute('data-toast-action-target'),
          valueTargetId: trigger.getAttribute('data-toast-action-value-target'),
          value: trigger.getAttribute('data-toast-action-value'),
        };
      }
      showToast(msg, kind, action);
    }
  }
  processTriggers(document);
  var toastObserver = new MutationObserver(function(mutations) {
    for (var i = 0; i < mutations.length; i++) {
      for (var j = 0; j < (mutations[i].addedNodes || []).length; j++) {
        var node = mutations[i].addedNodes[j];
        if (node.nodeType === 1) {
          if (node.matches && node.matches('.ss-toast-trigger')) {
            processTriggers(node.parentNode || document);
          } else {
            processTriggers(node);
          }
        }
      }
    }
  });
  toastObserver.observe(document.body, { childList: true, subtree: true });
})();

document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  var tabs = Array.from(document.querySelectorAll('[data-testid^=tab-], .tabs > button[role=tab]'));
  var idx = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
  if (e.key === 'j' || e.key === 'ArrowRight') {
    e.preventDefault();
    var next = (idx + 1) % tabs.length;
    tabs[next] && tabs[next].click();
  } else if (e.key === 'k' || e.key === 'ArrowLeft') {
    e.preventDefault();
    var prev = (idx - 1 + tabs.length) % tabs.length;
    tabs[prev] && tabs[prev].click();
  }
});

/* WCAG color contrast: force explicit colors on elements where Gradio's
   component-scoped CSS variables override our :root declarations.  This
   MutationObserver catches both the initial page render and any dynamic
   content Gradio inserts via tab switches or component updates. */
(function() {
  var FIX_COLORS = {
    '--text-dim': '#6F6254',
    '--text-muted': '#5F5144',
    '--text': '#1F1812',
    '--text-faint': '#7A6B5C',
  };
  function fixInlineColorVars(root) {
    var els = root.querySelectorAll('[style*="var(--text"]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var s = el.getAttribute('style') || '';
      var changed = false;
      for (var varName in FIX_COLORS) {
        var regex = new RegExp('var\\(' + varName.replace('--', '\\-\\-') + '\\)', 'g');
        if (regex.test(s)) {
          s = s.replace(regex, FIX_COLORS[varName]);
          changed = true;
        }
      }
      if (changed) {
        el.setAttribute('style', s);
      }
    }
  }
  /* Run once on page load */
  fixInlineColorVars(document);
  /* Re-check after Gradio hydration settles (2000ms) and again later
     (5000ms) to catch post-hydration style applications that bypass the
     MutationObserver (e.g. Svelte's element.style.color = '...'). */
  setTimeout(function() { fixInlineColorVars(document); }, 2000);
  setTimeout(function() { fixInlineColorVars(document); }, 5000);
  /* Watch for dynamically inserted content (tab switches, Gradio updates) */
  var observer = new MutationObserver(function(mutations) {
    for (var i = 0; i < mutations.length; i++) {
      for (var j = 0; j < (mutations[i].addedNodes || []).length; j++) {
        var node = mutations[i].addedNodes[j];
        if (node.nodeType === 1) {  /* ELEMENT_NODE */
          fixInlineColorVars(node);
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style'] });
})();
</script>"""


def header_block(brand_title: str, brand_subtitle: str, current_locale: str = DEFAULT_LOCALE) -> str:
    """Return the full header block (HTML + script + PWA links) as a single string.

    Includes:
    - Header HTML (brand title, subtitle, language selector, theme toggle button)
    - Theme persistence + keyboard shortcut JS
    - i18n script (locale persistence + reload)
    - Keyboard shortcuts JS (tab jumps, help overlay, locale/theme toggles)
    - PWA manifest link + theme color meta + service worker registration
    - Apple mobile web app meta tags
    - Walkthrough overlay (hidden until first-run JS opens it)
    - Keyboard shortcuts help overlay (hidden until `?` is pressed)

    Convenience for `gr.HTML(header_block(...))` in the app composition.
    """
    return (
        header_html(brand_title, brand_subtitle, current_locale)
        + header_script()
        + render_language_script()
        + render_shortcuts_help_html()
        + render_shortcuts_script()
        + render_walkthrough_html(current_locale)
        + render_walkthrough_script()
        + render_help_toggle_script()
        + render_palette_html(locale=current_locale)
        + render_palette_script()
        + render_undo_click_handler()
        + _pwa_css()
    )


def hydration_recovery_js() -> str:
    """Return a `<script>` that shows a branded recovery shell if Gradio
    never hydrates (PROJECT_INTELLIGENCE.md item #36).

    Gradio's default loading state is a bare "Loading..." string with no
    way for a user to recover if the JS bundle fails (e.g. a CDN hiccup or
    a JS syntax error in injected `app.load(..., js=...)` callbacks — see
    item #1). This script:

    1. Records any uncaught JS error / unhandled promise rejection.
    2. After a timeout (default 10s, overridable via the
       ``?hydration_timeout=<ms>`` query param for testing), checks whether
       `#main-content` has rendered any tabs.
    3. If not, replaces the page body with a branded recovery shell: a
       friendly message, a "Reload page" button, and a collapsible
       diagnostics panel showing the captured error(s) — pointing the user
       at something actionable instead of an infinite spinner.

    Must be passed to ``app.launch(head=...)`` — see :func:`pwa_head_html`
    docstring for why `<script>` tags only execute via `head=`, not
    ``gr.HTML(...)``.
    """
    return """
<script data-ss-exec="true">
(function() {
  var shopstackErrors = [];
  window.addEventListener('error', function(e) {
    shopstackErrors.push((e && e.message) || String(e));
  });
  window.addEventListener('unhandledrejection', function(e) {
    shopstackErrors.push('Unhandled rejection: ' + ((e && e.reason && e.reason.message) || String(e.reason)));
  });

  function hydrated() {
    var main = document.getElementById('main-content');
    return !!(main && main.querySelector('[role="tab"], .tabitem, button'));
  }

  function showRecoveryShell() {
    if (hydrated()) return;
    if (document.getElementById('shopstack-recovery-shell')) return;
    var params = new URLSearchParams(window.location.search);
    var errorList = shopstackErrors.length
      ? '<ul style="text-align:left;max-width:480px;margin:8px auto;padding-left:20px;">'
        + shopstackErrors.map(function(m) {
            var div = document.createElement('div');
            div.textContent = m;
            return '<li>' + div.innerHTML + '</li>';
          }).join('')
        + '</ul>'
      : '<p style="color:#94a3b8;">No JavaScript errors were captured, but the app did not finish loading in time.</p>';

    var shell = document.createElement('div');
    shell.id = 'shopstack-recovery-shell';
    shell.setAttribute('role', 'alert');
    shell.style.cssText = 'position:fixed;inset:0;z-index:99999;background:#0f172a;color:#f1f5f9;'
      + 'display:flex;align-items:center;justify-content:center;text-align:center;'
      + 'font-family:system-ui,-apple-system,sans-serif;padding:24px;';
    shell.innerHTML =
      '<div style="max-width:520px;">'
      + '<h1 style="font-size:1.5rem;margin-bottom:8px;">ShopStack is having trouble loading</h1>'
      + '<p style="color:#cbd5e1;margin-bottom:16px;">'
      + 'The app did not finish starting up. This is usually a temporary network '
      + 'or browser issue — reloading the page fixes it most of the time.'
      + '</p>'
      + '<button id="shopstack-recovery-reload" style="background:#facc15;color:#0f172a;border:none;'
      + 'border-radius:8px;padding:10px 20px;font-size:1rem;font-weight:600;cursor:pointer;margin-bottom:16px;">'
      + 'Reload page</button>'
      + '<details style="text-align:left;color:#94a3b8;font-size:0.8rem;">'
      + '<summary style="cursor:pointer;">Diagnostics</summary>'
      + errorList
      + '<p>If reloading does not help, check the server logs in your terminal '
      + 'for the ShopStack process for more detail.</p>'
      + '</details>'
      + '</div>';
    document.body.appendChild(shell);
    var reloadBtn = document.getElementById('shopstack-recovery-reload');
    if (reloadBtn) {
      reloadBtn.addEventListener('click', function() {
        window.location.reload();
      });
    }
  }

  var timeoutMs = 10000;
  try {
    var params = new URLSearchParams(window.location.search);
    var override = params.get('hydration_timeout');
    if (override) timeoutMs = parseInt(override, 10) || timeoutMs;
  } catch (e) { /* ignore malformed query params */ }

  // NOTE: do not gate on `window.addEventListener('load', ...)` — this
  // script is re-executed by the bootstrap re-execution helper
  // (PROJECT_INTELLIGENCE.md item #99) *after* `load` has already fired.
  setTimeout(showRecoveryShell, timeoutMs);
})();
</script>"""


def pwa_head_html() -> str:
    """Return the PWA manifest link, theme color meta, and service worker JS.

    The PWA shell is cached by the service worker registered here, so
    the app can be installed as a PWA on mobile. The service worker
    itself is served from ``/sw.js`` (mounted by
    :func:`shopstack.ui.pwa_mount.mount_pwa_static` at root path,
    bypassing Gradio 6.x's ``/static/*`` interception).

    Must be passed to ``app.launch(head=...)``, NOT rendered via
    ``gr.HTML(...)``: Gradio's HTML components set ``innerHTML``, and
    ``<script>`` tags inserted via ``innerHTML`` never execute. The
    ``head`` parameter is rendered server-side into the document
    ``<head>`` by Gradio's template, so its ``<script>`` tag runs
    normally on page load.
    """
    return """
<!-- PWA: manifest + theme color (Phase 4 #5) -->
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0f172a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<script data-ss-exec="true">
// Register service worker for PWA shell caching (Phase 4 #5)
if ('serviceWorker' in navigator) {
  // NOTE: do not gate on `window.addEventListener('load', ...)` — this
  // script is re-executed by the bootstrap re-execution helper
  // (PROJECT_INTELLIGENCE.md item #99) *after* the `load` event has
  // already fired, so a `load` listener registered here would never run.
  navigator.serviceWorker.register('/sw.js', { scope: '/' })
    .then(function(reg) {
      console.log('[ShopStack PWA] service worker registered, scope:', reg.scope);
    })
    .catch(function(err) {
      console.warn('[ShopStack PWA] service worker registration failed:', err);
    });
}
</script>""" + hydration_recovery_js()


def _pwa_css() -> str:
    """Return optional CSS for the PWA/header shell.

    Kept as a dedicated helper so `header_block()` can concatenate a stable
    set of fragments even when the PWA shell does not need extra styling.
    """
    return ""
