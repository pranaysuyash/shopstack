"""Inventory alert classification — expiring soon, low stock, needs confirmation.

Pure business logic — no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AlertLevel(Enum):
    """Severity levels for inventory alerts."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class InventoryAlert:
    """A single inventory alert."""
    alert_id: str
    level: AlertLevel
    kind: str           # "expiring_soon" | "low_stock" | "needs_confirmation" | "price_drop"
    canonical_name: str
    display_name: str
    message: str
    detail: str = ""
    confidence: float = 1.0
    action_label: str = ""
    action_target: str = ""

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "level": self.level.value,
            "kind": self.kind,
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "message": self.message,
            "detail": self.detail,
            "confidence": self.confidence,
            "action_label": self.action_label,
            "action_target": self.action_target,
        }


def classify_inventory_alert(
    canonical_name: str,
    display_name: str,
    *,
    days_until_expiry: int | None = None,
    quantity: float = 0.0,
    min_quantity: float = 0.0,
    confidence: float = 1.0,
    purchase_date: str = "",
    item_id: str = "",
) -> InventoryAlert | None:
    """Classify whether an inventory item needs an alert.

    Returns an InventoryAlert if the item triggers any alert condition,
    or None if everything looks fine.

    Priority: expiring_soon > needs_confirmation > low_stock.
    """
    alert_id = f"alert_{item_id or canonical_name}"

    # Expiring soon
    if days_until_expiry is not None:
        if days_until_expiry < 0:
            return InventoryAlert(
                alert_id=alert_id,
                level=AlertLevel.CRITICAL,
                kind="expiring_soon",
                canonical_name=canonical_name,
                display_name=display_name,
                message=f"{display_name} expired {abs(days_until_expiry)} days ago",
                detail="Discard or check if still safe to use.",
                confidence=confidence,
                action_label="Remove from inventory",
                action_target=item_id,
            )
        if days_until_expiry <= 2:
            return InventoryAlert(
                alert_id=alert_id,
                level=AlertLevel.CRITICAL,
                kind="expiring_soon",
                canonical_name=canonical_name,
                display_name=display_name,
                message=f"{display_name} expires in {days_until_expiry} day{'s' if days_until_expiry != 1 else ''}",
                detail="Use today or tomorrow for best quality.",
                confidence=confidence,
                action_label="Mark as used",
                action_target=item_id,
            )
        if days_until_expiry <= 5:
            return InventoryAlert(
                alert_id=alert_id,
                level=AlertLevel.WARNING,
                kind="expiring_soon",
                canonical_name=canonical_name,
                display_name=display_name,
                message=f"{display_name} expires in {days_until_expiry} days",
                detail="Plan to use this week.",
                confidence=confidence,
                action_label="Plan a meal",
                action_target=item_id,
            )

    # Needs confirmation (low confidence)
    if confidence < 0.4:
        return InventoryAlert(
            alert_id=alert_id,
            level=AlertLevel.WARNING,
            kind="needs_confirmation",
            canonical_name=canonical_name,
            display_name=display_name,
            message=f"Is {display_name} still available?",
            detail="We're not sure — please confirm.",
            confidence=confidence,
            action_label="Confirm",
            action_target=item_id,
        )

    # Low stock
    if min_quantity > 0 and quantity <= min_quantity and quantity > 0:
        return InventoryAlert(
            alert_id=alert_id,
            level=AlertLevel.INFO,
            kind="low_stock",
            canonical_name=canonical_name,
            display_name=display_name,
            message=f"{display_name} running low ({quantity:.0f} left)",
            detail="Consider adding to your shopping list.",
            confidence=confidence,
            action_label="Add to basket",
            action_target=item_id,
        )

    return None
