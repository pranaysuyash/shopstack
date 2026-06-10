"""Decision rules — classification logic for household shopping decisions.

This module computes buy / skip / use-soon / optional / compare / wait
decisions from inventory state, shopping list, and market signals. Pure logic —
no HTML rendering, no database access except through passed-in interfaces.

Every decision produces a DecisionResult (from shopstack.schemas.models).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from shopstack.schemas.models import (
    DecisionEvidence,
    DecisionResult,
    DecisionSet,
    DecisionWarning,
)
from shopstack.decisions.types import Decision, ACTION_MAP
from shopstack.persistence.database import Database
from shopstack.repos.inventory import InventoryRepo

logger = logging.getLogger(__name__)

_LOW_STOCK_THRESHOLD = 0.5
_USE_SOON_DAYS = 3
_RECENT_PURCHASE_DAYS = 2


def classify_all(
    db: Database,
    inventory: InventoryRepo,
    market_snapshot=None,
    source_registry: Any = None,
) -> DecisionSet:
    active_inv = [lot for lot in db.get_inventory() if lot.status == "active"]
    use_soon_items = inventory.get_use_soon(days=_USE_SOON_DAYS).get("items", [])
    active_list = db.get_active_shopping_list()
    purchases = db.get_purchase_events(limit=50)
    recent_dates: set[date] = set()
    for p in purchases:
        try:
            pdate = p.timestamp.date() if hasattr(p.timestamp, "date") else p.timestamp
            if pdate and pdate >= date.today() - timedelta(days=_RECENT_PURCHASE_DAYS):
                recent_dates.add(pdate)
        except Exception:
            pass

    use_soon_names = {item.get("canonical_name", "") for item in use_soon_items}
    list_names: set[str] = set()
    if active_list and active_list.items:
        list_names = {item.canonical_name for item in active_list.items if item.status in ("pending", "seen")}

    market_by_canonical: dict[str, Any] = {}
    market_evidence_map: dict[str, Any] = {}

    # Build market data from single snapshot or multi-source registry
    _multi_source_market_data(market_snapshot, source_registry, market_by_canonical, market_evidence_map)

    seen: set[str] = set()
    decisions: list[DecisionResult] = []

    for lot in active_inv:
        cname = lot.canonical_name
        if cname in seen:
            continue
        seen.add(cname)

        meta = _get_produce_meta(cname)
        market = market_by_canonical.get(cname)

        use_soon_match = cname in use_soon_names
        low_stock = lot.quantity <= _LOW_STOCK_THRESHOLD or lot.status == "low"
        on_list = cname in list_names
        recently_bought = lot.purchase_date and lot.purchase_date in recent_dates

        action, reason_str, confidence = _classify(
            quantity=lot.quantity,
            unit=lot.unit,
            low_stock=low_stock,
            use_soon=use_soon_match,
            on_list=on_list,
            recently_bought=bool(recently_bought),
            has_market=bool(market),
            waste_risk=meta.waste_risk if meta else "unknown",
        )

        evidence_list: list[DecisionEvidence] = []
        if recently_bought:
            evidence_list.append(DecisionEvidence(source="purchase_history", value=lot.purchase_date.isoformat() if lot.purchase_date else "", confidence=0.9))
        if market:
            evidence_list.append(DecisionEvidence(source="market_snapshot", value=market.price_inr, confidence=0.7, captured_at=market.captured_at, is_stale=getattr(market, 'is_stale', False)))

        data_freshness, data_freshness_label = _freshness_for(cname, market_evidence_map)
        decisions.append(DecisionResult(
            canonical_name=cname,
            display_name=lot.display_name,
            action=action,
            confidence=confidence,
            reasons=[reason_str],
            evidence=evidence_list,
            quantity_at_home=lot.quantity,
            unit=lot.unit,
            market_price=market.price_inr if market else None,
            market_price_per_kg=market.price_per_kg if market else None,
            market_available=bool(market),
            market_raw_size=market.raw_size if market else "",
            shopping_list_status="on_list" if on_list else "",
            waste_risk=meta.waste_risk if meta else "unknown",
            shelf_life_days=meta.shelf_life_days if meta else 0,
            last_purchase_date=lot.purchase_date,
            location=lot.storage_location_id or "",
            data_freshness=data_freshness,
            data_freshness_label=data_freshness_label,
        ))

    if active_list and active_list.items:
        for item in active_list.items:
            if item.status not in ("pending", "seen"):
                continue
            if item.canonical_name in seen:
                continue
            seen.add(item.canonical_name)

            inv_match = next((lot for lot in active_inv if lot.canonical_name == item.canonical_name), None)
            meta = _get_produce_meta(item.canonical_name)
            market = market_by_canonical.get(item.canonical_name)
            qty = inv_match.quantity if inv_match else 0
            low_stock = qty <= _LOW_STOCK_THRESHOLD
            use_soon_match = item.canonical_name in use_soon_names

            if inv_match is None:
                action = Decision.BUY.value
                reason_str = "On your list, not in inventory"
                confidence = 0.9
            else:
                action, reason_str, confidence = _classify(
                    quantity=qty,
                    unit=inv_match.unit,
                    low_stock=low_stock,
                    use_soon=use_soon_match,
                    on_list=True,
                    recently_bought=False,
                    has_market=bool(market),
                    waste_risk=meta.waste_risk if meta else "unknown",
                )

            data_freshness, data_freshness_label = _freshness_for(item.canonical_name, market_evidence_map)
            decisions.append(DecisionResult(
                canonical_name=item.canonical_name,
                display_name=item.canonical_name.replace("_", " ").title(),
                action=action,
                confidence=confidence,
                reasons=[reason_str],
                quantity_at_home=qty,
                unit=inv_match.unit if inv_match else "unit",
                market_price=market.price_inr if market else None,
                market_price_per_kg=market.price_per_kg if market else None,
                market_available=bool(market),
                market_raw_size=market.raw_size if market else "",
                shopping_list_status="on_list",
                waste_risk=meta.waste_risk if meta else "unknown",
                shelf_life_days=meta.shelf_life_days if meta else 0,
                last_purchase_date=inv_match.purchase_date if inv_match else None,
                location=inv_match.storage_location_id if inv_match else "",
                data_freshness=data_freshness,
                data_freshness_label=data_freshness_label,
            ))

    if market_snapshot is not None:
        market_source_name = getattr(market_snapshot, 'source', 'market')
        for cname, r in market_by_canonical.items():
            if cname in seen:
                continue
            seen.add(cname)

            meta = _get_produce_meta(cname)
            price_ppk = r.price_per_kg or 0
            if price_ppk <= 0:
                continue

            all_weighted = [
                rec for rec in market_snapshot.normalized_records
                if rec.canonical_name == cname and rec.is_weight_based and not rec.is_combo
            ]
            if len(all_weighted) >= 2:
                prices = [rec.price_per_kg for rec in all_weighted if rec.price_per_kg]
                if prices and price_ppk <= min(prices) * 1.05:
                    action = Decision.OPTIONAL.value
                    reason_str = f"Good price: \u20b9{price_ppk:.0f}/kg on {market_source_name}"
                    confidence = 0.7
                else:
                    action = Decision.WATCH.value
                    reason_str = f"Available at \u20b9{price_ppk:.0f}/kg on {market_source_name}"
                    confidence = 0.5
            else:
                action = Decision.WATCH.value
                reason_str = f"Available at \u20b9{price_ppk:.0f}/kg on {market_source_name}"
                confidence = 0.5

            data_freshness, data_freshness_label = _freshness_for(cname, market_evidence_map)
            decisions.append(DecisionResult(
                canonical_name=cname,
                display_name=cname.replace("_", " ").title(),
                action=ACTION_MAP.get(action, "wait"),
                confidence=confidence,
                reasons=[reason_str],
                quantity_at_home=0,
                unit="",
                market_price=r.price_inr,
                market_price_per_kg=r.price_per_kg,
                market_available=True,
                market_raw_size=r.raw_size,
                waste_risk=meta.waste_risk if meta else "unknown",
                shelf_life_days=meta.shelf_life_days if meta else 0,
                data_freshness=data_freshness,
                data_freshness_label=data_freshness_label,
            ))

    return DecisionSet(decisions=decisions)


def _classify(
    quantity: float,
    unit: str,
    low_stock: bool,
    use_soon: bool,
    on_list: bool,
    recently_bought: bool,
    has_market: bool,
    waste_risk: str,
) -> tuple[str, str, float]:

    if use_soon and quantity > 0:
        if low_stock:
            return Decision.USE_SOON.value, "Use remaining before it expires, then restock", 0.85
        return Decision.USE_SOON.value, "Use existing before buying more", 0.9

    if low_stock and quantity <= 0:
        if has_market:
            return Decision.BUY.value, "Out of stock, available on Swiggy", 0.9
        return Decision.BUY.value, "Out of stock", 0.85

    if low_stock:
        if has_market:
            return Decision.BUY.value, f"Running low ({quantity} {unit} left)", 0.85
        return Decision.BUY.value, f"Running low ({quantity} {unit} left)", 0.8

    if on_list and quantity > 0:
        if waste_risk == "high":
            return Decision.SKIP.value, "Already have enough, high waste risk if you buy more", 0.8
        return Decision.SKIP.value, "Already have enough at home", 0.75

    if quantity > 0 and not low_stock and not use_soon:
        if recently_bought:
            return Decision.SKIP.value, "Recently purchased", 0.8
        if waste_risk == "high":
            return Decision.SKIP.value, "Stocked, high waste risk", 0.7
        return Decision.SKIP.value, "Well stocked", 0.7

    return Decision.WATCH.value, "Monitor", 0.5


def _get_produce_meta(canonical_name: str):
    try:
        from shopstack.market.metadata import get_produce_metadata
        return get_produce_metadata(canonical_name)
    except Exception:
        return None


def _freshness_for(cname: str, evidence_map: dict[str, Any]) -> tuple[str, str]:
    """Derive (data_freshness, data_freshness_label) from market evidence."""
    ev = evidence_map.get(cname)
    if not ev:
        return "unknown", ""
    age = ev.get("age_days", 0)
    is_stale = ev.get("is_stale", False)
    freshness = "stale" if is_stale else "fresh"
    captured = ev.get("captured_at")
    if captured:
        try:
            from datetime import datetime
            if isinstance(captured, str):
                captured = datetime.fromisoformat(captured)
            label = f"Snapshot from {captured.strftime('%-d %b %Y')}"
        except Exception:
            label = ""
    else:
        label = ""
    return freshness, label


def classify_inventory_comparison(
    total_have: float, requested_qty: float, unit: str, is_use_soon: bool
) -> tuple[str, str]:
    """Return (decision, reason) from raw inventory comparison facts.

    Thresholds:
      >= 2x requested → skip (already plenty)
      >= 1x requested → optional (have enough, buy only if needed)
      < 1x requested  → buy (need more)
    """
    if total_have <= 0:
        return "buy", f"Not found in inventory."

    shortfall = max(requested_qty - total_have, 0)
    surplus_ratio = total_have / requested_qty if requested_qty > 0 else float("inf")

    if surplus_ratio >= 2:
        return "skip", f"Already have {total_have} {unit} at home."
    if surplus_ratio >= 1:
        return "optional", f"Have {total_have} {unit}. Only buy if needed."
    return "buy", f"Have only {total_have} {unit}. Buy {shortfall} {unit}."


def _multi_source_market_data(
    market_snapshot,
    source_registry,
    market_by_canonical: dict,
    market_evidence_map: dict,
) -> None:
    """Populate market_by_canonical and market_evidence_map from single snapshot or multi-source registry."""
    if source_registry is not None:
        try:
            all_snapshots = source_registry.all_snapshots()
            for source_id, snap in all_snapshots.items():
                if snap and snap.normalized_records:
                    for r in snap.normalized_records:
                        if r.is_available and r.is_weight_based and not r.is_combo:
                            existing = market_by_canonical.get(r.canonical_name)
                            if existing is None or (r.price_per_kg and existing.price_per_kg and r.price_per_kg < existing.price_per_kg):
                                market_by_canonical[r.canonical_name] = r

            for source_id, snap in all_snapshots.items():
                if not snap or not snap.normalized_records:
                    continue
                for cname in set(market_by_canonical.keys()):
                    records = [r for r in snap.normalized_records if r.canonical_name == cname]
                    if not records:
                        continue
                    available = [r for r in records if r.is_available]
                    sold_out = [r for r in records if not r.is_available]
                    best = market_by_canonical.get(cname)
                    existing_evidence = market_evidence_map.get(cname)
                    price_per_kg = best.price_per_kg if best else None
                    if existing_evidence:
                        if price_per_kg is not None and existing_evidence.get("best_value_per_kg") is not None:
                            if price_per_kg < existing_evidence["best_value_per_kg"]:
                                existing_evidence["source"] = source_id
                                existing_evidence["best_value_price"] = best.price_inr if best else None
                                existing_evidence["best_value_per_kg"] = price_per_kg
                    else:
                        try:
                            from shopstack.market.sources._repository import snapshot_freshness
                            freshness = snapshot_freshness(snap)
                        except Exception:
                            freshness = {"age_days": 0, "is_stale": False}
                        market_evidence_map[cname] = {
                            "source": source_id,
                            "captured_at": snap.captured_at,
                            "age_days": freshness.get("age_days", 0),
                            "is_stale": freshness.get("is_stale", True),
                            "best_value_price": best.price_inr if best else None,
                            "best_value_per_kg": price_per_kg,
                        }
        except Exception:
            logger.info("Multi-source market data unavailable, falling back to single snapshot", exc_info=True)
            pass

    # Fallback: single snapshot path
    if market_snapshot is not None and not market_by_canonical:
        for r in market_snapshot.normalized_records:
            if r.is_available and r.is_weight_based and not r.is_combo:
                existing = market_by_canonical.get(r.canonical_name)
                if existing is None or (r.price_per_kg and existing.price_per_kg and r.price_per_kg < existing.price_per_kg):
                    market_by_canonical[r.canonical_name] = r
        for cname in set(market_by_canonical.keys()):
            records = [r for r in market_snapshot.normalized_records if r.canonical_name == cname]
            available = [r for r in records if r.is_available]
            sold_out = [r for r in records if not r.is_available]
            best = market_by_canonical.get(cname)
            freshness = _build_freshness(market_snapshot)
            market_evidence_map[cname] = {
                "source": market_snapshot.source,
                "captured_at": market_snapshot.captured_at,
                "age_days": freshness.get("age_days", 0),
                "is_stale": freshness.get("is_stale", True),
                "best_value_price": best.price_inr if best else None,
                "best_value_per_kg": best.price_per_kg if best else None,
            }


def _build_freshness(market_snapshot) -> dict[str, Any]:
    try:
        from shopstack.market.sources.swiggy import snapshot_freshness
        return snapshot_freshness(market_snapshot)
    except Exception:
        return {"age_days": 0, "is_stale": False, "label": "unknown"}


def detect_purchase_cadence(db: Database) -> dict[str, dict[str, Any]]:
    purchases = db.get_purchase_events(limit=200)
    by_item: dict[str, list[Any]] = {}
    for p in purchases:
        try:
            dt = p.timestamp if hasattr(p.timestamp, "year") else None
        except Exception:
            dt = None
        if dt is None:
            continue
        by_item.setdefault(p.canonical_name, []).append(p)

    cadence: dict[str, dict[str, Any]] = {}
    for cname, events in by_item.items():
        events.sort(key=lambda e: e.timestamp, reverse=True)
        if len(events) < 2:
            continue
        intervals = []
        for i in range(len(events) - 1):
            d1 = events[i].timestamp.date() if hasattr(events[i].timestamp, "date") else events[i].timestamp
            d2 = events[i + 1].timestamp.date() if hasattr(events[i + 1].timestamp, "date") else events[i + 1].timestamp
            if d1 and d2:
                gap = (d1 - d2).days
                if gap > 0:
                    intervals.append(gap)
        if not intervals:
            continue
        avg_interval = sum(intervals) / len(intervals)
        last = events[0].timestamp.date() if hasattr(events[0].timestamp, "date") else events[0].timestamp
        next_expected = last + timedelta(days=round(avg_interval))
        typical_qty = sum(e.quantity for e in events) / len(events)
        cadence[cname] = {
            "avg_interval_days": round(avg_interval, 1),
            "last_bought": last,
            "typical_qty": round(typical_qty, 2),
            "typical_unit": events[0].unit,
            "next_expected": next_expected,
            "purchase_count": len(events),
        }
    return cadence


def detect_waste_patterns(db: Database) -> list[dict[str, Any]]:
    cadence = detect_purchase_cadence(db)
    waste_signals: list[dict[str, Any]] = []
    inv = db.get_inventory()

    for cname, info in cadence.items():
        if info["purchase_count"] < 3:
            continue
        meta = _get_produce_meta(cname)
        waste_risk = meta.waste_risk if meta else "unknown"
        if waste_risk != "high":
            continue

        lot = next((lot for lot in inv if lot.canonical_name == cname and lot.status == "active"), None)
        overstocked = lot and lot.quantity > 1.0
        if overstocked or info["avg_interval_days"] < 2:
            waste_signals.append({
                "canonical_name": cname,
                "display_name": cname.replace("_", " ").title(),
                "reason": f"High waste-risk produce bought every {info['avg_interval_days']:.0f} days",
                "current_quantity": lot.quantity if lot else 0,
                "unit": lot.unit if lot else "unit",
                "waste_risk": waste_risk,
                "avg_interval_days": info["avg_interval_days"],
            })

    return waste_signals


def check_swiggy_availability(canonical_names: list[str]) -> dict[str, dict[str, Any]]:
    try:
        from shopstack.market.sources.swiggy import load_snapshot
        snap = load_snapshot()
    except Exception:
        return {}

    result: dict[str, dict[str, Any]] = {}
    all_records: dict[str, list[Any]] = {}
    for r in snap.normalized_records:
        all_records.setdefault(r.canonical_name, []).append(r)

    for cname in canonical_names:
        records = all_records.get(cname, [])
        if not records:
            continue
        available = [r for r in records if r.is_available]
        sold_out = [r for r in records if not r.is_available]
        if available:
            best = min(
                (r for r in available if r.is_weight_based and not r.is_combo and r.price_per_kg),
                key=lambda r: r.price_per_kg,
                default=available[0],
            )
            result[cname] = {
                "available": True,
                "price": best.price_inr,
                "price_per_kg": best.price_per_kg,
                "raw_size": best.raw_size,
            }
        elif sold_out:
            result[cname] = {
                "available": False,
                "price": sold_out[0].price_inr,
                "price_per_kg": sold_out[0].price_per_kg,
                "raw_size": sold_out[0].raw_size,
            }
    return result
