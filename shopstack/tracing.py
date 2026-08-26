"""OpenTelemetry tracing for ShopStack provider calls.

Opt-in OpenTelemetry instrumentation. The exporter is only installed
when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, so tests and offline
runs are not affected by the SDK's reconnect retry behavior.

Used by ``shopstack.providers.openai_provider``,
``shopstack.providers.huggingface_provider``,
``shopstack.providers.local_provider`` to wrap each LLM call
in a span. Cost and latency attributes are populated from the
provider's response.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_TRACER: Any = None
_IS_INSTRUMENTED: bool = False


def is_otel_available() -> bool:
    """Return True if the tracing API and SDK are importable.

    ``opentelemetry-api`` is a base dependency, while the SDK is optional.
    Check the modules that :func:`setup_tracing` actually imports so a
    lightweight install degrades to the documented no-op span behavior.
    """
    try:
        from opentelemetry import trace  # noqa: F401
        from opentelemetry.sdk.resources import Resource  # noqa: F401
        from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
        return True
    except ImportError:
        return False


def setup_tracing(
    service_name: str = "shopstack",
    endpoint: str = "",
    project_name: str = "",
) -> Any:
    """Initialize the global OpenTelemetry tracer.

    Idempotent: subsequent calls return the cached tracer. The OTLP
    exporter is installed only when an endpoint is explicitly set
    (via the ``endpoint`` arg or the ``OTEL_EXPORTER_OTLP_ENDPOINT``
    env var); otherwise spans are recorded but not exported, which
    keeps the test process from hanging on unreachable collector
    retries.

    Args:
        service_name: Value of the ``service.name`` resource attribute.
        endpoint: OTLP gRPC endpoint. Empty string falls back to
            ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var, then to no-op.
        project_name: Phoenix project name for trace grouping. Empty
            string falls back to ``PHOENIX_PROJECT_NAME`` env var.

    Returns:
        The configured ``Tracer`` instance, or ``None`` if the OTel
        packages are not installed.
    """
    global _TRACER, _IS_INSTRUMENTED

    if _IS_INSTRUMENTED:
        return _TRACER

    if not is_otel_available():
        logger.info("OpenTelemetry not installed. Tracing disabled. Install: uv pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc")
        return None

    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    project = project_name or os.getenv("PHOENIX_PROJECT_NAME", "shopstack")

    # Only install the OTLP exporter when an endpoint is explicitly configured.
    # Without an explicit endpoint, fall through to a no-op exporter so the
    # test process never blocks on unreachable collector retries.
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=(("phoenix-project", project),))
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception as e:
            logger.info("OTLP exporter not available (%s), using console span exporter", e)
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing spans are recorded but not exported")

    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)
    _IS_INSTRUMENTED = True
    return _TRACER


def get_tracer() -> Any:
    """Return the global tracer, initializing it lazily if needed."""
    global _TRACER
    if _TRACER is None:
        _TRACER = setup_tracing()
    return _TRACER


def trace_call(name: str, attributes: dict[str, Any] | None = None):
    """Open a span around a provider call.

    Returns a context manager. When the OTel SDK is not installed
    or no exporter is configured, returns a ``_NopSpan`` that
    accepts the same context-manager protocol with no observable
    effect.
    """
    tracer = get_tracer()
    if tracer is None:
        return _NopSpan()
    return tracer.start_as_current_span(name, attributes=attributes)


class _NopSpan:
    """No-op span returned by ``trace_call`` when OTel is disabled.

    Implements the subset of the ``Span`` protocol that
    ``shopstack.providers.*`` actually uses (``__enter__``,
    ``__exit__``, ``set_attribute``, ``set_status``, ``record_exception``).
    """
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass
