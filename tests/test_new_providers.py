"""Tests for all newly created provider implementations.

Tests cover:
- MiniCPMVProvider (vision)
- MiniCPM5Provider (planner)
- Qwen3TTSProvider (TTS)
- NuExtract3OCRProvider (OCR)
- RMBGSegmentationProvider (segmentation)
- ParakeetSTTProvider (STT)

Each test validates init behavior with missing deps, graceful fallback,
and basic property correctness.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ============================================================
#  MiniCPMVProvider
# ============================================================


def _mock_transformers_missing() -> None:
    """Patch sys.modules so transformers/torch imports raise ImportError."""
    import sys
    sys.modules["transformers"] = None  # type: ignore[assignment]
    sys.modules["torch"] = None  # type: ignore[assignment]


class TestMiniCPMVProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPMVProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPMVProvider()
            assert provider.name == "minicpmv"
            assert provider.model_id == "minicpm-v-8b"
            assert provider.parameter_count == 8.0
            assert "vision" in provider.capabilities
            assert "object_detection" in provider.capabilities

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPMVProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPMVProvider()
            assert provider.last_latency_ms is None

    def test_understand_unavailable(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPMVProvider()
            result = provider.understand("/fake.jpg")
            assert "error" in result
            assert result["model"] == "minicpmv"

    def test_detect_unavailable(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPMVProvider()
            result = provider.detect("/fake.jpg")
            assert len(result) == 1
            assert "error" in result[0]

    def test_understand_missing_file(self):
        """Even if deps exist, missing image file returns error."""
        with patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()}, clear=False):
            from shopstack.providers.vision_provider import MiniCPMVProvider
            provider = MiniCPMVProvider()
            provider._available = True
            result = provider.understand("/tmp/nonexistent_image.jpg")
            assert "error" in result


# ============================================================
#  MiniCPM5Provider
# ============================================================


class TestMiniCPM5ProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            assert provider.name == "minicpm5"
            assert provider.model_id == "minicpm5-1b"
            assert provider.parameter_count == 1.0
            assert "text" in provider.capabilities
            assert "planning" in provider.capabilities

    def test_last_latency_default(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            assert provider.last_latency_ms is None

    def test_last_token_count_default(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            assert provider.last_token_count is None

    def test_complete_unavailable(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            result = provider.complete("Hello")
            assert "error" in result
            assert result["model"] == "minicpm5"

    def test_plan_unavailable(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            result = provider.plan({"prompt": "What's in my fridge?"})
            assert "error" in result

    def test_plan_with_string_context(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            result = provider.plan("plain string")
            # When not available, plan() returns error dict (same pattern as HFProvider/LocalProvider)
            assert "error" in result
            assert result["model"] == "minicpm5"

    def test_plan_with_empty_prompt(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            result = provider.plan({"prompt": ""})
            # When not available, plan() returns error dict
            assert "error" in result
            assert result["model"] == "minicpm5"

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = MiniCPM5Provider()
            assert not provider.healthcheck()


# ============================================================
#  Qwen3TTSProvider
# ============================================================


class TestQwen3TTSProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = Qwen3TTSProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = Qwen3TTSProvider()
            assert provider.name == "qwen3_tts"
            assert provider.model_id == "qwen3-tts-0.6b"
            assert provider.parameter_count == 0.6
            assert "tts" in provider.capabilities

    def test_synthesize_empty_text(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = Qwen3TTSProvider()
            result = provider.synthesize("")
            assert result == b""

    def test_synthesize_returns_empty_when_not_available(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = Qwen3TTSProvider()
            result = provider.synthesize("Hello")
            assert result == b""

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = Qwen3TTSProvider()
            assert not provider.healthcheck()

    def test_name_correct(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        assert Qwen3TTSProvider.name == "qwen3_tts"


# ============================================================
#  NuExtract3OCRProvider
# ============================================================


class TestNuExtract3OCRProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = NuExtract3OCRProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = NuExtract3OCRProvider()
            assert provider.name == "nuextract3"
            assert provider.model_id == "nuextract3-4b"
            assert provider.parameter_count == 4.0
            assert "ocr" in provider.capabilities

    def test_extract_unavailable(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = NuExtract3OCRProvider()
            result = provider.extract("/fake.jpg")
            assert "error" in result
            assert result["model"] == "nuextract3"

    def test_extract_missing_file(self):
        with patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()}, clear=False):
            from shopstack.providers.ocr_provider import NuExtract3OCRProvider
            provider = NuExtract3OCRProvider()
            provider._available = True
            result = provider.extract("/tmp/nonexistent_image.jpg")
            assert "error" in result

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = NuExtract3OCRProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = NuExtract3OCRProvider()
            assert provider.last_latency_ms is None


# ============================================================
#  RMBGSegmentationProvider
# ============================================================


class TestRMBGSegmentationProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = RMBGSegmentationProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = RMBGSegmentationProvider()
            assert provider.name == "rmbg"
            assert provider.model_id == "rmbg-1.4"
            assert provider.parameter_count == 0.3
            assert "segmentation" in provider.capabilities

    def test_segment_unavailable(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = RMBGSegmentationProvider()
            result = provider.segment("/fake.jpg")
            assert len(result) == 1
            assert "error" in result[0]
            assert result[0]["error"] is not None

    def test_segment_missing_file(self):
        with patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()}, clear=False):
            from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
            provider = RMBGSegmentationProvider()
            provider._available = True
            result = provider.segment("/tmp/nonexistent.jpg")
            assert len(result) == 1
            assert "not found" in result[0]["error"]

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = RMBGSegmentationProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = RMBGSegmentationProvider()
            assert provider.last_latency_ms is None


# ============================================================
#  ParakeetSTTProvider
# ============================================================


class TestParakeetSTTProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = ParakeetSTTProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = ParakeetSTTProvider()
            assert provider.name == "parakeet"
            assert "stt" in provider.capabilities

    def test_transcribe_missing_file(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = ParakeetSTTProvider()
            result = provider.transcribe("/tmp/nonexistent.wav")
            assert "error" in result
            assert "not found" in result["error"]

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = ParakeetSTTProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with patch.dict("sys.modules", {"transformers": None, "torch": None}, clear=False):
            provider = ParakeetSTTProvider()
            assert provider.last_latency_ms is None


# ============================================================
#  Registry wiring tests
# ============================================================


class TestNewProviderRegistryWiring:
    def test_registry_falls_back_from_unavailable_backends(self):
        from shopstack.config import Settings
        from shopstack.providers.registry import ProviderRegistry

        settings = Settings(
            _env_file=None,
            off_the_grid=False,
        )
        registry = ProviderRegistry(settings)
        # These should resolve to mock since deps aren't installed
        assert registry.planner is not None
        assert registry.stt is not None
        assert registry.vision is not None

    def test_registry_resolves_new_backends(self):
        """Registry can attempt to resolve new backends even if deps are missing."""
        from shopstack.config import Settings
        from shopstack.providers.registry import ProviderRegistry

        settings = Settings(
            _env_file=None,
            off_the_grid=False,
            planner_backend="minicpm5",
            stt_backend="parakeet",
        )
        registry = ProviderRegistry(settings)
        # The planner should attempt minicpm5 resolution, which will fail
        # gracefully to mock since transformers/torch not installed
        assert registry.planner is not None
        assert registry.planner.available
        # stt should also fall back to mock
        assert registry.stt is not None
        assert registry.stt.available


# ============================================================
#  Import smoke tests
# ============================================================


class TestProviderImport:
    def test_minicpmv_import(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        assert MiniCPMVProvider.name == "minicpmv"

    def test_minicpm5_import(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        assert MiniCPM5Provider.name == "minicpm5"

    def test_nuextract3_import(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        assert NuExtract3OCRProvider.name == "nuextract3"

    def test_rmbg_import(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        assert RMBGSegmentationProvider.name == "rmbg"

    def test_parakeet_import(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        assert ParakeetSTTProvider.name == "parakeet"

    def test_qwen3_tts_import(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        assert Qwen3TTSProvider.name == "qwen3_tts"
