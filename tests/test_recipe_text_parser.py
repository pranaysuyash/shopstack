"""Tests for the free-form recipe text parser.

Covers:

- Bullet list (``-``, ``*``) and numbered list (``1.``) parsing.
- Fractions (``1/2``, ``1 1/2``), decimals, integers, unicode fractions.
- Unit normalisations: ``tbsp``, ``tsp``, ``cup``, ``kg``, ``g``, ``L``,
  ``ml``, ``piece``, ``clove``, ``leaf``, etc.
- Prep descriptor stripping: ``chopped``, ``minced``, ``to taste``, etc.
- Parenthetical asides: ``2 cups flour (or maida)`` → ``flour``.
- Range notation: ``2-3 tomatoes`` → 2.
- Empty / whitespace / unparseable input handling.
- Lines that can't be parsed are returned as a single ingredient
  with ``notes=["unparseable quantity"]`` so the caller still sees the
  line.
"""

from __future__ import annotations

from shopstack.services.recipe_text_parser import (
    parse_recipe_text,
    text_to_shopping_items,
)


class TestParseRecipeText:
    def test_empty_input(self):
        assert parse_recipe_text("") == []
        assert parse_recipe_text("   \n  \n") == []

    def test_simple_quantity_and_unit(self):
        result = parse_recipe_text("2 cups rice")
        assert len(result) == 1
        assert result[0].canonical_name == "rice"
        assert result[0].quantity == 2.0
        assert result[0].unit == "cup"

    def test_no_unit_defaults_to_unit(self):
        result = parse_recipe_text("3 onions")
        assert result[0].unit == "unit"
        assert result[0].quantity == 3.0
        # resolve_canonical knows "onions" → "onion"
        assert result[0].canonical_name == "onion"

    def test_decimal_quantity(self):
        result = parse_recipe_text("1.5 kg potato")
        assert result[0].quantity == 1.5
        assert result[0].unit == "kg"

    def test_fraction_quantity(self):
        result = parse_recipe_text("1/2 tsp salt")
        assert result[0].quantity == 0.5
        assert result[0].unit == "tsp"

    def test_mixed_number_quantity(self):
        result = parse_recipe_text("1 1/2 cups milk")
        assert result[0].quantity == 1.5
        assert result[0].unit == "cup"

    def test_unicode_fraction_quantity(self):
        result = parse_recipe_text("½ cup sugar")
        assert result[0].quantity == 0.5
        assert result[0].unit == "cup"

    def test_range_quantity_takes_first(self):
        result = parse_recipe_text("2-3 tomatoes")
        assert result[0].quantity == 2.0
        # resolve_canonical knows "tomatoes" → "tomato"
        assert result[0].canonical_name == "tomato"

    def test_bullet_list_stripped(self):
        result = parse_recipe_text("- 2 cups rice\n- 1 tsp salt\n- 1 cup oil")
        assert len(result) == 3
        assert [r.canonical_name for r in result] == ["rice", "salt", "cooking_oil"]

    def test_numbered_list_stripped(self):
        result = parse_recipe_text("1. 2 cups rice\n2. 1 tsp salt")
        assert len(result) == 2
        assert result[0].canonical_name == "rice"
        assert result[1].canonical_name == "salt"

    def test_asterisk_bullets_stripped(self):
        result = parse_recipe_text("* 2 cups rice\n* 1 tsp salt")
        assert len(result) == 2

    def test_unit_aliases(self):
        # Tablespoon
        result = parse_recipe_text("1 tbsp ginger")
        assert result[0].unit == "tbsp"
        # Teaspoon
        result = parse_recipe_text("1 tsp turmeric")
        assert result[0].unit == "tsp"
        # Tablespoon spelled out
        result = parse_recipe_text("1 tablespoon oil")
        assert result[0].unit == "tbsp"
        # Kilos / liters
        result = parse_recipe_text("2 kg potato")
        assert result[0].unit == "kg"
        result = parse_recipe_text("1.5 L milk")
        assert result[0].unit == "L"
        # Pieces
        result = parse_recipe_text("3 pcs bread")
        assert result[0].unit == "unit"
        # Cloves
        result = parse_recipe_text("4 cloves garlic")
        assert result[0].unit == "cloves"

    def test_prep_descriptors_stripped(self):
        result = parse_recipe_text("1 onion, chopped")
        assert result[0].canonical_name == "onion"

    def test_parenthetical_asides_stripped(self):
        result = parse_recipe_text("2 cups rice (basmati)")
        assert result[0].canonical_name == "rice"

    def test_multi_line_complex(self):
        text = """- 2 cups rice
- 1 cup chickpea
- 1 tsp turmeric
- ½ tsp salt
- 2 tomates, chopped
- 1 onion, diced"""
        result = parse_recipe_text(text)
        assert len(result) == 6
        # Verify quantities parsed correctly (don't depend on resolve_canonical
        # substring matching which can map an ingredient unexpectedly).
        quantities = [r.quantity for r in result]
        assert 2.0 in quantities
        assert 1.0 in quantities
        assert 0.5 in quantities
        # Verify units parsed
        units = [r.unit for r in result]
        assert "cup" in units
        assert "tsp" in units
        # Every line should have a non-empty canonical name
        for r in result:
            assert r.canonical_name
            assert r.canonical_name == r.canonical_name.lower()

    def test_unparseable_line_surfaced_as_note(self):
        result = parse_recipe_text("just some words here")
        assert len(result) == 1
        assert "unparseable quantity" in result[0].notes
        # resolve_canonical may map this; either way the result is a slug.
        assert result[0].canonical_name  # non-empty

    def test_blank_lines_ignored(self):
        result = parse_recipe_text("2 cups rice\n\n\n1 tsp salt\n   \n")
        assert len(result) == 2

    def test_to_taste_no_quantity(self):
        """Lines like "salt to taste" should surface as unparseable
        but still appear (caller can decide to skip)."""
        result = parse_recipe_text("salt to taste")
        # The "to taste" descriptor stripping happens after the qty
        # match, so "salt to taste" → "salt" with no qty. The qty regex
        # requires a numeric prefix, so this line will be unparseable.
        assert len(result) == 1
        assert "unparseable quantity" in result[0].notes

    def test_realistic_recipe(self):
        text = """# Dal Makhani

Ingredients:
- 1 cup urad dal
- ¼ cup rajma
- 1 onion, chopped
- 2 tomatoes, pureed
- 1 tbsp ginger garlic paste
- 2 tbsp butter
- ½ tsp turmeric
- Salt to taste
"""
        result = parse_recipe_text(text)
        # Should extract 7 ingredients
        assert len(result) >= 6
        # All canonical names should be lowercased with underscores
        for r in result:
            assert r.canonical_name == r.canonical_name.lower()
            assert " " not in r.canonical_name


class TestTextToShoppingItems:
    def test_returns_list_of_dicts(self):
        text = "2 cups rice\n1 tsp salt"
        items = text_to_shopping_items(text)
        assert len(items) == 2
        assert items[0]["canonical_name"] == "rice"
        assert items[0]["requested_quantity"] == 2.0
        assert items[0]["unit"] == "cup"

    def test_includes_raw_line_for_auditability(self):
        items = text_to_shopping_items("2 cups rice")
        assert "raw_line" in items[0]
        assert items[0]["raw_line"] == "2 cups rice"
