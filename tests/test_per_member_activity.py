"""Tests for shopstack.services.per_member_activity (Phase 11)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest

from shopstack.services.per_member_activity import (
    MemberActivity,
    PerMemberActivity,
    aggregate_by_actor,
    render_per_member_html,
    with_actor,
)


@dataclass
class FakeTrace:
    actor_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    decision: dict = field(default_factory=dict)
    proposed_tool_calls: list = field(default_factory=list)
    input_type: str = "text"


# ── with_actor ──────────────────────────────────────────────


def test_with_actor_on_dataclass_sets_attr():
    tr = FakeTrace()
    result = with_actor(tr, "alice")
    assert result.actor_id == "alice"


def test_with_actor_on_dict_returns_new_dict():
    tr = {"actor_id": "", "decision": {}}
    result = with_actor(tr, "bob")
    assert result["actor_id"] == "bob"
    # Original unchanged
    assert tr["actor_id"] == ""


def test_with_actor_on_dict_without_actor_id_returns_unchanged():
    tr = {"decision": {}}  # no actor_id key
    result = with_actor(tr, "alice")
    assert result is tr or result == tr


def test_with_actor_strips_whitespace():
    tr = FakeTrace()
    result = with_actor(tr, "  alice  ")
    assert result.actor_id == "alice"


def test_with_actor_empty_actor_id():
    tr = FakeTrace(actor_id="alice")
    result = with_actor(tr, "")
    assert result.actor_id == ""


def test_with_actor_none_input():
    assert with_actor(None, "alice") is None


# ── aggregate_by_actor ──────────────────────────────────────


def test_aggregate_empty():
    a = aggregate_by_actor([])
    assert a.total_traces == 0
    assert a.members == []


def test_aggregate_counts_per_actor():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace(actor_id="alice", timestamp=today),
        FakeTrace(actor_id="alice", timestamp=today),
        FakeTrace(actor_id="bob", timestamp=today),
    ]
    a = aggregate_by_actor(traces, today=today)
    assert a.total_traces == 3
    by_actor = {m.actor_id: m.total_traces for m in a.members}
    assert by_actor == {"alice": 2, "bob": 1}


def test_aggregate_groups_unknown_actor():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace(actor_id="alice", timestamp=today),
        FakeTrace(actor_id="", timestamp=today),  # unknown
    ]
    a = aggregate_by_actor(traces, today=today)
    assert any(m.actor_id == "alice" for m in a.members)
    assert any(m.actor_id == "(unknown)" for m in a.members)
    assert a.unknown_actor_traces == 1


def test_aggregate_respects_window():
    today = datetime(2026, 6, 13)
    old = today - timedelta(days=60)
    traces = [
        FakeTrace(actor_id="alice", timestamp=today),
        FakeTrace(actor_id="alice", timestamp=old),  # outside window
    ]
    a = aggregate_by_actor(traces, window_days=30, today=today)
    # The lifetime total is 2, but only 1 is within the window
    assert a.total_traces == 2
    by_actor = {m.actor_id: m.total_traces for m in a.members}
    assert by_actor == {"alice": 1}


def test_aggregate_tracks_first_and_last_active():
    today = datetime(2026, 6, 13)
    earlier = today - timedelta(days=5)
    traces = [
        FakeTrace(actor_id="alice", timestamp=earlier),
        FakeTrace(actor_id="alice", timestamp=today),
    ]
    a = aggregate_by_actor(traces, today=today)
    m = next(m for m in a.members if m.actor_id == "alice")
    assert m.first_active <= m.last_active


def test_aggregate_sorts_by_count_desc():
    today = datetime(2026, 6, 13)
    traces = (
        [FakeTrace(actor_id="alice", timestamp=today)] * 2 +
        [FakeTrace(actor_id="bob", timestamp=today)] * 5
    )
    a = aggregate_by_actor(traces, today=today)
    assert [m.actor_id for m in a.members[:2]] == ["bob", "alice"]


def test_aggregate_unknown_always_last():
    today = datetime(2026, 6, 13)
    traces = (
        [FakeTrace(actor_id="", timestamp=today)] * 5 +
        [FakeTrace(actor_id="alice", timestamp=today)] * 2
    )
    a = aggregate_by_actor(traces, today=today)
    actor_ids = [m.actor_id for m in a.members]
    assert actor_ids[0] == "alice"
    assert "(unknown)" in actor_ids


def test_aggregate_action_label_from_decision():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace(actor_id="alice", timestamp=today,
                  decision={"action": "add_inventory_item"}),
    ]
    a = aggregate_by_actor(traces, today=today)
    m = next(m for m in a.members if m.actor_id == "alice")
    assert "add_inventory_item" in m.by_action


def test_aggregate_handles_dict_traces():
    today = datetime(2026, 6, 13)
    traces = [
        {"actor_id": "alice", "timestamp": today, "decision": {}},
    ]
    a = aggregate_by_actor(traces, today=today)
    assert a.members[0].actor_id == "alice"


# ── render_per_member_html ────────────────────────────────────


def test_render_empty():
    a = PerMemberActivity()
    html = render_per_member_html(a)
    assert "No member activity" in html
    assert "pm-empty" in html


def test_render_with_members():
    a = PerMemberActivity(
        total_traces=5,
        members=[
            MemberActivity(actor_id="alice", total_traces=3,
                           by_action={"add_inventory_item": 3},
                           last_active="2026-06-13T10:00:00"),
            MemberActivity(actor_id="bob", total_traces=2,
                           by_action={"consume_item": 2},
                           last_active="2026-06-12T10:00:00"),
        ],
    )
    html = render_per_member_html(a)
    assert "alice" in html
    assert "bob" in html
    assert "3" in html
    assert "2" in html
    assert "add_inventory_item" in html
    assert "consume_item" in html


def test_render_with_unknown_actor_count():
    a = PerMemberActivity(
        total_traces=10,
        unknown_actor_traces=7,
        members=[
            MemberActivity(actor_id="alice", total_traces=3),
        ],
    )
    html = render_per_member_html(a)
    assert "7" in html  # unknown count


def test_render_color_coding_or_no_color():
    """HTML should have at least the member rows + counts."""
    a = PerMemberActivity(
        total_traces=1,
        members=[MemberActivity(actor_id="x", total_traces=1)],
    )
    html = render_per_member_html(a)
    assert "pm-member-row" in html
    assert "pm-actor" in html
    assert "pm-count" in html


def test_render_escapes_xss():
    a = PerMemberActivity(
        total_traces=1,
        members=[
            MemberActivity(
                actor_id="<script>alert(1)</script>",
                total_traces=1,
                by_action={"<script>": 1},
            ),
        ],
    )
    html = render_per_member_html(a)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
