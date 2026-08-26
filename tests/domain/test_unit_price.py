"""Tests for shopstack.domain.unit_price."""

from shopstack.domain.unit_price import (
    parse_size,
    compute_unit_prices,
    resolve_canonical,
    normalize_item_name,
    canonicalize_name,
)


class TestParseSize:
    def test_weight_kg(self):
        r = parse_size("1 kg")
        assert r.normalized_quantity == 1000
        assert r.normalized_unit == "g"
        assert r.is_weight_based
        assert r.package_count == 1

    def test_weight_g(self):
        r = parse_size("500 g")
        assert r.normalized_quantity == 500
        assert r.normalized_unit == "g"
        assert r.is_weight_based

    def test_weight_kg_x_multipack(self):
        r = parse_size("1 kg x 2")
        assert r.normalized_quantity == 2000
        assert r.package_count == 2

    def test_pieces(self):
        r = parse_size("6 pieces")
        assert r.normalized_quantity == 6
        assert r.normalized_unit == "pieces"
        assert r.is_piece_based

    def test_pieces_multipack(self):
        r = parse_size("4 pieces x 3")
        assert r.normalized_quantity == 12
        assert r.package_count == 3

    def test_combo(self):
        r = parse_size("3 combo")
        assert r.is_combo
        assert "combo_or_pack_no_weight" in (r.warnings or [])

    def test_indian_decimal_kg(self):
        # Indian households write decimals with a comma
        # ("1,5 kg" not "1.5 kg"). The Swiggy data for Indian
        # markets uses both numberings.
        r = parse_size("1,5 kg")
        assert r.normalized_quantity == 1500
        assert r.normalized_unit == "g"
        assert r.is_weight_based

    def test_indian_decimal_l(self):
        r = parse_size("0,5 l")
        assert r.normalized_quantity == 500
        assert r.normalized_unit == "mL"

    def test_indian_decimal_g_small(self):
        r = parse_size("0,5 g")
        assert r.normalized_quantity == 0.5
        assert r.normalized_unit == "g"

    def test_indian_decimal_with_multipack(self):
        r = parse_size("1,5 kg x 2")
        assert r.normalized_quantity == 3000
        assert r.package_count == 2

    def test_indian_decimal_size_class_small(self):
        r = parse_size("1,5 small")
        assert r.is_size_class
        assert r.size_class == "small"
        assert r.normalized_quantity == 120

    def test_indian_decimal_size_class_large(self):
        r = parse_size("1,5 large")
        assert r.size_class == "large"
        assert r.normalized_quantity == 270

    def test_international_decimal_size_class(self):
        r = parse_size("1.5 medium")
        assert r.size_class == "medium"
        assert r.normalized_quantity == 180

    def test_list_separator_not_converted(self):
        # A real list separator "1, 2, 3 pieces" must not be
        # wrongly converted to "1. 2. 3 pieces"
        r = parse_size("1, 2, 3 pieces")
        # The regex won't match (spaces in input); we just verify
        # we didn't corrupt the input
        assert r.warnings and "unrecognized_size" in r.warnings[0]
    def test_pack(self):
        r = parse_size("5 pack")
        assert r.is_pack
        assert "combo_or_pack_no_weight" in (r.warnings or [])

    def test_size_class(self):
        r = parse_size("6 medium")
        assert r.is_size_class
        assert r.is_weight_based
        assert r.normalized_quantity == 6 * 120
        assert r.size_class == "medium"

    def test_plain_number(self):
        r = parse_size("10")
        assert r.normalized_quantity == 10
        assert r.normalized_unit == "pieces"
        assert r.is_piece_based

    def test_unrecognized(self):
        r = parse_size("some junk")
        assert r.warnings
        assert "unrecognized_size" in r.warnings[0]

    def test_empty(self):
        r = parse_size("")
        assert r.warnings == ["empty_size"]


class TestComputeUnitPrices:
    def test_price_per_kg(self):
        result = compute_unit_prices(
            price=50, quantity=500, unit="g",
            is_weight_based=True, is_piece_based=False,
        )
        assert result["price_per_kg"] == 100.0
        assert result["price_per_100g"] == 10.0
        assert result["price_per_piece"] is None

    def test_price_per_piece(self):
        result = compute_unit_prices(
            price=30, quantity=6, unit="pieces",
            is_weight_based=False, is_piece_based=True,
        )
        assert result["price_per_piece"] == 5.0
        assert result["price_per_kg"] is None

    def test_zero_price(self):
        result = compute_unit_prices(
            price=0, quantity=500, unit="g",
            is_weight_based=True, is_piece_based=False,
        )
        assert all(v is None for v in result.values())

    def test_zero_quantity(self):
        result = compute_unit_prices(
            price=50, quantity=0, unit="g",
            is_weight_based=True, is_piece_based=False,
        )
        assert all(v is None for v in result.values())


class TestResolveCanonical:
    def test_exact(self):
        assert resolve_canonical("tomato") == "tomato"

    def test_substring(self):
        assert resolve_canonical("fresh indian tomato") == "tomato"

    def test_alias(self):
        assert resolve_canonical("tamatar") == "tomato"

    def test_alias_with_spaces(self):
        assert resolve_canonical("shimla mirch") == "capsicum"

    def test_unknown(self):
        assert resolve_canonical("super rare fruit") is None

    def test_empty(self):
        assert resolve_canonical("") is None


class TestNormalizeItemName:
    def test_exact_match(self):
        assert normalize_item_name("tamatar") == "tomato"

    def test_unknown_returned_as_is(self):
        n = normalize_item_name("xyz_unknown")
        assert n == "xyz_unknown"


class TestCanonicalizeName:
    def test_single_item(self):
        slug, variety, parts = canonicalize_name("Indian Tomato (Hybrid)")
        assert slug == "tomato"
        assert variety == "Hybrid"

    def test_combo(self):
        slug, variety, parts = canonicalize_name("Potato & Onion")
        assert slug.startswith("combo_")
        assert len(parts) >= 2

    def test_brand_prefix_strip(self):
        slug, _, _ = canonicalize_name("nectr Tomato")
        assert slug == "tomato"
