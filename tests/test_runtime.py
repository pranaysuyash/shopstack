from __future__ import annotations

from shopstack.providers.runtime import (
    RuntimeDiagnostics,
    AggregateDiagnostics,
    collect_runtime_diagnostics,
    diagnostics_to_rows,
)


class TestRuntimeDiagnostics:
    def test_empty_diagnostics(self):
        diag = AggregateDiagnostics()
        assert diag.active_total_params_b == 0.0
        assert diag.within_budget is True
        assert diag.providers == []

    def test_diagnostics_to_rows_empty(self):
        diag = AggregateDiagnostics()
        rows = diagnostics_to_rows(diag)
        assert rows == []

    def test_provider_diagnostics_dataclass(self):
        d = RuntimeDiagnostics(
            provider_name="test",
            backend="mock",
            model_id="test-model",
            loaded=True,
            params_b=3.0,
        )
        assert d.provider_name == "test"
        assert d.loaded is True
        assert d.params_b == 3.0
        assert d.last_latency_ms is None
        assert d.last_token_count is None

    def test_diagnostics_to_rows_populated(self):
        diag = AggregateDiagnostics(
            providers=[
                RuntimeDiagnostics(provider_name="planner", backend="mock", loaded=True, params_b=0.0),
                RuntimeDiagnostics(provider_name="vision", backend="mock", loaded=True, params_b=0.0),
            ],
            active_total_params_b=0.0,
            budget_limit_b=32.0,
            within_budget=True,
        )
        rows = diagnostics_to_rows(diag)
        assert len(rows) == 2
        assert rows[0]["provider"] == "planner"
        assert rows[0]["loaded"] == "Yes"

    def test_budget_exceeded(self):
        diag = AggregateDiagnostics(
            active_total_params_b=40.0,
            budget_limit_b=32.0,
            within_budget=False,
        )
        assert diag.within_budget is False
        assert diag.active_total_params_b == 40.0

    def test_blocked_off_grid_status(self):
        class _MockProvider:
            backend = "openai"
            model_id = "gpt-4o"
            parameter_count = 0.0
            available = False
            _last_latency_ms = None
            _last_token_count = None
            capabilities = {"text", "planning"}

        class _Registry:
            _providers = {"planner": _MockProvider()}
            _pending = {"planner": "openai"}
            _backend_requests = {"planner": "openai"}
            _fallback_backends = {}
            _blocked_backends = {"planner": "openai"}

            def _mock_for(self, _name):
                return _MockProvider()

        diag = collect_runtime_diagnostics(_Registry())
        planner = next(p for p in diag.providers if p.provider_name == "planner")
        assert planner.blocked_by_off_grid is True
        assert planner.status == "blocked_off_grid"
        assert planner.loaded is False
