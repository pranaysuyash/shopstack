"""Fine-tuned parser UI screen — Phase 8 #16 wiring.

Thin server-rendered "what the parser understood" panel.
Wired into the Ask panel as a sub-section under the answer.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.services.fine_tuned_parser import classify_intent, render_intent_html

logger = logging.getLogger(__name__)


def parser_preview_screen(utterance: str) -> str:
    """Return the "what I understood" panel for ``utterance``.

    Returns an empty string (graceful) when ``utterance`` is
    empty or the parser can't classify.
    """
    if not utterance or not utterance.strip():
        return ""
    try:
        parsed = classify_intent(utterance)
        return render_intent_html(parsed)
    except Exception as exc:
        logger.warning("parser_preview_screen failed: %s", exc)
        return ""


__all__ = ["parser_preview_screen"]
