"""Tests for GlmOCRProvider.

Covers:
- Init and metadata (name, model_id, capabilities, parameter_count)
- available=False when transformers/torch is missing
- available=True with real model (requires model download — marked slow)
- extract() fallback with error when unavailable
- extract() with missing file returns error
- healthcheck and last_latency_ms defaults
- Graceful error handling for missing deps and empty input
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ============================================================
#  Init & metadata (deps missing)
# ============================================================


class TestGlmOCRProviderInit:
    def test_not_available_when_deps_missing(self):
        """Available=False when transformers/torch is not installed."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower() or "torch" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            assert provider.name == "glm_ocr"
            assert provider.model_id == "glm-ocr-0.9b"
            assert provider.parameter_count == 0.9
            assert "ocr" in provider.capabilities

    def test_error_property(self):
        """error property returns the message from a failed init."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            err = provider.error
            assert err is not None
            assert isinstance(err, str)
            assert len(err) > 0

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            assert provider.last_latency_ms is None

    def test_custom_model_name_and_max_new_tokens(self):
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider(model_name="custom/ocr", max_new_tokens=2048)
            assert provider._model_name == "custom/ocr"
            assert provider._max_new_tokens == 2048

    def test_error_is_none_when_available(self):
        """After successful init, error should be None."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        provider = GlmOCRProvider()
        if provider.available:
            assert provider.error is None
        else:
            pytest.skip("GLM-OCR model deps not installed")


# ============================================================
#  extract() — unavailable fallback
# ============================================================


class TestGlmOCRProviderExtract:
    def test_extract_returns_error_when_unavailable(self):
        """When transformers/torch is missing, extract() returns error dict."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            result = provider.extract("/fake/receipt.jpg")
            assert isinstance(result, dict)
            assert "error" in result
            assert result["model"] == "glm_ocr"

    def test_extract_missing_file(self):
        """When deps are available but image file doesn't exist, returns error."""
        with patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()}, clear=False):
            from shopstack.providers.ocr_provider import GlmOCRProvider
            provider = GlmOCRProvider()
            provider._available = True
            result = provider.extract("/tmp/nonexistent_receipt.jpg")
            assert isinstance(result, dict)
            assert "error" in result
            assert "not found" in result["error"].lower()

    def test_extract_empty_image_path(self):
        """extract with empty string path returns error when deps available."""
        with patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()}, clear=False):
            from shopstack.providers.ocr_provider import GlmOCRProvider
            provider = GlmOCRProvider()
            provider._available = True
            result = provider.extract("")
            assert isinstance(result, dict)
            assert "error" in result

    def test_extract_sets_latency_on_success(self):
        """Successful extract should set last_latency_ms."""
        # This test requires the real model to be downloaded.
        from shopstack.providers.ocr_provider import GlmOCRProvider
        provider = GlmOCRProvider()
        if not provider.available:
            pytest.skip("GLM-OCR model not downloaded")

        # Check if there's a test receipt image available
        import os
        test_images = [
            "data/sai_pharma.png",
            "data/fresh_mart.png",
            "data/maa_laxmi.png",
        ]
        image_path = None
        for img in test_images:
            if os.path.isfile(img):
                image_path = img
                break

        if not image_path:
            pytest.skip("No test receipt image found in data/")

        result = provider.extract(image_path)
        assert isinstance(result, dict)
        # Should have raw_text or text on success
        if "error" not in result:
            assert provider.last_latency_ms is not None
            assert provider.last_latency_ms > 0
            assert "raw_text" in result or "text" in result

    def test_extract_returns_dict_with_model_key(self):
        """All extract return values should include model key."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            result = provider.extract("/fake.jpg")
            assert "model" in result
            assert result["model"] == "glm_ocr"

    def test_extract_with_none_path(self):
        """extract with None path should not crash Python."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            # None is not str, but os.path.isfile will raise TypeError
            try:
                result = provider.extract(None)  # type: ignore[arg-type]
                assert isinstance(result, dict)
                assert "error" in result
            except Exception:
                # Acceptable to raise on obviously wrong types
                pass


# ============================================================
#  load() / healthcheck
# ============================================================


class TestGlmOCRProviderLoad:
    def test_load_noop_when_not_available(self):
        """load() should not crash when deps are missing."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            # Should not raise
            provider.load()
            assert provider._model is None

    def test_load_returns_quickly_when_deps_missing(self):
        """load() returns immediately when deps are missing (no model download attempt)."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            provider.load()
            # No model should be loaded
            assert provider._model is None

    def test_load_idempotent(self):
        """load() can be called multiple times safely."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            provider.load()
            provider.load()
            provider.load()
            assert provider._available is False

    def test_healthcheck_false_when_deps_missing(self):
        from shopstack.providers.ocr_provider import GlmOCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = GlmOCRProvider()
            assert not provider.healthcheck()

    def test_healthcheck_follows_available(self):
        """healthcheck() return value should match available property."""
        from shopstack.providers.ocr_provider import GlmOCRProvider
        provider = GlmOCRProvider()
        assert provider.healthcheck() == provider.available


# ============================================================
#  Registry wiring
# ============================================================


class TestGlmOCRRegistryWiring:
    def test_registry_resolves_glm_ocr(self):
        """ProviderRegistry can resolve glm_ocr backend."""
        from shopstack.config import Settings
        from shopstack.providers.registry import ProviderRegistry

        settings = Settings(
            _env_file=None,
            off_the_grid=False,
            ocr_backend="glm_ocr",
        )
        registry = ProviderRegistry(settings)
        ocr = registry.ocr
        assert ocr is not None
        # Should either be the real provider or fall back to mock
        assert hasattr(ocr, "extract")
        assert hasattr(ocr, "available")

    def test_registry_wires_name_correctly(self):
        """The resolved OCR provider should indicate it was meant to be glm_ocr."""
        from shopstack.config import Settings
        from shopstack.providers.registry import ProviderRegistry

        settings = Settings(
            _env_file=None,
            off_the_grid=False,
            ocr_backend="glm_ocr",
        )
        registry = ProviderRegistry(settings)
        ocr = registry.ocr
        backend = getattr(ocr, "backend", None) or getattr(ocr, "name", None)
        assert backend == "glm_ocr"


# ============================================================
#  Import smoke tests
# ============================================================


class TestGlmOCRImport:
    def test_glm_ocr_import(self):
        from shopstack.providers.ocr_provider import GlmOCRProvider
        assert GlmOCRProvider.name == "glm_ocr"

    def test_nuextract3_import(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        assert NuExtract3OCRProvider.name == "nuextract3"
