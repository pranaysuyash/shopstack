"""Tests for the combo parser v2 (description-based component extraction).

The combo parser v2 parses the product ``description`` field for
component lists rather than relying on hardcoded name-based heuristics.
This is the long-term fix recommended by the 2026-06-14 audit.

The Swiggy snapshot at ``data/swiggy_fresh_vegetables_cards_6jun26.json``
has the Sambar Veg Combo with description:
    "Drumstick, Brinjal, Raw Banana and Pumpkin Fresh veggies combo
     for Vishu festive cooking"

The OLD heuristic (name-based) would return the hardcoded
``["drumstick", "brinjal", "raw_banana", "pumpkin"]`` — which happens
to be correct for this one case but is brittle (any new combo like
"Paneer Tikka Combo" or "Diwali Special Combo" would have no
hardcoded mapping and would fail).

The NEW parser extracts components from the description, filtering
out generic marketing phrases, and resolves each candidate to its
canonical name. This works for any combo with a well-formed
description.
"""
from __future__ import annotations

import pytest

from shopstack.domain.unit_price import canonicalize_name


class TestComboParserV2:
    """The description-based combo parser should extract components
    that match the actual data, not the hardcoded fallback."""

    def test_sambar_veg_from_actual_swiggy_description(self):
        """Sambar Veg Combo description from the Swiggy snapshot.

        Expected components: Drumstick, Brinjal, Raw Banana, Pumpkin
        (the actual items listed in the description).
        """
        _, _, components = canonicalize_name(
            "Sambar Veg Combo",
            description="Drumstick, Brinjal, Raw Banana and Pumpkin Fresh veggies combo for Vishu festive cooking",
        )
        assert "drumstick" in components
        assert "brinjal" in components
        assert "raw_banana" in components
        assert "pumpkin" in components
        # Should NOT contain the old wrong components
        assert "radish" not in components
        assert "cluster_beans" not in components
        assert "ladys_finger" not in components

    def test_description_components_override_hardcoded_fallback(self):
        """If the description is provided, use it; don't fall back to
        the hardcoded name-based heuristic."""
        _, _, components = canonicalize_name(
            "Sambar Veg Combo",
            description="Okra, Pumpkin, Carrot Fresh combo",
        )
        # The description's components should be used, not the
        # hardcoded "drumstick, brinjal, raw_banana, pumpkin"
        assert "okra" in components or "ladys_finger" in components
        assert "pumpkin" in components
        assert "carrot" in components

    def test_filters_marketing_phrases(self):
        """Generic marketing phrases like 'fresh', 'combo', 'festive',
        'cooking' should be filtered out, not treated as components."""
        _, _, components = canonicalize_name(
            "Diwali Special Combo",
            description="Drumstick, Brinjal and Raw Banana Fresh combo for festive cooking",
        )
        assert "drumstick" in components
        assert "brinjal" in components
        assert "raw_banana" in components
        # The marketing phrases should NOT be components
        assert "fresh" not in components
        assert "combo" not in components
        assert "festive" not in components
        assert "cooking" not in components
        assert "fresh combo" not in components
        assert "combo for" not in components

    def test_handles_and_separator(self):
        """The parser splits on 'and' as well as commas."""
        _, _, components = canonicalize_name(
            "Mixed Veg Combo",
            description="Tomato and Onion and Carrot Fresh pack",
        )
        assert "tomato" in components
        assert "onion" in components
        assert "carrot" in components

    def test_handles_ampersand_separator(self):
        """The parser splits on '&' as well as commas."""
        _, _, components = canonicalize_name(
            "Bhindi Combo",
            description="Ladies Finger & Okra Fresh pack",
        )
        # Both should resolve to the same canonical (ladys_finger)
        assert "ladys_finger" in components

    def test_empty_description_falls_back_to_name_heuristic(self):
        """If no description is provided, fall back to the hardcoded
        name-based heuristic for known combos (sambar veg, herbs mix)."""
        _, _, components = canonicalize_name("Sambar Veg Combo")
        # The hardcoded fallback should return the previously-correct
        # components (which we also fixed to match the actual data)
        assert "drumstick" in components
        assert "brinjal" in components
        assert "raw_banana" in components
        assert "pumpkin" in components

    def test_unresolved_candidates_are_dropped(self):
        """Candidates that don't match any canonical should be dropped,
        not appended as raw text (which would create non-canonical
        components that never match inventory)."""
        _, _, components = canonicalize_name(
            "Mystery Combo",
            description="Asparagus, Quinoa, Dragon Fruit Combo pack",
        )
        # Asparagus, Quinoa, Dragon Fruit are not in our alias maps
        # — they should NOT appear in components
        assert "asparagus" not in components
        assert "quinoa" not in components
        assert "dragon fruit" not in components

    def test_deduplicates_repeated_candidates(self):
        """If a component is mentioned twice (e.g. in title and
        description), it should appear only once."""
        _, _, components = canonicalize_name(
            "Tomato Combo",
            description="Tomato, Tomato, Onion Fresh pack",
        )
        assert components.count("tomato") == 1
        assert "onion" in components

    def test_handles_missing_description_gracefully(self):
        """Empty/None description should not crash."""
        _, _, components_a = canonicalize_name("Sambar Veg Combo", description="")
        _, _, components_b = canonicalize_name("Sambar Veg Combo", description=None)
        # Both should fall back to the hardcoded heuristic
        assert "drumstick" in components_a
        assert "drumstick" in components_b
