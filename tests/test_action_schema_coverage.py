"""Regression tests for the decision-action schema coverage (2026-06-15).

Background
==========

The decision engine produces ``DecisionResult`` records with an
``action`` field that is the canonical "what should the user do?"
string. The schema layer (``shopstack.schemas.models``) defines the
canonical action vocabulary in two places:

1. ``_ACTION_COLORS`` — maps action string → CSS hex color (used
   by ``shopstack.ui.components.cards.render_decision_card`` and
   downstream renderers to badge a decision).

2. ``_ACTION_ICONS`` — maps action string → unicode emoji icon
   (same renderers).

3. ``DecisionAction`` enum — the canonical type-safe list of
   action values.

The ``Decision`` enum in ``shopstack.decisions.types`` is the
upstream source — it has 7 values (``BUY``, ``SKIP``, ``USE_SOON``,
``OPTIONAL``, ``COMPARE``, ``CONFIRM``, ``WATCH``). Some of these
have one-to-one mappings to schema actions; some have many-to-one
mappings via ``ACTION_MAP``.

Bug fixed on 2026-06-15
=======================

Prior to this fix, the action string ``"watch"`` was produced by
three code paths (see ``shopstack/decisions/rules.py:201``,
``rules.py:380``, and ``rules.py:531`` which returns
``Decision.WATCH.value`` directly), but ``"watch"`` had no entry
in ``_ACTION_COLORS`` or ``_ACTION_ICONS``. The renderers fell
through to a default dim color (``var(--text-dim)``) and an empty
string for the icon, producing visually broken decision cards for
"watch" actions.

The fix adds ``"watch"`` to both maps (grey-blue color and
magnifying-glass icon to convey "track, no action"), and this
test guards against future schema/renderer drift.

Long-term supersession
======================

``ACTION_MAP`` in ``shopstack/decisions/types.py`` is currently
defined but not consumed anywhere in the codebase — all decision
rules in ``shopstack/decisions/rules.py`` either produce
``DecisionResult(action=...)`` directly or return
``Decision.<X>.value`` (the raw enum value, not the mapped
value). The collapse of ``"confirm"`` → ``"wait"`` in
``ACTION_MAP`` is dead code.

Per ``motto_v3`` §7 (Supersession), the canonical mapping is the
schema itself (``DecisionAction`` + ``_ACTION_COLORS`` +
``_ACTION_ICONS``). The ``ACTION_MAP`` dict is a vestigial
backward-compat shim. Tracked in
``Docs/decision_records/2026-06-15_action_map_cleanup.md`` for
a follow-up pass.
"""
from __future__ import annotations

import pytest

from shopstack.schemas.models import (
    DecisionAction,
    _ACTION_COLORS,
    _ACTION_ICONS,
)


# All actions the rules actually produce. Updated as new actions
# are added to the rule engine.
RULES_PRODUCED_ACTIONS: set[str] = {
    "buy",      # shopstack/decisions/rules.py + decision_engine.py
    "skip",
    "use_soon",
    "optional",
    "compare",
    "wait",      # schema-level wait (don't act now, wait for conditions)
    "watch",     # rules.py:201, 380, 531 — track but don't act
    "substitute",
    "confirm",
}


def test_decision_action_enum_matches_rule_vocabulary() -> None:
    """DecisionAction enum must contain every action rules produce.

    Guards against silent schema drift: if a rule produces
    ``action="something_new"`` but the enum does not list it,
    downstream code that switches on ``DecisionAction`` (or
    Pydantic-validates the action string) breaks.
    """
    enum_values = {a.value for a in DecisionAction}
    missing = RULES_PRODUCED_ACTIONS - enum_values
    assert not missing, (
        f"DecisionAction enum missing values produced by the rule "
        f"engine: {sorted(missing)}. The enum is the canonical type-"
        f"safe list; add the missing values to shopstack/schemas/"
        f"models.py::DecisionAction."
    )


def test_action_colors_covers_all_decision_actions() -> None:
    """_ACTION_COLORS must define a color for every DecisionAction.

    The 2026-06-15 regression: ``"watch"`` was produced by three
    rule paths but had no color, causing renderers to fall through
    to ``var(--text-dim)`` (a dim default). This test fails fast
    if a new action is added to the enum without a color.
    """
    for action in DecisionAction:
        assert action.value in _ACTION_COLORS, (
            f"_ACTION_COLORS is missing color for action={action.value!r}. "
            f"Add a CSS hex string to shopstack/schemas/models.py::_ACTION_COLORS. "
            f"Without a color, the decision card will render with the default "
            f"var(--text-dim), which is visually broken (looks like a debug placeholder)."
        )
        color = _ACTION_COLORS[action.value]
        assert isinstance(color, str) and color.startswith("#"), (
            f"_ACTION_COLORS[{action.value!r}]={color!r} is not a valid CSS hex color."
        )
        assert len(color) in (4, 7), (
            f"_ACTION_COLORS[{action.value!r}]={color!r} is not 3- or 6-digit hex."
        )


def test_action_icons_covers_all_decision_actions() -> None:
    """_ACTION_ICONS must define an icon for every DecisionAction.

    The 2026-06-15 regression: ``"watch"`` had no icon, producing
    empty-string icons in decision cards. This test fails fast
    if a new action is added to the enum without an icon.
    """
    for action in DecisionAction:
        assert action.value in _ACTION_ICONS, (
            f"_ACTION_ICONS is missing icon for action={action.value!r}. "
            f"Add a unicode emoji/icon string to shopstack/schemas/"
            f"models.py::_ACTION_ICONS. Without an icon, the decision card "
            f"will render with an empty icon, which is visually broken."
        )
        icon = _ACTION_ICONS[action.value]
        assert isinstance(icon, str) and len(icon) > 0, (
            f"_ACTION_ICONS[{action.value!r}] is empty."
        )


def test_colors_and_icons_have_same_keys() -> None:
    """_ACTION_COLORS and _ACTION_ICONS must have the exact same keys.

    Both maps are consumed by the same renderer; if their key
    sets diverge, a card rendered with one will fall through to
    defaults for the other. This guard prevents key-set drift.
    """
    color_keys = set(_ACTION_COLORS.keys())
    icon_keys = set(_ACTION_ICONS.keys())
    assert color_keys == icon_keys, (
        f"_ACTION_COLORS and _ACTION_ICONS key sets diverge. "
        f"In colors only: {color_keys - icon_keys}. "
        f"In icons only: {icon_keys - color_keys}. "
        f"Both maps are consumed by the same decision-card renderer; "
        f"their keys must match exactly."
    )


def test_no_dead_action_in_color_icon_maps() -> None:
    """_ACTION_COLORS / _ACTION_ICONS must not have keys outside the enum.

    If a color/icon is defined for an action that the enum does
    not list, it's dead code (or worse, a hint that the enum is
    out of sync). Per ``motto_v3`` §7, no dead sources of truth.
    """
    enum_values = {a.value for a in DecisionAction}
    for map_name, mapping in (
        ("_ACTION_COLORS", _ACTION_COLORS),
        ("_ACTION_ICONS", _ACTION_ICONS),
    ):
        dead = set(mapping.keys()) - enum_values
        assert not dead, (
            f"{map_name} has keys not in DecisionAction enum: {sorted(dead)}. "
            f"Either add the value to DecisionAction or remove the dead entry."
        )


def test_watch_action_is_distinct_from_wait() -> None:
    """``wait`` and ``watch`` are two distinct schema actions.

    Per the 2026-06-15 audit, the ``DecisionSet.wait`` property
    intentionally combines both actions because they share the
    "no immediate action" UX semantics. But they have distinct
    canonical meanings:

    - ``wait`` — "don't act now, wait for better conditions"
      (e.g., price too high, expected drop soon).
    - ``watch`` — "track this item, no immediate action"
      (e.g., default fallback when no rule fires).

    They must be visually distinct so the user can tell them
    apart in the UI. This test guards against a future "lets
    unify these" refactor that accidentally makes them
    indistinguishable.
    """
    assert _ACTION_COLORS["wait"] != _ACTION_COLORS["watch"], (
        f"wait and watch must have different colors. "
        f"Both={_ACTION_COLORS['wait']!r} would make them "
        f"visually indistinguishable in the UI."
    )
    assert _ACTION_ICONS["wait"] != _ACTION_ICONS["watch"], (
        f"wait and watch must have different icons. "
        f"Both={_ACTION_ICONS['wait']!r} would make them "
        f"visually indistinguishable in the UI."
    )


@pytest.mark.parametrize("action_value", sorted(RULES_PRODUCED_ACTIONS))
def test_rule_produced_action_is_in_both_color_and_icon_maps(action_value: str) -> None:
    """Every action the rule engine produces has a color AND an icon.

    Parameterized over the full vocabulary so adding a new
    ``action="foo"`` to rules.py without adding it to the schema
    fails the right test.
    """
    assert action_value in _ACTION_COLORS, (
        f"Rule engine produces action={action_value!r} but _ACTION_COLORS "
        f"has no entry. Add a hex color."
    )
    assert action_value in _ACTION_ICONS, (
        f"Rule engine produces action={action_value!r} but _ACTION_ICONS "
        f"has no entry. Add a unicode icon."
    )
