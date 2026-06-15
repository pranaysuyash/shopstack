"""Shared internal utilities for ShopStack services and screens.

This module collects small helpers that were duplicated across
multiple files. The consolidation is a Pass 10 cleanup; the goal
is a single canonical location for each helper so drift can't
spawn parallel implementations.

**When to add to this module:**

* Helper is used in 2+ files AND is <20 lines AND has a single
  clear responsibility.
* The function is pure (no side effects, no singleton access).
* A test exists or is added for the helper.

**When NOT to add:**

* Helper is screen-specific (lives in the screen module).
* Helper requires singleton access (e.g., ``db``, ``current_user_id``)
  and isn't easily mockable.
* Helper is 50+ lines (it should probably be a service).

**Why not in ``shopstack/util.py`` or ``shopstack/_utils.py``?**

* ``shopstack/util.py`` is too generic — would collect unrelated
  functions across all layers (services, UI, providers).
* ``shopstack/_utils.py`` is conventionally for stdlib-private
  helpers; we want this to be importable as a real module.
* ``shopstack/services/_utils.py`` keeps these helpers with the
  service layer (which is where 2 of the 3 duplicates lived).
  The UI-screen duplicate imports from the service-layer module.
"""
from __future__ import annotations

from typing import Any


def safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """Walk a chain of dict keys / dataclass attributes.

    Returns the **first** non-None value found in the chain.
    Stops walking as soon as a key resolves to a non-None value
    (so we don't override a real value with the second key's
    default, and we don't ``getattr`` on a string returned by
    an earlier key).

    Args:
        obj: A dict or any object with attributes.
        *keys: Chain of keys to walk.
        default: Value to return if any step yields ``None``.

    Returns:
        The first non-None value at the end of the chain, or
        ``default`` if all keys resolve to ``None``.

    Examples:
        >>> safe_get({"a": {"b": 1}}, "a", "b")
        1
        >>> safe_get({"a": {"b": 1}}, "a", "missing", default="fallback")
        'fallback'
        >>> safe_get(None, "anything", default="fallback")
        'fallback'
        >>> safe_get("DMart", "best_source", "cheapest_source", default="")
        'DMart'  # first non-None wins; doesn't fall through to getattr on str
    """
    cur = obj
    for k in keys:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(k, default)
        else:
            cur = getattr(cur, k, default)
        if cur is not None:
            return cur
    return cur if cur is not None else default


__all__ = ["safe_get"]
