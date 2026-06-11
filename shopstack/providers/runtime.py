from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shopstack.model_registry import MAX_ACTIVE_MODEL_PARAMS_B


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
    pending: bool = False
    requested_backend: str = ""
    last_latency_ms: float | None = None
    last_token_count: int | None = None
    status: str = ""


@dataclass
class AggregateDiagnostics:
    providers: list[RuntimeDiagnostics] = field(default_factory=list)
    active_total_params_b: float = 0.0
    budget_limit_b: float = 32.0
    within_budget: bool = True


def collect_runtime_diagnostics(provider_registry: Any) -> AggregateDiagnostics:
    providers = getattr(provider_registry, "_providers", {})
    pending = getattr(provider_registry, "_pending", {})
    backend_requests = getattr(provider_registry, "_backend_requests", {})
    fallback_backends = getattr(provider_registry, "_fallback_backends", {})
    mock_for = getattr(provider_registry, "_mock_for", lambda name: None)
    diagnostics_list: list[RuntimeDiagnostics] = []

    all_names = set(providers.keys()) | set(pending.keys())
    for name in sorted(all_names):
        provider = providers.get(name)
        requested_backend = backend_requests.get(name, pending.get(name, "mock"))
        normalized_backend = requested_backend.lower() if requested_backend else ""
        is_mock_backend = normalized_backend in {"", "mock", "mocked"}
        if provider is None:
            mock = mock_for(name)
            diag = RuntimeDiagnostics(
                provider_name=name,
                backend=requested_backend,
                model_id=getattr(mock, "model_id", ""),
                local_path="",
                quantization="",
                params_b=float(getattr(mock, "parameter_count", 0.0)) if mock is not None else 0.0,
                context_length=0,
                loaded=False,
                pending=True,
                last_latency_ms=None,
                last_token_count=None,
                status="pending",
            )
        else:
            provider_name = type(provider).__name__.lower()
            is_fallback = (
                (name in fallback_backends)
                and (not is_mock_backend)
                and provider_name.startswith("mock")
            )
            diag = RuntimeDiagnostics(
                provider_name=name,
                backend=getattr(provider, "backend", requested_backend),
                model_id=getattr(provider, "model_id", ""),
                local_path=getattr(provider, "local_path", ""),
                quantization=getattr(provider, "quantization", ""),
                params_b=getattr(provider, "parameter_count", 0.0),
                context_length=getattr(provider, "_n_ctx", 0),
                loaded=False if is_fallback else getattr(provider, "available", False),
                pending=is_fallback,
                last_latency_ms=getattr(provider, "_last_latency_ms", None),
                last_token_count=getattr(provider, "_last_token_count", None),
                status="fallback" if is_fallback else getattr(provider, "status", "resolved"),
            )
        diagnostics_list.append(diag)

    active_total = sum(p.params_b for p in diagnostics_list if p.loaded)
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
            "status": p.status,
            "params_b": f"{p.params_b:.2f}",
            "latency_ms": str(p.last_latency_ms) if p.last_latency_ms is not None else "",
            "tokens": str(p.last_token_count) if p.last_token_count is not None else "",
        })
    return rows
