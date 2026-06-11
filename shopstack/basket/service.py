from __future__ import annotations

import logging
from typing import Any

from shopstack.basket.models import BasketCandidate, BasketItem
from shopstack.basket.scoring import calculate_scores
from shopstack.schemas.models import DecisionSet

logger = logging.getLogger(__name__)

def optimize_baskets(decision_set: DecisionSet, source_registry: Any = None) -> list[BasketCandidate]:
    """Generate and rank basket candidates based on buy decisions."""
    buy_items = decision_set.buy
    if not buy_items:
        return []

    # Map canonical names to market records across all sources
    all_snapshots = {}
    if source_registry:
        try:
            all_snapshots = source_registry.all_snapshots()
        except Exception:
            pass

    if not all_snapshots:
        # Fallback to single snapshot if available
        # But we really want multi-source
        return []

    candidates: list[BasketCandidate] = []
    
    # 1. Generate a single-source basket for each source
    for source_id, snapshot in all_snapshots.items():
        if not snapshot or not snapshot.normalized_records:
            continue
        
        candidate = BasketCandidate(source_name=source_id, id=f"basket_{source_id}")
        source_records = {r.canonical_name: r for r in snapshot.normalized_records if r.is_available}
        
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
                    freshness="stale" if getattr(snapshot, "is_stale", False) else "fresh",
                    waste_risk=decision.waste_risk,
                    is_ad=getattr(record, "is_ad", False),
                    is_upgrade=getattr(record, "is_upgrade", False),
                )
                candidate.items.append(item)
                total_cost += item.price_inr
            else:
                missing.append(cname)
                
        candidate.total_cost = total_cost
        candidate.missing_items = missing
        
        if candidate.items:
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
            item = BasketItem(
                canonical_name=cname,
                display_name=decision.display_name,
                source=best_source,
                quantity=1.0,
                price_inr=best_record.price_inr,
                price_per_kg=best_record.price_per_kg,
                freshness="stale" if getattr(snapshot, "is_stale", False) else "fresh",
                waste_risk=decision.waste_risk,
                is_ad=getattr(best_record, "is_ad", False),
                is_upgrade=getattr(best_record, "is_upgrade", False),
            )
            mixed_candidate.items.append(item)
            mixed_cost += item.price_inr
        else:
            mixed_missing.append(cname)
            
    mixed_candidate.total_cost = mixed_cost
    mixed_candidate.missing_items = mixed_missing
    
    if mixed_candidate.items:
        calculate_scores(mixed_candidate)
        candidates.append(mixed_candidate)
        
    # Sort by overall score descending
    candidates.sort(key=lambda c: c.overall_score, reverse=True)
    
    return candidates
