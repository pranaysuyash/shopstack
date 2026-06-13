from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_TRACER: Any = None
_IS_INSTRUMENTED: bool = False


def is_otel_available() -> bool:
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


def setup_tracing(
    service_name: str = "shopstack",
    endpoint: str = "",
    project_name: str = "",
) -> Any:
    global _TRACER, _IS_INSTRUMENTED

    if _IS_INSTRUMENTED:
        return _TRACER

    if not is_otel_available():
        logger.info("OpenTelemetry not installed. Tracing disabled. Install: uv pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")
        return None

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
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
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
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
    global _TRACER
    if _TRACER is None:
        _TRACER = setup_tracing()
    return _TRACER


def trace_call(name: str, attributes: dict[str, Any] | None = None):
    tracer = get_tracer()
    if tracer is None:
        return _NopSpan()
    return tracer.start_as_current_span(name, attributes=attributes)


class _NopSpan:
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
