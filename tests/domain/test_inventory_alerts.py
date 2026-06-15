"""Tests for shopstack.domain.inventory_alerts."""

from __future__ import annotations

import pytest

from shopstack.domain.inventory_alerts import (
    AlertLevel,
    AlertSeverity,
    InventoryAlert,
    StockAlert,
    StockLevel,
    check_all_stock_levels,
    check_expiry,
    check_movement,
    check_stale_snapshot,
    check_stock_level,
    classify_inventory_alert,
    classify_stock,
    is_critical_stock,
    is_low_stock,
    is_overstock,
    notification_priority,
)


class TestClassifyStock:
    """Tests for classify_stock — threshold-based severity classification."""

    def test_critical_below_quarter_threshold(self):
        level = classify_stock("i1", "milk", current_qty=0.1, min_threshold=1.0, max_threshold=10.0)
        assert level.severity == AlertSeverity.CRITICAL
        assert level.alert == InventoryAlert.STOCK_CRITICAL

    def test_warning_at_half_threshold(self):
        level = classify_stock("i1", "milk", current_qty=0.5, min_threshold=1.0, max_threshold=10.0)
        assert level.severity == AlertSeverity.WARNING
        assert level.alert == InventoryAlert.STOCK_LOW

    def test_info_in_normal_range(self):
        level = classify_stock("i1", "milk", current_qty=2.0, min_threshold=1.0, max_threshold=10.0)
        assert level.severity == AlertSeverity.INFO
        assert level.alert is None

    def test_overstock_above_double_max(self):
        level = classify_stock("i1", "rice", current_qty=25.0, min_threshold=1.0, max_threshold=10.0)
        assert level.severity == AlertSeverity.LOW
        assert level.alert == InventoryAlert.STOCK_OVER

    def test_zero_quantity_critical(self):
        level = classify_stock("i1", "sugar", current_qty=0.0, min_threshold=1.0, max_threshold=10.0)
        assert level.severity == AlertSeverity.CRITICAL

    def test_min_threshold_zero_normalized(self):
        # Should not divide by zero
        level = classify_stock("i1", "sugar", current_qty=2.0, min_threshold=0, max_threshold=10.0)
        assert level.severity in (AlertSeverity.INFO, AlertSeverity.LOW)
        assert level.min_threshold == 1.0  # normalized to 1.0

    def test_quantity_rounded(self):
        level = classify_stock("i1", "salt", current_qty=0.123, min_threshold=1.0, max_threshold=10.0)
        assert level.current_quantity == 0.12

    def test_unit_preserved(self):
        level = classify_stock("i1", "rice", current_qty=2.0, min_threshold=1.0, max_threshold=10.0, unit="kg")
        assert level.unit == "kg"

    def test_exact_threshold_has_stock_low_alert(self):
        # At exact threshold, code reports INFO severity but STOCK_LOW alert
        # (inconsistency in classify_stock: severity uses 0.5 ratio, alert
        # uses 1.0 ratio). Document the actual behavior.
        level = classify_stock("i1", "milk", current_qty=1.0, min_threshold=1.0, max_threshold=10.0)
        assert level.alert == InventoryAlert.STOCK_LOW


class TestClassifyInventoryAlertBackwardCompat:
    """Tests that classify_inventory_alert is a backward-compat alias."""

    def test_classify_inventory_alert_matches_classify_stock(self):
        a = classify_inventory_alert("i1", "milk", 0.5, 1.0, 10.0)
        b = classify_stock("i1", "milk", 0.5, 1.0, 10.0)
        assert a.severity == b.severity
        assert a.alert == b.alert
        assert a.current_quantity == b.current_quantity

    def test_alert_level_alias(self):
        assert AlertLevel is AlertSeverity
        assert AlertLevel.CRITICAL == AlertSeverity.CRITICAL
        assert AlertLevel.WARNING == AlertSeverity.WARNING


class TestIsLowStock:
    """Tests for is_low_stock — boolean severity predicate."""

    def test_warning_is_low_stock(self):
        level = classify_stock("i1", "milk", 0.5, 1.0, 10.0)
        assert is_low_stock(level) is True

    def test_critical_is_low_stock(self):
        level = classify_stock("i1", "milk", 0.1, 1.0, 10.0)
        assert is_low_stock(level) is True

    def test_info_is_not_low_stock(self):
        level = classify_stock("i1", "milk", 2.0, 1.0, 10.0)
        assert is_low_stock(level) is False

    def test_overstock_is_not_low_stock(self):
        level = classify_stock("i1", "milk", 25.0, 1.0, 10.0)
        assert is_low_stock(level) is False


class TestIsCriticalStock:
    """Tests for is_critical_stock — boolean critical-only predicate."""

    def test_critical_is_critical(self):
        level = classify_stock("i1", "milk", 0.1, 1.0, 10.0)
        assert is_critical_stock(level) is True

    def test_warning_is_not_critical(self):
        level = classify_stock("i1", "milk", 0.5, 1.0, 10.0)
        assert is_critical_stock(level) is False

    def test_info_is_not_critical(self):
        level = classify_stock("i1", "milk", 2.0, 1.0, 10.0)
        assert is_critical_stock(level) is False


class TestIsOverstock:
    """Tests for is_overstock — overstocked predicate."""

    def test_overstock_detected(self):
        level = classify_stock("i1", "rice", 25.0, 1.0, 10.0)
        assert is_overstock(level) is True

    def test_low_severity_without_overstock_alert(self):
        # Construct manually to test edge case
        level = StockLevel(
            item_id="i1", item_name="x",
            current_quantity=5.0, min_threshold=1.0, max_threshold=10.0,
            severity=AlertSeverity.LOW, alert=None,
        )
        assert is_overstock(level) is False

    def test_normal_stock_not_overstock(self):
        level = classify_stock("i1", "rice", 2.0, 1.0, 10.0)
        assert is_overstock(level) is False


class TestCheckStockLevel:
    """Tests for check_stock_level — generate alert from a StockLevel."""

    def test_critical_alert(self):
        level = classify_stock("i1", "milk", 0.1, 1.0, 10.0)
        alert = check_stock_level(level)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.STOCK_CRITICAL
        assert alert.severity == AlertSeverity.CRITICAL
        assert "milk" in alert.message

    def test_low_alert(self):
        level = classify_stock("i1", "milk", 0.5, 1.0, 10.0)
        alert = check_stock_level(level)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.STOCK_LOW
        assert alert.severity == AlertSeverity.WARNING

    def test_overstock_alert(self):
        level = classify_stock("i1", "rice", 25.0, 1.0, 10.0)
        alert = check_stock_level(level)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.STOCK_OVER

    def test_normal_stock_no_alert(self):
        level = classify_stock("i1", "rice", 2.0, 1.0, 10.0)
        assert check_stock_level(level) is None

    def test_alert_includes_item_id(self):
        level = classify_stock("item-abc", "milk", 0.1, 1.0, 10.0)
        alert = check_stock_level(level)
        assert alert.item_id == "item-abc"


class TestCheckAllStockLevels:
    """Tests for check_all_stock_levels — batch alert generation."""

    def test_returns_only_alerting_items(self):
        levels = [
            classify_stock("i1", "milk", 0.1, 1.0, 10.0),  # critical
            classify_stock("i2", "rice", 2.0, 1.0, 10.0),   # info (no alert)
            classify_stock("i3", "sugar", 0.5, 1.0, 10.0),  # warning
        ]
        alerts = check_all_stock_levels(levels)
        assert len(alerts) == 2
        assert {a.item_id for a in alerts} == {"i1", "i3"}

    def test_empty_input(self):
        assert check_all_stock_levels([]) == []


class TestCheckExpiry:
    """Tests for check_expiry — expiry-based alert generation."""

    def test_already_expired(self):
        alert = check_expiry("i1", "milk", days_until_expiry=-1)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.EXPIRED
        assert alert.severity == AlertSeverity.CRITICAL
        assert "milk" in alert.message

    def test_expiring_today(self):
        alert = check_expiry("i1", "milk", days_until_expiry=0)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.EXPIRED

    def test_expiring_soon(self):
        alert = check_expiry("i1", "milk", days_until_expiry=3)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.EXPIRING_SOON
        assert alert.severity == AlertSeverity.WARNING
        assert "3 days" in alert.message

    def test_far_from_expiry_no_alert(self):
        alert = check_expiry("i1", "milk", days_until_expiry=30)
        assert alert is None

    def test_at_threshold_boundary(self):
        # 7 days should still trigger EXPIRING_SOON
        alert = check_expiry("i1", "milk", days_until_expiry=7)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.EXPIRING_SOON


class TestCheckStaleSnapshot:
    """Tests for check_stale_snapshot — staleness alert generation."""

    def test_never_inventoried(self):
        alert = check_stale_snapshot("i1", "rice", days_since_snapshot=0)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.NOT_INVENTORIED
        assert alert.severity == AlertSeverity.WARNING

    def test_stale_snapshot(self):
        alert = check_stale_snapshot("i1", "rice", days_since_snapshot=30)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.STALE_SNAPSHOT

    def test_at_threshold_boundary(self):
        # 14 days is the threshold — should trigger
        alert = check_stale_snapshot("i1", "rice", days_since_snapshot=14)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.STALE_SNAPSHOT

    def test_fresh_snapshot_no_alert(self):
        alert = check_stale_snapshot("i1", "rice", days_since_snapshot=7)
        assert alert is None


class TestCheckMovement:
    """Tests for check_movement — no-movement alert generation."""

    def test_no_movement_for_long(self):
        alert = check_movement("i1", "rice", days_since_movement=120)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.NO_MOVEMENT
        assert alert.severity == AlertSeverity.LOW

    def test_at_threshold_boundary(self):
        # 90 days is the threshold — should trigger
        alert = check_movement("i1", "rice", days_since_movement=90)
        assert alert is not None
        assert alert.alert_type == InventoryAlert.NO_MOVEMENT

    def test_recent_movement_no_alert(self):
        alert = check_movement("i1", "rice", days_since_movement=30)
        assert alert is None


class TestNotificationPriority:
    """Tests for notification_priority — alert-to-channel mapping."""

    def test_critical_uses_push(self):
        assert notification_priority(AlertSeverity.CRITICAL) == "push"

    def test_warning_uses_email(self):
        assert notification_priority(AlertSeverity.WARNING) == "email"

    def test_info_uses_in_app(self):
        assert notification_priority(AlertSeverity.INFO) == "in_app"

    def test_low_uses_in_app(self):
        assert notification_priority(AlertSeverity.LOW) == "in_app"

    def test_low_priority_is_in_app_or_push(self):
        # sanity check that all severities return a string
        result = notification_priority(AlertSeverity.LOW)
        assert isinstance(result, str)
        assert result in ("in_app", "push", "email")


class TestStockLevelDataclass:
    """Tests for StockLevel dataclass."""

    def test_default_severity(self):
        level = StockLevel(
            item_id="i1", item_name="x",
            current_quantity=5.0, min_threshold=1.0, max_threshold=10.0,
        )
        assert level.severity == AlertSeverity.INFO
        assert level.alert is None
        assert level.unit == "unit"

    def test_frozen_dataclass(self):
        level = StockLevel(
            item_id="i1", item_name="x",
            current_quantity=5.0, min_threshold=1.0, max_threshold=10.0,
        )
        with pytest.raises((AttributeError, Exception)):
            level.current_quantity = 99  # frozen


class TestStockAlertDataclass:
    """Tests for StockAlert dataclass."""

    def test_required_fields(self):
        alert = StockAlert(
            item_id="i1", item_name="milk",
            alert_type=InventoryAlert.STOCK_LOW,
            severity=AlertSeverity.WARNING,
            current_qty=0.5, threshold=1.0,
            message="milk low",
        )
        assert alert.reason == ""
        assert alert.message == "milk low"

    def test_with_reason(self):
        alert = StockAlert(
            item_id="i1", item_name="milk",
            alert_type=InventoryAlert.STOCK_LOW,
            severity=AlertSeverity.WARNING,
            current_qty=0.5, threshold=1.0,
            message="low", reason="pantry check",
        )
        assert alert.reason == "pantry check"
