"""Enhanced decision engine services.

The review (§3.1) identifies this as the keystone — the product becomes real
when all roads lead to a decision engine that answers:

  For this household, given inventory + preferences + market data +
  price memory + freshness, what should the user buy, skip, use soon,
  compare, or add to basket?

Every decision produces a structured DecisionResult with:
  - action
  - confidence
  - reasons[]
  - evidence[]
  - warnings[]
  - data_freshness

These services are pure logic — no UI, no Gradio, no HTML.
They consume typed models and return typed results.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from shopstack.schemas.models import (
    DecisionEvidence,
    DecisionResult,
    DecisionWarning,
    FreshnessStatus,
    new_id,
)
from shopstack.services.freshness import (
    classify_freshness,
    classify_snapshot_freshness,
    FreshnessReport,
)

logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────────────────
_LOW_STOCK_THRESHOLD = 0.5
_USE_SOON_DAYS = 3
_RECENT_PURCHASE_DAYS = 2
_COMPARISON_SPREAD_THRESHOLD = 0.15


def should_buy(
    canonical_name: str,
    display_name: str,
    quantity_at_home: float = 0.0,
    unit: str = "unit",
    market_record=None,
    freshness: FreshnessReport | None = None,
    on_shopping_list: bool = False,
    is_staple: bool = False,
    waste_risk: str = "unknown",
    purchase_cadence_days: float | None = None,
    last_purchase_date: date | None = None,
    recently_bought: bool = False,
) -> DecisionResult | None:
    """Decide if an item should be bought.

    Returns a DecisionResult with action="buy" if conditions are met,
    or None if the item should not be recommended for purchase.

    Decision logic:
      - Out of stock AND available on market → BUY (high confidence)
      - Low stock AND available → BUY (good confidence)
      - On shopping list AND not in inventory → BUY
      - Staple running low → BUY (boosted confidence)
      - Recently purchased → DO NOT recommend buy (return None)
    """
    if recently_bought:
        return None  # skip — already bought recently

    reasons: list[str] = []
    evidence: list[DecisionEvidence] = []
    warnings: list[DecisionWarning] = []
    confidence = 0.0

    has_market = market_record is not None
    market_available = has_market and getattr(market_record, "is_available", True)
    market_price = getattr(market_record, "price_inr", None) if has_market else None
    market_ppk = getattr(market_record, "price_per_kg", None) if has_market else None
    market_raw_size = getattr(market_record, "raw_size", "") if has_market else ""

    # ── Evidence ──
    evidence.append(DecisionEvidence(
        source="inventory",
        value=f"{quantity_at_home} {unit}",
        confidence=0.95,
    ))

    if has_market:
        evidence.append(DecisionEvidence(
            source="market_snapshot",
            value=market_price,
            confidence=0.7 if not (freshness and freshness.is_stale) else 0.4,
            captured_at=freshness.captured_at if freshness else None,
            is_stale=freshness.is_stale if freshness else False,
        ))

    if on_shopping_list:
        evidence.append(DecisionEvidence(source="shopping_list", value="on_list", confidence=0.9))
        reasons.append("On your shopping list")

    if quantity_at_home <= 0:
        reasons.append("Out of stock at home")
        confidence = 0.9
        if market_available:
            reasons.append("Available on market")
            confidence = 0.92
        else:
            warnings.append(DecisionWarning(
                code="no_availability",
                message="Not available on any tracked market",
                severity="warning",
            ))
            confidence = 0.7
    elif quantity_at_home <= _LOW_STOCK_THRESHOLD:
        reasons.append(f"Running low ({quantity_at_home} {unit} left)")
        confidence = 0.82
        if is_staple:
            reasons.append("Household staple — restock recommended")
            confidence = 0.88
    else:
        return None  # enough stock, don't recommend buy

    # ── Waste risk adjustment ──
    if waste_risk == "high" and quantity_at_home > 0:
        warnings.append(DecisionWarning(
            code="waste_risk",
            message=f"High waste risk — you have {quantity_at_home} {unit} already",
            severity="warning",
        ))
        confidence *= 0.85

    # ── Freshness warning ──
    if freshness and freshness.is_stale:
        warnings.append(DecisionWarning(
            code="stale_data",
            message=freshness.warning,
            severity="warning",
        ))

    # ── Price signal ──
    if market_ppk is not None and market_ppk > 0:
        reasons.append(f"Market price: ₹{market_price:.0f} (₹{market_ppk:.0f}/kg)")

    # ── Ad/upgrade trust signal (§3.7): sponsored listings reduce confidence ──
    if has_market:
        record_is_ad = getattr(market_record, "is_ad", False)
        record_is_upgrade = getattr(market_record, "is_upgrade", False)
        tag = getattr(market_record, "tag", "") or ""
        if record_is_ad or record_is_upgrade or "ad" in tag.lower():
            warnings.append(DecisionWarning(
                code="sponsored_listing",
                message="This product is a sponsored/ad listing — verify price against other sources.",
                severity="info",
            ))
            if record_is_ad:
                reasons.append("Sponsored listing — verify price independently")
                confidence *= 0.85  # reduce confidence for ads

    confidence = min(confidence, 0.95)

    return DecisionResult(
        canonical_name=canonical_name,
        display_name=display_name,
        action="buy",
        confidence=round(confidence, 2),
        reasons=reasons,
        evidence=evidence,
        warnings=warnings,
        data_freshness=freshness.status if freshness else "unknown",
        data_freshness_label=freshness.label if freshness else "",
        quantity_at_home=quantity_at_home,
        unit=unit,
        market_price=market_price,
        market_price_per_kg=market_ppk,
        market_available=market_available,
        waste_risk=waste_risk,
    )


def should_skip(
    canonical_name: str,
    display_name: str,
    quantity_at_home: float = 0.0,
    unit: str = "unit",
    waste_risk: str = "unknown",
    on_shopping_list: bool = False,
    recently_bought: bool = False,
    market_record=None,
    freshness: FreshnessReport | None = None,
) -> DecisionResult | None:
    """Decide if an item should be skipped (not bought today).

    Skip logic must be nuanced per the review:
      - already have enough
      - recently purchased
      - high waste risk
      - on list but well-stocked

    Returns a DecisionResult with action="skip", or None if no skip applies.
    """
    reasons: list[str] = []
    evidence: list[DecisionEvidence] = []
    warnings: list[DecisionWarning] = []
    confidence = 0.0

    evidence.append(DecisionEvidence(
        source="inventory",
        value=f"{quantity_at_home} {unit}",
        confidence=0.95,
    ))

    if quantity_at_home <= 0:
        return None  # can't skip what you don't have

    if recently_bought:
        reasons.append("Recently purchased — no need to rebuy")
        evidence.append(DecisionEvidence(source="purchase_history", value="recent", confidence=0.9))
        confidence = 0.85
    elif waste_risk == "high" and quantity_at_home > 1.0:
        reasons.append(f"Stocked ({quantity_at_home} {unit}), high waste risk if you buy more")
        confidence = 0.80
    elif on_shopping_list and quantity_at_home > _LOW_STOCK_THRESHOLD:
        reasons.append(f"Already have {quantity_at_home} {unit} — well stocked")
        confidence = 0.75
    elif quantity_at_home > _LOW_STOCK_THRESHOLD and not on_shopping_list:
        return None  # not on list and has stock — skip doesn't apply
    else:
        return None

    if waste_risk == "high":
        warnings.append(DecisionWarning(
            code="waste_risk",
            message="Buying more may lead to waste",
            severity="info",
        ))

    return DecisionResult(
        canonical_name=canonical_name,
        display_name=display_name,
        action="skip",
        confidence=round(min(confidence, 0.95), 2),
        reasons=reasons,
        evidence=evidence,
        warnings=warnings,
        data_freshness=freshness.status if freshness else "unknown",
        data_freshness_label=freshness.label if freshness else "",
        quantity_at_home=quantity_at_home,
        unit=unit,
        waste_risk=waste_risk,
    )


def use_soon(
    canonical_name: str,
    display_name: str,
    quantity_at_home: float = 0.0,
    unit: str = "unit",
    shelf_life_days: int = 0,
    purchase_date: date | None = None,
    waste_risk: str = "unknown",
    today: date | None = None,
) -> DecisionResult | None:
    """Decide if an item should be used soon (approaching expiry / spoilage).

    Use-soon creates daily retention — users may not shop every day but
    can check "what should I use soon?" often.

    Returns a DecisionResult with action="use_soon", or None if no urgency.
    """
    current = today or date.today()

    if quantity_at_home <= 0:
        return None

    reasons: list[str] = []
    evidence: list[DecisionEvidence] = []
    warnings: list[DecisionWarning] = []
    confidence = 0.0

    # ── Shelf life based ──
    if shelf_life_days > 0 and purchase_date is not None:
        age_days = (current - purchase_date).days
        remaining = shelf_life_days - age_days

        evidence.append(DecisionEvidence(
            source="shelf_life",
            value=f"{remaining} days remaining (of {shelf_life_days})",
            confidence=0.85,
        ))

        if remaining <= 0:
            reasons.append(f"Past expected shelf life ({abs(remaining)} days overdue)")
            confidence = 0.95
        elif remaining <= 1:
            reasons.append("Use today — at end of expected shelf life")
            confidence = 0.90
        elif remaining <= _USE_SOON_DAYS:
            reasons.append(f"Use within {remaining} days for best freshness")
            confidence = 0.80
        else:
            return None  # still fresh, no urgency
    elif waste_risk == "high" and quantity_at_home > 0:
        # ── Waste risk heuristic when no shelf life data ──
        reasons.append(f"High waste-risk item — use existing {quantity_at_home} {unit} before buying more")
        evidence.append(DecisionEvidence(source="produce_metadata", value="high_waste_risk", confidence=0.7))
        confidence = 0.72
    elif shelf_life_days > 0 and purchase_date is None and quantity_at_home > 0:
        # ── Known shelf life but no purchase date — cannot verify freshness ──
        reasons.append(f"Item has {shelf_life_days}-day shelf life but no purchase date recorded")
        evidence.append(DecisionEvidence(source="produce_metadata", value=f"shelf_life={shelf_life_days}d", confidence=0.5))
        warnings.append(DecisionWarning(
            code="unknown_purchase_date",
            message="Purchase date unknown — cannot verify freshness",
            severity="info",
        ))
            confidence = 0.55
    else:
        return None  # no use-soon signal

    return DecisionResult(
        canonical_name=canonical_name,
        display_name=display_name,
        action="use_soon",
        confidence=round(min(confidence, 0.95), 2),
        reasons=reasons,
        evidence=evidence,
        warnings=warnings,
        data_freshness="live",
        quantity_at_home=quantity_at_home,
        unit=unit,
        waste_risk=waste_risk,
        shelf_life_days=shelf_life_days,
    )


def compare_candidates(
    canonical_name: str,
    display_name: str,
    available_records: list,
    all_records: list,
    freshness: FreshnessReport | None = None,
) -> DecisionResult | None:
    """Decide if an item warrants comparison across variants/packs.

    Comparison is warranted when:
      - Multiple weight-based options exist for the same canonical product
      - Price spread is significant (>15% between cheapest and most expensive)
      - Both available and sold-out variants exist

    Returns a DecisionResult with action="compare", or None.
    """
    if len(available_records) < 2:
        return None

    weight_records = [
        r for r in available_records
        if getattr(r, "is_weight_based", False)
        and not getattr(r, "is_combo", False)
        and getattr(r, "price_per_kg", None) is not None
    ]

    if len(weight_records) < 2:
        return None

    prices_per_kg = [r.price_per_kg for r in weight_records]
    min_ppk = min(prices_per_kg)
    max_ppk = max(prices_per_kg)

    # ── Price spread check ──
    if min_ppk <= 0 or max_ppk <= 0:
        return None
    spread = (max_ppk - min_ppk) / min_ppk
    if spread < _COMPARISON_SPREAD_THRESHOLD:
        return None  # prices too similar, no real comparison needed

    reasons = [
        f"{len(weight_records)} options available with {spread:.0%} price spread",
        f"Best: ₹{min_ppk:.0f}/kg vs ₹{max_ppk:.0f}/kg",
    ]
    evidence = [
        DecisionEvidence(source="market_snapshot", value=f"₹{min_ppk:.0f}/kg (cheapest)", confidence=0.7),
        DecisionEvidence(source="market_snapshot", value=f"₹{max_ppk:.0f}/kg (most expensive)", confidence=0.7),
    ]
    warnings = []
    confidence = 0.75

    if freshness and freshness.is_stale:
        warnings.append(DecisionWarning(
            code="stale_data",
            message=freshness.warning,
            severity="warning",
        ))
        confidence *= 0.85

    # ── Check for sold-out variants ──
    sold_out = [r for r in all_records if not getattr(r, "is_available", True)]
    if sold_out:
        reasons.append(f"{len(sold_out)} variant(s) sold out")
        warnings.append(DecisionWarning(
            code="sold_out_variants",
            message=f"Some variants unavailable — comparison may be incomplete",
            severity="info",
        ))

    # ── Ad/upgrade trust signal for comparison results ──
    ad_records = [r for r in available_records if getattr(r, "is_ad", False)]
    upgrade_records = [r for r in available_records if getattr(r, "is_upgrade", False)]
    if ad_records:
        warnings.append(DecisionWarning(
            code="sponsored_comparison",
            message=f"{len(ad_records)} option(s) are sponsored ads — prices may not reflect market baseline.",
            severity="info",
        ))
    if upgrade_records:
        warnings.append(DecisionWarning(
            code="upgrade_variants",
            message=f"{len(upgrade_records)} option(s) are premium/upgrade variants — compare against regular options.",
            severity="info",
        ))

    return DecisionResult(
        canonical_name=canonical_name,
        display_name=display_name,
        action="compare",
        confidence=round(confidence, 2),
        reasons=reasons,
        evidence=evidence,
        warnings=warnings,
        data_freshness=freshness.status if freshness else "unknown",
        data_freshness_label=freshness.label if freshness else "",
        market_available=True,
    )


def detect_stale_snapshot_warnings(
    snapshot_freshness: FreshnessReport,
    decisions: list[DecisionResult],
) -> list[DecisionResult]:
    """Attach global stale-data warnings to all decisions when the snapshot is old.

    Per the review: "A grocery app loses trust quickly if it acts like
    a stale scrape is live truth."
    """
    if not snapshot_freshness.is_stale:
        return decisions

    global_warning = DecisionWarning(
        code="stale_snapshot",
        message=snapshot_freshness.warning,
        severity="warning",
    )

    for d in decisions:
        # Don't double-add if already has a stale warning
        if not any(w.code == "stale_snapshot" for w in d.warnings):
            d.warnings.append(global_warning)
        d.data_freshness = snapshot_freshness.status
        d.data_freshness_label = snapshot_freshness.label

    return decisions
