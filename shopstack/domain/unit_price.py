"""Unit price calculation and item name normalization.

Pure business logic — no external dependencies.
Supersedes shopstack/market/normalization.py for these symbols.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WEIGHT_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(kg|g|ml|l|liter|litre)\s*(?:x\s*(\d+))?$",
    re.IGNORECASE,
)
_PIECE_PATTERN = re.compile(
    r"^(\d+)\s*(?:pieces|piece|pcs|pc)\s*(?:x\s*(\d+))?$",
    re.IGNORECASE,
)
_COMBO_PATTERN = re.compile(r"^(\d+)\s*(?:combo|pack)$", re.IGNORECASE)
_SIZE_CLASS_PATTERN = re.compile(
    r"^(\d+)\s*(small|medium|large)$",
    re.IGNORECASE,
)
_SIZE_CLASS_GRAM_ESTIMATES: dict[str, int] = {
    "small": 80,
    "medium": 120,
    "large": 180,
}


@dataclass
class SizeParseResult:
    normalized_quantity: float | None = None
    normalized_unit: str | None = None
    package_count: int = 1
    is_weight_based: bool = False
    is_piece_based: bool = False
    is_combo: bool = False
    is_pack: bool = False
    is_size_class: bool = False
    size_class: str = ""
    warnings: list[str] | None = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def _normalize_weight_unit(unit: str) -> str:
    u = unit.lower().strip()
    if u in ("kg",):
        return "kg"
    if u in ("g",):
        return "g"
    if u in ("ml",):
        return "ml"
    if u in ("l", "liter", "litre"):
        return "l"
    return u


def parse_size(raw_size: str) -> SizeParseResult:
    if not raw_size:
        return SizeParseResult(warnings=["empty_size"])

    stripped = raw_size.strip()

    m = _WEIGHT_PATTERN.match(stripped)
    if m:
        qty = float(m.group(1))
        unit_raw = m.group(2).lower()
        pkg = int(m.group(3)) if m.group(3) else 1
        unit = _normalize_weight_unit(unit_raw)
        if unit_raw in ("kg", "l", "liter", "litre"):
            qty = qty * 1000
        total_qty = qty * pkg
        return SizeParseResult(
            normalized_quantity=total_qty,
            normalized_unit=unit,
            package_count=pkg,
            is_weight_based=True,
        )

    m = _PIECE_PATTERN.match(stripped)
    if m:
        qty = int(m.group(1))
        pkg = int(m.group(2)) if m.group(2) else 1
        total_pieces = qty * pkg
        return SizeParseResult(
            normalized_quantity=float(total_pieces),
            normalized_unit="pieces",
            package_count=pkg,
            is_piece_based=True,
        )

    m = _COMBO_PATTERN.match(stripped)
    if m:
        qty = int(m.group(1))
        return SizeParseResult(
            normalized_quantity=float(qty),
            normalized_unit="combo",
            package_count=qty,
            is_combo=True,
        )

    m = _SIZE_CLASS_PATTERN.match(stripped)
    if m:
        qty = int(m.group(1))
        cls = m.group(2).lower()
        est = _SIZE_CLASS_GRAM_ESTIMATES.get(cls, 100)
        return SizeParseResult(
            normalized_quantity=float(qty * est),
            normalized_unit="g",
            package_count=1,
            is_size_class=True,
            size_class=cls,
        )

    return SizeParseResult(warnings=[f"unparseable_size:{raw_size}"])


# ── Canonical name maps ────────────────────────────────────────────────

CANONICAL_MAP: dict[str, str] = {
    "milk": "milk",
    "doodh": "milk",
    "dudh": "milk",
    "bread": "bread",
    "roti": "bread",
    "chawal": "rice",
    "rice": "rice",
    "anda": "eggs",
    "eggs": "eggs",
    "egg": "eggs",
    "tel": "cooking_oil",
    "oil": "cooking_oil",
    "cooking oil": "cooking_oil",
    "namak": "salt",
    "salt": "salt",
    "chini": "sugar",
    "sugar": "sugar",
    " chai": "tea",
    "tea": "tea",
    "patti": "tea",
    "coffee": "coffee",
    "atta": "flour",
    "flour": "flour",
    "maida": "refined_flour",
    "onion": "onions",
    "pyaaz": "onions",
    "onions": "onions",
    "tomato": "tomatoes",
    "tamatar": "tomatoes",
    "tomatoes": "tomatoes",
    "aloo": "potatoes",
    "potatoes": "potatoes",
    "potato": "potatoes",
    "garlic": "garlic",
    "lehsun": "garlic",
    "ginger": "ginger",
    "adrak": "ginger",
    "chicken": "chicken",
    "murg": "chicken",
    "paneer": "paneer",
    "dahi": "yogurt",
    "yogurt": "yogurt",
    "curd": "yogurt",
    "butter": "butter",
    "makhan": "butter",
    "ghee": "ghee",
    "dal": "lentils",
    "lentils": "lentils",
    "daal": "lentils",
    "soap": "soap",
    "sabun": "soap",
    "shampoo": "shampoo",
    "toothpaste": "toothpaste",
    "dant manjan": "toothpaste",
}

ITEM_ALIASES: dict[str, list[str]] = {
    "milk": ["milk", "doodh", "dudh"],
    "bread": ["bread", "roti"],
    "rice": ["rice", "chawal"],
    "eggs": ["eggs", "egg", "anda"],
    "cooking_oil": ["oil", "tel", "cooking oil"],
    "salt": ["salt", "namak"],
    "sugar": ["sugar", "chini"],
    "tea": ["tea", "patti", "chai"],
    "flour": ["flour", "atta"],
    "onions": ["onion", "onions", "pyaaz"],
    "tomatoes": ["tomato", "tomatoes", "tamatar"],
    "potatoes": ["potato", "potatoes", "aloo"],
    "garlic": ["garlic", "lehsun"],
    "ginger": ["ginger", "adrak"],
    "chicken": ["chicken", "murg"],
    "paneer": ["paneer"],
    "yogurt": ["yogurt", "dahi", "curd"],
    "butter": ["butter", "makhan"],
    "ghee": ["ghee"],
    "lentils": ["lentils", "dal", "daal"],
    "soap": ["soap", "sabun"],
    "shampoo": ["shampoo"],
    "toothpaste": ["toothpaste", "dant manjan"],
}


def resolve_canonical(name: str) -> str:
    """Resolve an item name to its canonical form."""
    key = name.lower().strip()
    return CANONICAL_MAP.get(key, key)


def normalize_item_name(name: str) -> str:
    """Normalize an item name for comparison."""
    key = name.lower().strip()
    canonical = resolve_canonical(key)
    return canonical


def canonicalize_name(name: str) -> str:
    """Canonicalize item name (alias for resolve_canonical)."""
    return resolve_canonical(name)


def compute_unit_prices(
    items: list[dict],
    price_key: str = "price",
    size_key: str = "size",
    quantity_key: str = "quantity",
) -> list[dict]:
    """Compute unit prices for a list of items.

    Each item dict should have at minimum a price and size/quantity.
    Returns the same list with 'unit_price' and 'unit' added.
    """
    results = []
    for item in items:
        price = item.get(price_key)
        if price is None:
            results.append({**item, "unit_price": None, "unit": "unknown"})
            continue

        size_raw = str(item.get(size_key, ""))
        qty = item.get(quantity_key)

        parsed = parse_size(size_raw)
        if parsed.normalized_quantity and parsed.normalized_quantity > 0:
            unit_price = float(price) / parsed.normalized_quantity
            results.append({
                **item,
                "unit_price": round(unit_price, 4),
                "unit": parsed.normalized_unit or "unknown",
            })
        elif qty and float(qty) > 0:
            unit_price = float(price) / float(qty)
            results.append({
                **item,
                "unit_price": round(unit_price, 4),
                "unit": "each",
            })
        else:
            results.append({**item, "unit_price": None, "unit": "unknown"})

    return results
