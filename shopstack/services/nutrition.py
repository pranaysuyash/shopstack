from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "NutritionInfo",
    "NutritionSummary",
    "format_nutrition_html",
    "get_inventory_nutrition_summary",
    "get_nutrition_info",
    "load_nutrition_reference",
    "lookup_nutrition_html",
]

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_NUTRITION_FILE = _DATA_DIR / "nutrition_reference.json"

_cache: dict[str, dict[str, Any]] | None = None
_alias_map: dict[str, str] | None = None


@dataclass
class NutritionInfo:
    canonical_name: str
    calories_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    calcium_mg: float = 0
    iron_mg: float = 0
    common_serving_amount: float = 100
    common_serving_unit: str = "g"
    category: str = ""
    notes: str = ""


@dataclass
class NutritionSummary:
    items: list[dict[str, Any]]
    total_calories: float
    total_protein: float
    total_carbs: float
    total_fat: float
    missing_items: list[str]


def load_nutrition_reference() -> dict[str, dict[str, Any]]:
    global _cache, _alias_map
    if _cache is not None and _alias_map is not None:
        return _cache

    _cache = {}
    _alias_map = {}

    if not _NUTRITION_FILE.exists():
        logger.warning("Nutrition reference file not found: %s", _NUTRITION_FILE)
        return _cache

    try:
        raw = json.loads(_NUTRITION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load nutrition reference: %s", exc)
        return _cache

    for entry in raw:
        canonical = entry.get("canonical_name", "").strip().lower()
        if not canonical:
            continue
        _cache[canonical] = entry
        _alias_map[canonical] = canonical
        for alias in entry.get("display_names", []):
            key = alias.strip().lower()
            if key:
                _alias_map[key] = canonical

    return _cache


def _ensure_loaded() -> None:
    if _cache is None:
        load_nutrition_reference()


def _brand_aware_match(key: str) -> str | None:
    """Resolve a branded/packaged item name (e.g. "Amul Toned Milk 500ml")
    to a canonical nutrition entry via fuzzy word-overlap matching.

    The exact alias lookup in :func:`get_nutrition_info` only matches
    bare product names ("toned milk"). Real inventory items carry brand
    names and pack sizes ("Amul Toned Milk 500ml") that never match
    exactly. We reuse :mod:`shopstack.domain.product_matching`'s
    word-overlap scorer against every known alias and accept the
    highest-scoring match above its 0.5 "is_match" threshold.
    """
    from shopstack.domain.product_matching import best_match

    assert _alias_map is not None
    match = best_match(key, list(_alias_map.keys()), threshold=0.5)
    if match is None:
        return None
    return _alias_map.get(match.matched_name)


def get_nutrition_info(name: str) -> NutritionInfo | None:
    _ensure_loaded()
    assert _alias_map is not None
    assert _cache is not None

    key = name.strip().lower()
    canonical = _alias_map.get(key)
    if canonical is None:
        canonical = _brand_aware_match(key)
    if canonical is None:
        return None

    entry = _cache.get(canonical)
    if entry is None:
        return None

    per_100 = entry.get("per_100g", {})
    serving = entry.get("common_serving", {})

    return NutritionInfo(
        canonical_name=entry.get("canonical_name", canonical),
        calories_kcal=per_100.get("calories_kcal", 0),
        protein_g=per_100.get("protein_g", 0),
        carbs_g=per_100.get("carbs_g", 0),
        fat_g=per_100.get("fat_g", 0),
        fiber_g=per_100.get("fiber_g", 0),
        calcium_mg=per_100.get("calcium_mg", 0),
        iron_mg=per_100.get("iron_mg", 0),
        common_serving_amount=serving.get("amount", 100),
        common_serving_unit=serving.get("unit", "g"),
        category=entry.get("category", ""),
        notes=entry.get("notes", ""),
    )


def _extract_from_lot_nutrition(nutrition: dict) -> dict[str, float]:
    """Extract macros from a per-lot ``nutrition_per_100g`` dict (OFF format).

    Keys follow Open Food Facts ``nutriments`` naming (``energy-kcal_100g``,
    ``proteins_100g``, ``carbohydrates_100g``, ``fat_100g``, ``fiber_100g``).
    Missing keys default to 0.
    """
    return {
        "calories_kcal": float(nutrition.get("energy-kcal_100g", nutrition.get("energy_100g", 0)) or 0),
        "protein_g": float(nutrition.get("proteins_100g", nutrition.get("proteins", 0)) or 0),
        "carbs_g": float(nutrition.get("carbohydrates_100g", nutrition.get("carbohydrates", 0)) or 0),
        "fat_g": float(nutrition.get("fat_100g", nutrition.get("fat", 0)) or 0),
        "fiber_g": float(nutrition.get("fiber_100g", 0) or 0),
    }


def get_inventory_nutrition_summary(database: Any, user_id: str = "") -> NutritionSummary:
    _ensure_loaded()
    assert _cache is not None

    inventory = database.get_inventory(status="active", user_id=user_id)

    items: list[dict[str, Any]] = []
    missing: list[str] = []
    total_cal = 0.0
    total_pro = 0.0
    total_carb = 0.0
    total_fat = 0.0

    for lot in inventory:
        multiplier = lot.quantity / 100.0 if lot.quantity > 0 else 0.0

        # Prefer per-lot nutrition from barcode lookup over static reference.
        if lot.nutrition_per_100g:
            macros = _extract_from_lot_nutrition(lot.nutrition_per_100g)
            item_cal = macros["calories_kcal"] * multiplier
            item_pro = macros["protein_g"] * multiplier
            item_carb = macros["carbs_g"] * multiplier
            item_fat = macros["fat_g"] * multiplier
        else:
            info = get_nutrition_info(lot.canonical_name)
            if info is None:
                info = get_nutrition_info(lot.display_name)
            if info is None:
                missing.append(lot.display_name or lot.canonical_name)
                continue

            item_cal = info.calories_kcal * multiplier
            item_pro = info.protein_g * multiplier
            item_carb = info.carbs_g * multiplier
            item_fat = info.fat_g * multiplier

        total_cal += item_cal
        total_pro += item_pro
        total_carb += item_carb
        total_fat += item_fat

        items.append({
            "name": lot.display_name or lot.canonical_name,
            "quantity": lot.quantity,
            "unit": lot.unit,
            "calories_kcal": round(item_cal, 1),
            "protein_g": round(item_pro, 1),
            "carbs_g": round(item_carb, 1),
            "fat_g": round(item_fat, 1),
        })

    return NutritionSummary(
        items=items,
        total_calories=round(total_cal, 1),
        total_protein=round(total_pro, 1),
        total_carbs=round(total_carb, 1),
        total_fat=round(total_fat, 1),
        missing_items=missing,
    )


def format_nutrition_html(summary: NutritionSummary) -> str:
    from html import escape

    from shopstack.ui import card as ui_card
    from shopstack.ui import render_metric

    disclaimer = (
        "<div style='margin-top:16px;padding:8px 12px;border-radius:6px;"
        "background:var(--surface);font-size: 0.6875rem;color:var(--text-dim);'>"
        "&#9432; Nutrition data is approximate household guidance, not medical advice."
        "</div>"
    )

    macro_grid = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0;'>"
        f"{render_metric('Calories', f'{summary.total_calories:.0f} kcal')}{render_metric('Protein', f'{summary.total_protein:.1f} g')}"
        f"{render_metric('Carbs', f'{summary.total_carbs:.1f} g')}{render_metric('Fat', f'{summary.total_fat:.1f} g')}"
        "</div>"
    )

    if not summary.items:
        items_html = "<div style='color:var(--text-dim);'>No inventory items matched nutrition data.</div>"
    else:
        rows = ""
        for item in summary.items:
            rows += (
                "<tr>"
                f"<td style='border-bottom:1px solid var(--border);padding:6px 8px'>{escape(str(item['name']))}</td><td style='border-bottom:1px solid var(--border);padding:6px 8px'>{item['quantity']:.1f} {escape(str(item['unit']))}</td>"
                f"<td style='border-bottom:1px solid var(--border);padding:6px 8px'>{item['calories_kcal']:.0f}</td><td style='border-bottom:1px solid var(--border);padding:6px 8px'>{item['protein_g']:.1f}</td>"
                f"<td style='border-bottom:1px solid var(--border);padding:6px 8px'>{item['carbs_g']:.1f}</td><td style='border-bottom:1px solid var(--border);padding:6px 8px'>{item['fat_g']:.1f}</td>"
                "</tr>"
            )
        items_html = (
            "<table style='border-collapse:collapse;width:100%;font-size: 0.75rem;'>"
            "<tr>"
            "<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px'>Item</th>"
            "<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px'>Qty</th>"
            "<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px'>Cal</th>"
            "<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px'>Protein</th>"
            "<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px'>Carbs</th>"
            "<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px'>Fat</th>"
            "</tr>"
            f"{rows}"
            "</table>"
        )

    missing_html = ""
    if summary.missing_items:
        names = ", ".join(escape(n) for n in summary.missing_items[:10])
        missing_html = (
            "<div style='margin-top:8px;font-size: 0.75rem;color:var(--text-dim);'>"
            f"<strong>No nutrition data:</strong> {names}"
            "</div>"
        )

    return (
        macro_grid
        + ui_card("Kitchen Nutrition Breakdown", items_html)
        + missing_html
        + disclaimer
    )


def lookup_nutrition_html(query: str) -> str:
    from html import escape

    from shopstack.ui import badge_html, render_metric
    from shopstack.ui import card as ui_card

    if not query or not query.strip():
        return "<div style='color:var(--text-dim);'>Type an item name to look up nutrition facts.</div>"

    info = get_nutrition_info(query.strip())
    if info is None:
        return (
            "<div style='color:var(--text-dim);'>"
            f"No nutrition data found for <strong>{escape(query.strip())}</strong>."
            "</div>"
        )

    serving_mult = info.common_serving_amount / 100.0

    per_100g_grid = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0;'>"
        f"{render_metric('Calories', f'{info.calories_kcal:.0f} kcal')}{render_metric('Protein', f'{info.protein_g:.1f} g')}"
        f"{render_metric('Carbs', f'{info.carbs_g:.1f} g')}{render_metric('Fat', f'{info.fat_g:.1f} g')}"
        f"{render_metric('Fiber', f'{info.fiber_g:.1f} g')}{render_metric('Calcium', f'{info.calcium_mg:.0f} mg')}"
        f"{render_metric('Iron', f'{info.iron_mg:.1f} mg')}"
        "</div>"
    )

    serving_card = ui_card(
        f"Per Common Serving ({info.common_serving_amount:.0f} {escape(info.common_serving_unit)})",
        (
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;'>"
            f"{render_metric('Calories', f'{info.calories_kcal * serving_mult:.0f} kcal')}{render_metric('Protein', f'{info.protein_g * serving_mult:.1f} g')}"
            f"{render_metric('Carbs', f'{info.carbs_g * serving_mult:.1f} g')}{render_metric('Fat', f'{info.fat_g * serving_mult:.1f} g')}"
            "</div>"
        ),
    )

    category_badge = badge_html(info.category, "blue") if info.category else ""

    disclaimer = (
        "<div style='margin-top:12px;padding:8px 12px;border-radius:6px;"
        "background:var(--surface);font-size: 0.6875rem;color:var(--text-dim);'>"
        "&#9432; Nutrition data is approximate household guidance, not medical advice."
        "</div>"
    )

    return (
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;'><h3 style='margin:0;'>{escape(info.canonical_name.title())}</h3>"
        f"{category_badge}"
        "</div>"
        + ui_card("Per 100g", per_100g_grid)
        + serving_card
        + disclaimer
    )
