"""AI nutrition coaching — Phase 6 #17.

The :mod:`shopstack.services.nutrition` module is a *lookup* — it tells
you what's in the inventory and the totals. This module turns that
into *coaching*: comparing the household's stock against recommended
daily intakes, identifying gaps, and recommending specific items to
add to the next shopping list.

**Why a separate module:**

Coaching is opinionated and requires assumptions (household size,
dietary pattern, age/sex of members, daily intake targets). The
lookup is neutral data. Keeping them separate lets the lookup stay
small, fast, and reusable in other surfaces, while the coaching
logic can grow without bloating the data layer.

**Inputs:**

- :class:`NutritionSummary` (from :mod:`shopstack.services.nutrition`).
- A :class:`HouseholdProfile` (members, dietary pattern) — defaults
  to a family of 4 (Indian RDA baseline) when unknown.

**Outputs:**

- A :class:`NutritionCoaching` with:
  - Per-nutrient status (sufficient / low / surplus vs the household's
    weekly target).
  - A prioritized list of *gap-filling* recommendations — "your
    iron is at 40% of target this week; add palak (spinach) to the
    next list."
  - A short coaching message ("🟢 Good balance overall" / "🟡 Add
    more protein" / "🔴 Low in iron and fiber — see suggestions").

**Why not call an LLM:**

This is opinionated guidance from a known-good reference table, not
creative generation. The coaching is a *rules engine*: the reference
data is in the module (per-nutrient RDA × household size × 7 days),
and the recommendations come from a small dictionary of
nutrient → suggested canonical_name mappings. Deterministic,
testable, free, offline, and on the user's device.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape
from typing import Any, Iterable

from shopstack.services.i18n import DEFAULT_LOCALE, t
from shopstack.services.nutrition import (
    NutritionInfo,
    NutritionSummary,
    get_nutrition_info,
)

logger = logging.getLogger(__name__)


# ─── Reference data ──────────────────────────────────────────────────


# Indian Council of Medical Research (ICMR) Recommended Dietary
# Allowances for an "average" adult. Used as a per-person baseline;
# the household-level weekly target is per-person × household size × 7.
# Source: ICMR Nutrient Requirements for Indians (2020), balanced-diet
# tables for a 30-50 yr sedentary adult. Numbers are deliberately
# round — this is household guidance, not medical advice.
DEFAULT_RDA_PER_DAY: dict[str, float] = {
    "calories_kcal": 2000.0,
    "protein_g":      50.0,
    "carbs_g":       300.0,
    "fat_g":          70.0,
    "fiber_g":        30.0,
    "calcium_mg":   1000.0,
    "iron_mg":        17.0,
}


# Nutrient → list of canonical_name suggestions that boost it.
# Picked from the nutrition_reference.json (so the suggestions are
# guaranteed to look up). Order: best source first.
NUTRIENT_SUGGESTIONS: dict[str, list[str]] = {
    "protein_g":   ["paneer", "curd", "milk", "lentils", "chickpea", "rajma"],
    "fiber_g":     ["spinach", "carrot", "apple", "banana", "oats", "wheat_flour"],
    "calcium_mg":  ["milk", "curd", "paneer", "ragi", "almonds"],
    "iron_mg":     ["spinach", "lentils", "rajma", "chickpea", "dates"],
    "calories_kcal": ["rice", "wheat_flour", "potato", "banana", "almonds"],
    "carbs_g":     ["rice", "wheat_flour", "potato", "oats", "banana"],
    "fat_g":       ["cooking_oil", "ghee", "butter", "almonds", "peanuts"],
}


# ─── Household profile ──────────────────────────────────────────────


@dataclass
class HouseholdProfile:
    """Size + dietary pattern for the household.

    Defaults to a 4-person vegetarian household, which is the
    most common case in the target audience (Indian middle-class
    families).
    """

    size: int = 4
    dietary: str = "vegetarian"  # "vegetarian" | "vegan" | "omnivore"

    @property
    def weekly_multiplier(self) -> float:
        """Per-nutrient weekly target = RDA × size × 7 days."""
        return float(self.size) * 7.0


# ─── Coaching result ──────────────────────────────────────────────────


@dataclass
class NutrientStatus:
    """Status of one nutrient in the household's stock vs the weekly target."""

    nutrient: str
    in_stock: float  # total in inventory (in nutrient units)
    target: float    # weekly target (RDA × size × 7)
    unit: str        # "kcal" | "g" | "mg"

    @property
    def pct(self) -> float:
        if self.target <= 0:
            return 0.0
        return round(self.in_stock / self.target * 100, 1)

    @property
    def status(self) -> str:
        """One of: "low" (<60%), "fair" (60-90%), "good" (90-110%),
        "surplus" (>110%)."""
        p = self.pct
        if p < 60:
            return "low"
        if p < 90:
            return "fair"
        if p < 110:
            return "good"
        return "surplus"

    @property
    def color(self) -> str:
        return {
            "low":     "var(--red, #A63F31)",
            "fair":    "var(--amber, #A76012)",
            "good":    "var(--green, #176B49)",
            "surplus": "var(--text-dim, #6F6254)",
        }[self.status]


@dataclass
class CoachingSuggestion:
    """One actionable 'add this to your list' item."""

    nutrient: str
    canonical_name: str
    display_name: str
    reason: str


@dataclass
class NutritionCoaching:
    """The full coaching result for a household's inventory."""

    profile: HouseholdProfile
    statuses: list[NutrientStatus] = field(default_factory=list)
    suggestions: list[CoachingSuggestion] = field(default_factory=list)
    headline: str = ""  # 🟢 / 🟡 / 🔴 + 1-sentence summary
    overall: str = "good"  # "good" | "fair" | "low"
    covered_items: int = 0
    missing_items: list[str] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return any(s.status in ("low", "fair") for s in self.statuses)

    @property
    def gap_count(self) -> int:
        return sum(1 for s in self.statuses if s.status in ("low", "fair"))


# ─── Coaching logic ─────────────────────────────────────────────────


# Friendly labels for the per-nutrient section
NUTRIENT_LABELS: dict[str, str] = {
    "calories_kcal": "Calories",
    "protein_g":     "Protein",
    "carbs_g":       "Carbs",
    "fat_g":         "Fat",
    "fiber_g":       "Fiber",
    "calcium_mg":    "Calcium",
    "iron_mg":       "Iron",
}
NUTRIENT_UNITS: dict[str, str] = {
    "calories_kcal": "kcal",
    "protein_g":     "g",
    "carbs_g":       "g",
    "fat_g":         "g",
    "fiber_g":       "g",
    "calcium_mg":    "mg",
    "iron_mg":       "mg",
}


def build_coaching(
    summary: NutritionSummary,
    profile: HouseholdProfile | None = None,
) -> NutritionCoaching:
    """Compute the coaching result for a household's nutrition summary.

    Args:
        summary: The output of
            :func:`shopstack.services.nutrition.get_inventory_nutrition_summary`.
        profile: Optional household profile. Defaults to a 4-person
            vegetarian family (the most common target).

    Returns:
        A :class:`NutritionCoaching` with per-nutrient status,
        prioritized suggestions, and a one-line headline.
    """
    if profile is None:
        profile = HouseholdProfile()

    weekly = profile.weekly_multiplier
    statuses: list[NutrientStatus] = []
    suggestions: list[CoachingSuggestion] = []

    for nutrient, rda in DEFAULT_RDA_PER_DAY.items():
        in_stock = float(getattr(summary, _summary_attr(nutrient), 0.0))
        target = rda * weekly
        status = NutrientStatus(
            nutrient=nutrient,
            in_stock=in_stock,
            target=target,
            unit=NUTRIENT_UNITS.get(nutrient, ""),
        )
        statuses.append(status)
        # Only suggest when the household is at <60% of weekly target
        if status.pct < 60:
            for canon in NUTRIENT_SUGGESTIONS.get(nutrient, []):
                info = get_nutrition_info(canon)
                if info is None:
                    continue
                # Skip if the household already has plenty of it
                # (best-effort: check via the summary items list)
                if _household_has(summary, canon):
                    continue
                suggestions.append(CoachingSuggestion(
                    nutrient=nutrient,
                    canonical_name=canon,
                    display_name=canon.replace("_", " ").title(),
                    reason=_suggestion_reason(nutrient, status, info),
                ))
                break  # one suggestion per nutrient

    # Overall
    low_count = sum(1 for s in statuses if s.status == "low")
    fair_count = sum(1 for s in statuses if s.status == "fair")
    if low_count >= 3:
        overall = "low"
        headline = f"🔴 {low_count} nutrients below half of weekly target — see suggestions."
    elif low_count >= 1 or fair_count >= 3:
        overall = "fair"
        headline = f"🟡 {low_count + fair_count} nutrients could use a boost — see suggestions."
    else:
        overall = "good"
        headline = "🟢 Your kitchen is well-stocked across the key nutrients this week."

    return NutritionCoaching(
        profile=profile,
        statuses=statuses,
        suggestions=suggestions,
        headline=headline,
        overall=overall,
        covered_items=len(summary.items),
        missing_items=list(summary.missing_items or []),
    )


def _summary_attr(nutrient: str) -> str:
    """Map a nutrient key to the matching NutritionSummary attribute."""
    return {
        "calories_kcal": "total_calories",
        "protein_g":     "total_protein",
        "carbs_g":       "total_carbs",
        "fat_g":         "total_fat",
    }.get(nutrient, nutrient)


def _household_has(summary: NutritionSummary, canonical_name: str) -> bool:
    """True if the household already has a non-trivial amount of canonical_name."""
    for item in summary.items:
        if (item.get("name", "").replace(" ", "_").lower() == canonical_name
                and float(item.get("quantity", 0)) > 0):
            return True
    return False


def _suggestion_reason(nutrient: str, status: NutrientStatus, info: NutritionInfo) -> str:
    """Build a human-readable reason for a coaching suggestion."""
    label = NUTRIENT_LABELS.get(nutrient, nutrient)
    name = info.canonical_name.replace("_", " ").title()
    return (
        f"{label} is at {status.pct:.0f}% of weekly target. "
        f"{name} is a good source."
    )


# ─── HTML rendering ────────────────────────────────────────────────


def render_coaching_html(
    coaching: NutritionCoaching,
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Render the coaching result as an XSS-safe HTML block.

    The block has three sections:
    1. A headline (🟢/🟡/🔴 + summary).
    2. Per-nutrient status bars (with color coding).
    3. Prioritized suggestions (a clickable list of canonical items
       the user can push to the next shopping list).
    """
    parts: list[str] = []
    parts.append(
        "<div class='nc-block'>"
        f"<div class='nc-headline'>{escape(coaching.headline)}</div>"
    )
    # Per-nutrient status bars
    parts.append("<div class='nc-bars'>")
    for s in coaching.statuses:
        pct = max(0, min(100, s.pct))
        label = NUTRIENT_LABELS.get(s.nutrient, s.nutrient)
        parts.append(
            "<div class='nc-bar-row'>"
            f"<div class='nc-bar-label'>{escape(label)}</div>"
            f"<div class='nc-bar-track'>"
            f"<div class='nc-bar-fill' style='width:{pct:.0f}%;background:{s.color};'></div>"
            f"</div>"
            f"<div class='nc-bar-pct' style='color:{s.color};'>{s.pct:.0f}%</div>"
            f"</div>"
        )
    parts.append("</div>")

    # Suggestions
    if coaching.suggestions:
        parts.append(
            f"<div class='nc-section-h'>{escape('Add to your next list')}</div>"
            "<ul class='nc-suggestions'>"
        )
        for sg in coaching.suggestions:
            parts.append(
                "<li class='nc-suggestion'>"
                f"<span class='nc-sg-name'>{escape(sg.display_name)}</span>"
                f"<span class='nc-sg-reason'>{escape(sg.reason)}</span>"
                f"</li>"
            )
        parts.append("</ul>")

    # Disclaimer
    parts.append(
        "<div class='nc-disclaimer'>"
        "Approximate household guidance. Not medical advice. "
        f"Targets assume a {coaching.profile.size}-person {coaching.profile.dietary} family."
        "</div>"
    )

    parts.append("</div>")
    return "".join(parts)


__all__ = [
    "DEFAULT_RDA_PER_DAY",
    "CoachingSuggestion",
    "HouseholdProfile",
    "NUTRIENT_SUGGESTIONS",
    "NUTRIENT_LABELS",
    "NUTRIENT_UNITS",
    "NutrientStatus",
    "NutritionCoaching",
    "build_coaching",
    "render_coaching_html",
]
