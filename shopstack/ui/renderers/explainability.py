"""Decision explainability HTML renderer.

**Why this exists (motto_v3 first-principles / mode-portable):**

The same ``DecisionExplanation`` (a Pydantic model from
``shopstack.services.explainability``) is consumed by 3 modes:

  1. Gradio UI — needs HTML to render in a card
  2. CLI       — needs plain text to print to terminal
  3. HTTP API  — needs JSON

This module is the **HTML adapter**. The service is the
concept; this is the rendering.

The HTML output is XSS-safe (all user-facing strings pass
through ``html.escape()``). The structure uses semantic HTML5
(`<section>`, `<dl>`, `<ul>`) so screen readers and the
browser dev tools can navigate it.

**Why a separate module?**

The ``explainability`` service is pure-Python (no I/O, no
HTML). Splitting the renderer out means:

  - The service is testable without any rendering concerns.
  - The renderer can be replaced (e.g. for mobile, for a
    different design system) without touching the service.
  - The CLI / API can use the service directly without
    pulling in the HTML / html.escape dependency.
"""
from __future__ import annotations

from html import escape
from typing import Any

from shopstack.services.explainability import DecisionExplanation


# ── Color tokens (CSS custom properties from shopstack.ui.theme) ───────
#
# We use CSS custom properties (--text, --text-dim, --green, --red, etc.)
# defined in shopstack.ui.theme. The HTML stays consistent with the
# rest of the app's design system.


_CONFIDENCE_LABEL_COLOR = {
    "very high": "var(--green)",
    "high": "var(--green)",
    "medium": "var(--amber)",
    "low": "var(--red)",
    "very low": "var(--red)",
}


def render_explanation_html(explanation: DecisionExplanation) -> str:
    """Render a ``DecisionExplanation`` as a self-contained HTML string.

    The output is a `<section>` that can be embedded inside
    another container (e.g. inside a dashboard card). It's
    intentionally minimal — the design system provides the
    surrounding chrome (borders, padding, etc.) via CSS
    variables.

    XSS-safe: every dynamic string is HTML-escaped.
    """
    label = escape(explanation.confidence_label)
    label_color = _CONFIDENCE_LABEL_COLOR.get(explanation.confidence_label, "var(--text)")
    summary = escape(explanation.summary)
    canonical = escape(explanation.canonical_name.replace("_", " "))
    key_signal = escape(explanation.key_signal)
    confidence_pct = int(round(explanation.confidence * 100))
    freshness = escape(explanation.freshness_label or explanation.freshness_status or "unknown")
    caveat = escape(explanation.confidence_caveat)
    override_hint = escape(explanation.override_hint)

    # Warnings — render as a list.
    warnings_html = ""
    if explanation.warnings:
        items = "".join(
            f"<li><code>{escape(w['code'])}</code>: {escape(w['message'])}"
            f" <span class='muted'>({escape(w['severity'])})</span></li>"
            for w in explanation.warnings
        )
        warnings_html = (
            f"<section class='explain-warnings'>"
            f"<h4>Caveats</h4>"
            f"<ul>{items}</ul>"
            f"</section>"
        )

    # Evidence summary — render as a definition list.
    evidence_html = ""
    if explanation.evidence_summary:
        items = "".join(
            f"<li>{escape(e)}</li>" for e in explanation.evidence_summary
        )
        evidence_html = (
            f"<section class='explain-evidence'>"
            f"<h4>What ShopStack looked at</h4>"
            f"<ul>{items}</ul>"
            f"</section>"
        )

    # Override hint — only render if non-empty.
    override_html = ""
    if override_hint:
        override_html = (
            f"<p class='explain-override muted'>"
            f"<strong>Override:</strong> {override_hint}"
            f"</p>"
        )

    # Caveat — only render if non-empty.
    caveat_html = ""
    if caveat:
        caveat_html = f"<p class='explain-caveat'>{caveat}</p>"

    return (
        f"<section class='decision-explanation' "
        f"data-canonical-name='{escape(explanation.canonical_name)}' "
        f"data-item-id='{escape(explanation.item_id)}'>"
        f"<h3 class='explain-title'>Why ShopStack says: {canonical}</h3>"
        f"<p class='explain-summary'>{summary}</p>"
        f"<dl class='explain-meta'>"
        f"<dt>Confidence</dt>"
        f"<dd><span class='confidence-label' style='color:{label_color};'>{label}</span> "
        f"({confidence_pct}%)</dd>"
        f"<dt>Key signal</dt>"
        f"<dd>{key_signal}</dd>"
        f"<dt>Data freshness</dt>"
        f"<dd>{freshness}</dd>"
        f"</dl>"
        f"{caveat_html}"
        f"{evidence_html}"
        f"{warnings_html}"
        f"{override_html}"
        f"</section>"
    )


def render_explanation_text(explanation: DecisionExplanation) -> str:
    """Render a ``DecisionExplanation`` as plain text.

    Used by the CLI for the ``--human`` output mode. Mirrors
    the HTML structure but as plain text (no tags, no CSS).
    """
    canonical = explanation.canonical_name.replace("_", " ")
    lines = [
        f"Why ShopStack says: {canonical}",
        f"  {explanation.summary}",
        f"  Confidence: {explanation.confidence_label} "
        f"({int(round(explanation.confidence * 100))}%)",
        f"  Key signal: {explanation.key_signal}",
        f"  Data freshness: {explanation.freshness_label or explanation.freshness_status or 'unknown'}",
    ]
    if explanation.confidence_caveat:
        lines.append(f"  {explanation.confidence_caveat}")
    if explanation.warnings:
        lines.append("  Caveats:")
        for w in explanation.warnings:
            lines.append(f"    - [{w['code']}] {w['message']}")
    if explanation.evidence_summary:
        lines.append("  What ShopStack looked at:")
        for e in explanation.evidence_summary:
            lines.append(f"    - {e}")
    if explanation.override_hint:
        lines.append(f"  Override: {explanation.override_hint}")
    return "\n".join(lines)
