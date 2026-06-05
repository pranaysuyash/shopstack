from __future__ import annotations

from shopstack import model_registry


def test_total_active_params_counts_active_only():
    active = model_registry.total_active_params()
    candidates_only = model_registry.total_selected_params(include_candidates=True)
    assert active <= candidates_only
    assert active >= 0
