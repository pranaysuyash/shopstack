"""Regional alias regression fixture.

Per audit 2026-06-14: the alias maps had drift bugs (e.g. ``padavalakayi``
listed as both carrot and snake_gourd alias, ``dahi`` resolving to
``yogurt`` in some maps and ``curd`` in others, ``mirchi`` routing to
``capsicum`` in one resolver and ``green_chilli`` in another). These
tests lock in the canonical mappings and cross-resolver consistency
for all supported regional languages so regressions are caught
immediately.

Adding new aliases: add them to ``ITEM_ALIASES`` in
``shopstack/domain/unit_price.py``, then add the expected
(query, canonical) pair to ``REGIONAL_ALIAS_FIXTURES`` below.

Each entry: (query, expected_resolve_canonical, expected_normalize_item_name, note)
"""
from __future__ import annotations

import pytest

from shopstack.domain.unit_price import (
    ITEM_ALIASES,
    _CANONICAL_MAP,
    normalize_item_name,
    resolve_canonical,
)


# ── Regional alias regression fixture ─────────────────────────────────────
# Format: (query, resolve_canonical_expected, normalize_expected, note)
# The two resolvers intentionally differ in some cases (resolve_canonical
# is the market-search resolver, normalize_item_name is the
# shopping-list-normalization resolver), so we test them separately
# and add cross-resolver consistency tests for the critical mappings.
REGIONAL_ALIAS_FIXTURES: list[tuple[str, str, str, str]] = [
    # ── Hindi (market canonical is "curd", not "yogurt") ────────────────
    ("dahi", "curd", "curd", "Hindi: dahi → curd (was: yogurt)"),
    ("curd", "curd", "curd", "English: curd stays curd"),
    ("yogurt", "curd", "curd", "English: yogurt → curd (Indian market canonical)"),
    ("doodh", "milk", "milk", "Hindi: doodh → milk"),
    ("pyaaz", "onion", "onion", "Hindi: pyaaz → onion"),
    ("aloo", "potato", "potato", "Hindi: aloo → potato"),
    ("tamatar", "tomato", "tomato", "Hindi: tamatar → tomato"),
    ("gajar", "carrot", "carrot", "Hindi: gajar → carrot"),
    ("lehsun", "garlic", "garlic", "Hindi: lehsun → garlic"),
    ("adrak", "ginger", "ginger", "Hindi: adrak → ginger"),
    ("namak", "salt", "salt", "Hindi: namak → salt"),
    ("cheeni", "sugar", "sugar", "Hindi: cheeni → sugar"),
    ("chawal", "rice", "rice", "Hindi: chawal → rice"),
    ("dal", "lentils", "lentils", "Hindi: dal → lentils"),
    ("paneer", "paneer", "paneer", "Hindi: paneer stays paneer"),
    ("bhindi", "ladys_finger", "ladys_finger", "Hindi: bhindi → ladys_finger"),
    ("karela", "bitter_gourd", "bitter_gourd", "Hindi: karela → bitter_gourd"),
    ("lauki", "bottle_gourd", "bottle_gourd", "Hindi: lauki → bottle_gourd"),
    ("turai", "ridge_gourd", "ridge_gourd", "Hindi: turai → ridge_gourd"),
    ("baingan", "brinjal", "brinjal", "Hindi: baingan → brinjal"),
    ("dhania", "coriander", "coriander", "Hindi: dhania → coriander"),
    ("pudina", "mint", "mint", "Hindi: pudina → mint"),
    # ── Kannada (padavalakayi bug fix verification) ────────────────────
    ("padavalakayi", "snake_gourd", "snake_gourd",
     "Kannada: padavalakayi → snake_gourd in both resolvers (audit bug fix)"),
    # ── Tamil ──────────────────────────────────────────────────────────
    ("thakkali", "tomato", "tomato", "Tamil: thakkali → tomato"),
    ("vankaya", "brinjal", "brinjal", "Telugu: vankaya → brinjal"),
    ("kathirikai", "brinjal", "brinjal", "Tamil: kathirikai → brinjal"),
    ("vendakkai", "ladys_finger", "ladys_finger", "Tamil: vendakkai → ladys_finger"),
    ("murungakkai", "drumstick", "drumstick", "Tamil: murungakkai → drumstick"),
]


# ── Tests ────────────────────────────────────────────────────────────────


class TestRegionalAliases:
    """Each (query, expected_resolve, expected_normalize) pair must
    produce the expected canonical name through BOTH resolution paths.
    """

    @pytest.mark.parametrize("query,resolve_exp,normalize_exp,note", REGIONAL_ALIAS_FIXTURES)
    def test_resolve_canonical_matches(
        self, query: str, resolve_exp: str, normalize_exp: str, note: str,
    ) -> None:
        result = resolve_canonical(query)
        assert result == resolve_exp, (
            f"resolve_canonical({query!r}) = {result!r}, expected {resolve_exp!r}. "
            f"Note: {note}"
        )

    @pytest.mark.parametrize("query,resolve_exp,normalize_exp,note", REGIONAL_ALIAS_FIXTURES)
    def test_normalize_item_name_matches(
        self, query: str, resolve_exp: str, normalize_exp: str, note: str,
    ) -> None:
        result = normalize_item_name(query)
        assert result == normalize_exp, (
            f"normalize_item_name({query!r}) = {result!r}, expected {normalize_exp!r}. "
            f"Note: {note}"
        )


class TestCrossResolverConsistency:
    """Cross-resolver consistency checks for the dairy category where the
    dahi→curd/yogurt divergence was found. Both resolvers must agree
    on the canonical name for the same input."""

    @pytest.mark.parametrize("query", ["dahi", "curd", "yogurt", "doodh", "pyaaz", "tamatar"])
    def test_resolvers_agree_on_canonical_form(self, query: str) -> None:
        """The two resolvers must return the same canonical form
        (ignoring the dash/underscore space formatting difference)."""
        resolve_result = resolve_canonical(query)
        normalize_result = normalize_item_name(query)
        if resolve_result is None:
            pytest.skip(f"resolve_canonical has no mapping for {query!r}")
        # Both should produce the same canonical slug (modulo _/space)
        resolve_slug = resolve_result.replace(" ", "_")
        normalize_slug = normalize_result.replace(" ", "_")
        assert resolve_slug == normalize_slug, (
            f"Resolvers disagree on {query!r}: "
            f"resolve_canonical={resolve_result!r} → {resolve_slug!r}, "
            f"normalize_item_name={normalize_result!r} → {normalize_slug!r}. "
            f"This is the kind of split that made 'dahi' search miss "
            f"'curd' inventory rows. Fix the alias maps."
        )


class TestAliasMapConsistency:
    """Map-internal consistency checks that catch the kind of drift that
    caused the dahi→curd/yogurt split and the padavalakayi→carrot bug."""

    def test_dahi_resolves_to_curd(self) -> None:
        canonical = resolve_canonical("dahi")
        assert canonical == "curd", (
            f"dahi must resolve to 'curd' (Indian market canonical), "
            f"got {canonical!r}. The _CANONICAL_MAP and ITEM_ALIASES "
            f"maps have diverged — fix in shopstack/domain/unit_price.py."
        )

    def test_curd_resolves_consistently(self) -> None:
        canonical = resolve_canonical("curd")
        normalized = normalize_item_name("curd")
        assert canonical == "curd" and normalized == "curd", (
            f"curd resolution diverged: resolve_canonical={canonical!r}, "
            f"normalize_item_name={normalized!r}"
        )

    def test_yogurt_resolves_to_curd(self) -> None:
        canonical = resolve_canonical("yogurt")
        assert canonical == "curd", (
            f"yogurt must resolve to 'curd', got {canonical!r}. "
            f"Fix _CANONICAL_MAP['yogurt'] in unit_price.py."
        )

    def test_padavalakayi_not_mapped_to_carrot(self) -> None:
        """padavalakayi (Kannada snake gourd) must NOT be a carrot alias."""
        carrot_aliases = ITEM_ALIASES.get("carrot", [])
        assert "padavalakayi" not in carrot_aliases, (
            "padavalakayi is Kannada for snake gourd, NOT carrot. "
            "Remove it from ITEM_ALIASES['carrot']."
        )

    def test_padavalakayi_maps_to_snake_gourd(self) -> None:
        assert "padavalakayi" in ITEM_ALIASES.get("snake_gourd", []), (
            "padavalakayi should be an alias for snake_gourd."
        )

    def test_canonical_map_does_not_split_alias_canonicals(self) -> None:
        """If _CANONICAL_MAP routes X→Y and ITEM_ALIASES lists Y←X,
        then Y must be the canonical and X must NOT also be a canonical."""
        alias_canonicals = set(ITEM_ALIASES.keys())
        for query, target in _CANONICAL_MAP.items():
            if query in alias_canonicals and target != query:
                pytest.fail(
                    f"_CANONICAL_MAP routes {query!r} → {target!r} but "
                    f"ITEM_ALIASES treats {query!r} as a canonical name. "
                    f"This is the dahi→yogurt vs dahi→curd divergence. "
                    f"Pick one canonical and update both maps."
                )
