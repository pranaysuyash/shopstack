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



def _patch_modules(mapping: dict) -> "_ModulePatcher":
    """Safely patch sys.modules — works around a Python 3.14 segfault
    in unittest.mock.patch.dict(sys.modules, clear=False) on exit.

    For mapping values that are ``None``, the module is set to ``None``
    in ``sys.modules`` (the standard Python idiom for an unavailable
    module — ``import x`` then raises ``ImportError``). We do NOT pop
    the key, because popping causes a fresh import of any C-extension
    module, which can segfault on Python 3.14.
    """
    import sys as _sys
    saved = {k: _sys.modules.get(k) for k in mapping}
    for k, v in mapping.items():
        if v is None:
            _sys.modules[k] = None
        else:
            _sys.modules[k] = v
    return _ModulePatcher(saved)

class _ModulePatcher:
    def __init__(self, saved):
        self.saved = saved
    def __enter__(self):
        return self
    def __exit__(self, *args):
        import sys as _sys
        for k, v in self.saved.items():
            if v is None:
                _sys.modules.pop(k, None)
            else:
                _sys.modules[k] = v



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
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPMVProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPMVProvider()
            assert provider.name == "minicpmv"
            assert provider.model_id == "minicpm-v-8b"
            assert provider.parameter_count == 8.0
            assert "vision" in provider.capabilities
            assert "object_detection" in provider.capabilities

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPMVProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPMVProvider()
            assert provider.last_latency_ms is None

    def test_understand_unavailable(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPMVProvider()
            result = provider.understand("/fake.jpg")
            assert "error" in result
            assert result["model"] == "minicpmv"

    def test_detect_unavailable(self):
        from shopstack.providers.vision_provider import MiniCPMVProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPMVProvider()
            result = provider.detect("/fake.jpg")
            assert len(result) == 1
            assert "error" in result[0]

    def test_understand_missing_file(self):
        """Even if deps exist, missing image file returns error."""
        with _patch_modules( {"transformers": MagicMock(), "torch": MagicMock()}):
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
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            assert provider.name == "minicpm5"
            assert provider.model_id == "minicpm5-1b"
            assert provider.parameter_count == 1.0
            assert "text" in provider.capabilities
            assert "planning" in provider.capabilities

    def test_last_latency_default(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            assert provider.last_latency_ms is None

    def test_last_token_count_default(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            assert provider.last_token_count is None

    def test_complete_unavailable(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            result = provider.complete("Hello")
            assert "error" in result
            assert result["model"] == "minicpm5"

    def test_plan_unavailable(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            result = provider.plan({"prompt": "What's in my fridge?"})
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["tool"] == "respond"
            assert len(result[0]["args"]["message"]) > 0

    def test_plan_with_string_context(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            result = provider.plan("plain string")
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["tool"] == "respond"
            assert len(result[0]["args"]["message"]) > 0

    def test_plan_with_empty_prompt(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            result = provider.plan({"prompt": ""})
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["tool"] == "respond"
            assert len(result[0]["args"]["message"]) > 0

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.planner_provider import MiniCPM5Provider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = MiniCPM5Provider()
            assert not provider.healthcheck()


# ============================================================
#  Qwen3TTSProvider
# ============================================================


class TestQwen3TTSProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(prefer_gtts_fallback=False)
            assert not provider.available
            assert provider.error is not None
            assert "qwen-tts" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(prefer_gtts_fallback=False)
            assert provider.name == "qwen3_tts"
            assert provider.model_id == "qwen3-tts-1.7b"
            assert provider.parameter_count == 1.7
            assert "tts" in provider.capabilities

    def test_synthesize_empty_text(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(prefer_gtts_fallback=False)
            result = provider.synthesize("")
            assert result == b""

    def test_synthesize_returns_empty_when_not_available(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(prefer_gtts_fallback=False)
            result = provider.synthesize("Hello")
            assert result == b""

    def test_synthesize_falls_back_to_gtts(self):
        """When qwen_tts SDK missing but gTTS available, should return gTTS audio."""
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            # gTTS is likely installed; synthesize should work
            provider = Qwen3TTSProvider(prefer_gtts_fallback=True)
            result = provider.synthesize("Hello")
            if provider._gtts_available:
                assert isinstance(result, bytes)
                assert len(result) > 0
            else:
                assert result == b""

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(prefer_gtts_fallback=False)
            assert not provider.healthcheck()

    def test_name_correct(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        assert Qwen3TTSProvider.name == "qwen3_tts"

    def test_voice_default(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(prefer_gtts_fallback=False)
            assert provider._voice in provider.VOICES

    def test_voice_custom(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(
                voice="Emma", prefer_gtts_fallback=False
            )
            assert provider._voice == "Emma"

    def test_voice_invalid_falls_back_to_default(self):
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        with _patch_modules( {"qwen_tts": None}):
            provider = Qwen3TTSProvider(
                voice="NonExistent", prefer_gtts_fallback=False
            )
            assert provider._voice == "Ryan"

    def test_model_name_update(self):
        """Default model name uses the 12Hz variant."""
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        assert "12Hz" in Qwen3TTSProvider()._model_name


# ============================================================
#  NuExtract3OCRProvider
# ============================================================


class TestNuExtract3OCRProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = NuExtract3OCRProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = NuExtract3OCRProvider()
            assert provider.name == "nuextract3"
            assert provider.model_id == "nuextract3-4b"
            assert provider.parameter_count == 4.0
            assert "ocr" in provider.capabilities

    def test_extract_unavailable(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = NuExtract3OCRProvider()
            result = provider.extract("/fake.jpg")
            assert "error" in result
            assert result["model"] == "nuextract3"

    def test_extract_missing_file(self):
        with _patch_modules( {"transformers": MagicMock(), "torch": MagicMock()}):
            from shopstack.providers.ocr_provider import NuExtract3OCRProvider
            provider = NuExtract3OCRProvider()
            provider._available = True
            result = provider.extract("/tmp/nonexistent_image.jpg")
            assert "error" in result

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = NuExtract3OCRProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = NuExtract3OCRProvider()
            assert provider.last_latency_ms is None

    def test_ocr_no_text_returns_error(self):
        """When pytesseract is available but returns no text, returns error."""
        from unittest.mock import MagicMock as Mock

        mock_pytesseract = Mock()
        mock_pytesseract.image_to_string.return_value = ""

        with (
            _patch_modules({"transformers": Mock(), "torch": Mock()}),
            _patch_modules({"pytesseract": mock_pytesseract}),
        ):
            # Re-import to pick up patched deps
            from shopstack.providers.ocr_provider import NuExtract3OCRProvider
            provider = NuExtract3OCRProvider()
            provider._available = True
            provider._pytesseract_available = True

            # Create a dummy image file
            import tempfile
            from pathlib import Path

            img_path = Path(tempfile.mkdtemp()) / "test.txt"
            img_path.write_text("fake-image")

            try:
                result = provider.extract(str(img_path))
                assert "error" in result
                assert "no text" in result["error"].lower()
            finally:
                img_path.unlink(missing_ok=True)

    def test_ocr_pytesseract_unavailable_returns_error(self):
        """When pytesseract is unavailable, returns error."""
        with (
            _patch_modules({"transformers": MagicMock(), "torch": MagicMock()}),
            _patch_modules({"pytesseract": None}),
        ):
            from shopstack.providers.ocr_provider import NuExtract3OCRProvider
            provider = NuExtract3OCRProvider()
            assert not provider._pytesseract_available

    def test_ocr_calls_tesseract(self):
        """Verify _ocr_image calls pytesseract.image_to_string."""
        import sys
        from unittest.mock import MagicMock as Mock
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider

        mock_pytesseract = Mock()
        mock_pytesseract.image_to_string.return_value = "Milk 64 MRP 64"
        # Mock torch + transformers too, so the constructor's
        # ``import torch; from transformers import ...`` doesn't
        # load the real C-extensions (sentencepiece segfaults on
        # Python 3.14 in the test env — see addendum 2026-06-09).
        mock_torch = Mock()
        mock_transformers = Mock()
        mock_transformers.AutoModelForCausalLM = Mock()
        mock_transformers.AutoTokenizer = Mock()

        # Save originals and patch in mocks directly to avoid a segfault
        # in unittest.mock._clear_dict on Python 3.14 when using
        # patch.dict("sys.modules", ...).
        _saved = {}
        for mod_name, mock_obj in [
            ("pytesseract", mock_pytesseract),
            ("torch", mock_torch),
            ("transformers", mock_transformers),
        ]:
            _saved[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = mock_obj
        try:
            provider = NuExtract3OCRProvider()
            # Force _pytesseract_available True so we go down the
            # `import pytesseract; pytesseract.image_to_string(...)`
            # path. The mock above makes the import resolve to the
            # MagicMock, so the real tesseract binary is never invoked.
            provider._pytesseract_available = True

            result = provider._ocr_image("/fake/path")
            assert result == "Milk 64 MRP 64"
            mock_pytesseract.image_to_string.assert_called_once()
        finally:
            for mod_name, original in _saved.items():
                if original is None:
                    sys.modules.pop(mod_name, None)
                else:
                    sys.modules[mod_name] = original


# ============================================================
#  RMBGSegmentationProvider
# ============================================================


class TestRMBGSegmentationProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = RMBGSegmentationProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = RMBGSegmentationProvider()
            assert provider.name == "rmbg"
            assert provider.model_id == "rmbg-1.4"
            assert provider.parameter_count == 0.3
            assert "segmentation" in provider.capabilities

    def test_segment_unavailable(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = RMBGSegmentationProvider()
            result = provider.segment("/fake.jpg")
            assert len(result) == 1
            assert "error" in result[0]
            assert result[0]["error"] is not None

    def test_segment_missing_file(self):
        with _patch_modules( {"transformers": MagicMock(), "torch": MagicMock()}):
            from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
            provider = RMBGSegmentationProvider()
            provider._available = True
            result = provider.segment("/tmp/nonexistent.jpg")
            assert len(result) == 1
            assert "not found" in result[0]["error"]

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = RMBGSegmentationProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = RMBGSegmentationProvider()
            assert provider.last_latency_ms is None


# ============================================================
#  ParakeetSTTProvider
# ============================================================


class TestParakeetSTTProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            # fallback_whisper=False to test Parakeet's own availability
            # without the Whisper fallback layer (LocalWhisperProvider may
            # be available even when Parakeet's deps are missing).
            provider = ParakeetSTTProvider(fallback_whisper=False)
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = ParakeetSTTProvider()
            assert provider.name == "parakeet"
            assert "stt" in provider.capabilities

    def test_transcribe_missing_file(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = ParakeetSTTProvider()
            result = provider.transcribe("/tmp/nonexistent.wav")
            assert "error" in result
            assert "not found" in result["error"]

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = ParakeetSTTProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = ParakeetSTTProvider()
            assert provider.last_latency_ms is None


# ============================================================
#  SenseVoiceSTTProvider
# ============================================================


class TestSenseVoiceProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.stt_provider import SenseVoiceSTTProvider
        with _patch_modules( {"funasr": None}):
            # fallback_whisper=False to test SenseVoice's own availability
            # without the Whisper fallback layer.
            provider = SenseVoiceSTTProvider(fallback_whisper=False)
            assert not provider.available
            assert provider.error is not None
            assert "funasr" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.stt_provider import SenseVoiceSTTProvider
        provider = SenseVoiceSTTProvider(fallback_whisper=False)
        assert provider.name == "sensevoice"
        assert "stt" in provider.capabilities

    def test_transcribe_missing_file(self):
        from shopstack.providers.stt_provider import SenseVoiceSTTProvider
        provider = SenseVoiceSTTProvider(fallback_whisper=False)
        result = provider.transcribe("/tmp/nonexistent.wav")
        assert "error" in result
        assert "not found" in result["error"]

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.stt_provider import SenseVoiceSTTProvider
        with _patch_modules( {"funasr": None}):
            provider = SenseVoiceSTTProvider(fallback_whisper=False)
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.stt_provider import SenseVoiceSTTProvider
        with _patch_modules( {"funasr": None}):
            provider = SenseVoiceSTTProvider(fallback_whisper=False)
            assert provider.last_latency_ms is None


# ============================================================
#  Qwen3ASRProvider
# ============================================================


class TestQwen3ASRProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.stt_provider import Qwen3ASRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            # fallback_whisper=False to test Qwen3-ASR's own availability
            # without the Whisper fallback layer.
            provider = Qwen3ASRProvider(fallback_whisper=False)
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.stt_provider import Qwen3ASRProvider
        provider = Qwen3ASRProvider(fallback_whisper=False)
        assert provider.name == "qwen3_asr"
        assert "stt" in provider.capabilities

    def test_transcribe_missing_file(self):
        from shopstack.providers.stt_provider import Qwen3ASRProvider
        provider = Qwen3ASRProvider(fallback_whisper=False)
        result = provider.transcribe("/tmp/nonexistent.wav")
        assert "error" in result
        assert "not found" in result["error"]

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.stt_provider import Qwen3ASRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = Qwen3ASRProvider(fallback_whisper=False)
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.stt_provider import Qwen3ASRProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = Qwen3ASRProvider(fallback_whisper=False)
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
#  GroundingDINOProvider
# ============================================================


class TestGroundingDINOProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = GroundingDINOProvider()
            assert not provider.available
            assert provider.error is not None
            assert "transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = GroundingDINOProvider()
            assert provider.name == "grounding_dino"
            assert provider.model_id == "grounding-dino-tiny"
            assert provider.parameter_count == 0.043
            assert "grounding" in provider.capabilities

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = GroundingDINOProvider()
            assert not provider.healthcheck()

    def test_last_latency_default(self):
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = GroundingDINOProvider()
            assert provider.last_latency_ms is None

    def test_ground_unavailable(self):
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = GroundingDINOProvider()
            result = provider.ground("/fake.jpg", "tomato")
            assert "error" in result
            assert result["found"] is False
            assert result["model"] == "grounding_dino"

    def test_ground_missing_file(self):
        with _patch_modules( {"transformers": MagicMock(), "torch": MagicMock()}):
            from shopstack.providers.grounding_provider import GroundingDINOProvider
            provider = GroundingDINOProvider()
            provider._available = True
            result = provider.ground("/tmp/nonexistent_image.jpg", "tomato")
            assert "error" in result
            assert result["found"] is False
            assert "not found" in result["error"].lower()

    def test_ground_empty_prompt(self):
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        with _patch_modules( {"transformers": None, "torch": None}):
            provider = GroundingDINOProvider()
            result = provider.ground("/fake.jpg", "")
            assert "error" in result
            assert result["found"] is False

    def test_ground_casts_pixel_values_to_model_dtype(self):
        import torch

        from shopstack.providers.grounding_provider import GroundingDINOProvider

        provider = GroundingDINOProvider.__new__(GroundingDINOProvider)
        provider._available = True
        provider._error = None
        provider._last_latency_ms = None
        provider._model_name = "IDEA-Research/grounding-dino-tiny"
        provider._device = "auto"
        provider._box_threshold = 0.3
        provider._text_threshold = 0.25

        pixel_values = MagicMock()
        pixel_values.to.return_value = pixel_values
        input_ids = MagicMock()
        pixel_mask = MagicMock()
        inputs = {
            "pixel_values": pixel_values,
            "input_ids": input_ids,
            "pixel_mask": pixel_mask,
        }
        provider._processor = MagicMock()
        provider._processor.return_value = inputs
        provider._processor.post_process_grounded_object_detection.return_value = [{
            "boxes": [MagicMock(tolist=lambda: [11, 22, 33, 44])],
            "labels": ["milk bottle"],
            "scores": [0.91],
        }]

        model_param = MagicMock()
        model_param.dtype = torch.bfloat16
        provider._model = MagicMock()
        provider._model.device = "cuda"
        provider._model.parameters.return_value = iter([model_param])
        provider._model.return_value = MagicMock()

        mock_image = MagicMock()
        mock_image.convert.return_value = mock_image
        with _patch_modules({"torch": torch}), \
             patch("PIL.Image.open", return_value=mock_image), \
             patch("os.path.isfile", return_value=True), \
             patch("torch.no_grad"):
            result = provider.ground("/fake.jpg", "milk bottle")

        pixel_values.to.assert_called_once_with(device="cuda", dtype=torch.bfloat16)
        assert result["found"] is True
        assert result["bbox"] == [11.0, 22.0, 33.0, 44.0]
        assert result["confidence"] == 0.91
        assert result["label"] == "milk bottle"


# ============================================================
#  CosyVoiceTTSProvider
# ============================================================


class TestCosyVoiceTTSProviderInit:
    def test_not_available_when_deps_missing(self):
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        with _patch_modules( {"cosyvoice": None}):
            provider = CosyVoiceTTSProvider(prefer_gtts_fallback=False)
            assert not provider.available
            assert provider.error is not None
            assert "cosyvoice" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        provider = CosyVoiceTTSProvider(prefer_gtts_fallback=False)
        assert provider.name == "cosyvoice"
        assert provider.model_id == "cosyvoice2-0.5b"
        assert provider.parameter_count == 0.5
        assert "tts" in provider.capabilities

    def test_synthesize_empty_text(self):
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        with _patch_modules( {"cosyvoice": None}):
            provider = CosyVoiceTTSProvider(prefer_gtts_fallback=False)
            result = provider.synthesize("")
            assert result == b""

    def test_synthesize_returns_empty_when_not_available(self):
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        with _patch_modules( {"cosyvoice": None}):
            provider = CosyVoiceTTSProvider(prefer_gtts_fallback=False)
            result = provider.synthesize("Hello")
            assert result == b""

    def test_synthesize_falls_back_to_gtts(self):
        """When CosyVoice missing but gTTS available, should return gTTS audio."""
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        with _patch_modules( {"cosyvoice": None}):
            provider = CosyVoiceTTSProvider(prefer_gtts_fallback=True)
            result = provider.synthesize("Hello")
            if provider._gtts_available:
                assert isinstance(result, bytes)
                assert len(result) > 0
            else:
                assert result == b""

    def test_healthcheck_false_when_not_available(self):
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        with _patch_modules( {"cosyvoice": None}):
            provider = CosyVoiceTTSProvider(prefer_gtts_fallback=False)
            assert not provider.healthcheck()

    def test_healthcheck_true_with_gtts_fallback(self):
        """healthcheck returns True when gTTS fallback is available."""
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        with _patch_modules( {"cosyvoice": None}):
            provider = CosyVoiceTTSProvider(prefer_gtts_fallback=True)
            if provider._gtts_available:
                assert provider.healthcheck()
            else:
                assert not provider.healthcheck()

    def test_language_instruction_map(self):
        """Language instruction map should contain key languages."""
        from shopstack.providers.cosyvoice_provider import _LANGUAGE_INSTRUCT
        assert "en" in _LANGUAGE_INSTRUCT
        assert "hi" in _LANGUAGE_INSTRUCT
        assert "ta" in _LANGUAGE_INSTRUCT
        assert "bn" in _LANGUAGE_INSTRUCT
        assert len(_LANGUAGE_INSTRUCT) >= 20


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

    def test_sensevoice_import(self):
        from shopstack.providers.stt_provider import SenseVoiceSTTProvider
        assert SenseVoiceSTTProvider.name == "sensevoice"

    def test_qwen3_asr_import(self):
        from shopstack.providers.stt_provider import Qwen3ASRProvider
        assert Qwen3ASRProvider.name == "qwen3_asr"

    def test_grounding_dino_import(self):
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        assert GroundingDINOProvider.name == "grounding_dino"

    def test_cosyvoice_import(self):
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        assert CosyVoiceTTSProvider.name == "cosyvoice"
