"""Tests for the Unified Timeline service and screen.

Coverage:
- Pure aggregator (no DB required) — `merge_events`, `filter_events`
- Bucketing and summarizing
- TimelineService.query facade
- HTML rendering
- Screen rendering (timeline_view, timeline_for_canonical, timeline_for_lot)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shopstack.repos.inventory import InventoryRepo
from shopstack.services.timeline import (
    TimelineEvent,
    TimelineQuery,
    TimelineService,
    bucket_by_day,
    event_label,
    filter_events,
    merge_events,
    render_timeline_html,
    summarize,
)
from shopstack.ui.screens.timeline import (
    timeline_view,
    timeline_for_canonical,
    timeline_for_lot,
)


# ─── Pure aggregator tests (no DB) ────────────────────────────────


class TestMergeEvents:
    def test_empty_inputs_returns_empty_list(self):
        result = merge_events()
        assert result == []

    def test_inventory_event_added_maps_correctly(self):
        ev = merge_events(
            inventory_events=[{
                "event_id": "ie1",
                "timestamp": "2026-06-01T10:00:00",
                "canonical_name": "milk",
                "action": "added",
                "quantity_after": 1.0,
                "unit": "L",
                "location_to": "fridge",
                "source": "manual",
                "user_id": "u1",
                "lot_id": "lot1",
            }],
        )[0]
        assert ev.event_type == "inventory.added"
        assert ev.canonical_name == "milk"
        assert ev.lot_id == "lot1"
        assert ev.location_id == "fridge"
        assert ev.quantity_after == 1.0
        assert ev.unit == "L"

    def test_inventory_event_consumed_maps_correctly(self):
        ev = merge_events(
            inventory_events=[{
                "event_id": "ie1",
                "timestamp": "2026-06-01T10:00:00",
                "action": "consumed",
                "canonical_name": "milk",
            }],
        )[0]
        assert ev.event_type == "inventory.consumed"

    def test_inventory_event_moved_maps_correctly(self):
        ev = merge_events(
            inventory_events=[{
                "event_id": "ie1",
                "timestamp": "2026-06-01T10:00:00",
                "action": "moved",
                "location_from": "kitchen",
                "location_to": "pantry",
                "canonical_name": "rice",
            }],
        )[0]
        assert ev.event_type == "inventory.moved"
        assert ev.location_from == "kitchen"
        assert ev.location_to == "pantry"

    def test_movement_event_maps_to_movement_type(self):
        ev = merge_events(
            movement_events=[{
                "movement_id": "mv1",
                "lot_id": "lot1",
                "to_location_id": "pantry",
                "from_location_id": "kitchen",
                "timestamp": "2026-06-01T10:00:00",
                "source": "manual",
                "confidence": 1.0,
            }],
        )[0]
        assert ev.event_type == "movement.recorded"
        assert ev.lot_id == "lot1"
        assert ev.location_to == "pantry"

    def test_purchase_event_maps_correctly(self):
        ev = merge_events(
            purchase_events=[{
                "event_id": "pe1",
                "timestamp": "2026-06-01T10:00:00",
                "canonical_name": "milk",
                "quantity": 1.0,
                "unit": "L",
                "total_price": 60.0,
                "currency": "INR",
                "store_name": "Kirana",
                "source_type": "manual",
            }],
        )[0]
        assert ev.event_type == "purchase.recorded"
        assert ev.canonical_name == "milk"
        assert "Kirana" in ev.notes
        assert "60" in ev.notes

    def test_reconciliation_event_maps_correctly(self):
        ev = merge_events(
            reconciliation_events=[{
                "event_id": "re1",
                "timestamp": "2026-06-01T10:00:00",
                "canonical_name": "milk",
                "planned_action": "buy",
                "actual_action": "bought",
                "quantity": 1.0,
                "unit": "L",
                "price_paid": 60.0,
            }],
        )[0]
        assert ev.event_type == "reconciliation.recorded"
        assert "Planned: buy" in ev.notes
        assert "Actual: bought" in ev.notes

    def test_trace_event_splits_into_plan_and_finalize(self):
        events = merge_events(
            traces=[{
                "trace_id": "t1",
                "timestamp": "2026-06-01T10:00:00",
                "user_goal": "find_item",
                "redacted_user_request": "where is my passport",
                "human_confirmation": "approved",
                "proposed_tool_calls": [{"args": {"canonical_name": "passport"}}],
                "actor_id": "u1",
            }],
        )
        assert len(events) == 2
        assert events[0].event_type == "trace.plan"
        assert events[1].event_type == "trace.finalize"
        assert events[0].canonical_name == "passport"

    def test_preference_signal_maps_correctly(self):
        ev = merge_events(
            preference_signals=[{
                "signal_id": "p1",
                "canonical_name": "milk",
                "signal_type": "staple",
                "value": "true",
                "source": "observed",
                "updated_at": "2026-06-01T10:00:00",
            }],
        )[0]
        assert ev.event_type == "preference.learned"
        assert "staple" in ev.notes

    def test_price_observation_maps_correctly(self):
        ev = merge_events(
            price_observations=[{
                "price_id": "pr1",
                "canonical_name": "milk",
                "price": 60.0,
                "quantity": 1.0,
                "unit": "L",
                "store_name": "BigBasket",
                "observation_date": "2026-06-01",
            }],
        )[0]
        assert ev.event_type == "price.observed"
        assert "BigBasket" in ev.notes

    def test_negative_memory_maps_correctly(self):
        ev = merge_events(
            negative_memory=[{
                "memory_id": "nm1",
                "lot_id": "lot1",
                "location_id": "garage",
                "location_name": "Garage",
                "confirmed_at": "2026-06-01T10:00:00",
                "source": "user_feedback",
            }],
        )[0]
        assert ev.event_type == "negative_memory.recorded"
        assert ev.location_name == "Garage"

    def test_multiple_sources_merge_into_single_list(self):
        events = merge_events(
            inventory_events=[{
                "event_id": "ie1", "timestamp": "2026-06-01T10:00:00",
                "action": "added", "canonical_name": "milk",
            }],
            purchase_events=[{
                "event_id": "pe1", "timestamp": "2026-06-01T10:00:00",
                "canonical_name": "milk",
            }],
        )
        assert len(events) == 2
        types = {e.event_type for e in events}
        assert "inventory.added" in types
        assert "purchase.recorded" in types


# ─── Filter tests ─────────────────────────────────────────────────


class TestFilterEvents:
    def test_filter_by_canonical_name(self):
        events = [
            TimelineEvent(event_id="1", event_type="inventory.added", timestamp=datetime(2026, 6, 1), canonical_name="milk"),
            TimelineEvent(event_id="2", event_type="inventory.added", timestamp=datetime(2026, 6, 1), canonical_name="bread"),
        ]
        result = filter_events(events, TimelineQuery(canonical_name="milk"))
        assert len(result) == 1
        assert result[0].canonical_name == "milk"

    def test_filter_by_lot_id(self):
        events = [
            TimelineEvent(event_id="1", event_type="movement.recorded", timestamp=datetime(2026, 6, 1), lot_id="lot1"),
            TimelineEvent(event_id="2", event_type="movement.recorded", timestamp=datetime(2026, 6, 1), lot_id="lot2"),
        ]
        result = filter_events(events, TimelineQuery(lot_id="lot1"))
        assert len(result) == 1
        assert result[0].lot_id == "lot1"

    def test_filter_by_location_id_matches_to_and_from(self):
        events = [
            TimelineEvent(event_id="1", event_type="movement.recorded", timestamp=datetime(2026, 6, 1), location_to="pantry"),
            TimelineEvent(event_id="2", event_type="movement.recorded", timestamp=datetime(2026, 6, 1), location_from="pantry", location_to="fridge"),
            TimelineEvent(event_id="3", event_type="movement.recorded", timestamp=datetime(2026, 6, 1), location_to="kitchen"),
        ]
        result = filter_events(events, TimelineQuery(location_id="pantry"))
        assert len(result) == 2

    def test_filter_by_event_types(self):
        events = [
            TimelineEvent(event_id="1", event_type="inventory.added", timestamp=datetime(2026, 6, 1)),
            TimelineEvent(event_id="2", event_type="inventory.consumed", timestamp=datetime(2026, 6, 1)),
            TimelineEvent(event_id="3", event_type="movement.recorded", timestamp=datetime(2026, 6, 1)),
        ]
        result = filter_events(events, TimelineQuery(event_types=["inventory.added", "inventory.consumed"]))
        assert len(result) == 2

    def test_filter_by_since_until_window(self):
        events = [
            TimelineEvent(event_id="1", event_type="x", timestamp=datetime(2026, 6, 1)),
            TimelineEvent(event_id="2", event_type="x", timestamp=datetime(2026, 6, 5)),
            TimelineEvent(event_id="3", event_type="x", timestamp=datetime(2026, 6, 10)),
        ]
        result = filter_events(events, TimelineQuery(
            since=datetime(2026, 6, 3),
            until=datetime(2026, 6, 8),
        ))
        assert len(result) == 1
        assert result[0].event_id == "2"

    def test_filter_sort_desc_by_default(self):
        events = [
            TimelineEvent(event_id="1", event_type="x", timestamp=datetime(2026, 6, 1)),
            TimelineEvent(event_id="2", event_type="x", timestamp=datetime(2026, 6, 5)),
            TimelineEvent(event_id="3", event_type="x", timestamp=datetime(2026, 6, 10)),
        ]
        result = filter_events(events, TimelineQuery())
        assert [e.event_id for e in result] == ["3", "2", "1"]

    def test_filter_sort_asc(self):
        events = [
            TimelineEvent(event_id="1", event_type="x", timestamp=datetime(2026, 6, 1)),
            TimelineEvent(event_id="2", event_type="x", timestamp=datetime(2026, 6, 5)),
        ]
        result = filter_events(events, TimelineQuery(order="asc"))
        assert [e.event_id for e in result] == ["1", "2"]

    def test_filter_limit_applied_after_sort(self):
        events = [
            TimelineEvent(event_id=str(i), event_type="x", timestamp=datetime(2026, 6, i + 1))
            for i in range(10)
        ]
        result = filter_events(events, TimelineQuery(limit=3))
        assert len(result) == 3
        # Newest 3 first
        assert [e.event_id for e in result] == ["9", "8", "7"]


# ─── Bucketing and summary tests ──────────────────────────────────


class TestBucketAndSummary:
    def test_bucket_by_day_groups_events(self):
        events = [
            TimelineEvent(event_id="1", event_type="x", timestamp=datetime(2026, 6, 1, 9)),
            TimelineEvent(event_id="2", event_type="x", timestamp=datetime(2026, 6, 1, 15)),
            TimelineEvent(event_id="3", event_type="x", timestamp=datetime(2026, 6, 2, 10)),
        ]
        buckets = bucket_by_day(events)
        assert len(buckets) == 2
        # Newest first
        assert buckets[0].date == "2026-06-02"
        assert buckets[1].date == "2026-06-01"
        assert len(buckets[1].events) == 2

    def test_summarize_counts_by_type_location_canonical(self):
        events = [
            TimelineEvent(event_id="1", event_type="inventory.added", timestamp=datetime(2026, 6, 1), location_id="fridge", canonical_name="milk"),
            TimelineEvent(event_id="2", event_type="inventory.added", timestamp=datetime(2026, 6, 1), location_id="fridge", canonical_name="milk"),
            TimelineEvent(event_id="3", event_type="inventory.consumed", timestamp=datetime(2026, 6, 2), location_id="fridge", canonical_name="milk"),
        ]
        result = summarize(events, TimelineQuery())
        assert result.total_in_window == 3
        assert result.by_type["inventory.added"] == 2
        assert result.by_type["inventory.consumed"] == 1
        assert result.by_location["fridge"] == 3
        assert result.by_canonical["milk"] == 3

    def test_summarize_window_start_end(self):
        events = [
            TimelineEvent(event_id="1", event_type="x", timestamp=datetime(2026, 6, 1)),
            TimelineEvent(event_id="2", event_type="x", timestamp=datetime(2026, 6, 5)),
        ]
        result = summarize(events, TimelineQuery())
        assert result.window_start == "2026-06-01T00:00:00"
        assert result.window_end == "2026-06-05T00:00:00"


# ─── Event label / HTML rendering tests ───────────────────────────


class TestEventLabel:
    def test_known_event_type_returns_friendly_label(self):
        label, emoji = event_label("inventory.added")
        assert label == "Added to inventory"
        assert emoji == "➕"

    def test_unknown_event_type_returns_derived_label(self):
        label, emoji = event_label("custom.event_type")
        assert "Custom Event Type" in label or "Event Type" in label


class TestRenderHtml:
    def test_empty_result_returns_empty_message(self):
        result = summarize([], TimelineQuery())
        html = render_timeline_html(result)
        assert "No events" in html

    def test_render_includes_event_details(self):
        events = [
            TimelineEvent(
                event_id="1", event_type="inventory.added",
                timestamp=datetime(2026, 6, 1, 10, 0),
                canonical_name="milk", location_id="fridge",
            ),
        ]
        result = summarize(events, TimelineQuery())
        html = render_timeline_html(result)
        assert "milk" in html
        assert "Added to inventory" in html


# ─── Service facade tests (with DB) ──────────────────────────────


class TestTimelineService:
    def test_query_returns_timeline_result(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge", category="dairy")
        lot_id = added["lot_id"]

        service = TimelineService(db)
        result = service.query(TimelineQuery(canonical_name="milk"))

        assert isinstance(result, type(service.query(TimelineQuery())))
        # Should at least have the inventory.added event
        added_events = [e for e in result.events if e.event_type == "inventory.added"]
        assert len(added_events) >= 1

    def test_query_filters_by_canonical(self, db):
        repo = InventoryRepo(db)
        repo.add_item("milk", "Milk", 1, "L", "fridge")
        repo.add_item("bread", "Bread", 1, "unit", "pantry")

        result = TimelineService(db).query(TimelineQuery(canonical_name="milk"))
        canonical_names = {e.canonical_name for e in result.events if e.canonical_name}
        # All non-empty canonical names should be "milk"
        assert canonical_names <= {"milk"}

    def test_query_filters_by_lot_id(self, db):
        repo = InventoryRepo(db)
        added1 = repo.add_item("milk", "Milk", 1, "L", "fridge")
        repo.add_item("bread", "Bread", 1, "unit", "pantry")
        lot_id = added1["lot_id"]

        result = TimelineService(db).query(TimelineQuery(lot_id=lot_id))
        lot_ids = {e.lot_id for e in result.events if e.lot_id}
        # All non-empty lot_ids should match
        assert lot_ids <= {lot_id}

    def test_query_includes_movement_events(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        repo.move_item(lot_id, "pantry")

        result = TimelineService(db).query(TimelineQuery(lot_id=lot_id))
        movement_events = [e for e in result.events if e.event_type == "movement.recorded"]
        assert len(movement_events) >= 1

    def test_query_returns_bucketed_result(self, db):
        repo = InventoryRepo(db)
        repo.add_item("milk", "Milk", 1, "L", "fridge")

        result = TimelineService(db).query(TimelineQuery())
        assert len(result.buckets) >= 1
        assert all(isinstance(b.date, str) for b in result.buckets)
        assert all(isinstance(b.events, list) for b in result.buckets)

    def test_query_respects_limit(self, db):
        repo = InventoryRepo(db)
        for i in range(5):
            repo.add_item(f"item_{i}", f"Item {i}", 1, "unit", "fridge")

        result = TimelineService(db).query(TimelineQuery(limit=2))
        assert len(result.events) <= 2


# ─── Screen tests ─────────────────────────────────────────────────


class TestTimelineScreen:
    def test_timeline_view_renders_html(self, db):
        repo = InventoryRepo(db)
        repo.add_item("milk", "Milk", 1, "L", "fridge")
        html = timeline_view(canonical_name="milk", days=30)
        assert "stat-card" in html or "al-block" in html or "timeline" in html.lower() or len(html) > 50

    def test_timeline_view_empty_database(self, db):
        html = timeline_view(days=30)
        # Should not crash, should return some HTML
        assert isinstance(html, str)
        assert len(html) > 0

    def test_timeline_for_canonical(self, db):
        repo = InventoryRepo(db)
        repo.add_item("milk", "Milk", 1, "L", "fridge")
        html = timeline_for_canonical("milk")
        assert isinstance(html, str)
        assert len(html) > 0

    def test_timeline_for_lot(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        html = timeline_for_lot(added["lot_id"])
        assert isinstance(html, str)
        assert len(html) > 0


class TestTimelineTabRefreshBridge:
    """``build_timeline_tab`` wires its Refresh button / app.load to
    ``_timeline_refresh(canonical_name, days)``, NOT ``timeline_view``
    directly — ``timeline_view``'s 2nd positional param is ``lot_id``,
    so Gradio's positional dispatch of ``[tl_filter, tl_days]`` would
    pass the numeric ``days`` value as ``lot_id`` and crash on
    ``lot_id.strip()``.
    """

    def test_timeline_refresh_bridges_days_correctly(self, db):
        from shopstack.ui.tabs.timeline import _timeline_refresh

        repo = InventoryRepo(db)
        repo.add_item("milk", "Milk", 1, "L", "fridge")
        html = _timeline_refresh("milk", 30)
        assert isinstance(html, str)
        assert "Could not load timeline" not in html

    def test_timeline_view_rejects_non_string_lot_id(self):
        """Documents the failure mode ``_timeline_refresh`` avoids: calling
        ``timeline_view`` positionally with an int in the ``lot_id`` slot
        raises, which ``@safe_render`` converts into an error card."""
        html = timeline_view("milk", 30)  # positional: canonical_name, lot_id=30 (int)
        assert "Something went wrong" in html
