from __future__ import annotations

from benchmarks.modal.text_normalization import compute_wer, normalize_text, transliterate_devanagari


def test_transliterate_devanagari_round_trips_common_household_phrase() -> None:
    assert transliterate_devanagari("दूध घर पे है क्या?") == "doodh ghar pe hai kya?"


def test_normalize_text_applies_household_aliases_after_transliteration() -> None:
    assert normalize_text("ब्रेड एक्सपायरी कल का है स्किप कर दूँ।", transliterate=True) == "bred expiry kal ka hai skip kar doon"


def test_compute_wer_is_zero_for_equivalent_devanagari_and_romanized_phrase() -> None:
    assert compute_wer("doodh ghar pe hai kya", "दूध घर पे है क्या?", transliterate_hypothesis=True) == 0.0
