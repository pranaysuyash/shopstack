from __future__ import annotations

from pathlib import Path

import pytest

from shopstack.providers.local_provider import LocalProvider

_NONEXISTENT_MODEL_DIR = "/tmp/shopstack_test_nonexistent_models"


def _provider_without_model() -> LocalProvider:
    return LocalProvider(
        model_dir=_NONEXISTENT_MODEL_DIR,
        model_repo="nonexistent/repo",
        model_file="nonexistent.gguf",
        allow_download=False,
    )


# Path guaranteed not to exist — used to test graceful failure when model is missing
_NONEXISTENT_MODEL_DIR = "/tmp/shopstack_test_nonexistent_models"


def _provider_without_model() -> LocalProvider:
    """Create a LocalProvider pointing at a non-existent model path."""
    return LocalProvider(
        model_dir=_NONEXISTENT_MODEL_DIR,
        model_repo="nonexistent/repo",
        model_file="nonexistent.gguf",
        allow_download=False,
    )


class TestLocalProviderInit:
    def test_not_available_when_no_model(self):
        provider = _provider_without_model()
        assert provider.name == "local"
        assert not provider.available
        assert provider.error is not None
        error_lower = provider.error.lower()
        assert (
            "mlx-lm" in error_lower
            or "inference engine" in error_lower
            or "gguf model not found" in error_lower
        ), f"Unexpected error: {provider.error}"

    def test_capabilities(self):
        provider = _provider_without_model()
        assert "text" in provider.capabilities
        assert "planning" in provider.capabilities
        assert "embeddings" in provider.capabilities

    def test_complete_fallback(self):
        provider = _provider_without_model()
        result = provider.complete("Hello")
        assert "error" in result
        assert not provider.available

    def test_embed_fallback(self):
        provider = _provider_without_model()
        result = provider.embed(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 128
        assert all(v == 0.0 for v in result[0])

    def test_analyze_image_fallback(self):
        provider = _provider_without_model()
        result = provider.analyze_image("/fake/path.jpg")
        assert "error" in result

    def test_transcribe_audio_fallback(self):
        provider = _provider_without_model()
        result = provider.transcribe_audio("/fake/path.wav")
        assert "error" in result

    def test_detect_objects_fallback(self):
        provider = _provider_without_model()
        result = provider.detect_objects("/fake/path.jpg")
        assert "error" in result[0]

    def test_extract_text_fallback(self):
        provider = _provider_without_model()
        result = provider.extract_text("/fake/path.jpg")
        assert "error" in result

    def test_available_and_error_properties(self):
        provider = _provider_without_model()
        assert provider.available is False
        assert isinstance(provider.error, str)

    def test_backend_default_empty(self):
        provider = _provider_without_model()
        assert provider.backend == ""

    def test_available_when_model_present(self):
        """When model exists at default path, provider should load successfully."""
        default_dir = str(Path(__file__).resolve().parent.parent / "shopstack" / "data" / "models")
        default_repo = "Llama-3.2-3B-Instruct-GGUF"
        default_file = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
        model_path = Path(default_dir) / default_repo / default_file
        if not model_path.is_file():
            pytest.skip("Default model not found, skipping availability test")
        provider = LocalProvider(model_dir=default_dir, allow_download=False)
        assert provider.available, f"Provider should be available when model exists at {model_path}"
        assert provider.backend == "llama.cpp"
        assert provider.error is None

