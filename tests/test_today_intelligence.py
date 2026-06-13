"""Tests for shopstack.services.today_intelligence (Phase 9)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from shopstack.services.today_intelligence import (
    TodayAction,
    TodayIntelligence,
    build_today_intelligence,
    render_today_intelligence_html,
)


@dataclass
class FakeState:
    """Minimal stand-in for DashboardState."""
    use_soon_items: list[dict] = field(default_factory=list)
    restock_predictions: list[dict] = field(default_factory=list)
    price_drops: list[dict] = field(default_factory=list)


# ── build_today_intelligence basics ─────────────────────────────


def test_build_empty_intelligence():
    intel = build_today_intelligence(FakeState())
    assert intel.is_quiet is True
    assert intel.top_actions == []
    assert intel.headline.startswith("🟢")


def test_build_with_use_soon():
    state = FakeState(use_soon_items=[
        {"canonical_name": "tomato", "days_until_expiry": 1},
    ])
    intel = build_today_intelligence(state)
    assert not intel.is_quiet
    assert len(intel.top_actions) == 1
    assert intel.top_actions[0].action == "use_soon"
    assert intel.top_actions[0].canonical_name == "tomato"
    assert intel.top_actions[0].urgency == 95
    assert "spoil" in intel.top_actions[0].reason.lower()


def test_build_with_restock():
    state = FakeState(restock_predictions=[
        {"canonical_name": "milk", "days_until_restock": 2},
    ])
    intel = build_today_intelligence(state)
    assert len(intel.top_actions) == 1
    assert intel.top_actions[0].action == "restock_due"
    assert "milk" in intel.top_actions[0].reason.lower()


def test_build_with_price_drop():
    state = FakeState(price_drops=[
        {"canonical_name": "rice", "drop_pct": 25},
    ])
    intel = build_today_intelligence(state)
    assert intel.top_actions[0].action == "price_drop"
    assert "-25%" in intel.top_actions[0].secondary


def test_build_with_community_medians():
    intel = build_today_intelligence(
        FakeState(),
        community_medians={"milk": 50.0, "bread": 30.0},
    )
    # Both are overpriced signals
    actions = intel.top_actions
    assert any(a.action == "overpriced" and a.canonical_name == "milk" for a in actions)
    assert any(a.action == "overpriced" and a.canonical_name == "bread" for a in actions)


def test_build_dedupes_same_item_in_multiple_lists():
    # If milk is both use-soon AND restock_due, it should appear once
    state = FakeState(
        use_soon_items=[{"canonical_name": "milk"}],
        restock_predictions=[{"canonical_name": "milk"}],
    )
    intel = build_today_intelligence(state)
    # Dedup by (canonical_name, action) — so use_soon and restock_due are
    # both kept (different action). But within the same action, only one.
    milk_actions = [a for a in intel.top_actions if a.canonical_name == "milk"]
    assert len(milk_actions) == 2  # use_soon + restock_due both fire


def test_build_dedupes_same_item_same_action():
    # Two use-soon entries for the same item should dedupe to one
    state = FakeState(use_soon_items=[
        {"canonical_name": "tomato"},
        {"canonical_name": "tomato"},
    ])
    intel = build_today_intelligence(state)
    assert len(intel.top_actions) == 1


def test_build_sorts_by_urgency_desc():
    state = FakeState(
        use_soon_items=[{"canonical_name": "tomato"}],  # urgency 95
        price_drops=[{"canonical_name": "rice"}],  # urgency 60
    )
    intel = build_today_intelligence(state)
    # First action should be use-soon (higher urgency)
    assert intel.top_actions[0].action == "use_soon"
    assert intel.top_actions[1].action == "price_drop"


def test_build_max_top_caps_results():
    state = FakeState(
        use_soon_items=[{"canonical_name": f"item{i}"} for i in range(8)],
    )
    intel = build_today_intelligence(state, max_top=3)
    assert len(intel.top_actions) == 3
    assert len(intel.secondary) == 5
    assert intel.total_signals == 8


def test_build_with_trip_advice():
    fake_trip = type("FakeTrip", (), {
        "recommendation": "go_in_store",
        "label": "Go in-store",
        "reason": "Use-soon items + good weather",
    })()
    intel = build_today_intelligence(FakeState(), trip_advice=fake_trip)
    # Trip action is added
    trip_actions = [a for a in intel.top_actions if a.action == "trip"]
    assert len(trip_actions) == 1


def test_build_with_neutral_trip_no_action():
    fake_trip = type("FakeTrip", (), {
        "recommendation": "neutral",
        "label": "Either way",
        "reason": "Nothing urgent",
    })()
    intel = build_today_intelligence(FakeState(), trip_advice=fake_trip)
    # Neutral recommendation doesn't fire a trip action
    trip_actions = [a for a in intel.top_actions if a.action == "trip"]
    assert trip_actions == []


def test_build_headline_includes_counts():
    state = FakeState(
        use_soon_items=[{"canonical_name": "tomato"}],
        price_drops=[{"canonical_name": "rice"}],
    )
    intel = build_today_intelligence(state)
    assert "1 use-soon" in intel.headline
    assert "1 price drops" in intel.headline


def test_build_by_source_counts():
    state = FakeState(
        use_soon_items=[{"canonical_name": "x"}, {"canonical_name": "y"}],
        price_drops=[{"canonical_name": "z"}],
    )
    intel = build_today_intelligence(state)
    assert intel.by_source == {"use_soon": 2, "price_drop": 1}


def test_build_assigns_ranks():
    state = FakeState(
        use_soon_items=[{"canonical_name": "a"}],
        restock_predictions=[{"canonical_name": "b"}],
        price_drops=[{"canonical_name": "c"}],
    )
    intel = build_today_intelligence(state)
    assert [a.rank for a in intel.top_actions] == [1, 2, 3]


def test_build_with_dict_state():
    """Allow dict-shaped state too (defensive)."""
    intel = build_today_intelligence({
        "use_soon_items": [{"canonical_name": "tomato"}],
    })
    assert intel.top_actions[0].action == "use_soon"


def test_build_safe_against_none_values():
    intel = build_today_intelligence(None)
    assert intel.is_quiet is True


# ── render_today_intelligence_html ──────────────────────────────


def test_render_quiet_intel():
    intel = TodayIntelligence(is_quiet=True)
    html = render_today_intelligence_html(intel)
    assert "Nothing urgent" in html
    assert "ti-quiet" in html


def test_render_with_actions():
    state = FakeState(
        use_soon_items=[{"canonical_name": "tomato"}],
        price_drops=[{"canonical_name": "rice"}],
    )
    intel = build_today_intelligence(state)
    html = render_today_intelligence_html(intel)
    assert "ti-block" in html
    assert "Tomato" in html or "tomato" in html
    assert "Rice" in html or "rice" in html
    assert "#1" in html
    assert "#2" in html


def test_render_with_secondary_collapsed():
    state = FakeState(
        use_soon_items=[{"canonical_name": f"item{i}"} for i in range(6)],
    )
    intel = build_today_intelligence(state, max_top=2)
    html = render_today_intelligence_html(intel)
    assert "details" in html  # The secondary is in a <details>
    assert "4 more" in html  # 6 - 2 = 4 secondary items


def test_render_color_coding_by_action():
    state = FakeState(
        use_soon_items=[{"canonical_name": "tomato"}],
        price_drops=[{"canonical_name": "rice"}],
    )
    intel = build_today_intelligence(state)
    html = render_today_intelligence_html(intel)
    # Amber for use-soon
    assert "A76012" in html
    # Green for price-drop
    assert "176B49" in html


def test_render_escapes_xss():
    state = FakeState(use_soon_items=[{"canonical_name": "<script>alert(1)</script>"}])
    intel = build_today_intelligence(state)
    html = render_today_intelligence_html(intel)
    # The canonical name is title-cased ("<Script>Alert(1)</Script>") in
    # the renderer. Just check the raw tag never appears unescaped.
    assert "<script>alert" not in html.lower()
    # The escaped form (any case) must appear
    assert "&lt;script&gt;" in html.lower()
