from __future__ import annotations

from shopstack.eval.retrieval_corpus import build_retrieval_corpus, validate_retrieval_corpus


def test_retrieval_corpus_is_unique_and_has_all_contract_classes():
    cases = build_retrieval_corpus()
    assert len(cases) == 29
    assert validate_retrieval_corpus(cases) == ()
    assert {case.category for case in cases} == {"english", "hindi", "hard_negative", "no_match"}
    assert sum(bool(case.hard_negatives) for case in cases) == 6


def test_retrieval_corpus_rejects_expected_hard_negative_collision():
    cases = build_retrieval_corpus()
    invalid = cases[0].__class__(
        case_id="bad",
        query="milk",
        expected="milk",
        category="hard_negative",
        hard_negatives=("milk",),
    )
    errors = validate_retrieval_corpus((*cases, invalid))
    assert "expected item is also hard negative: bad" in errors
