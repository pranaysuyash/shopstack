from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
        is_pack = "pack" in stripped.lower()
        return SizeParseResult(
            is_combo=not is_pack,
            is_pack=is_pack,
            warnings=["combo_or_pack_no_weight"],
        )

    m = _SIZE_CLASS_PATTERN.match(stripped)
    if m:
        count = int(m.group(1))
        cls = m.group(2).lower()
        estimated_grams = count * _SIZE_CLASS_GRAM_ESTIMATES[cls]
        return SizeParseResult(
            normalized_quantity=float(estimated_grams),
            normalized_unit="g",
            package_count=count,
            is_size_class=True,
            is_weight_based=True,
            size_class=cls,
            warnings=[f"estimated_size_class_weight:{cls}:{_SIZE_CLASS_GRAM_ESTIMATES[cls]}g_each"],
        )

    if re.match(r"^\d+\s*$", stripped):
        n = int(stripped)
        return SizeParseResult(
            normalized_quantity=float(n),
            normalized_unit="pieces",
            package_count=n,
            is_piece_based=True,
        )

    return SizeParseResult(warnings=[f"unrecognized_size:{stripped}"])


def _normalize_weight_unit(unit: str) -> str:
    mapping = {
        "kg": "g",
        "g": "g",
        "l": "mL",
        "ml": "mL",
        "liter": "mL",
        "litre": "mL",
    }
    return mapping.get(unit, unit)


def compute_unit_prices(
    price: float,
    quantity: float | None,
    unit: str | None,
    is_weight_based: bool,
    is_piece_based: bool,
) -> dict[str, float | None]:
    result: dict[str, float | None] = {
        "price_per_kg": None,
        "price_per_100g": None,
        "price_per_piece": None,
    }
    if price <= 0 or quantity is None or quantity <= 0:
        return result

    if is_weight_based and unit == "g":
        result["price_per_kg"] = round(price / quantity * 1000, 2)
        result["price_per_100g"] = round(price / quantity * 100, 2)
    elif is_piece_based and unit == "pieces":
        result["price_per_piece"] = round(price / quantity, 2)

    return result


_CANONICAL_MAP: dict[str, str] = {
    "tomato": "tomato",
    "indian tomato": "tomato",
    "hybrid tomato": "tomato",
    "desi tomato": "tomato",
    "snibs snack tomatoes": "tomato",
    "cherry tomato": "tomato",
    "onion": "onion",
    "sambar onion": "sambar_onion",
    "white onion": "white_onion",
    "value pack onion": "onion",
    "potato": "potato",
    "baby potato": "baby_potato",
    "chandramukhi potato": "potato",
    "sweet potato": "sweet_potato",
    "carrot": "carrot",
    "ooty carrot": "carrot",
    "cucumber": "cucumber",
    "english cucumber": "cucumber",
    "green cucumber": "cucumber",
    "brinjal": "brinjal",
    "kateri brinjal": "brinjal",
    "long purple brinjal": "brinjal",
    "capsicum": "capsicum",
    "green capsicum": "capsicum",
    "bell pepper": "bell_pepper",
    "red bell pepper": "bell_pepper",
    "yellow bell pepper": "bell_pepper",
    "red & yellow bell pepper": "bell_pepper",
    "ridge gourd": "ridge_gourd",
    "bottle gourd": "bottle_gourd",
    "bitter gourd": "bitter_gourd",
    "forest bitter gourd": "bitter_gourd",
    "snake gourd": "snake_gourd",
    "pointed gourd": "pointed_gourd",
    "round gourd": "round_gourd",
    "cauliflower": "cauliflower",
    "coccinia": "coccinia",
    "cluster beans": "cluster_beans",
    "french beans": "french_beans",
    "haricot beans": "haricot_beans",
    "broad beans": "broad_beans",
    "cowpea beans": "cowpea_beans",
    "ladys finger": "ladys_finger",
    "lady finger": "ladys_finger",
    "okra": "ladys_finger",
    "drumstick": "drumstick",
    "beetroot": "beetroot",
    "radish": "radish",
    "white radish": "radish",
    "raw banana": "raw_banana",
    "raw mango": "raw_mango",
    "totapuri raw mango": "raw_mango",
    "yam": "yam",
    "colocasia": "colocasia",
    "arvi": "colocasia",
    "broccoli": "broccoli",
    "zucchini": "zucchini",
    "green zucchini": "zucchini",
    "yellow zucchini": "zucchini",
    "coconut": "coconut",
    "red cabbage": "red_cabbage",
    "curry leaves": "curry_leaves",
    "coriander leaves": "coriander",
    "mint leaves": "mint",
    "green chilli": "green_chilli",
    "garlic": "garlic",
    "ginger": "ginger",
}

_COMBO_KEYWORDS = ("combo", "&", "mix")

# User-facing alias map: Hindi/regional/colloquial → canonical English name.
# This is the single source of truth for linguistic aliases.
# Market product variants (e.g. "baby potato", "sambar onion") are NOT here
# because they represent distinct inventory items — those live in _CANONICAL_MAP.
ITEM_ALIASES: dict[str, list[str]] = {
    "tomato": ["tamatar", "tomatoes"],
    "coriander": ["dhania", "cilantro"],
    "curd": ["dahi", "yogurt"],
    "wheat flour": ["atta", "aata"],
    "rice": ["chawal"],
    "lentils": ["dal", "daal"],
    "onion": ["pyaaz", "pyaz", "eerulli"],
    "potato": ["aloo", "alu", "chikka aloo"],
    "cucumber": ["sowthekaayi"],
}


def normalize_item_name(name: str) -> str:
    """Normalize a user-supplied item name: clean punctuation + resolve aliases.

    This is the canonical normalization for user-input and inventory matching.
    Market-data normalization uses ``canonicalize_name`` instead.
    """
    normal = re.sub(r"[^\w\s]", " ", name.lower()).strip()
    normal = re.sub(r"\s+", " ", normal)
    for canonical, aliases in ITEM_ALIASES.items():
        if normal == canonical or normal in aliases:
            return canonical
    return normal


def canonicalize_name(raw_name: str) -> tuple[str, str, list[str]]:
    cleaned = _clean_name(raw_name)
    is_combo = _detect_combo(raw_name)
    components: list[str] = []

    if is_combo:
        components = _extract_combo_components(cleaned)
        slug_parts = [c for c in components if c]
        if slug_parts:
            slug = "combo_" + "_".join(slug_parts[:5])
        else:
            slug = "combo_" + cleaned.replace(" ", "_")[:40]
        return slug, "", components

    lowered = cleaned.lower()
    canonical = _CANONICAL_MAP.get(lowered, "")
    if not canonical:
        for key, val in _CANONICAL_MAP.items():
            if key in lowered or lowered in key:
                canonical = val
                break
    if not canonical:
        canonical = lowered.replace(" ", "_")[:40]

    variety = ""
    if raw_name != cleaned:
        paren = re.search(r"\(([^)]+)\)", raw_name)
        if paren:
            variety = paren.group(1)

    return canonical, variety, []


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"\s*-\s*.*$", "", name)
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    prefixes = ("nectr ", "pluckk ozone washed ", "pluckk ", "freshcon cooked ", "urban harvest ")
    for prefix in prefixes:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = re.sub(r"\s+\(chemical free\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+chemical free", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+protected cultivation", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _detect_combo(name: str) -> bool:
    lowered = name.lower()
    if "combo" in lowered:
        return True
    if " & " in lowered or "&" in lowered:
        parts = [p.strip() for p in lowered.split("&") if p.strip()]
        if len(parts) >= 2:
            return True
    if "herbs mix" in lowered:
        return True
    if "sambar veg" in lowered:
        return True
    return False


def _extract_combo_components(cleaned_name: str) -> list[str]:
    lowered = cleaned_name.lower()
    if "herbs mix" in lowered:
        return ["curry_leaves", "coriander", "mint"]
    if "sambar veg" in lowered:
        return ["drumstick", "radish", "cluster_beans", "ladys_finger"]

    parts = re.split(r"[,&]|, and | and ", lowered)
    components: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        clean_part = _clean_name(part)
        canonical = _CANONICAL_MAP.get(clean_part, "")
        if not canonical:
            for key, val in _CANONICAL_MAP.items():
                if key in clean_part:
                    canonical = val
                    break
        if not canonical:
            canonical = clean_part.replace(" ", "_")[:30]
        components.append(canonical)
    return components
