"""Pure inventory-alert logic: threshold checks, severity, and notification generation.

Extracted from ``shopstack/decisions/rules.py`` as the canonical source for:
- Stock-level threshold checks (low, critical, overstock)
- Alert severity classification
- Alert message generation
- Notification priority (push / email / in-app)

This module is pure logic — no I/O, no database, no UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    LOW = "low"


class InventoryAlert(str, Enum):
    STOCK_LOW = "stock_low"
    STOCK_CRITICAL = "stock_critical"
    STOCK_OVER = "stock_over"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    NO_MOVEMENT = "no_movement"
    STALE_SNAPSHOT = "stale_snapshot"
    NOT_INVENTORIED = "not_inventoried"


# Backward-compat alias
AlertLevel = AlertSeverity


@dataclass(frozen=True)
class StockLevel:
    item_id: str
    item_name: str
    current_quantity: float
    min_threshold: float
    max_threshold: float
    unit: str = "unit"
    severity: AlertSeverity = AlertSeverity.INFO
    alert: InventoryAlert | None = None


AlertReason = str


@dataclass(frozen=True)
class StockAlert:
    item_id: str
    item_name: str
    alert_type: InventoryAlert
    severity: AlertSeverity
    current_qty: float
    threshold: float
    message: str
    reason: AlertReason = ""


# Thresholds
_CRITICAL_RATIO = 0.25
_WARNING_RATIO = 0.50
_OVERSTOCK_RATIO = 2.0

_DAYS_EXPIRING_SOON = 7
_DAYS_EXPIRED = 0
_DAYS_NO_MOVEMENT = 90
_DAYS_STALE_SNAPSHOT = 14


def classify_stock(
    item_id: str,
    item_name: str,
    current_qty: float,
    min_threshold: float,
    max_threshold: float,
    unit: str = "unit",
) -> StockLevel:
    if min_threshold <= 0:
        min_threshold = 1.0
    if current_qty <= min_threshold * _CRITICAL_RATIO:
        severity = AlertSeverity.CRITICAL
    elif current_qty <= min_threshold * _WARNING_RATIO:
        severity = AlertSeverity.WARNING
    elif current_qty >= max_threshold * _OVERSTOCK_RATIO:
        severity = AlertSeverity.LOW
    else:
        severity = AlertSeverity.INFO
    alerts: list[InventoryAlert] = []
    if current_qty <= min_threshold * _CRITICAL_RATIO:
        alerts.append(InventoryAlert.STOCK_CRITICAL)
    elif current_qty <= min_threshold:
        alerts.append(InventoryAlert.STOCK_LOW)
    if current_qty >= max_threshold * _OVERSTOCK_RATIO:
        alerts.append(InventoryAlert.STOCK_OVER)
    return StockLevel(
        item_id=item_id,
        item_name=item_name,
        current_quantity=round(current_qty, 2),
        min_threshold=min_threshold,
        max_threshold=max_threshold,
        unit=unit,
        severity=severity,
        alert=alerts[0] if alerts else None,
    )


# Backward-compatibility adapter
def classify_inventory_alert(
    item_id: str,
    item_name: str,
    current_qty: float,
    min_threshold: float,
    max_threshold: float,
    unit: str = "unit",
) -> StockLevel:
    return classify_stock(item_id, item_name, current_qty, min_threshold, max_threshold, unit)


def is_low_stock(level: StockLevel) -> bool:
    return level.severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL)


def is_critical_stock(level: StockLevel) -> bool:
    return level.severity == AlertSeverity.CRITICAL


def is_overstock(level: StockLevel) -> bool:
    return level.severity == AlertSeverity.LOW and level.alert == InventoryAlert.STOCK_OVER


def check_stock_level(level: StockLevel) -> StockAlert | None:
    if level.current_quantity <= level.min_threshold * _CRITICAL_RATIO:
        return StockAlert(
            item_id=level.item_id, item_name=level.item_name,
            alert_type=InventoryAlert.STOCK_CRITICAL, severity=AlertSeverity.CRITICAL,
            current_qty=level.current_quantity, threshold=level.min_threshold,
            message=f"{level.item_name} critically low ({level.current_quantity} {level.unit}, min {level.min_threshold})",
        )
    if level.current_quantity <= level.min_threshold:
        return StockAlert(
            item_id=level.item_id, item_name=level.item_name,
            alert_type=InventoryAlert.STOCK_LOW, severity=AlertSeverity.WARNING,
            current_qty=level.current_quantity, threshold=level.min_threshold,
            message=f"{level.item_name} running low ({level.current_quantity} {level.unit}, min {level.min_threshold})",
        )
    if level.current_quantity >= level.max_threshold * _OVERSTOCK_RATIO:
        return StockAlert(
            item_id=level.item_id, item_name=level.item_name,
            alert_type=InventoryAlert.STOCK_OVER, severity=AlertSeverity.INFO,
            current_qty=level.current_quantity, threshold=level.max_threshold,
            message=f"{level.item_name} overstocked ({level.current_quantity} {level.unit}, max {level.max_threshold})",
        )
    return None


def check_all_stock_levels(levels: Sequence[StockLevel]) -> list[StockAlert]:
    return [a for level in levels if (a := check_stock_level(level)) is not None]


def check_expiry(
    item_id: str, item_name: str, days_until_expiry: int,
) -> StockAlert | None:
    if days_until_expiry <= _DAYS_EXPIRED:
        return StockAlert(
            item_id=item_id, item_name=item_name,
            alert_type=InventoryAlert.EXPIRED, severity=AlertSeverity.CRITICAL,
            current_qty=days_until_expiry, threshold=float(_DAYS_EXPIRED),
            message=f"{item_name} has expired",
        )
    if days_until_expiry <= _DAYS_EXPIRING_SOON:
        return StockAlert(
            item_id=item_id, item_name=item_name,
            alert_type=InventoryAlert.EXPIRING_SOON, severity=AlertSeverity.WARNING,
            current_qty=days_until_expiry, threshold=float(_DAYS_EXPIRING_SOON),
            message=f"{item_name} expiring in {days_until_expiry} days",
        )
    return None


def check_stale_snapshot(
    item_id: str, item_name: str, days_since_snapshot: int,
) -> StockAlert | None:
    if days_since_snapshot <= 0:
        return StockAlert(
            item_id=item_id, item_name=item_name,
            alert_type=InventoryAlert.NOT_INVENTORIED, severity=AlertSeverity.WARNING,
            current_qty=float(days_since_snapshot), threshold=0.0,
            message=f"{item_name} has never been inventoried",
        )
    if days_since_snapshot >= _DAYS_STALE_SNAPSHOT:
        return StockAlert(
            item_id=item_id, item_name=item_name,
            alert_type=InventoryAlert.STALE_SNAPSHOT, severity=AlertSeverity.WARNING,
            current_qty=float(days_since_snapshot), threshold=float(_DAYS_STALE_SNAPSHOT),
            message=f"{item_name} snapshot is {days_since_snapshot} days old",
        )
    return None


def check_movement(
    item_id: str, item_name: str, days_since_movement: int,
) -> StockAlert | None:
    if days_since_movement >= _DAYS_NO_MOVEMENT:
        return StockAlert(
            item_id=item_id, item_name=item_name,
            alert_type=InventoryAlert.NO_MOVEMENT, severity=AlertSeverity.LOW,
            current_qty=float(days_since_movement), threshold=float(_DAYS_NO_MOVEMENT),
            message=f"{item_name} has not been moved in {days_since_movement} days",
        )
    return None


def notification_priority(severity: AlertSeverity) -> str:
    return {
        AlertSeverity.CRITICAL: "push",
        AlertSeverity.WARNING: "email",
        AlertSeverity.INFO: "in_app",
        AlertSeverity.LOW: "in_app",
    }.get(severity, "in_app")
