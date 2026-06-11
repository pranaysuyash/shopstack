from __future__ import annotations
from typing import Any
from shopstack.basket.models import BasketCandidate

def apply_constraints(candidate: BasketCandidate, rules: dict[str, Any]) -> BasketCandidate:
    """
    Apply hard constraints to a candidate basket.
    Rules could contain:
      - max_cost: float
      - require_fresh: bool
      - avoid_ads: bool
    """
    
    # Example logic for constraints
    if rules.get("max_cost") and candidate.total_cost > rules["max_cost"]:
        candidate.overall_score -= 1000  # heavy penalty

    if rules.get("require_fresh"):
        for item in candidate.items:
            if item.freshness == "stale":
                candidate.overall_score -= 50
                
    if rules.get("avoid_ads"):
        for item in candidate.items:
            if item.is_ad:
                candidate.overall_score -= 20
                
    return candidate
