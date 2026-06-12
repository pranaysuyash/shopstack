from __future__ import annotations

import logging

from shopstack.basket.models import BasketCandidate, BasketItem
from shopstack.basket.scoring import calculate_scores
from shopstack.schemas.models import DecisionSet

logger = logging.getLogger(__name__)


def _prefer_freshness(
    source_id: str,
    snapshot,
    source_registry,
) -> str:
    """Resolve freshness from source registry metadata when available."""
    if source_registry is not None:
        try:
            status = source_registry.freshness_of(source_id)
            if isinstance(status, dict) and "is_stale" in status:
                return "stale" if bool(status.get("is_stale")) else "fresh"
        except Exception as exc:  # pragma: no cover - defensive compatibility
            logger.debug("Freshness lookup failed for %s: %s", source_id, exc)

    if getattr(snapshot, "is_stale", False):
        return "stale"
    return "fresh"


def _build_decision_only_basket(decision_set: DecisionSet) -> list[BasketCandidate]:
    """Build a useful fallback basket without any live snapshot data."""
    if not decision_set.buy:
        return []

    candidate = BasketCandidate(source_name="decision_only", id="basket_decision_only")
    for decision in decision_set.buy:
        candidate.items.append(
            BasketItem(
                canonical_name=decision.canonical_name,
                display_name=decision.display_name,
                source="decision_only",
                quantity=float(getattr(decision, "requested_quantity", 1.0)),
                price_inr=0.0,
                price_status="unavailable",
                notes="No active market snapshot loaded — price will be local list estimate.",
                freshness="unknown",
                waste_risk=getattr(decision, "waste_risk", "unknown"),
                is_ad=False,
                is_upgrade=False,
            )
        )
    candidate.missing_items = []
    calculate_scores(candidate)
    return [candidate]


def _load_fallback_snapshot(source_registry) -> dict[str, object]:
    """Try a deterministic single-source fallback for demo stability."""
    snapshots: dict[str, object] = {}
    if source_registry is None:
        return snapshots

    try:
        registered = list(source_registry.registered())
    except Exception:
        registered = []

    for source_id in ("swiggy", "blinkit", "zepto", "dmart"):
        if source_id not in registered:
            continue
        try:
            snapshot = source_registry.latest(source_id)
            if snapshot is None:
                snapshot = source_registry.load(source_id)
            if snapshot is not None and getattr(snapshot, "normalized_records", None):
                snapshots[source_id] = snapshot
                break
        except Exception as exc:  # pragma: no cover - data adapter failures
            logger.debug("Fallback snapshot load failed for %s: %s", source_id, exc)
            continue

    return snapshots


def optimize_baskets(
    decision_set: DecisionSet,
    source_registry=None,
) -> list[BasketCandidate]:
    """Generate and rank basket candidates based on buy decisions."""
    buy_items = decision_set.buy
    if not buy_items:
        return []

    # Map canonical names to market records across all sources
    all_snapshots: dict[str, object] = {}
    if source_registry:
        try:
            all_snapshots = source_registry.all_snapshots()
        except Exception:
            all_snapshots = {}

    if not all_snapshots:
        all_snapshots = _load_fallback_snapshot(source_registry)
    if not all_snapshots:
        # Deterministic UX: never return empty for non-empty shopping lists.
        return _build_decision_only_basket(decision_set)

    # If source snapshots exist but contain no market rows, still avoid hard-empty.
    if not any(snapshot.normalized_records for snapshot in all_snapshots.values()):
        return _build_decision_only_basket(decision_set)

    candidates: list[BasketCandidate] = []
    
    # 1. Generate a single-source basket for each source
    for source_id, snapshot in all_snapshots.items():
        if not snapshot or not snapshot.normalized_records:
            continue
        
        candidate = BasketCandidate(source_name=source_id, id=f"basket_{source_id}")
        source_records = {r.canonical_name: r for r in snapshot.normalized_records if r.is_available}
        source_freshness = _prefer_freshness(source_id, snapshot, source_registry)
        
        total_cost = 0.0
        missing = []
        
        for decision in buy_items:
            cname = decision.canonical_name
            record = source_records.get(cname)
            if record:
                item = BasketItem(
                    canonical_name=cname,
                    display_name=decision.display_name,
                    source=source_id,
                    quantity=1.0,  # default
                    price_inr=record.price_inr,
                    price_per_kg=record.price_per_kg,
                    freshness=source_freshness,
                    waste_risk=decision.waste_risk,
                    is_ad=getattr(record, "is_ad", False),
                    is_upgrade=getattr(record, "is_upgrade", False),
                    notes=record.raw_name if record.is_ad or record.is_upgrade else None,
                )
                candidate.items.append(item)
                total_cost += item.price_inr
            else:
                missing.append(cname)
                
        candidate.total_cost = total_cost
        candidate.missing_items = missing
        if candidate.items or candidate.missing_items:
            calculate_scores(candidate)
            candidates.append(candidate)
            
    # 2. Generate a mixed (cheapest overall) basket
    mixed_candidate = BasketCandidate(source_name="mixed", id="basket_mixed")
    mixed_cost = 0.0
    mixed_missing = []
    
    for decision in buy_items:
        cname = decision.canonical_name
        best_record = None
        best_source = None
        
        for source_id, snapshot in all_snapshots.items():
            if not snapshot or not snapshot.normalized_records:
                continue
            for r in snapshot.normalized_records:
                if r.canonical_name == cname and r.is_available:
                    if best_record is None or r.price_inr < best_record.price_inr:
                        best_record = r
                        best_source = source_id
                        
        if best_record and best_source:
            snapshot = all_snapshots[best_source]
            source_freshness = _prefer_freshness(best_source, snapshot, source_registry)
            mixed_candidate.items.append(
                BasketItem(
                    canonical_name=cname,
                    display_name=decision.display_name,
                    source=best_source,
                    quantity=1.0,
                    price_inr=best_record.price_inr,
                    price_per_kg=best_record.price_per_kg,
                    freshness=source_freshness,
                    waste_risk=decision.waste_risk,
                    is_ad=getattr(best_record, "is_ad", False),
                    is_upgrade=getattr(best_record, "is_upgrade", False),
                    notes=best_record.raw_name if best_record.is_ad or best_record.is_upgrade else None,
                )
            )
            mixed_cost += best_record.price_inr
        else:
            mixed_missing.append(cname)
            
    mixed_candidate.total_cost = mixed_cost
    mixed_candidate.missing_items = mixed_missing
    if mixed_candidate.items or mixed_candidate.missing_items:
        calculate_scores(mixed_candidate)
        candidates.append(mixed_candidate)
        
    # Sort by overall score descending
    candidates.sort(key=lambda c: c.overall_score, reverse=True)
    
    return candidates
