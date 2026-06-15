"""Tests for shelf_intelligence._safe_* — Item #5 (motto_v3 §0.6).

The pre-fix code did ``except Exception: return <empty>`` on any
provider failure, silently dropping the user's shelf-scan
results. Post-fix: log at WARNING so the operator can see the
failure (and a future ``/health/ui`` error surface can pick it
up), then return the empty value.

The tests in this file lock in the new contract:
* a real exception during detection / segmentation / OCR is
  logged at WARNING
* the empty-value fallback is still returned (the user's
  scan still completes — we just don't pretend it succeeded)

Naming follows the existing test_shelf_intelligence.py
convention so the new test classes are discoverable.
"""
from __future__ import annotations

import logging

import pytest

from shopstack.services.shelf_intelligence import (
    _safe_detection,
    _safe_ocr,
    _safe_segmentation,
)


class _ExplodingProvider:
    """Stand-in for a provider that raises on every call.

    A real shelf_intelligence call to ``provider.detect(path)``
    would hit the actual model. We just want the helper's
    try/except branch. By default this raises on every
    attribute that the safe helpers access (object_detection,
    segmentation, ocr).
    """

    def __init__(self, attr: str | None = None, exc: Exception | None = None):
        # When ``attr`` is None, raise on every attribute; the
        # safe helpers all check different attributes.
        self._attr = attr
        self._exc = exc or RuntimeError("simulated provider failure")

    def __getattr__(self, name: str):
        if self._attr is None or name == self._attr:
            raise self._exc
        # Return None for unrelated attributes so the helper's
        # ``getattr(providers, "...", None)`` short-circuits as
        # if the provider isn't wired at all.
        return None


def _providers_with(attr: str, exc: Exception | None = None) -> _ExplodingProvider:
    return _ExplodingProvider(attr=attr, exc=exc)


class TestSafeDetection:
    def test_returns_empty_list_on_exception(self):
        providers = _ExplodingProvider(attr="object_detection")
        result = _safe_detection(providers, "/tmp/fake-image.jpg")
        assert result == []

    def test_logs_warning_on_exception(self, caplog):
        providers = _ExplodingProvider(attr="object_detection")
        with caplog.at_level(logging.WARNING, logger="shopstack.services.shelf_intelligence"):
            _safe_detection(providers, "/tmp/fake-image.jpg")
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("object_detection" in r.message for r in warnings), (
            f"_safe_detection must log at WARNING on provider failure, "
            f"got: {[r.message for r in warnings]}"
        )

    def test_returns_empty_list_when_provider_attribute_missing(self):
        """No ``object_detection`` attribute on providers is a
        legitimate config (the provider wasn't wired). The
        helper returns [] silently — no log — because that's
        not a failure, it's a no-op.
        """

        class _Empty:
            pass

        result = _safe_detection(_Empty(), "/tmp/fake-image.jpg")
        assert result == []


class TestSafeSegmentation:
    def test_returns_empty_list_on_exception(self):
        providers = _ExplodingProvider(attr="segmentation")
        result = _safe_segmentation(providers, "/tmp/fake-image.jpg")
        assert result == []

    def test_logs_warning_on_exception(self, caplog):
        providers = _ExplodingProvider(attr="segmentation")
        with caplog.at_level(logging.WARNING, logger="shopstack.services.shelf_intelligence"):
            _safe_segmentation(providers, "/tmp/fake-image.jpg")
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("segmentation" in r.message for r in warnings)

    def test_returns_empty_list_when_provider_attribute_missing(self):
        class _Empty:
            pass

        result = _safe_segmentation(_Empty(), "/tmp/fake-image.jpg")
        assert result == []


class TestSafeOCR:
    def test_returns_empty_dict_on_exception(self):
        providers = _ExplodingProvider(attr="ocr")
        result = _safe_ocr(providers, "/tmp/fake-image.jpg")
        assert result == {}

    def test_logs_warning_on_exception(self, caplog):
        providers = _ExplodingProvider(attr="ocr")
        with caplog.at_level(logging.WARNING, logger="shopstack.services.shelf_intelligence"):
            _safe_ocr(providers, "/tmp/fake-image.jpg")
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("ocr" in r.message for r in warnings)

    def test_returns_empty_dict_when_provider_attribute_missing(self):
        class _Empty:
            pass

        result = _safe_ocr(_Empty(), "/tmp/fake-image.jpg")
        assert result == {}


# ── All three share the pattern: failures are logged, not silent ──


class TestAllSafeHelpersShareContract:
    """If a future contributor refactors one of the three
    helpers, this test reminds them that ALL three must keep
    the log-on-failure contract.
    """

    def test_exploding_provider_is_logged_for_every_helper(self, caplog):
        # Use a single provider that explodes on every attribute access.
        providers = _ExplodingProvider()
        with caplog.at_level(logging.WARNING, logger="shopstack.services.shelf_intelligence"):
            _safe_detection(providers, "/tmp/x.jpg")
            _safe_segmentation(providers, "/tmp/x.jpg")
            _safe_ocr(providers, "/tmp/x.jpg")
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        # Three helpers, three warnings.
        assert len(warnings) >= 3, (
            f"Expected at least 3 WARNINGs, got: {[r.message for r in warnings]}"
        )
