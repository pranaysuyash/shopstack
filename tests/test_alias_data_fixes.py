"""Regression tests for alias data-layer bugs fixed in 2026-06-14.

These tests lock in the fixes for the three alias bugs that the
GitHub audit flagged:

  1. dahi/curd/yogurt resolved to different canonicals depending on
     which resolver was called (FIXED: all three now resolve to "curd")

  2. padavalakayi (Kannada for snake gourd) was listed as both a carrot
     alias and a snake_gourd alias (FIXED: removed from carrot)

  3. The combo parser hardcoded sambar veg components that didn't
     match the actual Swiggy data (FIXED: components now match the
     description, and a description-based parser is the primary path)

Per motto_v3 §0.8 (Data Layer and Configuration Rule), alias maps
are product architecture. These tests ensure the fixes stick.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from shopstack.domain import unit_price
from shopstack.domain.product_matching import _ALIAS_TO_CANONICAL
from shopstack.domain.unit_price import (
    _CANONICAL_MAP,
    ITEM_ALIASES,
    canonicalize_name,
    normalize_item_name,
    resolve_canonical,
)


# ── Regression: dahi/curd/yogurt unified to "curd" ─────────────────────


class TestDahiCurdYogurtUnification:
    """All three queries must resolve to the same canonical: 'curd'."""

    @pytest.mark.parametrize("query", ["dahi", "curd", "yogurt"])
    def test_resolve_canonical_returns_curd(self, query: str):
        assert resolve_canonical(query) == "curd", (
            f"resolve_canonical({query!r}) must return 'curd' "
            f"(Indian market canonical), got {resolve_canonical(query)!r}"
        )

    @pytest.mark.parametrize("query", ["dahi", "curd", "yogurt"])
    def test_normalize_item_name_returns_curd(self, query: str):
        result = normalize_item_name(query)
        assert result == "curd", (
            f"normalize_item_name({query!r}) must return 'curd', "
            f"got {result!r}"
        )

    def test_canonical_map_no_longer_routes_dahi_to_yogurt(self):
        """_CANONICAL_MAP must not route dahi/curd/yogurt to yogurt."""
        for query in ("dahi", "curd", "yogurt"):
            if query in _CANONICAL_MAP:
                assert _CANONICAL_MAP[query] == "curd", (
                    f"_CANONICAL_MAP[{query!r}] = {_CANONICAL_MAP[query]!r} "
                    f"must be 'curd', not 'yogurt'. This is the dahi→yogurt "
                    f"divergence that broke inventory search."
                )

    def test_product_matching_canonical_is_curd_not_yogurt(self):
        """_ALIAS_TO_CANONICAL in product_matching.py must treat
        'curd' as the canonical, not 'yogurt'."""
        assert "curd" in _ALIAS_TO_CANONICAL, (
            "_ALIAS_TO_CANONICAL must include 'curd' as a canonical"
        )
        assert "yogurt" not in _ALIAS_TO_CANONICAL or \
            _ALIAS_TO_CANONICAL.get("yogurt") == "curd", (
            "If 'yogurt' is in _ALIAS_TO_CANONICAL, it must resolve to 'curd'"
        )


# ── Regression: padavalakayi no longer misclassified as carrot ─────────


class TestPadavalakayiSnakeGourd:
    """padavalakayi is Kannada for snake gourd, NOT carrot."""

    def test_padavalakayi_not_a_carrot_alias(self):
        """padavalakayi must NOT appear in ITEM_ALIASES['carrot']."""
        carrot_aliases = ITEM_ALIASES.get("carrot", [])
        assert "padavalakayi" not in carrot_aliases, (
            "padavalakayi is Kannada for snake gourd, not carrot. "
            "Remove it from ITEM_ALIASES['carrot']."
        )

    def test_padavalakayi_resolves_to_snake_gourd(self):
        """padavalakayi must resolve to snake_gourd (not carrot)."""
        result = resolve_canonical("padavalakayi")
        assert result == "snake_gourd", (
            f"padavalakayi must resolve to 'snake_gourd', got {result!r}"
        )

    def test_padavalakayi_is_a_snake_gourd_alias(self):
        """padavalakayi should still be listed as a snake_gourd alias."""
        snake_gourd_aliases = ITEM_ALIASES.get("snake_gourd", [])
        assert "padavalakayi" in snake_gourd_aliases, (
            "padavalakayi should be in ITEM_ALIASES['snake_gourd']"
        )


# ── Regression: combo parser matches actual Swiggy data ───────────────


class TestSambarVegComboComponents:
    """The sambar veg combo components must match the Swiggy snapshot."""

    def test_sambar_veg_uses_actual_swiggy_components(self):
        """The Sambar Veg Combo description from the Swiggy snapshot
        is: 'Drumstick, Brinjal, Raw Banana and Pumpkin Fresh veggies
             combo for Vishu festive cooking'

        The combo parser must extract these components.
        """
        _, _, components = canonicalize_name(
            "Sambar Veg Combo",
            description="Drumstick, Brinjal, Raw Banana and Pumpkin Fresh veggies combo for Vishu festive cooking",
        )
        # All four actual components should be present
        for expected in ("drumstick", "brinjal", "raw_banana", "pumpkin"):
            assert expected in components, (
                f"Sambar Veg Combo should include {expected!r}, "
                f"got {components!r}. The combo parser isn't matching "
                f"the actual Swiggy data."
            )

    def test_sambar_veg_old_wrong_components_absent(self):
        """The OLD wrong components (radish, cluster_beans, ladys_finger)
        must no longer appear in sambar veg combos parsed from the
        Swiggy description."""
        _, _, components = canonicalize_name(
            "Sambar Veg Combo",
            description="Drumstick, Brinjal, Raw Banana and Pumpkin Fresh veggies combo for Vishu festive cooking",
        )
        for wrong in ("radish", "cluster_beans", "ladys_finger"):
            assert wrong not in components, (
                f"{wrong!r} was the OLD hardcoded component that didn't "
                f"match the actual Swiggy data. The description-based "
                f"parser should not return it."
            )


# ── Regression: combo parser v2 uses description when available ────────


class TestComboParserV2PrimaryPath:
    """The description-based parser is the primary path; the name-based
    fallback is only for empty descriptions."""

    def test_description_takes_precedence_over_name_heuristic(self):
        """If a description is provided, it should be used, not the
        hardcoded name-based heuristic."""
        _, _, components = canonicalize_name(
            "Sambar Veg Combo",
            description="Okra, Pumpkin Fresh combo",
        )
        # Description's components should be used
        assert "okra" in components or "ladys_finger" in components
        assert "pumpkin" in components
        # Hardcoded fallback should NOT add "brinjal" or "raw_banana"
        # (those were the wrong old components)
        assert "brinjal" not in components

    def test_no_description_falls_back_to_name_heuristic(self):
        """When no description is provided, the name-based heuristic
        still works for known combos (backward compat)."""
        _, _, components = canonicalize_name("Sambar Veg Combo")
        assert "drumstick" in components
        assert "brinjal" in components
        assert "raw_banana" in components
        assert "pumpkin" in components
