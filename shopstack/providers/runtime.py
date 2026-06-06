from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shopstack.model_registry import MAX_ACTIVE_MODEL_PARAMS_B, total_loaded_params


@dataclass
class RuntimeDiagnostics:
    provider_name: str = ""
    backend: str = ""
    model_id: str = ""
    local_path: str = ""
    quantization: str = ""
    params_b: float = 0.0
    context_length: int = 0
    loaded: bool = False
    last_latency_ms: float | None = None
    last_token_count: int | None = None


@dataclass
class AggregateDiagnostics:
    providers: list[RuntimeDiagnostics] = field(default_factory=list)
    active_total_params_b: float = 0.0
    budget_limit_b: float = 32.0
    within_budget: bool = True


def collect_runtime_diagnostics(provider_registry: Any) -> AggregateDiagnostics:
    providers = getattr(provider_registry, "_providers", {})
    diagnostics_list: list[RuntimeDiagnostics] = []

    for name, provider in providers.items():
        diag = RuntimeDiagnostics(
            provider_name=name,
            backend=getattr(provider, "backend", "") or type(provider).__name__,
            model_id=getattr(provider, "model_id", ""),
            loaded=getattr(provider, "available", False),
            params_b=getattr(provider, "parameter_count", 0.0),
            context_length=getattr(provider, "_n_ctx", 0),
            last_latency_ms=getattr(provider, "_last_latency_ms", None),
            last_token_count=getattr(provider, "_last_token_count", None),
        )
        diagnostics_list.append(diag)

    active_total = total_loaded_params()
    budget_limit = MAX_ACTIVE_MODEL_PARAMS_B
    within = active_total <= budget_limit

    return AggregateDiagnostics(
        providers=diagnostics_list,
        active_total_params_b=active_total,
        budget_limit_b=budget_limit,
        within_budget=within,
    )


def diagnostics_to_rows(diag: AggregateDiagnostics) -> list[dict[str, Any]]:
    rows = []
    for p in diag.providers:
        rows.append({
            "provider": p.provider_name,
            "backend": p.backend,
            "model": p.model_id,
            "loaded": "Yes" if p.loaded else "No",
            "params_b": f"{p.params_b:.2f}",
            "latency_ms": str(p.last_latency_ms) if p.last_latency_ms is not None else "",
            "tokens": str(p.last_token_count) if p.last_token_count is not None else "",
        })
    return rows
