from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from shopstack.market.schema import NormalizedMarketRecord


@dataclass
class ComparisonResult:
    canonical_name: str
    best_record: Optional[NormalizedMarketRecord]
    all_records: List[NormalizedMarketRecord]
    freshness_warnings: List[str]
    ad_warnings: List[str]
    confidence_score: float


def compare_records(
    canonical_name: str,
    records: List[NormalizedMarketRecord],
    today: Optional[date] = None
) -> ComparisonResult:
    """Compare multiple market records to find the best option."""
    if today is None:
        today = date.today()

    best_record = None
    freshness_warnings = []
    ad_warnings = []
    confidence_score = 1.0

    if not records:
        return ComparisonResult(
            canonical_name=canonical_name,
            best_record=None,
            all_records=[],
            freshness_warnings=[],
            ad_warnings=[],
            confidence_score=0.0
        )

    # Filter out unavailable items
    available_records = [r for r in records if r.is_available]
    if not available_records:
        confidence_score -= 0.5
    
    # Check for ads and freshness
    for rec in records:
        if rec.is_ad:
            ad_warnings.append(f"Record from {rec.source} is marked as an ad.")
        try:
            captured_date = date.fromisoformat(rec.captured_at[:10])
            if (today - captured_date).days > 1:
                freshness_warnings.append(
                    f"Data from {rec.source} is {(today - captured_date).days} days old."
                )
        except (ValueError, TypeError):
            freshness_warnings.append(f"Invalid date format for record from {rec.source}.")
            confidence_score -= 0.1
    
    # Sort by price_per_kg or price_inr
    if available_records:
        def sort_key(r: NormalizedMarketRecord):
            # Prefer price_per_kg if available, else use price_inr / normalized_quantity
            if r.price_per_kg:
                return r.price_per_kg
            if r.price_per_100g:
                return r.price_per_100g * 10
            if r.price_per_piece:
                return r.price_per_piece
            if r.normalized_quantity and r.normalized_quantity > 0:
                return r.price_inr / r.normalized_quantity
            return r.price_inr
        
        sorted_records = sorted(available_records, key=sort_key)
        best_record = sorted_records[0]
        
        # Penalize confidence if best record is an ad or stale
        if best_record.is_ad:
            confidence_score -= 0.2
        try:
            captured_date = date.fromisoformat(best_record.captured_at[:10])
            if (today - captured_date).days > 1:
                confidence_score -= 0.3
        except Exception:
            pass
            
        if len(sorted_records) < 2:
            confidence_score -= 0.1  # Less confidence if only one source

    return ComparisonResult(
        canonical_name=canonical_name,
        best_record=best_record,
        all_records=records,
        freshness_warnings=list(set(freshness_warnings)),
        ad_warnings=list(set(ad_warnings)),
        confidence_score=max(0.0, min(1.0, confidence_score))
    )
