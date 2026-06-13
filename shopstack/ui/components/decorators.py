"""Screen-function decorators — wrap output with canonical UI patterns.

Decorators in this module are the canonical way to apply a UI pattern
to a screen function's return value. The pattern is:

>>> @aria_live_screen()
>>> def consume_item(lot_id, qty):
...     # ... business logic ...
...     return "<div class='home-card'>…</div>"

The decorator wraps the string in an ``aria-live`` region, the
decorator handles the wrapping uniformly across the app, and the
screen function stays focused on its business logic.

New decorators added to the project should live here so the
``components/__init__.py`` re-export surface stays focused on HTML
primitives and the imports for new screen decorators stay obvious.
"""
from __future__ import annotations

import functools
from html import escape

# Inlined from shopstack.ui.components.primitives.aria_live_html to
# avoid the circular import (primitives re-exports this decorator
# for backward compat). Keep in sync with the canonical implementation.
def _aria_live_html(content: str, level: str = "polite") -> str:
    """Wrap content in a role='status' aria-live region (canonical impl)."""
    safe_level = escape(str(level))
    if safe_level not in ("polite", "assertive"):
        safe_level = "polite"
    return (
        f"<div role='status' aria-live='{safe_level}' aria-atomic='true'>"
        f"{content}"
        f"</div>"
    )


def aria_live_screen(level: str = "polite"):
    """Decorator: wrap a screen function's HTML output in an aria-live region.

    Apply this to any screen function that returns a string or a tuple
    of strings. The returned HTML is wrapped in
    ``<div role='status' aria-live='<level>'>`` so screen readers
    announce the new content when it lands in the result panel.

    Usage:

    >>> @aria_live_screen()
    ... def consume_item(lot_id, qty):
    ...     return "<div class='home-card'>…</div>"

    Args:
        level: ``polite`` (default) or ``assertive``.

    Returns:
        A decorator that wraps the function's string/tuple output in
        an ``aria-live`` region. Non-string items in a tuple are passed
        through unchanged (e.g. ``gr.State`` values, ints, etc.).
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if isinstance(result, str):
                return _aria_live_html(result, level=level)
            if isinstance(result, tuple):
                return tuple(
                    _aria_live_html(r, level=level) if isinstance(r, str) else r
                    for r in result
                )
            return result
        return wrapper
    return decorator


__all__ = ["aria_live_screen"]
