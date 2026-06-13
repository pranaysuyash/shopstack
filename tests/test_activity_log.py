"""Tests for shopstack.services.activity_log (Phase 6 #26)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from shopstack.services.activity_log import (
    ActivitySummary,
    KNOWN_ACTIONS,
    aggregate_activity,
    render_activity_log_html,
)


@dataclass
class FakeTrace:
    action_type: str
    created_at: datetime
    user_id: str = "hh-1"
    payload: dict | None = None


# ── Aggregation basics ────────────────────────────────────────────


def test_aggregate_activity_empty_input():
    s = aggregate_activity([])
    assert s.total_traces == 0
    assert s.days == []
    assert s.action_counts == {}


def test_aggregate_activity_counts_action_types():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        FakeTrace("add_purchase", today),
        FakeTrace("add_purchase", today),
        FakeTrace("consume", today),
    ]
    s = aggregate_activity(traces, today=today)
    assert s.total_traces == 3
    assert s.action_counts == {"add_purchase": 2, "consume": 1}


def test_aggregate_activity_groups_by_day():
    today = datetime(2026, 6, 13, 10, 0, 0)
    yesterday = today - timedelta(days=1)
    traces = [
        FakeTrace("add_purchase", today),
        FakeTrace("add_purchase", today),
        FakeTrace("consume", yesterday),
    ]
    s = aggregate_activity(traces, today=today)
    assert len(s.days) == 2
    day_keys = {d.date for d in s.days}
    assert "2026-06-13" in day_keys
    assert "2026-06-12" in day_keys


def test_aggregate_activity_respects_window():
    today = datetime(2026, 6, 13, 10, 0, 0)
    old = today - timedelta(days=60)
    traces = [
        FakeTrace("add_purchase", today),
        FakeTrace("add_purchase", old),  # outside the 30-day window
    ]
    s = aggregate_activity(traces, window_days=30, today=today)
    # Total includes the old one (lifetime), but timeline excludes it
    assert s.total_traces == 2
    # Timeline only has the new one
    assert sum(len(d.traces) for d in s.days) == 1


def test_aggregate_activity_extracts_canonical_from_payload():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        FakeTrace("add_purchase", today, payload={"canonical_name": "tomato"}),
        FakeTrace("add_purchase", today, payload={"canonical_name": "onion"}),
        FakeTrace("add_purchase", today, payload={"canonical_name": "tomato"}),
    ]
    s = aggregate_activity(traces, today=today)
    assert s.item_counts == {"tomato": 2, "onion": 1}
    assert s.top_item == "tomato"


def test_aggregate_activity_extracts_canonical_from_nested_input():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        FakeTrace("add_purchase", today,
                  payload={"input": {"canonical_name": "milk"}}),
    ]
    s = aggregate_activity(traces, today=today)
    assert s.item_counts == {"milk": 1}


def test_aggregate_activity_counts_per_member():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        FakeTrace("add_purchase", today, user_id="alice"),
        FakeTrace("add_purchase", today, user_id="alice"),
        FakeTrace("add_purchase", today, user_id="bob"),
    ]
    s = aggregate_activity(traces, today=today)
    assert s.member_counts == {"alice": 2, "bob": 1}
    assert s.most_active_member == "alice"


def test_aggregate_activity_finds_most_active_day():
    today = datetime(2026, 6, 13, 10, 0, 0)
    yesterday = today - timedelta(days=1)
    traces = [
        FakeTrace("a", today),
        FakeTrace("a", today),
        FakeTrace("a", yesterday),
    ]
    s = aggregate_activity(traces, today=today)
    assert s.most_active_day == "2026-06-13"


def test_aggregate_activity_finds_top_action():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        FakeTrace("consume", today),
        FakeTrace("consume", today),
        FakeTrace("consume", today),
        FakeTrace("add_purchase", today),
    ]
    s = aggregate_activity(traces, today=today)
    assert s.top_action == "consume"


def test_aggregate_activity_handles_dict_traces():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        {"action_type": "consume", "created_at": today, "user_id": "alice"},
    ]
    s = aggregate_activity(traces, today=today)
    assert s.total_traces == 1
    assert s.action_counts == {"consume": 1}


def test_aggregate_activity_handles_missing_fields_gracefully():
    today = datetime(2026, 6, 13, 10, 0, 0)
    # Use a raw dict with no user_id to exercise the "default to 'you'" branch
    traces = [{"action_type": "consume", "created_at": today}]
    s = aggregate_activity(traces, today=today)
    assert s.total_traces == 1
    # Default user is "you" when user_id is missing
    assert s.member_counts == {"you": 1}


def test_aggregate_activity_default_user_id_is_dataclass_default():
    today = datetime(2026, 6, 13, 10, 0, 0)
    # When FakeTrace's dataclass-default user_id is used ("hh-1"),
    # the aggregator should pick that up (not default to "you").
    traces = [FakeTrace("consume", today)]
    s = aggregate_activity(traces, today=today)
    assert s.member_counts == {"hh-1": 1}


def test_aggregate_activity_handles_string_timestamps():
    traces = [
        {"action_type": "consume", "created_at": "2026-06-13T10:00:00", "user_id": "alice"},
        {"action_type": "consume", "created_at": "2026-06-13T11:00:00Z", "user_id": "alice"},
    ]
    today = datetime(2026, 6, 13, 12, 0, 0)
    s = aggregate_activity(traces, today=today)
    assert s.total_traces == 2
    assert len(s.days) == 1
    assert s.days[0].date == "2026-06-13"


def test_aggregate_activity_known_actions_constant():
    # Sanity: the known-actions set covers the trace types we write
    assert "add_purchase" in KNOWN_ACTIONS
    assert "consume" in KNOWN_ACTIONS
    assert "recipe_add" in KNOWN_ACTIONS
    assert "backup_create" in KNOWN_ACTIONS


# ── Rendering ─────────────────────────────────────────────────────


def test_render_activity_log_html_empty_summary():
    s = ActivitySummary()
    html = render_activity_log_html(s)
    assert "No activity yet" in html


def test_render_activity_log_html_basic():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        FakeTrace("add_purchase", today, payload={"canonical_name": "milk"}),
        FakeTrace("add_purchase", today, payload={"canonical_name": "onion"}),
    ]
    summary = aggregate_activity(traces, today=today)
    html = render_activity_log_html(summary)
    assert "al-block" in html
    # The headline splits the count and "actions" with a </strong> tag,
    # so check for the rendered fragments separately.
    assert f"<strong>{summary.total_traces}</strong>" in html
    assert "actions" in html
    assert "Top actions" in html
    assert "Top items" in html


def test_render_activity_log_html_includes_member_name():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [FakeTrace("a", today, user_id="alice")]
    s = aggregate_activity(traces, today=today)
    html = render_activity_log_html(s)
    assert "alice" in html


def test_render_activity_log_html_includes_recent_timeline():
    today = datetime(2026, 6, 13, 10, 0, 0)
    yesterday = today - timedelta(days=1)
    traces = [
        FakeTrace("a", today),
        FakeTrace("a", yesterday),
    ]
    s = aggregate_activity(traces, today=today)
    html = render_activity_log_html(s)
    assert "al-timeline" in html
    assert "2026-06-13" in html
    assert "2026-06-12" in html


def test_render_activity_log_html_respects_max_days():
    today = datetime(2026, 6, 13, 10, 0, 0)
    # 10 days of activity
    traces = [
        FakeTrace("a", today - timedelta(days=i))
        for i in range(10)
    ]
    s = aggregate_activity(traces, today=today)
    html_max3 = render_activity_log_html(s, max_days=3)
    html_max10 = render_activity_log_html(s, max_days=10)
    # 3 days in the timeline
    assert html_max3.count("al-tl-day") == 3
    # 10 days in the timeline
    assert html_max10.count("al-tl-day") == 10


def test_render_activity_log_html_escapes_xss():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [FakeTrace("<script>", today)]
    s = aggregate_activity(traces, today=today)
    html = render_activity_log_html(s)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
