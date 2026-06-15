"""Parse free-form recipe text into structured ``RecipeIngredient`` rows.

The motivation is the Phase 3 #8 build: the user pastes (or OCRs) the
ingredients section of a recipe and the service proposes a shopping
list of what's missing. This is the parsing half; the matching half
lives in ``shopstack.services.recipes``.

**Input formats supported:**

- Bullet list (markdown): ``- 2 cups flour``
- Numbered list: ``1. 2 cups flour``
- Plain text: ``2 cups flour``
- Mixed units: ``1 tsp salt``, ``1 tbsp ginger``, ``1 cup yogurt``
- Indian-style: ``1 tsp haldi``, ``2 tbsp ghee``
- Garbled: ``2 cups flour (or maida)`` — extracts the canonical name part

**Output:** list of ``RecipeIngredient`` with parsed canonical_name,
quantity, and unit. The canonical name is the lowercased-underscored
first token after the qty+unit prefix; the caller can post-process with
``shopstack.domain.resolve_canonical`` if a strict
match is needed.

This is a *parser*, not a *classifier*. It doesn't try to validate the
result against the recipe DB — that's the caller's job.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Unit normalisations. The recipe DB uses ``kg``, ``g``, ``L``, ``ml``,
# ``tbsp``, ``tsp``, ``cup``, ``unit``, ``piece``, ``cloves``, ``leaves``,
# ``stick``, ``leaf``, ``pod``, ``bag``. Free text uses more variety.
_UNIT_ALIASES: dict[str, str] = {
    # mass
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "mg": "g",  # milligram → gram (with 0.001 scaling done by caller if needed)
    # volume
    "l": "L", "lt": "L", "ltr": "L", "liter": "L", "litre": "L",
    "liters": "L", "litres": "L", "lts": "L",
    "ml": "ml", "milliliter": "ml", "millilitre": "ml", "milliliters": "ml",
    # spoons
    "tsp": "tsp", "t": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tbs": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    # cups
    "cup": "cup", "cups": "cup", "c": "cup",
    # pieces
    "pc": "unit", "pcs": "unit", "piece": "unit", "pieces": "unit",
    "no": "unit", "nos": "unit", "unit": "unit", "units": "unit",
    "whole": "unit", "large": "unit", "medium": "unit", "small": "unit",
    "clove": "cloves", "cloves": "cloves",
    "leaf": "leaves", "leaves": "leaves",
    "stick": "stick", "sticks": "stick",
    "pod": "pod", "pods": "pod",
    "bag": "bag", "bags": "bag",
    "pinch": "tsp", "pinches": "tsp", "dash": "tsp", "dashes": "tsp",
}


# Quantities at the start of a line. Mixed: numbers, fractions, unicode
# fractions (½, ¼, ¾, ⅓, ⅔), ranges ("2-3"), mixed numbers ("1 1/2").
_QUANTITY_RE = re.compile(
    r"^(?P<qty>"
    r"\d+\s+\d+/\d+"      # mixed: "1 1/2"
    r"|\d+/\d+"           # fraction: "1/2"
    r"|\d+\.?\d*"         # decimal/integer: "2", "1.5"
    r"|[¼-¾⅓⅔]"          # unicode fractions
    r"|\d+-\d+"           # range: "2-3" (we take the first number)
    r")"
    r"\s*"
    r"(?P<unit>[a-zA-Z]+)?"
    r"\s+"
    r"(?P<name>.+?)$"
)

# Pre-cleaning: strip bullet / number markers, parenthetical asides,
# trailing "chopped" / "minced" / "diced" descriptors (these are prep
# notes, not ingredients we want to track).
_CLEAN_RE = re.compile(
    r"^[\s\-\*•·]+"                            # leading bullets
    r"|^\d+\.\s+"                                 # leading "1. "
    r"|\([^)]*\)"                                # parenthetical asides
    r"|,?\s*(chopped|minced|diced|grated|"
    r"crushed|sliced|cubed|peeled|optional|"
    r"to taste|as needed|finely|roughly).*$",
    re.IGNORECASE,
)


@dataclass
class ParsedIngredient:
    """One ingredient line parsed from free-form text."""

    canonical_name: str
    quantity: float = 1.0
    unit: str = "unit"
    raw_line: str = ""
    notes: list[str] = field(default_factory=list)


def _to_canonical_name(name: str) -> str:
    """Normalise a free-text ingredient name to a canonicalish slug.

    First tries ``resolve_canonical`` from the market alias map (which
    already knows ``"tomatoes"`` → ``"tomato"``, ``"eggs"`` → ``"egg"``,
    etc.). If that fails, falls back to a simple slug (``onion chopped``
    → ``"onion_chopped"``).
    """
    s = (name or "").strip().lower()
    if not s:
        return "unknown"
    try:
        from shopstack.domain import resolve_canonical

        resolved = resolve_canonical(s)
        if resolved:
            return resolved
    except Exception:
        pass
    # Fallback: simple slug
    s = re.sub(r"[^\w\s-]", " ", s)  # strip punctuation
    s = re.sub(r"\s+", "_", s)
    return s.strip("_") or "unknown"


def _parse_quantity(qty_str: str) -> float:
    """Convert a quantity string to a float. Handles fractions and ranges."""
    qty_str = qty_str.strip()
    # "1 1/2" → mixed
    m = re.match(r"^(\d+)\s+(\d+)/(\d+)$", qty_str)
    if m:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return whole + num / den
    # "1/2" → fraction
    m = re.match(r"^(\d+)/(\d+)$", qty_str)
    if m:
        return int(m.group(1)) / int(m.group(2))
    # "2-3" → range, take first
    m = re.match(r"^(\d+)-\d+$", qty_str)
    if m:
        return float(m.group(1))
    # unicode fractions
    fractions = {"¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 1/3, "⅔": 2/3}
    if qty_str in fractions:
        return float(fractions[qty_str])
    # plain decimal
    try:
        return float(qty_str)
    except ValueError:
        return 1.0


def parse_recipe_text(raw_text: str) -> list[ParsedIngredient]:
    """Parse free-form recipe text into structured ingredients.

    Args:
        raw_text: Multi-line text — one ingredient per line works best.
            Bullet markers (``-``, ``*``) and numbered lists (``1.``) are
            stripped automatically.

    Returns:
        List of ``ParsedIngredient``. Lines that can't be parsed are
        returned as a single ``ParsedIngredient`` with quantity=1.0 and
        unit="unit" (the line text becomes the canonical_name), so the
        caller still sees the line and can post-process.
    """
    if not raw_text or not raw_text.strip():
        return []

    parsed: list[ParsedIngredient] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Remove bullet markers, parentheticals, prep descriptors
        cleaned = _CLEAN_RE.sub("", line).strip(" ,;:-")
        if not cleaned:
            continue

        m = _QUANTITY_RE.match(cleaned)
        if not m:
            # Unparseable line — surface it as a single ingredient so
            # the caller can decide what to do.
            parsed.append(ParsedIngredient(
                canonical_name=_to_canonical_name(cleaned),
                raw_line=raw_line,
                notes=["unparseable quantity"],
            ))
            continue

        qty = _parse_quantity(m.group("qty"))
        unit_raw = (m.group("unit") or "").strip().lower()
        unit = _UNIT_ALIASES.get(unit_raw, unit_raw or "unit")
        name = m.group("name").strip()
        # Trailing prep notes inside the name: strip a trailing
        # comma + descriptor. Example: "tomato, chopped" → "tomato".
        name = re.sub(r",\s*\w+(\s+\w+)?$", "", name).strip()
        if not name:
            continue

        parsed.append(ParsedIngredient(
            canonical_name=_to_canonical_name(name),
            quantity=qty,
            unit=unit,
            raw_line=raw_line,
        ))
    return parsed


# ─── Higher-level: text → shopping list ───────────────────────────────────


def text_to_shopping_items(raw_text: str) -> list[dict[str, Any]]:
    """Convenience: parse + flatten into a shopping-list-ready list of
    dicts. The caller is responsible for canonicalisation / dedup /
    household-scoping (use ``shopstack.services.recipes.missing_to_shopping_items``
    or similar)."""
    return [
        {
            "canonical_name": p.canonical_name,
            "requested_quantity": p.quantity,
            "unit": p.unit,
            "raw_line": p.raw_line,
        }
        for p in parse_recipe_text(raw_text)
    ]


__all__ = [
    "ParsedIngredient",
    "parse_recipe_text",
    "text_to_shopping_items",
]
