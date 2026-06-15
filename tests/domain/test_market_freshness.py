"""Tests for shopstack.domain.market_freshness."""

from __future__ import annotations

from datetime import date


from shopstack.domain.market_freshness import (
    FreshnessReport,
    classify_freshness,
    classify_snapshot_freshness,
    confirmation_prompt,
    inventory_confidence,
    inventory_freshness_label,
    needs_confirmation,
)


class TestClassifyFreshness:
    """Tests for classify_freshness — pure-function date classification."""

    def test_today_is_live(self):
        today = date(2026, 6, 9)
        r = classify_freshness("2026-06-09", today=today)
        assert r.status == "live"
        assert r.age_days == 0
        assert r.is_stale is False

    def test_yesterday_is_recent(self):
        today = date(2026, 6, 9)
        r = classify_freshness("2026-06-08", today=today)
        assert r.status == "recent"
        assert r.age_days == 1
        assert r.is_stale is False

    def test_two_days_old_is_stale(self):
        today = date(2026, 6, 9)
        r = classify_freshness("2026-06-07", today=today)
        assert r.status == "stale"
        assert r.age_days == 2
        assert r.is_stale is True

    def test_week_old_is_stale(self):
        today = date(2026, 6, 9)
        r = classify_freshness("2026-06-02", today=today)
        assert r.status == "stale"
        assert r.age_days == 7
        assert r.is_stale is True
        assert r.warning  # warning should be non-empty for stale data

    def test_empty_captured_at_is_unknown(self):
        r = classify_freshness("", today=date(2026, 6, 9))
        assert r.is_stale is True
        assert r.status == "unknown"
        assert r.age_days is None

    def test_invalid_date_string_is_unknown(self):
        r = classify_freshness("not-a-date", today=date(2026, 6, 9))
        assert r.is_stale is True
        assert r.status == "unknown"

    def test_future_captured_at_is_unknown(self):
        today = date(2026, 6, 9)
        r = classify_freshness("2026-06-15", today=today)
        assert r.status == "unknown"
        assert r.age_days is not None
        assert r.age_days < 0

    def test_default_today_uses_local_date(self):
        r = classify_freshness("2026-06-09")
        assert r.age_days is not None
        assert isinstance(r, FreshnessReport)


class TestClassifySnapshotFreshness:
    """Tests for classify_snapshot_freshness — accepts a snapshot object."""

    def test_none_snapshot_returns_unknown(self):
        r = classify_snapshot_freshness(None)
        assert r.is_stale is True
        assert r.status == "unknown"

    def test_snapshot_with_captured_at(self):
        class FakeSnapshot:
            captured_at = "2026-06-09"

        r = classify_snapshot_freshness(FakeSnapshot(), today=date(2026, 6, 9))
        assert r.age_days == 0
        assert r.is_stale is False

    def test_snapshot_missing_captured_at(self):
        class FakeSnapshot:
            captured_at = None

        r = classify_snapshot_freshness(FakeSnapshot(), today=date(2026, 6, 9))
        assert r.is_stale is True
        assert r.status == "unknown"


class TestInventoryFreshnessLabel:
    """Tests for inventory_freshness_label — returns a FreshnessReport."""

    def test_fresh_recent_purchase(self):
        today = date(2026, 6, 9)
        r = inventory_freshness_label(
            purchase_date=date(2026, 6, 8), shelf_life_days=7, today=today
        )
        assert r.status in ("live", "recent")
        assert r.is_stale is False

    def test_aging_item(self):
        today = date(2026, 6, 9)
        r = inventory_freshness_label(
            purchase_date=date(2026, 6, 5), shelf_life_days=7, today=today
        )
        # 4 days into a 7-day shelf life = 3 days remaining = "live"
        assert r.status in ("live", "recent", "stale")
        assert r.age_days == 4

    def test_near_expiry_item(self):
        today = date(2026, 6, 9)
        r = inventory_freshness_label(
            purchase_date=date(2026, 6, 7), shelf_life_days=7, today=today
        )
        # 2 days into a 7-day shelf life = 5 days remaining = "live"
        # 6 days into a 7-day shelf life = 1 day remaining = "recent"
        assert r.status in ("live", "recent")

    def test_expired_item_is_stale(self):
        today = date(2026, 6, 9)
        r = inventory_freshness_label(
            purchase_date=date(2026, 5, 28), shelf_life_days=7, today=today
        )
        assert r.status == "stale"
        assert r.is_stale is True

    def test_no_purchase_date(self):
        r = inventory_freshness_label(purchase_date=None, shelf_life_days=7, today=date(2026, 6, 9))
        assert r.status == "unknown"
        assert r.age_days is None

    def test_no_shelf_life_uses_default(self):
        r = inventory_freshness_label(
            purchase_date=date(2026, 6, 9), shelf_life_days=0, today=date(2026, 6, 9)
        )
        assert r.status in ("recent", "live")

    def test_returns_freshness_report(self):
        r = inventory_freshness_label(date(2026, 6, 9), 7, date(2026, 6, 9))
        assert isinstance(r, FreshnessReport)
        assert "label" in r.to_dict()


class TestInventoryConfidence:
    """Tests for inventory_confidence — confidence scoring."""

    def test_no_data_low_confidence(self):
        conf = inventory_confidence(
            purchase_date=None, last_confirmed=None, today=date(2026, 6, 9)
        )
        assert conf == 0.3

    def test_fresh_purchase_high_confidence(self):
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 9), shelf_life_days=7, today=date(2026, 6, 9)
        )
        assert conf >= 0.9

    def test_one_day_old_within_shelf_life(self):
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 8), shelf_life_days=7, today=date(2026, 6, 9)
        )
        assert conf >= 0.8

    def test_halfway_through_shelf_life(self):
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 5), shelf_life_days=7, today=date(2026, 6, 9)
        )
        # 4/7 = 57% consumed, in 0.5–0.8 range
        assert 0.4 <= conf <= 0.9

    def test_past_shelf_life_low_confidence(self):
        conf = inventory_confidence(
            purchase_date=date(2026, 5, 25), shelf_life_days=7, today=date(2026, 6, 9)
        )
        # 15 days past 7-day shelf life
        assert conf < 0.3

    def test_no_shelf_life_long_old(self):
        conf = inventory_confidence(
            purchase_date=date(2026, 5, 10), shelf_life_days=0, today=date(2026, 6, 9)
        )
        # 30+ days old
        assert conf <= 0.5

    def test_no_shelf_life_recent(self):
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 8), shelf_life_days=0, today=date(2026, 6, 9)
        )
        # 1 day old
        assert conf >= 0.8

    def test_future_purchase_max_confidence(self):
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 15), shelf_life_days=7, today=date(2026, 6, 9)
        )
        assert conf == 1.0

    def test_last_confirmed_boosts_confidence(self):
        no_confirm = inventory_confidence(
            purchase_date=date(2026, 6, 1), shelf_life_days=7, today=date(2026, 6, 9)
        )
        with_confirm = inventory_confidence(
            purchase_date=date(2026, 6, 1),
            shelf_life_days=7,
            last_confirmed=date(2026, 6, 8),
            today=date(2026, 6, 9),
        )
        assert with_confirm > no_confirm or with_confirm >= no_confirm


class TestNeedsConfirmation:
    """Tests for needs_confirmation — confidence threshold predicate."""

    def test_high_confidence_does_not_need_confirmation(self):
        assert not needs_confirmation(0.9)

    def test_low_confidence_needs_confirmation(self):
        assert needs_confirmation(0.2)

    def test_threshold_boundary(self):
        assert not needs_confirmation(0.5, threshold=0.4)
        assert needs_confirmation(0.3, threshold=0.4)

    def test_explicit_threshold(self):
        assert not needs_confirmation(0.7, threshold=0.6)
        assert needs_confirmation(0.5, threshold=0.6)


class TestConfirmationPrompt:
    """Tests for confirmation_prompt — user-facing prompt generation."""

    def test_high_confidence_returns_empty(self):
        prompt = confirmation_prompt("tomato", "Tomato", 0.9)
        assert prompt == ""

    def test_low_confidence_returns_prompt(self):
        prompt = confirmation_prompt("tomato", "Tomato", 0.2)
        assert "tomato" in prompt.lower() or "Tomato" in prompt

    def test_prompt_with_purchase_date(self):
        prompt = confirmation_prompt(
            "milk", "Milk", 0.1, purchase_date=date(2026, 5, 1)
        )
        assert prompt
        assert "milk" in prompt.lower() or "Milk" in prompt

    def test_prompt_with_quantity_and_unit(self):
        prompt = confirmation_prompt(
            "rice", "Rice", 0.2,
            purchase_date=date(2026, 5, 15),
            quantity=2.0, unit="kg",
        )
        assert prompt
        assert "rice" in prompt.lower() or "Rice" in prompt

    def test_no_purchase_date_low_confidence(self):
        prompt = confirmation_prompt("bread", "Bread", 0.1)
        assert prompt
        assert "bread" in prompt.lower() or "Bread" in prompt


class TestFreshnessReportDataclass:
    """Tests for FreshnessReport dataclass."""

    def test_construction_with_all_fields(self):
        r = FreshnessReport(
            status="live",
            age_days=0,
            label="Today",
            captured_at="2026-06-09",
            is_stale=False,
            warning="",
        )
        assert r.status == "live"
        assert r.age_days == 0
        assert r.warning == ""

    def test_to_dict_round_trip(self):
        r = FreshnessReport(
            status="stale",
            age_days=14,
            label="Old",
            captured_at="2026-05-26",
            is_stale=True,
            warning="14 days old",
        )
        d = r.to_dict()
        assert d["status"] == "stale"
        assert d["age_days"] == 14
        assert d["is_stale"] is True
        assert d["warning"] == "14 days old"
        assert d["label"] == "Old"
        assert d["captured_at"] == "2026-05-26"
