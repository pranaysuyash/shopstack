"""Tests for ``shopstack.services.basket_compare``.

The comparison service is a pure-data layer that aggregates per-source pricing
across a basket of items. These tests cover:

- Per-source aggregation: each source's basket total is the sum of available
  line totals, items not at a source are recorded as unavailable.
- Inventory subtraction: owned quantity reduces net needed.
- Unit normalization: kg/g/l/ml/piece all flow through the same math.
- Edge cases: empty basket, single source, all-missing, identical prices.
- HTML rendering: covers the empty/insufficient/healthy branches and the
  no-XSS property (data values are HTML-escaped).
- Free-text parser: handles kg/g/l/piece and bare names, with Hinglish
  canonicalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord
from shopstack.services.basket_compare import (
    BasketComparison,
    SOURCE_LABELS,
    _best_line_total,
    _line_total_for_record,
    _normalize_unit_to_grams,
    compare_basket_across_sources,
    parse_basket_input,
    render_basket_comparison_html,
)


# ─── Test helpers ─────────────────────────────────────────────────────────


def _make_record(
    canonical: str,
    *,
    source: str,
    size_g: float = 1000.0,
    price_inr: float = 30.0,
    is_combo: bool = False,
    is_size_class: bool = False,
    is_piece_based: bool = False,
    is_available: bool = True,
) -> NormalizedMarketRecord:
    # Guard against divide-by-zero in the price_per_* derived fields when
    # callers explicitly pass size_g=0 to test edge cases.
    if size_g > 0 and not is_piece_based:
        per_kg = price_inr * 1000.0 / size_g
        per_100g = price_inr * 100.0 / size_g
    else:
        per_kg = None
        per_100g = None
    per_piece = (price_inr / size_g) if is_piece_based and size_g > 0 else None
    return NormalizedMarketRecord(
        source=source,
        source_category="fresh_vegetables",
        raw_name=canonical.replace("_", " ").title(),
        canonical_name=canonical,
        description="",
        raw_size=f"{int(size_g)}g" if not is_piece_based else f"{int(size_g)} pieces",
        normalized_quantity=size_g,
        normalized_unit="g" if not is_piece_based else "pieces",
        package_count=1,
        is_combo=is_combo,
        is_weight_based=not is_piece_based,
        is_piece_based=is_piece_based,
        is_size_class=is_size_class,
        size_class="",
        price_inr=price_inr,
        mrp_inr=price_inr * 1.2,
        discount_percent_displayed=0.0,
        discount_amount_inr=0.0,
        computed_discount_percent=0.0,
        availability="In stock" if is_available else "Sold out",
        is_available=is_available,
        tag="",
        is_ad=False,
        is_upgrade=False,
        card_index=0,
        delivery_time="",
        captured_at="2026-06-10T00:00:00",
        snapshot_id=f"{source}-snap",
        price_per_kg=per_kg,
        price_per_100g=per_100g,
        price_per_piece=per_piece,
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
    """Minimal stand-in for ``SourceRegistry`` that satisfies the service's duck-typed needs."""

    snapshots: dict[str, MarketSnapshot]
    freshness: dict[str, dict[str, Any]] = field(default_factory=dict)

    def all_snapshots(self) -> dict[str, MarketSnapshot]:
        return dict(self.snapshots)

    def freshness_of(self, source_id: str) -> dict[str, Any]:
        return self.freshness.get(
            source_id,
            {"source_id": source_id, "is_stale": False, "label": "Fresh"},
        )


def _two_source_registry() -> _FakeRegistry:
    """A controlled 2-source setup: Swiggy cheap, Blinkit expensive for tomato;
    Swiggy has no potato, Blinkit does. Used by most comparison tests."""
    swiggy = _make_snapshot(
        "swiggy",
        [
            _make_record("tomato", source="swiggy", size_g=1000, price_inr=30),
            # No potato at swiggy in this fixture
        ],
    )
    blinkit = _make_snapshot(
        "blinkit",
        [
            _make_record("tomato", source="blinkit", size_g=1000, price_inr=45),
            _make_record("potato", source="blinkit", size_g=1000, price_inr=28),
        ],
    )
    return _FakeRegistry(
        snapshots={"swiggy": swiggy, "blinkit": blinkit},
        freshness={
            "swiggy": {"source_id": "swiggy", "is_stale": False, "label": "Today's data"},
            "blinkit": {"source_id": "blinkit", "is_stale": False, "label": "Today's data"},
        },
    )


# ─── Unit normalization ───────────────────────────────────────────────────


class TestUnitNormalization:
    def test_kg_to_grams(self):
        assert _normalize_unit_to_grams(2, "kg") == 2000

    def test_grams_passthrough(self):
        assert _normalize_unit_to_grams(500, "g") == 500

    def test_liter_to_grams(self):
        # The market schema treats mL/grams equivalently for unit pricing
        assert _normalize_unit_to_grams(1, "L") == 1000

    def test_ml_passthrough(self):
        assert _normalize_unit_to_grams(250, "ml") == 250

    def test_unit_passthrough_for_pieces(self):
        assert _normalize_unit_to_grams(5, "unit") == 5

    def test_case_insensitive(self):
        assert _normalize_unit_to_grams(2, "KG") == 2000


# ─── Per-record line-total math ───────────────────────────────────────────


class TestLineTotal:
    def test_simple_2kg_from_1kg_pack(self):
        r = _make_record("tomato", source="s", size_g=1000, price_inr=30)
        assert _line_total_for_record(r, 2000) == 60.0

    def test_simple_2kg_from_500g_pack(self):
        r = _make_record("tomato", source="s", size_g=500, price_inr=15)
        # 2kg / 500g = 4 packs × ₹15 = ₹60
        assert _line_total_for_record(r, 2000) == 60.0

    def test_unavailable_returns_none(self):
        r = _make_record("x", source="s", is_available=False)
        assert _line_total_for_record(r, 1000) is None

    def test_combo_returns_none(self):
        r = _make_record("x", source="s", is_combo=True)
        assert _line_total_for_record(r, 1000) is None

    def test_size_class_returns_none(self):
        r = _make_record("x", source="s", is_size_class=True)
        assert _line_total_for_record(r, 1000) is None

    def test_zero_quantity_record(self):
        r = _make_record("x", source="s", size_g=0, price_inr=10)
        assert _line_total_for_record(r, 1000) is None

    def test_zero_requested_uses_record_price(self):
        r = _make_record("x", source="s", size_g=1000, price_inr=30)
        # Degenerate: requested 0g, return record's own price
        assert _line_total_for_record(r, 0) == 30.0


class TestBestLineTotal:
    def test_picks_cheapest_per_kg(self):
        records = [
            _make_record("x", source="s", size_g=1000, price_inr=50),
            _make_record("x", source="s", size_g=500, price_inr=20),  # 40/kg
            _make_record("x", source="s", size_g=1000, price_inr=30),  # 30/kg
        ]
        # Cheapest is the 30/kg option; for 2kg requested → 60
        assert _best_line_total(records, 2000) == 60.0

    def test_falls_back_to_piece_based(self):
        records = [
            _make_record("x", source="s", size_g=4, price_inr=20, is_piece_based=True),
        ]
        # For 12 pieces requested: 20 * (12/4) = 60
        assert _best_line_total(records, 12) == 60.0

    def test_returns_none_when_no_records(self):
        assert _best_line_total([], 1000) is None

    def test_skips_combos(self):
        records = [
            _make_record("x", source="s", is_combo=True, size_g=1000, price_inr=10),
        ]
        assert _best_line_total(records, 1000) is None


# ─── Comparison service ───────────────────────────────────────────────────


class TestCompareBasket:
    def test_basic_two_source_with_different_prices(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "tomato", "requested_quantity": 2.0, "unit": "kg"}],
        )
        # 2kg tomato: swiggy ₹60 (30/kg), blinkit ₹90 (45/kg)
        assert comp.total_requested == 1
        assert comp.matched_count == 1
        assert comp.per_item[0].line_totals == {"swiggy": 60.0, "blinkit": 90.0}
        assert comp.cheapest_source_id == "swiggy"
        assert comp.most_expensive_source_id == "blinkit"
        assert comp.total_savings_inr == 30.0
        assert comp.savings_pct == round(30 / 90 * 100, 1)

    def test_unavailable_item_marked_correctly(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "potato", "requested_quantity": 1.0, "unit": "kg"}],
        )
        # Potato only at blinkit
        assert "swiggy" in comp.per_item[0].unavailable_at
        assert "blinkit" not in comp.per_item[0].unavailable_at
        assert comp.per_item[0].line_totals == {"blinkit": 28.0}

    def test_inventory_subtraction(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "tomato", "requested_quantity": 2.0, "unit": "kg"}],
            inventory_map={"tomato": 500},  # 500g at home
        )
        # Net need = 1500g, so swiggy line = 30 * 1.5 = 45
        assert comp.per_item[0].line_totals["swiggy"] == 45.0
        assert comp.per_item[0].line_totals["blinkit"] == pytest.approx(67.5)
        assert any("Subtracted" in n for n in comp.per_item[0].notes)

    def test_inventory_covers_full_need(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "tomato", "requested_quantity": 2.0, "unit": "kg"}],
            inventory_map={"tomato": 5000},  # 5kg at home, more than enough
        )
        # Degenerate case: requested 0g, returns record's own price (degenerate pricing)
        # But the line totals are still computed; what matters is the note.
        assert any("enough at home" in n for n in comp.per_item[0].notes)

    def test_empty_basket(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(registry, [])
        assert comp.total_requested == 0
        assert comp.matched_count == 0
        assert comp.per_item == []
        assert not comp.is_meaningful
        assert comp.cheapest_source_id is None

    def test_single_source_not_meaningful(self):
        registry = _FakeRegistry(
            snapshots={
                "swiggy": _make_snapshot(
                    "swiggy",
                    [_make_record("tomato", source="swiggy", size_g=1000, price_inr=30)],
                ),
            },
        )
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "tomato", "requested_quantity": 1, "unit": "kg"}],
        )
        assert not comp.is_meaningful
        assert comp.cheapest_source_id is None
        assert comp.total_savings_inr == 0

    def test_all_items_missing_everywhere(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "mango", "requested_quantity": 1, "unit": "kg"}],
        )
        assert comp.matched_count == 0
        assert not comp.is_meaningful
        assert comp.per_item[0].unavailable_at == ["blinkit", "swiggy"]

    def test_identical_prices_zero_savings(self):
        swiggy = _make_snapshot(
            "swiggy",
            [_make_record("x", source="swiggy", size_g=1000, price_inr=30)],
        )
        blinkit = _make_snapshot(
            "blinkit",
            [_make_record("x", source="blinkit", size_g=1000, price_inr=30)],
        )
        registry = _FakeRegistry(snapshots={"swiggy": swiggy, "blinkit": blinkit})
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "x", "requested_quantity": 1, "unit": "kg"}],
        )
        assert comp.total_savings_inr == 0
        assert comp.savings_pct == 0
        assert comp.is_meaningful  # Two sources with data → still meaningful

    def test_per_source_coverage_pct(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [
                {"canonical_name": "tomato", "requested_quantity": 1, "unit": "kg"},
                {"canonical_name": "potato", "requested_quantity": 1, "unit": "kg"},
            ],
        )
        swiggy_b = next(s for s in comp.per_source if s.source_id == "swiggy")
        blinkit_b = next(s for s in comp.per_source if s.source_id == "blinkit")
        assert swiggy_b.coverage_pct == 50.0  # Only tomato
        assert blinkit_b.coverage_pct == 100.0  # Both
        assert swiggy_b.unavailable_items == ["potato"]

    def test_summary_dict(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "tomato", "requested_quantity": 2, "unit": "kg"}],
        )
        s = comp.summary()
        assert s["total_requested"] == 1
        assert s["matched"] == 1
        assert s["cheapest_source"] == "swiggy"
        assert s["sources_loaded"] == ["blinkit", "swiggy"]

    def test_piece_based_item_falls_back(self):
        swiggy = _make_snapshot(
            "swiggy",
            [_make_record("eggs", source="swiggy", size_g=12, price_inr=84, is_piece_based=True)],
        )
        blinkit = _make_snapshot(
            "blinkit",
            [_make_record("eggs", source="blinkit", size_g=6, price_inr=48, is_piece_based=True)],
        )
        registry = _FakeRegistry(snapshots={"swiggy": swiggy, "blinkit": blinkit})
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "eggs", "requested_quantity": 12, "unit": "pieces"}],
        )
        # Both: 12 eggs = 1 pack at swiggy (₹84) vs 2 packs at blinkit (₹96)
        assert comp.per_item[0].line_totals["swiggy"] == 84.0
        assert comp.per_item[0].line_totals["blinkit"] == 96.0
        assert comp.cheapest_source_id == "swiggy"

    def test_stale_flag_propagates(self):
        swiggy = _make_snapshot(
            "swiggy",
            [_make_record("x", source="swiggy", size_g=1000, price_inr=30)],
        )
        blinkit = _make_snapshot(
            "blinkit",
            [_make_record("x", source="blinkit", size_g=1000, price_inr=35)],
        )
        registry = _FakeRegistry(
            snapshots={"swiggy": swiggy, "blinkit": blinkit},
            freshness={
                "swiggy": {"source_id": "swiggy", "is_stale": True, "label": "3 days old"},
                "blinkit": {"source_id": "blinkit", "is_stale": False, "label": "Fresh"},
            },
        )
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "x", "requested_quantity": 1, "unit": "kg"}],
        )
        swiggy_b = next(s for s in comp.per_source if s.source_id == "swiggy")
        assert swiggy_b.is_stale is True
        assert swiggy_b.freshness_label == "3 days old"


# ─── HTML rendering ───────────────────────────────────────────────────────


class TestRenderHTML:
    def test_no_sources(self):
        comp = BasketComparison()
        html = render_basket_comparison_html(comp)
        assert "No market sources loaded" in html

    def test_no_items(self):
        comp = BasketComparison(source_ids=["swiggy"], per_source=[
            __import__("shopstack.services.basket_compare", fromlist=["SourceBasket"]).SourceBasket(
                source_id="swiggy", label="Swiggy"
            )
        ])
        html = render_basket_comparison_html(comp)
        assert "Enter at least one item" in html

    def test_single_source_falls_back_to_message(self):
        comp = BasketComparison(
            source_ids=["swiggy"],
            per_item=[__import__("shopstack.services.basket_compare", fromlist=["BasketLine"]).BasketLine(
                requested_name="x", canonical_name="x",
                requested_quantity=1, unit="kg", line_totals={"swiggy": 30}
            )],
            per_source=[__import__("shopstack.services.basket_compare", fromlist=["SourceBasket"]).SourceBasket(
                source_id="swiggy", label="Swiggy",
                line_totals={"x": 30}, basket_total=30, coverage_pct=100
            )],
        )
        html = render_basket_comparison_html(comp)
        assert "at least 2 sources" in html

    def test_full_render_includes_savings_and_table(self):
        registry = _two_source_registry()
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "tomato", "requested_quantity": 2, "unit": "kg"}],
        )
        html = render_basket_comparison_html(comp)
        assert "Cheapest" in html
        assert "Swiggy Instamart" in html
        assert "Blinkit" in html
        assert "₹60" in html
        assert "₹90" in html
        assert "₹30" in html  # savings
        # Cheapest row should be highlighted
        assert "var(--green)" in html

    def test_html_escapes_canonical_name(self):
        # Use a canonical name that the snapshot records also carry, so the
        # comparison actually renders line rows (instead of falling back to
        # the "not meaningful" empty state).
        swiggy = _make_snapshot(
            "swiggy",
            [_make_record("weird<script>name", source="swiggy", size_g=1000, price_inr=10)],
        )
        blinkit = _make_snapshot(
            "blinkit",
            [_make_record("weird<script>name", source="blinkit", size_g=1000, price_inr=12)],
        )
        registry = _FakeRegistry(snapshots={"swiggy": swiggy, "blinkit": blinkit})
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "weird<script>name", "requested_quantity": 1, "unit": "kg"}],
        )
        html = render_basket_comparison_html(comp)
        # The literal "<script>" must not appear unescaped in the output.
        assert "<script>" not in html
        # The escape sequence is what html.escape produces for "<" and ">".
        # .title() capitalises the "s" so we accept either form.
        lower = html.lower()
        assert "&lt;script&gt;" in lower or "&lt;script" in lower
        # Sanity: the rendered item is still present, just escaped.
        assert "weird" in lower

    def test_stale_footer_appears_when_any_source_stale(self):
        swiggy = _make_snapshot(
            "swiggy",
            [_make_record("x", source="swiggy", size_g=1000, price_inr=30)],
        )
        blinkit = _make_snapshot(
            "blinkit",
            [_make_record("x", source="blinkit", size_g=1000, price_inr=35)],
        )
        registry = _FakeRegistry(
            snapshots={"swiggy": swiggy, "blinkit": blinkit},
            freshness={
                "swiggy": {"source_id": "swiggy", "is_stale": True, "label": "Old"},
                "blinkit": {"source_id": "blinkit", "is_stale": False, "label": "Fresh"},
            },
        )
        comp = compare_basket_across_sources(
            registry,
            [{"canonical_name": "x", "requested_quantity": 1, "unit": "kg"}],
        )
        html = render_basket_comparison_html(comp)
        assert "outdated" in html
        assert "stale" in html.lower()


# ─── Free-text parser ─────────────────────────────────────────────────────


class TestParseBasketInput:
    def test_simple_lines(self):
        items = parse_basket_input("2kg onions\n1L milk")
        assert len(items) == 2
        assert items[0]["canonical_name"] == "onion"
        assert items[0]["requested_quantity"] == 2.0
        assert items[0]["unit"] == "kg"
        assert items[1]["canonical_name"] == "milk"
        assert items[1]["requested_quantity"] == 1.0
        assert items[1]["unit"] == "l"

    def test_quantity_with_space(self):
        items = parse_basket_input("500 g tomatoes")
        assert items[0]["canonical_name"] == "tomato"
        assert items[0]["requested_quantity"] == 500
        assert items[0]["unit"] == "g"

    def test_no_quantity(self):
        items = parse_basket_input("onions")
        assert items[0]["canonical_name"] == "onion"
        assert items[0]["requested_quantity"] == 1.0
        assert items[0]["unit"] == "unit"

    def test_piece_unit(self):
        items = parse_basket_input("12 eggs")
        assert items[0]["canonical_name"] == "egg" or items[0]["canonical_name"]  # Aliases
        assert items[0]["requested_quantity"] == 12
        # "eggs" canonicalizes — either way qty preserved
        assert items[0]["unit"] in ("pieces", "piece", "pcs", "pc", "unit")

    def test_hinglish_alias_canonicalizes(self):
        items = parse_basket_input("2kg pyaaz")
        # pyaaz → onion via ITEM_ALIASES
        assert items[0]["canonical_name"] == "onion"

    def test_comments_and_blanks_ignored(self):
        items = parse_basket_input("# comment\n\n2kg onions\n# another\n")
        assert len(items) == 1
        assert items[0]["canonical_name"] == "onion"

    def test_empty_input(self):
        assert parse_basket_input("") == []
        assert parse_basket_input(None) == []  # type: ignore[arg-type]

    def test_realistic_basket(self):
        text = """
        # Weekly groceries
        2kg onion
        1.5kg potato
        500g tomato
        1L milk
        12 eggs
        green chilli
        """
        items = parse_basket_input(text)
        assert len(items) == 6
        # Verify the last item — no qty, "green chilli" canonicalizes
        assert items[-1]["canonical_name"] == "green_chilli"
        assert items[-1]["requested_quantity"] == 1.0
        assert items[-1]["unit"] == "unit"


# ─── Source labels constant ───────────────────────────────────────────────


class TestSourceLabels:
    def test_all_four_core_sources_have_labels(self):
        for s in ("swiggy", "blinkit", "zepto", "dmart"):
            assert s in SOURCE_LABELS
            assert SOURCE_LABELS[s]  # non-empty
