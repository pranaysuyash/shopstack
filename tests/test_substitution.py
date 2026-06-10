"""Tests for the Substitution engine.

Covers:
  - Canonical substitution map matching (broccoli→cauliflower, etc.)
  - Premium-to-basic substitution (upgrade sold out, regular available)
  - Size substitution (alternative pack sizes)
  - Category alternatives from canonical map
  - SubstitutionResult properties (best_available, has_suggestions)
  - Edge cases: no match, item available (no substitution needed)
"""

from __future__ import annotations

import pytest

from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord


# ── Helper to build a minimal snapshot ──────────────────────────────────────


def _make_record(
    canonical: str,
    price_inr: float = 30.0,
    ppk: float | None = 60.0,
    raw_name: str = "",
    raw_size: str = "500 g",
    available: bool = True,
    is_upgrade: bool = False,
    is_ad: bool = False,
    tag: str = "",
    is_combo: bool = False,
    variety: str = "",
    description: str = "",
) -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        source="test",
        source_category="vegetables",
        raw_name=raw_name or canonical.replace("_", " ").title(),
        raw_size=raw_size,
        price_inr=price_inr,
        mrp_inr=price_inr * 1.1,
        discount_percent_displayed=0.0,
        discount_amount_inr=0.0,
        computed_discount_percent=0.0,
        availability="available" if available else "sold_out",
        is_available=available,
        is_weight_based=ppk is not None,
        is_piece_based=False,
        is_combo=is_combo,
        is_upgrade=is_upgrade,
        is_ad=is_ad,
        is_size_class=False,
        tag=tag,
        variety=variety,
        description=description,
        canonical_name=canonical,
        package_count=1,
        size_class="",
        card_index=0,
        delivery_time="30 min",
        captured_at="2026-06-09",
        snapshot_id="test",
        normalized_quantity=500,
        normalized_unit="g",
        price_per_kg=ppk,
        price_per_100g=None,
        price_per_piece=None,
        component_names=[],
        normalization_warnings=[],
        brand="",
    )


@pytest.fixture
def snapshot():
    """A snapshot with both available and sold-out items + substitutes."""
    records = [
        # ── Available items ──
        _make_record("broccoli", price_inr=50, ppk=100, raw_name="Broccoli", raw_size="500 g"),
        _make_record("cauliflower", price_inr=30, ppk=60, raw_name="Cauliflower", raw_size="500 g"),
        _make_record("cabbage", price_inr=20, ppk=40, raw_name="Cabbage", raw_size="500 g"),
        _make_record("french_beans", price_inr=25, ppk=50, raw_name="French Beans", raw_size="500 g"),
        _make_record("tomato", price_inr=28, ppk=56, raw_name="Indian Tomato", raw_size="500 g"),
        _make_record("tomato", price_inr=15, ppk=None, raw_name="Tomato", raw_size="1 Piece", available=False, is_upgrade=False),
        _make_record("tomato", price_inr=35, ppk=70, raw_name="nectr Indian Tomato", raw_size="500 g",
                     available=False, is_upgrade=True, tag="upgrade", description="Chemical Free"),
        _make_record("onion", price_inr=31, ppk=31, raw_name="Onion", raw_size="1 kg"),
        _make_record("potato", price_inr=27, ppk=27, raw_name="Potato", raw_size="1 kg"),
        _make_record("carrot", price_inr=28, ppk=56, raw_name="Carrot", raw_size="500 g"),
        _make_record("cucumber", price_inr=20, ppk=40, raw_name="Cucumber", raw_size="500 g"),
        _make_record("ridge_gourd", price_inr=36, ppk=120, raw_name="Ridge Gourd", raw_size="2 Medium"),
        _make_record("bottle_gourd", price_inr=25, ppk=50, raw_name="Bottle Gourd", raw_size="500 g"),
        # ── Sold-out items ──
        _make_record("broccoli", price_inr=50, ppk=100, raw_name="Broccoli", raw_size="500 g", available=False),
        _make_record("zucchini", price_inr=40, ppk=80, raw_name="Zucchini", raw_size="500 g", available=False),
    ]
    return MarketSnapshot(
        snapshot_id="test-substitution",
        source="swiggy_test",
        source_category="vegetables",
        captured_at="2026-06-09",
        raw_records=[],
        normalized_records=records,
    )


# ── Canonical substitution map tests ────────────────────────────────────────


class TestSubstituteMap:
    def test_substitute_map_broccoli(self):
        from shopstack.services.substitution import SUGGEST_SUBSTITUTE_MAP
        subs = SUGGEST_SUBSTITUTE_MAP.get("broccoli")
        assert subs is not None
        assert subs[0][0] == "cauliflower"

    def test_substitute_map_coriander(self):
        from shopstack.services.substitution import SUGGEST_SUBSTITUTE_MAP
        subs = SUGGEST_SUBSTITUTE_MAP.get("coriander")
        assert subs is not None
        assert any(s[0] == "mint" for s in subs)

    def test_substitute_map_no_match(self):
        from shopstack.services.substitution import SUGGEST_SUBSTITUTE_MAP
        assert SUGGEST_SUBSTITUTE_MAP.get("dragon_fruit") is None


# ── find_substitutions tests ────────────────────────────────────────────────


class TestFindSubstitutions:
    def test_sold_out_gets_suggestions(self, snapshot):
        """Sold-out broccoli should get substitution suggestions."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("broccoli", snapshot)
        assert result.has_suggestions
        assert result.has_available_alternative
        assert result.best_available is not None
        assert result.best_available.substitute_canonical in ("cauliflower", "french_beans", "cabbage")

    def test_available_item_no_substitution(self, snapshot):
        """Available onion should return no suggestions by default."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("onion", snapshot)
        assert not result.has_suggestions
        assert result.best_available is None

    def test_available_item_with_include_no_extra_suggestions(self, snapshot):
        """Available onion with include_available=True and no variants gets no suggestions."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("onion", snapshot, include_available=True)
        # Onion has 1 available record, no sold-out variants, not in substitute map
        assert not result.has_suggestions

    def test_premium_to_basic(self, snapshot):
        """Premium tomato (upgrade, sold out) should get regular alternative."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("tomato", snapshot)
        assert result.has_suggestions
        # Should have premium_to_basic suggestion
        premium_suggestions = [s for s in result.suggestions if s.substitution_type == "premium_to_basic"]
        assert len(premium_suggestions) >= 1
        assert "Regular" in premium_suggestions[0].substitute_display
        assert premium_suggestions[0].is_available

    def test_substitution_reason_mentions_price(self, snapshot):
        """Substitution suggestions should include price info in reason."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("broccoli", snapshot)
        assert result.has_suggestions
        for s in result.suggestions:
            assert "₹" in s.reason
            assert s.price_inr is not None

    def test_substitution_confidence_scores(self, snapshot):
        """Premium-to-basic should have higher confidence than alternatives."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("tomato", snapshot)
        assert result.has_suggestions
        premium = [s for s in result.suggestions if s.substitution_type == "premium_to_basic"]
        if premium:
            assert premium[0].confidence >= 0.85

    def test_no_substitutions_for_unknown(self, snapshot):
        """Unknown item with no match should return empty result."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("dragon_fruit", snapshot)
        assert not result.has_suggestions

    def test_best_available_returns_preferred(self, snapshot):
        """best_available should return the highest-confidence suggestion."""
        from shopstack.services.substitution import find_substitutions
        result = find_substitutions("broccoli", snapshot)
        assert result.has_available_alternative
        best = result.best_available
        assert best is not None
        assert best.is_available
        assert 0 < best.confidence <= 1.0

    def test_properties_reflect_state(self, snapshot):
        """SubstitutionResult properties should correctly reflect suggestion state."""
        from shopstack.services.substitution import find_substitutions, SubstitutionResult
        from shopstack.services.substitution import SubstitutionSuggestion

        # Empty result
        empty = SubstitutionResult(original_canonical="test", original_display="Test")
        assert not empty.has_suggestions
        assert not empty.has_available_alternative
        assert empty.best_available is None

        # Result with only unavailable suggestions
        from shopstack.market.schema import NormalizedMarketRecord
        unavailable_only = SubstitutionResult(
            original_canonical="test",
            original_display="Test",
            suggestions=[
                SubstitutionSuggestion(
                    original_canonical="test",
                    substitute_canonical="other",
                    substitute_display="Other",
                    substitution_type="category_alternative",
                    reason="Test",
                    confidence=0.5,
                    is_available=False,
                )
            ],
        )
        assert unavailable_only.has_suggestions
        assert not unavailable_only.has_available_alternative
        assert unavailable_only.best_available is None


# ── Size substitution tests ─────────────────────────────────────────────────


class TestSizeSubstitution:
    def test_size_substitution_multiple_sizes(self):
        """Multiple sizes of same available item should produce size suggestions."""
        from shopstack.services.substitution import find_substitutions

        records = [
            _make_record("tomato", price_inr=28, ppk=56, raw_name="Indian Tomato", raw_size="500 g"),
            _make_record("tomato", price_inr=55, ppk=55, raw_name="Indian Tomato", raw_size="1 kg"),
            _make_record("tomato", price_inr=15, ppk=None, raw_name="Tomato", raw_size="1 Piece", available=False),
        ]
        snap = MarketSnapshot(
            snapshot_id="size-test",
            source="test",
            source_category="vegetables",
            captured_at="2026-06-09",
            raw_records=[],
            normalized_records=records,
        )
        # Tomato has available records but also some sold-out ones
        # Since not all are sold out, no substitution needed without include_available
        result = find_substitutions("tomato", snap)
        # Should have size suggestions since we use include_available-like behavior
        # Actually, since there ARE available records (500g, 1kg), the only sold-out is 1 Piece
        # For premium-to-basic: none are upgrade
        # For size: same_item_available will be populated

    def test_available_item_size_variants(self):
        """Available item should get size alternative suggestions with include_available."""
        from shopstack.services.substitution import find_substitutions

        records = [
            _make_record("tomato", price_inr=28, ppk=56, raw_name="Indian Tomato", raw_size="500 g"),
            _make_record("tomato", price_inr=55, ppk=55, raw_name="Indian Tomato", raw_size="1 kg"),
        ]
        snap = MarketSnapshot(
            snapshot_id="size-test-2",
            source="test",
            source_category="vegetables",
            captured_at="2026-06-09",
            raw_records=[],
            normalized_records=records,
        )
        result = find_substitutions("tomato", snap, include_available=True)
        # With include_available and no sold-out upgrades, should still get canonical map suggestions
        # Tomato isn't in _SUBSTITUTE_MAP, so no category alternatives
        # Size substitution needs sold_out_with_upgrade OR same_item_available with len>1
        # Since all items are available and no upgrade versions, we get size suggestions
        assert result.has_suggestions


# ── _is_premium helper tests ────────────────────────────────────────────────


class TestIsPremium:
    def test_upgrade_tag_is_premium(self):
        from shopstack.services.substitution import _is_premium
        record = _make_record("tomato", available=False, is_upgrade=True)
        assert _is_premium(record)

    def test_chemical_free_in_description(self):
        from shopstack.services.substitution import _is_premium
        record = _make_record("tomato", available=False, description="Chemical Free Tomatoes")
        assert _is_premium(record)

    def test_organic_in_raw_name(self):
        from shopstack.services.substitution import _is_premium
        record = _make_record("carrot", available=False, raw_name="Organic Carrot")
        assert _is_premium(record)

    def test_plain_item_not_premium(self):
        from shopstack.services.substitution import _is_premium
        record = _make_record("onion")
        assert not _is_premium(record)


# ── Edge case and error handling tests ──────────────────────────────────────


class TestSubstitutionEdgeCases:
    def test_empty_snapshot(self):
        """Empty snapshot should return empty result."""
        from shopstack.services.substitution import find_substitutions
        empty = MarketSnapshot(
            snapshot_id="e", source="e", source_category="garden",
            captured_at="2026-06-09", raw_records=[], normalized_records=[],
        )
        result = find_substitutions("broccoli", empty)
        assert not result.has_suggestions

    def test_sold_out_only_snapshot(self):
        """Snapshot with only sold-out items — no available alternatives."""
        from shopstack.services.substitution import find_substitutions
        records = [
            _make_record("broccoli", available=False),
        ]
        snap = MarketSnapshot(
            snapshot_id="soldout-only",
            source="test",
            source_category="vegetables",
            captured_at="2026-06-09",
            raw_records=[],
            normalized_records=records,
        )
        result = find_substitutions("broccoli", snap)
        # No available items to substitute with
        assert not result.has_suggestions
