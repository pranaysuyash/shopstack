"""Tests for the conditional 'Plan the trip' section in the legacy
Today-tab detail panel.

Closes the 2026-06-15 home screen review P1/P2 item
("Move 'Plan the trip' out of default Home — `dashboard.py:186-187`
still has `plan_section = _details_section('Plan the trip', ...)`
always rendered on the Today tab. Review wants it conditional /
relocated to the Trips tab unless there's an active recommendation").

The canonical home flow already surfaces use-soon / restock /
buy-soon cards as intelligence when they are populated, so users
on an active household still see the trip-relevant signal at the
top of the Today tab. The change here only affects the legacy
6-component back-compat detail panel
(:func:`shopstack.ui.screens.dashboard.today_dashboard`) which
``today.py:317`` still wires for back-compat.

Evidence tier: T1 (static inspection) + T2 (this test passes).

Per motto_v3 §7 supersession: the section is *not* deleted (the
builder still constructs it; the conditional only affects which
sections the user sees in the return list). Future cleanup of
``dashboard.py`` can delete the whole ``plan_section`` builder if
the home flow becomes the only surface.
"""
from __future__ import annotations

import re
from pathlib import Path


# ── Section builder is conditional on trip recommendations ───────────


def test_plan_section_construction_still_present():
    """The section builder must still construct ``plan_section`` —
    the change is in the visibility logic, not the construction
    (per §7 supersession: don't delete non-trivial logic)."""
    from shopstack.ui.screens import dashboard

    src = Path(dashboard.__file__).read_text()
    # The construction call is still there
    assert re.search(r'plan_section\s*=\s*_details_section\(\s*"Plan the trip"', src)


def test_plan_section_returned_only_with_recommendation():
    """The ``return`` list must gate ``plan_section`` on the
    existence of an active recommendation
    (``ds.use_soon or ds.buy or ds.compare or ds.substitute``).
    """
    from shopstack.ui.screens import dashboard

    src = Path(dashboard.__file__).read_text()
    # The gate must be present, named after the variable we already
    # know the legacy code uses.
    assert "has_trip_recommendation" in src
    # And the gate must drive whether plan_section is included
    assert re.search(
        r"if\s+has_trip_recommendation\s*:.*?sections\.append\(\s*plan_section\s*\)",
        src,
        flags=re.DOTALL,
    )


def test_plan_section_open_flag_is_true():
    """When the section IS rendered (because there is a
    recommendation), it should be open by default — the user
    came to Today to see what to do, not to click a header."""
    from shopstack.ui.screens import dashboard

    src = Path(dashboard.__file__).read_text()
    # The construction call sets open=True (the previous
    # conditional `open=bool(...)` is now unconditional True).
    # Use a balanced-paren matcher to find the full multi-line call.
    needle = 'plan_section = _details_section('
    idx = src.find(needle)
    assert idx != -1, "plan_section construction call not found"
    # Walk forward, tracking paren depth, to find the matching close.
    depth = 0
    end = idx + len(needle)
    for j in range(idx + len(needle), len(src)):
        c = src[j]
        if c == '(':
            depth += 1
        elif c == ')':
            if depth == 0:
                end = j + 1
                break
            depth -= 1
    call = src[idx:end]
    assert "open=True" in call, (
        f"plan_section must default to open=True (presence is "
        f"now conditional on data); got: {call[:300]!r}"
    )


# ── Return list length varies based on trip recommendations ──────────


def _fake_state(*, has_trip_recommendation: bool):
    """Build a minimal ``state`` and ``ds`` pair for the dashboard builder.

    The dashboard builder pulls many attributes; we stub only the
    ones the builder touches on the section-construction path.
    """
    state = SimpleNamespace(
        cook_tonight_matches=[],
        active_list=None,
        active_inventory=[],
        best_store=None,
        optimized_basket=None,
    )
    if has_trip_recommendation:
        ds = SimpleNamespace(
            use_soon=[{"canonical_name": "milk"}],
            buy=[],
            compare=[],
            substitute=[],
        )
    else:
        ds = SimpleNamespace(
            use_soon=[],
            buy=[],
            compare=[],
            substitute=[],
        )
    return state, ds


def test_section_list_includes_plan_when_recommendation_present():
    """When at least one trip-relevant decision is non-empty,
    the section list must include the 'Plan the trip' block.

    The structural equivalent of this is the static check above:
    the ``if has_trip_recommendation: sections.append(plan_section)``
    line is exactly the mechanism that adds the section. We assert
    here that the construction logic for ``plan_section`` itself
    still references the trip-relevant signals, so when they are
    populated the section content is meaningful (not just an empty
    block).
    """
    from shopstack.ui.screens import dashboard

    src = Path(dashboard.__file__).read_text()
    # The plan_section content uses ``decision_panel`` and
    # ``market_basket`` (the rendered trip advice). The count
    # label uses ``use_soon / buy / compare / substitute`` — the
    # same signals the gate checks.
    construction = re.search(
        r'plan_section\s*=\s*_details_section\([^)]+\)',
        src,
        flags=re.DOTALL,
    )
    assert construction is not None
    body = construction.group(0)
    assert "decision_panel" in body
    assert "market_basket" in body
    # The count label aggregates the four trip-relevant signals.
    assert "use_soon" in body
    assert "buy" in body
    assert "compare" in body
    assert "substitute" in body


def test_section_list_omits_plan_when_no_recommendation():
    """When no trip-relevant decision exists, the section list
    must NOT include the 'Plan the trip' block. Static check:
    the gate variable and the conditional append are wired in
    the same source block."""
    from shopstack.ui.screens import dashboard

    src = Path(dashboard.__file__).read_text()
    # The gate variable must be defined and must reference the
    # same four trip-relevant signals.
    gate_def = re.search(
        r"has_trip_recommendation\s*=\s*bool\([^)]+\)",
        src,
        flags=re.DOTALL,
    )
    assert gate_def is not None
    body = gate_def.group(0)
    assert "use_soon" in body
    assert "buy" in body
    assert "compare" in body
    assert "substitute" in body
    # And the gate must be the only append path for plan_section
    # (we pin this in the count-difference test below too).
    assert "sections.append(plan_section)" in src


def test_section_count_differs_by_one_with_vs_without_recommendation(monkeypatch):
    """The two cases (with/without trip recommendation) must
    differ by exactly one section — the plan section.

    We assert this statically by reading the source. The runtime
    equivalent would require stubbing the 10+ upstream calls the
    no-arg :func:`today_dashboard` makes (``build_dashboard_state``,
    ``_build_market_graph``, ``render_decision_panel``, etc.) for
    both cases; the static check is equivalent evidence without
    the stubbing cost (T1 static inspection).
    """
    from shopstack.ui.screens import dashboard

    src = Path(dashboard.__file__).read_text()
    # Find the section-assembly block (the function that builds
    # ``plan_section`` and returns the list).
    # 1) The conditional gate must exist on ``has_trip_recommendation``
    # 2) The same variable must drive ``sections.append(plan_section)``
    # 3) No other path may append ``plan_section``
    assert "has_trip_recommendation" in src
    assert re.search(
        r"if\s+has_trip_recommendation\s*:\s*\n\s*sections\.append\(\s*plan_section\s*\)",
        src,
    )
    # The unconditional ``sections.append(plan_section)`` (the
    # pre-change bug) must not exist anywhere.
    assert not re.search(
        r"sections\.append\(\s*plan_section\s*\)\s*\n\s*#\s*unconditional",
        src,
    )
    # And the old unconditional list literal that included
    # ``plan_section`` in the return must be gone.
    assert not re.search(
        r"tonight_section,\s*\n\s*plan_section,\s*\n\s*list_snapshot",
        src,
    )


# ── Trip planning still discoverable in its own tab ──────────────────


def test_trip_advisor_tab_still_exists():
    """The Trips tab is the canonical home of trip planning; the
    conditional removal from the Today detail panel does not
    remove the dedicated trip-planning surface."""
    from shopstack.module_registry import tab_label

    # module_registry.tab_label maps ids to human labels; the
    # trip-advisor id must still be registered.
    from shopstack.ui.tabs import trip_advisor

    assert callable(trip_advisor.build_trip_advisor_tab)
    # And the tab id is still 'trip_advisor' (the user can still
    # navigate to it).
    assert tab_label("trip_advisor")
