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
    render_i18n_script,
    render_language_selector_html,
)
from shopstack.services.shortcuts import (
    render_shortcuts_help_html,
    render_shortcuts_script,
)
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
            f"padding:6px 10px;border-radius:var(--radius-sm);"
            f"background:var(--bg-card);border:1px solid var(--border);"
            f"font-size: 0.75rem;color:var(--text-muted);min-height:32px;\">"
            f"🏠&nbsp;{escape(display_name)}"
            f"</span>"
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
<script>
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
function showToast(msg, kind) {
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
  container.appendChild(el);
  announceToScreenReader((kind === 'success' ? 'Success: ' : kind === 'error' ? 'Error: ' : '') + msg);
  setTimeout(function() {
    el.style.opacity = '0';
    el.style.transform = 'translateY(12px)';
    el.style.transition = 'opacity 200ms, transform 200ms';
    setTimeout(function() { el.remove(); }, 220);
  }, 3000);
}

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
        + render_i18n_script()
        + render_shortcuts_help_html()
        + render_shortcuts_script()
        + render_walkthrough_html(current_locale)
        + render_walkthrough_script()
        + _pwa_block()
        + _pwa_css()
    )


def _pwa_block() -> str:
    """Return the PWA manifest link, theme color meta, and service worker JS.

    The PWA shell is cached by the service worker registered here, so
    the app can be installed as a PWA on mobile. The service worker
    itself is served from ``/sw.js`` (mounted by
    :func:`shopstack.ui.pwa_mount.mount_pwa_static` at root path,
    bypassing Gradio 6.x's ``/static/*`` interception).
    """
    return """
<!-- PWA: manifest + theme color (Phase 4 #5) -->
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#0f172a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<script>
// Register service worker for PWA shell caching (Phase 4 #5)
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/static/sw.js', { scope: '/' })
      .then(function(reg) {
        console.log('[ShopStack PWA] service worker registered, scope:', reg.scope);
      })
      .catch(function(err) {
        console.warn('[ShopStack PWA] service worker registration failed:', err);
      });
  });
}
</script>"""


def _pwa_css() -> str:
    """Return optional CSS for the PWA/header shell.

    Kept as a dedicated helper so `header_block()` can concatenate a stable
    set of fragments even when the PWA shell does not need extra styling.
    """
    return ""
