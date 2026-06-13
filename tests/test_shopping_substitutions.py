"""Tests for the shopping-list substitution service.

The substitution engine (``shopstack.services.substitution``) is already
extensively tested in ``test_substitution.py``. These tests focus on the
new wire-up layer: taking a shopping list, running the engine per item,
and producing well-formed HTML for the shopping list view.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord
from shopstack.services.shopping_substitutions import (
    ItemSubstitutions,
    get_substitutions_for_list,
    render_substitutions_html,
)


def _make_record(
    canonical: str,
    *,
    source: str,
    size_g: float = 1000,
    price: float = 30,
    available: bool = True,
    is_combo: bool = False,
    is_upgrade: bool = False,
) -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        source=source,
        source_category="fresh_vegetables",
        raw_name=canonical.replace("_", " ").title(),
        canonical_name=canonical,
        description="",
        raw_size=f"{int(size_g)}g",
        normalized_quantity=size_g,
        normalized_unit="g",
        package_count=1,
        is_combo=is_combo,
        is_weight_based=True,
        is_piece_based=False,
        is_size_class=False,
        size_class="",
        price_inr=price,
        mrp_inr=price * 1.2,
        discount_percent_displayed=0.0,
        discount_amount_inr=0.0,
        computed_discount_percent=0.0,
        availability="In stock" if available else "Sold out",
        is_available=available,
        tag="",
        is_ad=False,
        is_upgrade=is_upgrade,
        card_index=0,
        delivery_time="",
        captured_at="2026-06-10T00:00:00",
        snapshot_id=f"{source}-snap",
        price_per_kg=price * 1000 / size_g,
        price_per_100g=price * 100 / size_g,
        price_per_piece=None,
    )


def _make_snapshot(source: str, records: list[NormalizedMarketRecord]) -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id=f"{source}-snap",
        source=source,
        source_category="fresh_vegetables",
        captured_at="2026-06-10T00:00:00",
        raw_records=[],
        normalized_records=records,
        analytics={},
    )


@dataclass
class _FakeRegistry:
    snapshots: dict[str, MarketSnapshot]

    def all_snapshots(self) -> dict[str, MarketSnapshot]:
        return dict(self.snapshots)


def _registry_with_soldout() -> _FakeRegistry:
    """Broccoli is sold out, but cauliflower and beans are available."""
    snap = _make_snapshot("swiggy", [
        _make_record("broccoli", source="swiggy", available=False, is_upgrade=True),
        _make_record("cauliflower", source="swiggy", price=40),
        _make_record("french_beans", source="swiggy", price=50),
    ])
    return _FakeRegistry(snapshots={"swiggy": snap})


# ─── Service tests ────────────────────────────────────────────────────────


class TestGetSubstitutionsForList:
    def test_sold_out_item_returns_suggestions(self):
        items = [{"canonical_name": "broccoli", "display_name": "Broccoli"}]
        result = get_substitutions_for_list(items, _registry_with_soldout())
        assert len(result) == 1
        assert result[0].is_sold_out is True
        assert result[0].has_suggestions is True
        # The substitution map has broccoli → cauliflower as first option
        assert result[0].best.substitute_canonical == "cauliflower"

    def test_available_item_returns_no_suggestions(self):
        items = [{"canonical_name": "broccoli", "display_name": "Broccoli"}]
        snap = _make_snapshot("swiggy", [
            _make_record("broccoli", source="swiggy", price=80),
        ])
        reg = _FakeRegistry(snapshots={"swiggy": snap})
        result = get_substitutions_for_list(items, reg)
        assert len(result) == 1
        # No suggestions when item is in stock
        assert result[0].has_suggestions is False
        assert result[0].is_sold_out is False

    def test_no_market_data_returns_empty(self):
        items = [{"canonical_name": "broccoli", "display_name": "Broccoli"}]
        result = get_substitutions_for_list(items, None)
        assert len(result) == 1
        assert result[0].has_suggestions is False

        result = get_substitutions_for_list(items, _FakeRegistry(snapshots={}))
        assert len(result) == 1
        assert result[0].has_suggestions is False

    def test_multiple_items_mixed(self):
        items = [
            {"canonical_name": "broccoli", "display_name": "Broccoli"},
            {"canonical_name": "onion", "display_name": "Onion"},
        ]
        result = get_substitutions_for_list(items, _registry_with_soldout())
        assert len(result) == 2
        # Only broccoli (sold out) has suggestions
        assert result[0].has_suggestions is True
        assert result[1].has_suggestions is False

    def test_object_input_with_attribute_access(self):
        """Shopping list items may be objects, not dicts."""
        @dataclass
        class _ListItem:
            canonical_name: str
            display_name: str = ""

        items = [_ListItem(canonical_name="broccoli", display_name="Broccoli")]
        result = get_substitutions_for_list(items, _registry_with_soldout())
        assert len(result) == 1
        assert result[0].has_suggestions is True

    def test_empty_item_list(self):
        assert get_substitutions_for_list([], _registry_with_soldout()) == []
        assert get_substitutions_for_list([], None) == []

    def test_item_missing_canonical_name_is_skipped(self):
        items = [{"display_name": "Mystery"}]
        result = get_substitutions_for_list(items, _registry_with_soldout())
        # Empty canonical → skipped
        assert result == []


# ─── Renderer tests ───────────────────────────────────────────────────────


class TestRenderSubstitutionsHtml:
    def test_empty_returns_empty(self):
        assert render_substitutions_html([]) == ""

    def test_no_suggestions_returns_empty(self):
        items = [ItemSubstitutions(canonical_name="x", display_name="X", is_sold_out=False)]
        assert render_substitutions_html(items) == ""

    def test_renders_substitution_row(self):
        items = get_substitutions_for_list(
            [{"canonical_name": "broccoli", "display_name": "Broccoli"}],
            _registry_with_soldout(),
        )
        html = render_substitutions_html(items)
        assert "Substitution Suggestions" in html
        assert "Broccoli" in html
        assert "sold out" in html
        assert "Cauliflower" in html  # first substitute (capitalised)
        assert "₹40" in html  # price of cauliflower

    def test_html_escapes_xss(self):
        items = [
            ItemSubstitutions(
                canonical_name="weird<script>",
                display_name="Weird<script>",
                is_sold_out=True,
                suggestions=[
                    # Synthesise a bare-minimum suggestion
                    __import__("shopstack.services.substitution", fromlist=["SubstitutionSuggestion"]).SubstitutionSuggestion(
                        original_canonical="weird<script>",
                        substitute_canonical="safe_sub",
                        substitute_display="<script>alert(1)</script>",
                        substitution_type="category_alternative",
                        reason="xss test",
                        confidence=0.7,
                        price_inr=50.0,
                        price_per_kg=50.0,
                        is_available=True,
                    ),
                ],
            )
        ]
        html = render_substitutions_html(items)
        # The literal "<script>" should not appear unescaped
        assert "<script>alert(1)</script>" not in html
        # The escaped form should be present
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_renders_more_count_for_multiple_suggestions(self):
        snap = _make_snapshot("swiggy", [
            _make_record("broccoli", source="swiggy", available=False, is_upgrade=True),
            _make_record("cauliflower", source="swiggy", price=40),
            _make_record("french_beans", source="swiggy", price=50),
            _make_record("cabbage", source="swiggy", price=30),
            _make_record("zucchini", source="swiggy", price=60),
        ])
        reg = _FakeRegistry(snapshots={"swiggy": snap})
        items = get_substitutions_for_list(
            [{"canonical_name": "broccoli", "display_name": "Broccoli"}],
            reg,
        )
        html = render_substitutions_html(items)
        # We expect +N more (4 substitutes total)
        assert "+" in html
        assert "more" in html
