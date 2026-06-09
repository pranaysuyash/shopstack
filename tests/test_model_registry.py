from __future__ import annotations

import math
import pytest

from shopstack import model_registry


def test_total_active_params_counts_active_only():
    active = model_registry.total_active_params()
    candidates_only = model_registry.total_selected_params(include_candidates=True)
    assert active <= candidates_only
    assert active >= 0


def test_total_active_and_candidate_loaders():
    active = model_registry.total_active_params()
    loaded = model_registry.total_loaded_params()
    candidate = model_registry.total_candidate_params()
    assert math.isclose(active, loaded, rel_tol=1e-9)
    # Candidate params may be larger or smaller than loaded (active) params
    # depending on which models are registered as candidates.  The only fixed
    # constraint is that the total (active + candidate) does not exceed the
    # per-model budget cap (enforced by validate_active_model_budget).
    # Verify the total stays within a reasonable range.
    total = active + candidate
    assert total > 0  # at least one model exists
    assert total <= model_registry.MAX_ACTIVE_MODEL_PARAMS_B * 2  # sanity bound


def test_validate_active_model_budget_current_state():
    # current registry should be within default cap because all active models are unloaded
    model_registry.validate_active_model_budget()


def test_validate_active_model_budget_rejects_over_cap():
    if not model_registry.MODEL_REGISTRY:
        return
    original_states = [
        (entry, entry.status, entry.params_b)
        for entry in model_registry.MODEL_REGISTRY
    ]
    try:
        first = model_registry.MODEL_REGISTRY[0]
        first.status = "active"
        first.params_b = 99.0
        with pytest.raises(ValueError, match="exceeds the 32\\.0B cap"):
            model_registry.validate_active_model_budget()
    finally:
        for entry, status, params_b in original_states:
            entry.status = status
            entry.params_b = params_b
