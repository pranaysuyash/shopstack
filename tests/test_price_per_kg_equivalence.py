"""Regression tests for the price_per_kg divergence fix (2026-06-15).

Background
==========

Two implementations of "compute per-kg price" exist in the codebase:

1. ``shopstack.services.price_memory.PriceMemoryService._price_per_kg``
   — the canonical implementation that takes a full observation
   object (with ``price``, ``quantity``, ``unit``). Handles ``g``,
   ``kg``, ``mL``, and ``L`` (with the canonical liquid
   assumption 1 mL ≈ 1 g).

2. ``shopstack.domain.unit_price.compute_unit_prices`` — a
   sibling implementation that takes raw ``price``, ``quantity``,
   ``unit`` (and an ``is_weight_based`` / ``is_piece_based`` flag).
   Used by price-compare cards, market intelligence, and basket
   analytics.

Prior to 2026-06-15, ``compute_unit_prices`` only handled ``g`` and
``mL`` — meaning that a 5kg atta pack (the most common grocery
format) silently returned ``None`` for ``price_per_kg`` in any UI
surface that consumed ``compute_unit_prices``, while the same item
via ``_price_per_kg`` returned a correct per-kg price. The
divergence surfaced in the 2026-06-15 comprehensive review delta
(`Docs/COMPREHENSIVE_REVIEW_FINDINGS_2026-06-15_delta.md` Finding 1).

Fix
===

This test asserts that ``compute_unit_prices`` and
``PriceMemoryService._price_per_kg`` return equivalent ``price_per_kg``
values for the four canonical weight/volume units (``g``, ``kg``,
``mL``, ``L``) when given the same input data. The test is the
guard against the bug returning — any future change to either
implementation that breaks the equivalence (e.g., the "kg" or "L"
branch is dropped again) fails this test.

Long-term consolidation
=======================

The two implementations compute overlapping but differently-scoped
values (one takes a full observation, the other takes raw inputs)
from differently-normalized inputs (raw unit string vs
``parse_size()`` output). The 2026-06-15 comprehensive review
recommended a follow-up architecture review on whether one canonical
"price normalization" module should own this. Tracked in
``Docs/decision_records/2026-06-15_price_normalization.md``.

Until that consolidation lands, this test is the bridge that
prevents the two implementations from drifting apart again.
"""
from __future__ import annotations

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────


class _FakeObservation:
    """Minimal duck-type of a price observation row.

    Matches the columns of the ``price_observations`` SQLite table
    (see ``shopstack.persistence.database.Database.create_tables``):
    ``price``, ``quantity``, ``unit`` (REAL/TEXT).
    """

    def __init__(self, *, price: float, quantity: float, unit: str) -> None:
        self.price = price
        self.quantity = quantity
        self.unit = unit


# Representative real-world price points (₹ per package):
#   1 L Amul Toned Milk  → 64
#   500 g Daawat Basmati → 200
#   5 kg Aashirvaad Atta → 680
#   1 L Saffola Gold     → 195
#   250 g Tata Tea       →  95
#   1 L Nandini Curd     →  60
CANONICAL_PRICE_FIXTURES: list[tuple[str, float, float, str, bool]] = [
    # (label,                          price, quantity, unit, is_weight_based)
    ("1L milk @ ₹64",                   64,   1,        "L",   True),
    ("1L milk @ ₹64 (mL)",              64,   1000,     "mL",  True),
    ("500g rice @ ₹200",                200,  500,      "g",   True),
    ("5kg atta @ ₹680",                 680,  5,        "kg",  True),
    ("1L oil @ ₹195",                   195,  1,        "L",   True),
    ("250g tea @ ₹95",                  95,   250,      "g",   True),
    ("1L curd @ ₹60",                   60,   1,        "L",   True),
]


# ── Tests ────────────────────────────────────────────────────────────


@pytest.fixture
def price_memory_service():
    """Construct a PriceMemoryService without a DB (stateless method)."""
    from shopstack.services.price_memory import PriceMemoryService
    # Bypass __init__ because we only need the static _price_per_kg.
    return PriceMemoryService.__new__(PriceMemoryService)


def _assert_per_kg_match(
    label: str,
    price: float,
    quantity: float,
    unit: str,
    is_weight_based: bool,
    price_memory_service,
) -> None:
    """Assert that the two implementations agree on price_per_kg."""
    from shopstack.domain.unit_price import compute_unit_prices

    obs = _FakeObservation(price=price, quantity=quantity, unit=unit)
    canonical = price_memory_service._price_per_kg(obs)
    sibling = compute_unit_prices(
        price=price,
        quantity=quantity,
        unit=unit,
        is_weight_based=is_weight_based,
    )

    assert canonical is not None, (
        f"PriceMemoryService._price_per_kg returned None for {label!r}. "
        f"Input: price={price}, quantity={quantity}, unit={unit!r}."
    )
    sibling_ppk = sibling["price_per_kg"]
    assert sibling_ppk is not None, (
        f"compute_unit_prices returned None price_per_kg for {label!r}. "
        f"This is the 2026-06-15 regression: kg and L units were silently "
        f"dropped. Input: price={price}, quantity={quantity}, unit={unit!r}. "
        f"See Docs/COMPREHENSIVE_REVIEW_FINDINGS_2026-06-15_delta.md Finding 1."
    )
    # Both use round(..., 2) so the values should match exactly.
    assert round(canonical, 2) == round(sibling_ppk, 2), (
        f"price_per_kg divergence for {label!r}: "
        f"PriceMemoryService._price_per_kg={canonical!r}, "
        f"compute_unit_prices={sibling_ppk!r}. "
        f"The two implementations must agree; this guards against the "
        f"unit-coverage gap that caused liquid + 5kg-format items to "
        f"silently show '—' in price-compare cards."
    )


@pytest.mark.parametrize(
    "label,price,quantity,unit,is_weight_based",
    CANONICAL_PRICE_FIXTURES,
    ids=[f[0] for f in CANONICAL_PRICE_FIXTURES],
)
def test_compute_unit_prices_handles_all_weight_units(
    label: str,
    price: float,
    quantity: float,
    unit: str,
    is_weight_based: bool,
    price_memory_service,
) -> None:
    """compute_unit_prices returns price_per_kg for g, kg, mL, L.

    Regression for the 2026-06-15 bug: kg and L were silently
    dropped, leaving 5kg atta and 1L milk without a per-kg price
    in any UI surface backed by compute_unit_prices.
    """
    from shopstack.domain.unit_price import compute_unit_prices

    result = compute_unit_prices(
        price=price,
        quantity=quantity,
        unit=unit,
        is_weight_based=is_weight_based,
    )

    assert result["price_per_kg"] is not None, (
        f"compute_unit_prices returned None for {label!r}. "
        f"Input: price={price}, quantity={quantity}, unit={unit!r}, "
        f"is_weight_based={is_weight_based}. The 2026-06-15 fix "
        f"extended the weight-based branch to handle kg and L; "
        f"this guard prevents re-introduction of the unit-coverage gap."
    )

    # Sanity: kg/L inputs must give a value consistent with the
    # physical conversion (1 kg = 10 × 100 g, so price_per_100g
    # should be price_per_kg / 10 for kg and L inputs).
    if unit in ("kg", "L"):
        assert result["price_per_100g"] is not None, (
            f"price_per_100g missing for {label!r}."
        )
        assert round(result["price_per_kg"] / 10, 2) == round(
            result["price_per_100g"], 2
        ), (
            f"price_per_100g should equal price_per_kg / 10 for "
            f"kg/L inputs. Got price_per_kg={result['price_per_kg']}, "
            f"price_per_100g={result['price_per_100g']} for {label!r}."
        )


@pytest.mark.parametrize(
    "label,price,quantity,unit,is_weight_based",
    CANONICAL_PRICE_FIXTURES,
    ids=[f[0] for f in CANONICAL_PRICE_FIXTURES],
)
def test_price_per_kg_implementations_agree(
    label: str,
    price: float,
    quantity: float,
    unit: str,
    is_weight_based: bool,
    price_memory_service,
) -> None:
    """The two price_per_kg implementations return the same value.

    The canonical (``PriceMemoryService._price_per_kg``) and the
    sibling (``compute_unit_prices``) compute per-kg price from
    different shapes of input (observation vs raw fields), but
    for the same underlying price/quantity/unit they must agree.
    This is the bridge test that prevents the two implementations
    from silently diverging in the future.
    """
    _assert_per_kg_match(
        label, price, quantity, unit, is_weight_based,
        price_memory_service,
    )


def test_pieces_return_price_per_piece_not_kg(price_memory_service) -> None:
    """Pieces must not produce a per-kg price (would be meaningless)."""
    from shopstack.domain.unit_price import compute_unit_prices

    result = compute_unit_prices(
        price=50,
        quantity=1,
        unit="pieces",
        is_piece_based=True,
    )
    assert result["price_per_piece"] == 50.0
    assert result["price_per_kg"] is None
    assert result["price_per_100g"] is None


def test_unknown_unit_returns_all_none(price_memory_service) -> None:
    """Unknown units (no matching branch) must return all None.

    This is the safe default: a UI surface receiving a None knows
    to render '—' instead of an incorrect price. Returning a
    silent 0 or 0.0 would be worse — the user would think they
    have a free product.
    """
    from shopstack.domain.unit_price import compute_unit_prices

    result = compute_unit_prices(
        price=64,
        quantity=1,
        unit="unknown_unit",
        is_weight_based=True,
    )
    assert result == {
        "price_per_kg": None,
        "price_per_100g": None,
        "price_per_piece": None,
    }


def test_zero_or_negative_inputs_return_all_none(price_memory_service) -> None:
    """Zero or negative prices/quantities must not produce a result.

    A zero-quantity item is not a real product, and a zero-price
    item is either an error or a free sample — both should
    surface as 'no data' to the UI, not '₹0 per kg'.
    """
    from shopstack.domain.unit_price import compute_unit_prices

    for price, quantity in [(0, 1000), (-1, 1000), (1000, 0), (1000, -1)]:
        result = compute_unit_prices(
            price=price,
            quantity=quantity,
            unit="mL",
            is_weight_based=True,
        )
        assert result == {
            "price_per_kg": None,
            "price_per_100g": None,
            "price_per_piece": None,
        }, f"Got non-None for price={price}, quantity={quantity}: {result}"
