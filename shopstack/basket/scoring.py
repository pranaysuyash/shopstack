from __future__ import annotations

from shopstack.basket.models import BasketCandidate

def calculate_scores(candidate: BasketCandidate) -> BasketCandidate:
    # Usefulness: based on proportion of found items vs missing items
    total_wanted = candidate.item_count + len(candidate.missing_items)
    if total_wanted > 0:
        candidate.usefulness_score = (candidate.item_count / total_wanted) * 100
    else:
        candidate.usefulness_score = 0.0

    # Cost score: Inverse of cost (higher is better). Just a relative heuristic.
    if candidate.total_cost > 0:
        candidate.cost_score = 10000.0 / candidate.total_cost  # Arbitrary scaling
    else:
        candidate.cost_score = 0.0

    # Freshness score: penalty for stale items
    stale_count = sum(1 for i in candidate.items if i.freshness == "stale")
    candidate.freshness_score = max(0, 100 - (stale_count * 20))

    # Waste risk score: penalty for high waste items
    high_waste = sum(1 for i in candidate.items if i.waste_risk == "high")
    candidate.waste_risk_score = max(0, 100 - (high_waste * 15))

    # Preference score: penalize sponsored ads
    ads = sum(1 for i in candidate.items if i.is_ad)
    candidate.preference_score = max(0, 100 - (ads * 10))

    # Overall score: weighted sum
    candidate.overall_score = (
        candidate.usefulness_score * 0.4 +
        candidate.cost_score * 0.3 +
        candidate.freshness_score * 0.1 +
        candidate.waste_risk_score * 0.1 +
        candidate.preference_score * 0.1
    )
    return candidate
