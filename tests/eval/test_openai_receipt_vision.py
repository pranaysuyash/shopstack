from __future__ import annotations

from scripts.eval_openai_receipt_vision import EXPECTED, compare_receipt


def test_receipt_vision_scorer_requires_all_parsed_fields():
    assert compare_receipt(EXPECTED)["exact_match"] is True

    incomplete = {**EXPECTED, "lines": EXPECTED["lines"][:-1]}
    result = compare_receipt(incomplete)
    assert result["lines_match"] is False
    assert result["exact_match"] is False


def test_receipt_vision_scorer_handles_malformed_total_without_crashing():
    malformed = {**EXPECTED, "total": "not-a-number"}
    result = compare_receipt(malformed)
    assert result["total_match"] is False
    assert result["exact_match"] is False
