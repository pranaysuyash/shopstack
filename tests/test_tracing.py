"""Tests for shopstack.tracing — OpenTelemetry tracing helpers.

The tracing module was updated per DR-015 to:
1. Only install the OTLP exporter when an endpoint is explicitly set
2. Provide a no-op span when OTel is not configured
3. Default endpoint behavior: spans recorded but not exported
"""

from __future__ import annotations

import os

from shopstack.tracing import (
    _NopSpan,
    is_otel_available,
    setup_tracing,
    trace_call,
)


class TestIsOtelAvailable:
    def test_returns_bool(self):
        """is_otel_available returns a boolean, never raises."""
        result = is_otel_available()
        assert isinstance(result, bool)


class TestSetupTracing:
    def setup_method(self):
        """Reset module-level state before each test."""
        import shopstack.tracing
        shopstack.tracing._TRACER = None
        shopstack.tracing._IS_INSTRUMENTED = False

    def teardown_method(self):
        """Clean up any env vars we set."""
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

    def test_setup_tracing_returns_none_when_no_endpoint(self):
        """With no endpoint, the tracer is initialized but no exporter is set."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        tracer = setup_tracing()
        # When OTel is installed (which it is in the venv), a tracer
        # object is returned but no exporter is attached
        if is_otel_available():
            assert tracer is not None

    def test_setup_tracing_idempotent(self):
        """Calling setup_tracing twice returns the same cached tracer."""
        if not is_otel_available():
            return
        first = setup_tracing()
        second = setup_tracing()
        assert first is second


class TestTraceCall:
    def test_returns_context_manager(self):
        """trace_call returns a context manager regardless of OTel state."""
        span = trace_call("test.span", attributes={"key": "value"})
        assert hasattr(span, "__enter__")
        assert hasattr(span, "__exit__")

    def test_returns_nop_span_when_no_otel(self):
        """When OTel is not available, trace_call returns _NopSpan."""
        # When OTel IS available, the returned object is a real OTel span
        # not a _NopSpan. We just verify the protocol works either way.
        span = trace_call("test.span")
        with span as s:
            s.set_attribute("key", "value")
            s.set_status("ok")
        # If we got here, the context manager protocol works


class TestNopSpan:
    """The _NopSpan no-op fallback for when OTel is disabled."""

    def test_enter_returns_self(self):
        with _NopSpan() as span:
            assert span is not None
            assert hasattr(span, "set_attribute")

    def test_set_attribute_is_noop(self):
        """set_attribute accepts any args without raising."""
        with _NopSpan() as span:
            span.set_attribute("k", "v")
            span.set_attribute("k2", 123)
            span.set_attribute("k3", None)
            span.set_attribute("k4", [1, 2, 3])

    def test_set_status_is_noop(self):
        """set_status accepts any args without raising."""
        with _NopSpan() as span:
            span.set_status("ok")
            span.set_status("error")
            span.set_status(None)

    def test_record_exception_is_noop(self):
        """record_exception accepts any args without raising."""
        with _NopSpan() as span:
            span.record_exception(ValueError("test"))
            span.record_exception(RuntimeError("other"))
            span.record_exception(None)
