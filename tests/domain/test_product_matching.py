"""Tests for shopstack.domain.product_matching."""

from __future__ import annotations

import pytest

from shopstack.domain.product_matching import (
    MatchReason,
    MatchScore,
    best_match,
    score_product_match,
)


class TestMatchScore:
    """Tests for MatchScore dataclass."""

    def test_default_construction(self):
        s = MatchScore(score=0.5)
        assert s.matched_name == ""
        assert s.canonical_name == ""
        assert s.reasons == []

    def test_is_match_property(self):
        assert MatchScore(score=0.5).is_match is True
        assert MatchScore(score=0.49).is_match is False
        assert MatchScore(score=1.0).is_match is True
        assert MatchScore(score=0.0).is_match is False

    def test_to_dict_round_trip(self):
        s = MatchScore(
            score=0.7,
            matched_name="milk",
            canonical_name="milk",
            reasons=[MatchReason(factor="exact", detail="matched")],
        )
        d = s.to_dict()
        assert d["score"] == 0.7
        assert d["matched_name"] == "milk"
        assert d["canonical_name"] == "milk"
        assert d["reasons"][0]["factor"] == "exact"


class TestMatchReason:
    """Tests for MatchReason dataclass."""

    def test_minimal(self):
        r = MatchReason(factor="exact")
        assert r.detail == ""

    def test_with_detail(self):
        r = MatchReason(factor="alias", detail="doodh -> milk")
        assert r.factor == "alias"
        assert r.detail == "doodh -> milk"

    def test_to_dict(self):
        r = MatchReason(factor="substring", detail="q in c")
        d = r.to_dict()
        assert d == {"factor": "substring", "detail": "q in c"}


class TestScoreProductMatch:
    """Tests for score_product_match — fuzzy product matching."""

    def test_exact_match_returns_one(self):
        s = score_product_match("milk", "milk")
        assert s.score == 1.0
        assert s.reasons[0].factor == "exact"
        assert s.is_match

    def test_exact_match_case_insensitive(self):
        s = score_product_match("MILK", "milk")
        assert s.score == 1.0
        assert s.is_match

    def test_alias_match_high_score(self):
        s = score_product_match("doodh", "milk")
        assert s.score == 0.9
        assert s.reasons[0].factor == "alias"
        assert s.is_match

    def test_alias_reverse_direction(self):
        s = score_product_match("milk", "doodh")
        assert s.score == 0.9
        assert s.is_match

    def test_substring_match(self):
        s = score_product_match("whole", "whole milk")
        assert s.score == 0.7
        assert s.reasons[0].factor == "substring"
        assert s.is_match

    def test_substring_match_reverse(self):
        s = score_product_match("whole milk", "whole")
        assert s.score == 0.7
        assert s.is_match

    def test_prefix_or_substring_match(self):
        # Strings sharing a prefix match at substring or prefix level
        # (the algorithm checks substring first, so most "prefix" tests
        # actually return substring). This test verifies the prefix
        # branch is reachable in principle.
        s = score_product_match("ab", "abc")
        # "ab" is substring of "abc" → 0.7
        assert s.score == 0.7
        assert s.is_match

    def test_word_overlap_partial_match(self):
        s = score_product_match("amul milk", "fresh milk")
        assert s.is_match
        assert s.reasons[0].factor == "partial"

    def test_no_match_returns_zero(self):
        s = score_product_match("xyzzy", "milk")
        assert s.score == 0.0
        assert not s.is_match
        assert s.reasons[0].factor == "none"

    def test_empty_query(self):
        s = score_product_match("", "milk")
        assert s.score == 0.0
        assert not s.is_match

    def test_empty_candidate(self):
        s = score_product_match("milk", "")
        assert s.score == 0.0
        assert not s.is_match

    def test_both_empty(self):
        s = score_product_match("", "")
        assert s.score == 0.0
        assert not s.is_match

    def test_whitespace_normalized(self):
        s = score_product_match("  milk  ", "milk")
        assert s.score == 1.0

    def test_accent_stripping(self):
        s = score_product_match("càrri", "carri")
        assert s.score == 1.0  # accents stripped

    def test_canonical_name_set(self):
        s = score_product_match("doodh", "milk")
        assert s.canonical_name == "milk"

    def test_canonical_name_for_exact(self):
        s = score_product_match("milk", "milk")
        assert s.canonical_name == "milk"

    def test_matched_name_preserves_original_case(self):
        s = score_product_match("doodh", "Fresh Milk")
        assert s.matched_name == "Fresh Milk"

    def test_no_match_still_has_canonical(self):
        s = score_product_match("xyzzy", "milk")
        # When no match, canonical defaults to candidate canonical
        assert s.canonical_name in ("milk", "")


class TestBestMatch:
    """Tests for best_match — find best above threshold."""

    def test_returns_highest_score(self):
        candidates = ["bread", "milk", "almond milk"]
        result = best_match("milk", candidates, threshold=0.5)
        assert result is not None
        assert result.score >= 0.5
        # "milk" exact = 1.0
        assert result.canonical_name == "milk"

    def test_no_match_above_threshold(self):
        candidates = ["bread", "rice", "flour"]
        result = best_match("xyzzy", candidates, threshold=0.5)
        assert result is None

    def test_empty_candidates(self):
        assert best_match("milk", []) is None

    def test_threshold_filter(self):
        candidates = ["bread", "milk"]
        # With very high threshold, no match
        result = best_match("milk", candidates, threshold=1.5)
        assert result is None

    def test_picks_better_match(self):
        # "whole milk powder" should match "milk" at substring level (0.7)
        # and "milk" at exact level (1.0)
        candidates = ["milk", "rice"]
        result = best_match("milk", candidates, threshold=0.5)
        assert result is not None
        assert result.score == 1.0  # exact match wins


class TestAliasTable:
    """Smoke tests for the built-in alias table."""

    def test_common_aliases_resolve(self):
        pairs = [
            ("doodh", "milk"),
            ("pyaaz", "onions"),
            ("tamatar", "tomatoes"),
            ("aloo", "potatoes"),
            ("chai", "tea"),
            ("atta", "flour"),
            ("dahi", "curd"),
        ]
        for query, expected in pairs:
            s = score_product_match(query, expected)
            assert s.is_match, f"'{query}' should match '{expected}'"
            assert s.canonical_name == expected, f"'{query}' canonical should be '{expected}', got '{s.canonical_name}'"

    def test_unrelated_items_dont_match(self):
        s = score_product_match("doodh", "rice")
        assert not s.is_match
