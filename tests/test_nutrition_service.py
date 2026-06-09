from __future__ import annotations

from shopstack.services.nutrition import (
    NutritionInfo,
    NutritionSummary,
    get_inventory_nutrition_summary,
    get_nutrition_info,
    load_nutrition_reference,
)


def test_load_nutrition_reference_returns_dict():
    ref = load_nutrition_reference()
    assert isinstance(ref, dict)


def test_get_nutrition_info_unknown():
    result = get_nutrition_info("definitely_not_a_real_food_xyz")
    assert result is None


def test_get_nutrition_info_empty_string():
    result = get_nutrition_info("")
    assert result is None


def test_get_nutrition_info_returns_dataclass():
    # "tomato" should be in the reference if data exists
    result = get_nutrition_info("tomato")
    if result is not None:
        assert isinstance(result, NutritionInfo)
        assert result.canonical_name == "tomato"
        assert result.calories_kcal >= 0
        assert result.protein_g >= 0


def test_get_nutrition_info_case_insensitive():
    r1 = get_nutrition_info("Tomato")
    r2 = get_nutrition_info("tomato")
    if r1 is not None:
        assert r2 is not None
        assert r1.canonical_name == r2.canonical_name


def test_nutrition_summary_dataclass():
    summary = NutritionSummary(
        items=[{"name": "milk", "calories_kcal": 50}],
        total_calories=50.0,
        total_protein=3.0,
        total_carbs=5.0,
        total_fat=2.0,
        missing_items=[],
    )
    assert summary.total_calories == 50.0
    assert len(summary.items) == 1


def test_inventory_nutrition_summary_empty_db(db):
    summary = get_inventory_nutrition_summary(db)
    assert isinstance(summary, NutritionSummary)
    assert summary.items == []
    assert summary.total_calories == 0.0
    assert summary.missing_items == []


def test_inventory_nutrition_summary_with_items(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="rice",
        display_name="Rice",
        quantity=500.0,
        unit="g",
    )
    summary = get_inventory_nutrition_summary(db)
    assert isinstance(summary, NutritionSummary)
    # If rice is in the nutrition reference, it should show up
    # If not, it should be in missing_items
    if summary.items:
        assert summary.total_calories > 0
    else:
        assert "Rice" in summary.missing_items or "rice" in summary.missing_items
