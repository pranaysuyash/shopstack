"""Contract tests for the provider-neutral capability policy catalog."""

from __future__ import annotations

import json

import pytest

from shopstack.eval.capability_matrix import (
    CAPABILITY_DECISIONS,
    capability_decision_rows,
    get_capability_decision,
    validate_capability_matrix,
)


def test_canonical_matrix_is_unique_and_structurally_valid():
    assert len(CAPABILITY_DECISIONS) == 12
    assert validate_capability_matrix() == ()
    assert len({decision.key for decision in CAPABILITY_DECISIONS}) == 12


def test_matrix_separates_task_policy_from_provider_selection():
    planner = get_capability_decision("planner_tool_calling")
    assert planner.authority == "proposal"
    assert "no_mutation" in planner.fallback
    assert "model" not in planner.to_dict()
    assert "provider" not in planner.to_dict()


def test_retrieval_requires_negative_and_no_match_evidence():
    retrieval = get_capability_decision("embeddings_semantic")
    assert retrieval.route_reviewable is True
    assert "hard_negative_cases" in retrieval.required_evidence
    assert "no_match_abstention" in retrieval.required_evidence
    assert "no_match" in retrieval.fallback


def test_external_actions_are_marked_and_have_manual_fallback():
    purchase = get_capability_decision("external_purchase_execution")
    assert purchase.external_data is True
    assert purchase.route_reviewable is False
    assert "manual_checkout" in purchase.fallback
    assert "explicit confirmation" in purchase.confirmation_policy


def test_rows_are_json_serializable_for_read_only_reports():
    rows = capability_decision_rows()
    encoded = json.dumps(rows, sort_keys=True)
    assert len(rows) == 12
    assert "planner_tool_calling" in encoded


def test_validator_catches_duplicate_and_missing_policy_fields():
    original = CAPABILITY_DECISIONS[0]
    invalid = original.__class__(
        key=original.key,
        task=original.task,
        owner="",
        authority=original.authority,
        status=original.status,
        inputs=(),
        outputs=original.outputs,
        fallback=(),
        required_evidence=(),
        confirmation_policy="",
    )

    errors = validate_capability_matrix((invalid, invalid))

    assert any("duplicate capability key" in error for error in errors)
    assert any("owner must not be empty" in error for error in errors)
    assert any("inputs must not be empty" in error for error in errors)
    assert any("fallback must not be empty" in error for error in errors)
    assert any("required evidence must not be empty" in error for error in errors)
    assert any("confirmation policy must not be empty" in error for error in errors)


def test_unknown_capability_is_explicit():
    with pytest.raises(KeyError, match="unknown ShopStack capability"):
        get_capability_decision("not_a_real_capability")
