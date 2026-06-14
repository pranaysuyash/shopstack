"""Post-render JavaScript helpers — Gradio ``app.load(js=...)`` snippets.

These are Python functions that return **strings of JavaScript source
code**. Each string is intended to be passed as the ``js=`` parameter
of a Gradio event handler (typically ``app.load(None, js=...)``). When
the event fires, Gradio evaluates the JS in the browser with full DOM
access.

All JS in this module:

- Uses ``json.dumps`` (not ``html.escape``) for safe string
  interpolation into JS literals. ``html.escape`` would convert ``<``
  to ``&lt;``, producing a JS syntax error.
- Is idempotent on re-run (uses ``setTimeout`` to defer past Gradio's
  initial render).
- Returns a no-args function expression (``() => { ... }``) so
  Gradio's ``app.load`` can invoke it without binding any arguments.

The three helpers cover three distinct UX concerns:

1. ``busy_js`` — disable a long-running button the moment the user
   clicks (before the network round-trip starts). Pairs with
   :func:`shopstack.ui.components.primitives.with_loading_state` (the
   Python idle leg).
2. ``autocomplete_injector_js`` — satisfy the Vercel WIG requirement
   that every form input carry an ``autocomplete`` attribute. Gradio's
   Python API doesn't expose this; the JS walks the DOM after the
   first render and sets ``autocomplete="off"`` on any input that
   doesn't already have one.
3. ``url_state_sync_js`` — sync the active top-level tab to
   ``location.hash`` so users can deep-link a tab and use browser
   back/forward navigation between tabs.

Each helper has a corresponding test in
``tests/test_ui_support.py`` that verifies the JS string contains the
expected pieces (e.g. ``setAttribute('autocomplete', 'off')``,
``history.pushState``, ``busy.disabled = true``).

Note: in Pass 4 we extracted these from ``primitives.py`` so each
module stays focused on one concern. The implementations here are
the canonical source — ``primitives.py`` re-exports them for
backward compatibility with existing imports.
"""
from __future__ import annotations

import json as _json

# Tab IDs in canonical order (synced with module_registry.TAB_ORDER).
# Kept here (not in primitives.py) because it's only used by
# url_state_sync_js. If module_registry.TAB_ORDER ever changes, this
# tuple must be updated in lockstep.
_TAB_IDS_FOR_URL_SYNC: tuple[str, ...] = (
    "today", "basket", "market", "reconcile", "memory",
)


def busy_js(elem_id: str, original_label: str = "Working…") -> str:
    """Return a JS function body that disables a button by ``elem_id`` and shows a spinner.

    Use this as the ``js=`` parameter of a long-running click handler.
    The JS runs synchronously in the browser the moment the user clicks,
    *before* the network round-trip to the Python handler starts — so
    the visual feedback is immediate.

    The returned value is the JS function body as a string. Gradio wraps
    it and invokes it on the client. Whatever the function returns is
    passed as the first argument to the Python handler; we return the
    original ``args`` unchanged so the Python handler sees the same
    input values.

    Args:
        elem_id: The ``elem_id`` of the button to disable. Must be set on
            the ``gr.Button`` for the JS to find it. (Gradio puts it on
            the button as the ``id`` HTML attribute.)
        original_label: The label to show while busy. Defaults to
            ``"Working…"``. (The Python idle leg restores the original
            label via
            :func:`shopstack.ui.components.primitives.with_loading_state`.)

    Returns:
        JavaScript source string. Pass as ``js=busy_js(...)`` to
        ``.click()`` or ``.submit()``.

    Example:
        >>> from gradio import Button
        >>> btn = Button("Run Plan", elem_id="run-plan-btn", variant="primary")
        >>> btn.click(
        ...     run_plan_fn,
        ...     [...],
        ...     [result],
        ...     js=busy_js("run-plan-btn"),
        ...     api_name="run_plan",
        ... )
    """
    # Use json.dumps (not html.escape) for safe JS string interpolation:
    # `<` is HTML-safe inside a JS string literal, but `&` from the
    # HTML escape would produce a JS syntax error.
    safe_id = _json.dumps(str(elem_id))
    safe_label = _json.dumps(str(original_label))
    # The JS function receives the Gradio-injected `args` (a proxy over
    # the input component values). We return `args` unchanged so the
    # Python handler sees the same values.
    return (
        "(args) => {"
        f"  const btn = document.getElementById({safe_id});"
        f"  if (btn) {{ btn.disabled = true; btn.dataset.originalLabel = btn.textContent; btn.textContent = {safe_label}; }}"
        "  return args;"
        "}"
    )


def autocomplete_injector_js() -> str:
    """Return JS that injects ``autocomplete="off"`` into every form input.

    Browser password managers aggressively try to autofill form fields with
    stored credentials, which clashes with the chat-style textboxes used in
    ShopStack. The Vercel Web Interface Guidelines (and general
    best-practice) call for ``autocomplete="off"`` on every form input.

    This JS runs after the first Gradio render and sets the attribute
    on any input/textarea/select that doesn't already have one. (The
    original Pass-3 implementation used a ``MutationObserver`` to keep
    firing on every render; the parallel-session simplification runs
    once via ``setTimeout`` after page load, which is sufficient for
    static form fields and avoids the observer overhead.)
    """
    return (
        "() => {"
        "setTimeout(function(){"
        "document.querySelectorAll('input,textarea,select').forEach(function(el){"
        "if(!el.getAttribute('autocomplete'))el.setAttribute('autocomplete','off');"
        "});"
        "},100);"
        "}"
    )


def url_state_sync_js() -> str:
    """Return JS that syncs the active Gradio tab to the URL hash.

    Opening the app with a URL like ``#basket`` will deep-link to the
    Shopping tab. Clicking a tab updates the URL hash so the user can
    bookmark or share a specific view.

    **Sub-tab support (Pass 4):** the URL hash format is
    ``#<top_tab>/<sub_tab>``. The JS looks for any ``button[role=tab]``
    with a ``data-testid`` and updates the hash to the
    ``tab-<top>-sub-<sub>`` form, stripping the ``tab-`` prefix. On
    initial load, it splits the hash on ``/`` and clicks both the
    top-level tab and the sub-tab.

    Examples:

    - ``#basket`` → click the Shopping top tab.
    - ``#pantry/inventory`` → click the Pantry top tab, then the
      Inventory sub-tab.
    - ``#memory/what-happened`` → click the Insights top tab, then
      the "What Happened" sub-tab.

    Uses ``setTimeout`` (deferred past Gradio's initial render) and
    ``history.replaceState`` (so back/forward navigation works).
    """
    return (
        "() => {"
        "setTimeout(function(){"
        # Parse the initial hash: "#<top>[/<sub>]".
        "var h=window.location.hash.replace('#','');"
        "if(h){"
        "  var parts=h.split('/');"
        "  var top=parts[0];"
        "  var sub=parts[1]||null;"
        # Click the top-level tab first.
        "  var topBtn=document.querySelector('[data-testid=tab-'+top+']');"
        "  if(topBtn)topBtn.click();"
        # If a sub-tab was specified, click it after the top tab.
        "  if(sub){"
        "    setTimeout(function(){"
        "      var subBtn=document.querySelector('[data-testid=tab-'+top+'-sub-'+sub+']');"
        "      if(!subBtn){"
        # Fall back: try matching the sub-tab by its visible text
        # (Gradio sometimes renders sub-tabs without data-testid).
        "        var candidates=document.querySelectorAll('[data-testid^=tab-'+top+'-sub-]');"
        "        for(var i=0;i<candidates.length;i++){"
        "          if((candidates[i].textContent||'').toLowerCase().replace(/\\W+/g,'-')===sub){"
        "            subBtn=candidates[i];break;"
        "          }"
        "        }"
        "      }"
        "      if(subBtn)subBtn.click();"
        "    },50);"
        "  }"
        "}"
        # On any tab click (top-level or sub), update the URL hash.
        "document.querySelectorAll('[data-testid^=tab-]').forEach(function(t){"
        "t.addEventListener('click',function(){"
        "  var id=t.getAttribute('data-testid').replace('tab-','');"
        "  history.replaceState(null,'','#'+id);"
        "});"
        "});"
        "},200);"
        "}"
    )


def script_bootstrap_js() -> str:
    """Return JS that re-executes inline `<script data-ss-exec>` tags.

    PROJECT_INTELLIGENCE.md item #99: `<script>` elements injected via
    `gr.HTML(...)` or `app.launch(head=...)` are inserted via
    `innerHTML`/template parsing, which the HTML spec marks "already
    started" — browsers never execute them. This affects
    `header_script()`, `render_i18n_script()`, `render_shortcuts_script()`,
    `render_walkthrough_script()`, and `pwa_head_html()`'s service-worker
    registration and hydration-recovery scripts alike.

    This helper is itself passed via `app.load(None, js=...)`, which Gradio
    *does* execute (confirmed by item #1/#35's `autocomplete_injector_js`
    and `url_state_sync_js`). It finds every `<script data-ss-exec="true">`
    in the document, clones its text content into a freshly
    `document.createElement('script')`, and appends that to `<head>` —
    elements created this way are NOT "already started" and execute
    normally, running the inert scripts for real.

    Idempotent: marks each original tag with `data-ss-executed` so a
    second `app.load` pass (or re-render) does not double-execute it.
    """
    return (
        "() => {"
        "setTimeout(function(){"
        "document.querySelectorAll('script[data-ss-exec]:not([data-ss-executed])').forEach(function(old){"
        "old.setAttribute('data-ss-executed','true');"
        "var fresh=document.createElement('script');"
        "for(var i=0;i<old.attributes.length;i++){"
        "var a=old.attributes[i];"
        "if(a.name!=='data-ss-exec')fresh.setAttribute(a.name,a.value);"
        "}"
        "fresh.textContent=old.textContent;"
        "document.head.appendChild(fresh);"
        "});"
        "},0);"
        "}"
    )


__all__ = [
    "busy_js",
    "autocomplete_injector_js",
    "url_state_sync_js",
    "script_bootstrap_js",
    "_TAB_IDS_FOR_URL_SYNC",
]
