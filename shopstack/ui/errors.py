"""Safe-render utility — the canonical wrap for screen/handler
functions that catch exceptions.

Additive (2026-06-15). The pattern it replaces is the
``except Exception: return ""`` (or ``return home_card(...)``)
silently-swallow pattern that appears in 200+ places across
``shopstack/ui/`` and ``shopstack/services/``. Per motto_v3 §0.10
Observability Is Delivery + §0.14 Operator Workflow Rule, the
user must see a real, consistent, ShopStack-branded face
instead of a blank screen when something fails.

The wrapper:
  1. Runs the function.
  2. On exception, logs it with structured context
     (motto_v3 §0.10 — operator visibility).
  3. Generates a short error id the user can quote when
     reporting a problem (motto_v3 §0.11 — customer-facing
     claims must be auditable).
  4. Returns a :func:`branded_error_shell` so the user sees
     a consistent ShopStack-branded face instead of a raw
     exception or empty panel.

Usage::

    from shopstack.ui.errors import safe_render_html

    def render_my_panel() -> str:
        return safe_render_html(
            _render_my_panel_inner,
            user_message="Couldn't load today's intelligence",
            help_tab="today",
        )

Adoption is incremental: handlers can opt in one at a time.
The remaining 290+ silent-exception sites are flagged for
future passes (per motto_v3 §0.13 scope expansion control).
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from shopstack.ui.components.primitives import branded_error_shell

logger = logging.getLogger(__name__)


def safe_render_html(
    fn: Callable[[], str],
    *,
    user_message: str,
    help_tab: str = "today",
    icon: str = "⚠️",
    retry_label: str = "Retry",
    fail_user_message: str | None = None,
) -> str:
    """Run ``fn`` and return its HTML. If it raises, return a
    :func:`branded_error_shell` with a generated error id and
    log the exception with structured context.

    The wrapped function should take no arguments and return
    an HTML string. Use the standard pattern::

        def render_panel() -> str:
            return safe_render_html(
                _render_panel_inner,
                user_message="Couldn't load X",
                help_tab="today",
            )

    Args:
        fn: The actual render function (no args, returns str).
        user_message: The user-facing description shown in the
            branded error shell. Keep it short — one sentence.
        help_tab: Tab to send the user to when they click
            "Back to dashboard". Default ``"today"``.
        icon: Emoji shown above the error message. Default
            warning sign.
        retry_label: Label for the retry button. Pass empty
            string to omit the retry button.

    Returns:
        The HTML string from ``fn`` on success, or a
        :func:`branded_error_shell` on exception.
    """
    error_id = uuid.uuid4().hex[:8]
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "safe_render_html: %s error_id=%s exc_type=%s exc=%s",
            user_message, error_id, type(exc).__name__, exc,
        )
        detail = (
            f"Error id: {error_id}\n"
            f"Type: {type(exc).__name__}\n"
            f"Message: {exc}"
        )
        return branded_error_shell(
            message=fail_user_message or user_message,
            detail=detail,
            icon=icon,
            retry_label=retry_label,
            help_tab=help_tab,
        )


__all__ = ["safe_render_html"]
