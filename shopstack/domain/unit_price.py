"""Unit price calculation and item name normalization.

Pure business logic — no external dependencies.
Consolidates logic that was split across:
- shopstack/market/normalization.py (primary source)
- shopstack/domain/unit_price.py (old delegation shell)

This module IS the canonical implementation for both callers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────────────────

_WEIGHT_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(kg|g|ml|l|liter|litre)\s*(?:x\s*(\d+))?$",
    re.IGNORECASE,
)
_PIECE_PATTERN = re.compile(
    r"^(\d+)\s*(?:pieces|piece|pcs|pc)\s*(?:x\s*(\d+))?$",
    re.IGNORECASE,
)
_COMBO_PATTERN = re.compile(r"^(\d+)\s*(combo)$", re.IGNORECASE)
_PACK_PATTERN = re.compile(r"^(\d+)\s*(pack)$", re.IGNORECASE)
_SIZE_CLASS_PATTERN = re.compile(
    r"^(\d+)\s*(small|medium|large)$",
    re.IGNORECASE,
)
_SIZE_CLASS_GRAM_ESTIMATES: dict[str, int] = {
    "small": 80,
    "medium": 120,
    "large": 180,
}
_SIMPLE_NUMBER = re.compile(r"^(\d+)\s*$")

# Brand prefixes stripped before canonical resolution
_BRAND_PREFIX_PATTERNS = (
    "nectr ",
    "pluckk ozone washed ",
    "pluckk ",
    "freshcon cooked ",
    "urban harvest ",
    "organic india ",
    "24 mantra ",
    "freshcon ",
    "nourish organics ",
)

# Keywords that flag a name as a combo
_COMBO_KEYWORDS = ("combo", "&", "mix")


# ── SizeParseResult ───────────────────────────────────────────────────────

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


# ── Unit normalisation ────────────────────────────────────────────────────

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


# ── Size parsing ──────────────────────────────────────────────────────────

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
        return SizeParseResult(
            is_combo=True,
            warnings=["combo_or_pack_no_weight"],
        )

    m = _PACK_PATTERN.match(stripped)
    if m:
        return SizeParseResult(
            is_pack=True,
            warnings=["combo_or_pack_no_weight"],
        )

    m = _SIZE_CLASS_PATTERN.match(stripped)
    if m:
        count = int(m.group(1))
        cls = m.group(2).lower()
        estimated_grams = count * _SIZE_CLASS_GRAM_ESTIMATES[cls]
        est_per = _SIZE_CLASS_GRAM_ESTIMATES[cls]
        return SizeParseResult(
            normalized_quantity=float(estimated_grams),
            normalized_unit="g",
            package_count=count,
            is_size_class=True,
            is_weight_based=True,
            size_class=cls,
            warnings=[f"estimated_size_class_weight:{cls}:{est_per}g_each"],
        )

    m = _SIMPLE_NUMBER.match(stripped)
    if m:
        n = int(m.group(1))
        return SizeParseResult(
            normalized_quantity=float(n),
            normalized_unit="pieces",
            package_count=n,
            is_piece_based=True,
        )

    return SizeParseResult(warnings=[f"unrecognized_size:{stripped}"])


# ── Canonical name maps ───────────────────────────────────────────────────

# Market product → canonical slug
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
    "milk": "milk",
    "bread": "bread",
    "rice": "rice",
    "eggs": "eggs",
    "cooking_oil": "cooking_oil",
    "salt": "salt",
    "sugar": "sugar",
    "tea": "tea",
    "flour": "flour",
    "onions": "onion",
    "tomatoes": "tomato",
    "potatoes": "potato",
    "paneer": "paneer",
    "yogurt": "yogurt",
    "butter": "butter",
    "ghee": "ghee",
    "lentils": "lentils",
    "soap": "soap",
    "shampoo": "shampoo",
    "toothpaste": "toothpaste",
    "doodh": "milk",
    "dudh": "milk",
    "roti": "bread",
    "chawal": "rice",
    "anda": "eggs",
    "tel": "cooking_oil",
    "namak": "salt",
    "chini": "sugar",
    "patti": "tea",
    "atta": "flour",
    "maida": "refined_flour",
    "pyaaz": "onion",
    "aloo": "potato",
    "lehsun": "garlic",
    "adrak": "ginger",
    "murg": "chicken",
    "dahi": "yogurt",
    "curd": "yogurt",
    "makhan": "butter",
    "dal": "lentils",
    "daal": "lentils",
    "sabun": "soap",
    "dant manjan": "toothpaste",
    "shimla mirch": "capsicum",
    "tamatar": "tomato",
}

def _resolve_from_canonical_map(query: str) -> str | None:
    """Resolve query against _CANONICAL_MAP using exact + substring match."""
    q = query.strip().lower()

    if q in _CANONICAL_MAP:
        return _CANONICAL_MAP[q]

    for key, val in _CANONICAL_MAP.items():
        if key in q or q in key:
            return val

    return None


def _resolve_from_aliases(query: str) -> str | None:
    """Resolve query against ITEM_ALIASES."""
    q = re.sub(r"[^\w\s]", " ", query.strip().lower())
    q = re.sub(r"\s+", " ", q).strip()
    for canonical, aliases in ITEM_ALIASES.items():
        if q == canonical or q in aliases:
            return canonical
        for alias in aliases:
            if alias in q or q in alias:
                return canonical
    return None


# User-facing alias map: Hindi/regional/colloquial → canonical English name.
ITEM_ALIASES: dict[str, list[str]] = {
    "tomato": ["tamatar", "tomatoes", "thakkali"],
    "onion": ["pyaaz", "pyaz", "eerulli", "uli"],
    "sambar_onion": ["sambar pyaaz", "sambar ulli", "chinna ulli"],
    "potato": ["aloo", "alu", "chikka aloo", "batata", "urulai kazhangu"],
    "baby_potato": ["baby aloo", "baby batata"],
    "sweet_potato": ["shakarkand", "shakarkandi", "genasu"],
    "carrot": ["gajar", "padavalakayi"],
    "cucumber": ["sowthekaayi", "kheera", "kakdi"],
    "brinjal": ["baingan", "vankaya", "kathirikai", "eggplant", "aubergine"],
    "capsicum": ["shimla mirch", "donna mirchi", "kudaimilagai"],
    "bell_pepper": ["bell pepper", "capsicum shimla", "kudaimilagai"],
    "cauliflower": ["gobhi", "phool gobhi", "hogekayi"],
    "broccoli": ["broccoli", "broccoli gobhi"],
    "ridge_gourd": ["turai", "toraai", "peerkangai", "heerekayi"],
    "bottle_gourd": ["lauki", "dudhi", "sorekayi"],
    "bitter_gourd": ["karela", "pavakka", "kagalkayi"],
    "snake_gourd": ["chichinda", "pudalanga", "padavalakayi"],
    "pointed_gourd": ["parwal", "paraval", "tindora"],
    "cluster_beans": ["guar", "guar phali", "kothavarangai"],
    "french_beans": ["beans", "green beans", "hara phali", "farasbi"],
    "ladys_finger": ["bhindi", "okra", "vendakkai"],
    "drumstick": ["moringa", "nuggekaayi", "murungakkai"],
    "beetroot": ["chukandar", "beet", "beetroot"],
    "radish": ["mooli", "mullangi", "mula"],
    "raw_banana": ["kaccha kela", "vazhakkai"],
    "raw_mango": ["kaccha aam", "manga", "mamidi"],
    "yam": ["suran", "elephant foot yam", "senai"],
    "colocasia": ["arbi", "arvi", "seppankizhangu"],
    "zucchini": ["turai chini", "courgette"],
    "red_cabbage": ["laal gobhi", "red cabbage"],
    "coriander": ["dhania", "cilantro", "kothambari", "kothamalli"],
    "curry_leaves": ["kadi patta", "karibevu", "karivepaku", "kadi leaves"],
    "mint": ["pudina", "pudhina"],
    "green_chilli": ["hari mirch", "hasi menasu", "pachai milagai", "mirchi"],
    "garlic": ["lehsun", "lasun", "vellulli"],
    "ginger": ["adrak", "allam", "inji"],
    "curd": ["dahi", "yogurt", "mosaru", "perugu", "thayir"],
    "milk": ["doodh", "khir", "paal", "halu"],
    "paneer": ["paneer", "cottage cheese", "panir"],
    "wheat flour": ["atta", "aata", "godhi hittu"],
    "rice": ["chawal", "akki", "arisi"],
    "lentils": ["dal", "daal", "pappu", "paruppu"],
    "coconut": ["nariyal", "narkel", "tengina kayi"],
    "mustard_seeds": ["rai", "sarson", "sasive"],
    "turmeric": ["haldi", "arishina"],
    "cumin": ["jeera", "jeerige"],
    "fenugreek": ["methi", "methi seeds", "menthya"],
    "black_pepper": ["kali mirch", "kali menasu", "milagu"],
    "banana": ["kela", "balehannu", "vaazhai pazham"],
    "mango": ["aam", "mavina kayi", "maanga"],
    "apple": ["seb", "apple"],
    "orange": ["santara", "santra", "kintoor"],
    "grapes": ["angoor", "drakshi"],
    "papaya": ["papita", "pappali", "babbakayi"],
    "pineapple": ["ananas", "ananasina hayi"],
    "moong_dal": ["moong dal", "hesaru bele", "pasiparuppu"],
    "toor_dal": ["toor dal", "tovar dal", "sambar powder dal", "thuvaram paruppu"],
    "chana_dal": ["chana dal", "kadalai paruppu"],
    "urad_dal": ["urad dal", "uzhunnu paruppu"],
    "besan": ["gram flour", "chickpea flour", "kadle hittu"],
    "sugar": ["cheeni", "sakare", "sarkarai"],
    "salt": ["namak", "uppu"],
    "oil": ["tel", "enne", "ennai"],
    "ghee": ["ghee", "neyyi", "nei"],
    "vinegar": ["sirka", "vinagiri"],
}


# ── Resolution ────────────────────────────────────────────────────────────

def resolve_canonical(query: str) -> str | None:
    if not query:
        return None
    r = _resolve_from_canonical_map(query)
    if r:
        return r
    return _resolve_from_aliases(query)


def normalize_item_name(name: str) -> str:
    normal = re.sub(r"[^\w\s]", " ", name.lower()).strip()
    normal = re.sub(r"\s+", " ", normal)
    for canonical, aliases in ITEM_ALIASES.items():
        if normal == canonical or normal in aliases:
            return canonical
    return normal


CANONICAL_MAP = _CANONICAL_MAP


# ── Name cleaning ─────────────────────────────────────────────────────────

def _clean_name(name: str) -> str:
    cleaned = re.sub(r"\s*-\s*.*$", "", name)
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", cleaned).strip()
    cleaned = cleaned.replace("'", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    for prefix in _BRAND_PREFIX_PATTERNS:
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
        canonical = _resolve_from_canonical_map(clean_part)
        if not canonical:
            canonical = _resolve_from_aliases(clean_part)
        if not canonical:
            canonical = clean_part.replace(" ", "_")[:30]
        components.append(canonical)
    return components


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
        canonical = _resolve_from_canonical_map(lowered)
    if not canonical:
        canonical = _resolve_from_aliases(lowered)
    if not canonical:
        canonical = lowered.replace(" ", "_")[:40]

    variety = ""
    if raw_name != cleaned:
        paren = re.search(r"\(([^)]+)\)", raw_name)
        if paren:
            variety = paren.group(1)

    return canonical, variety, []


# ── Unit-price computation ────────────────────────────────────────────────

def compute_unit_prices(
    price: float | None = None,
    quantity: float | None = None,
    unit: str | None = None,
    is_weight_based: bool = False,
    is_piece_based: bool = False,
    _items: list[dict] | None = None,
    _price_key: str = "price",
    _size_key: str = "size",
    _quantity_key: str = "quantity",
) -> dict | list[dict]:
    if _items is not None:
        results = []
        for item in _items:
            p = item.get(_price_key)
            if p is None:
                results.append({**item, "unit_price": None, "unit": "unknown"})
                continue
            size_raw = str(item.get(_size_key, ""))
            qty = item.get(_quantity_key)
            parsed = parse_size(size_raw)
            if parsed.normalized_quantity and parsed.normalized_quantity > 0:
                up = float(p) / parsed.normalized_quantity
                results.append({**item, "unit_price": round(up, 4), "unit": parsed.normalized_unit or "unknown"})
            elif qty and float(qty) > 0:
                up = float(p) / float(qty)
                results.append({**item, "unit_price": round(up, 4), "unit": "each"})
            else:
                results.append({**item, "unit_price": None, "unit": "unknown"})
        return results

    result: dict = {"price_per_kg": None, "price_per_100g": None, "price_per_piece": None}
    if not price or price <= 0 or quantity is None or quantity <= 0:
        return result

    if is_weight_based and unit == "g":
        result["price_per_kg"] = round(price / quantity * 1000, 2)
        result["price_per_100g"] = round(price / quantity * 100, 2)
    elif is_piece_based and unit == "pieces":
        result["price_per_piece"] = round(price / quantity, 2)

    return result
