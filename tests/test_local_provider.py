from __future__ import annotations

import pytest

from shopstack.config import Settings
from shopstack.providers.local_provider import LocalProvider


class TestLocalProviderInit:
    def test_not_available_when_no_deps(self):
        provider = LocalProvider()
        assert provider.name == "local"
        assert not provider.available
        assert provider.error is not None
        assert provider.error is not None
        assert ("mlx-lm" in provider.error.lower() or "inference engine" in provider.error.lower())

    def test_capabilities(self):
        provider = LocalProvider()
        assert "text" in provider.capabilities
        assert "planning" in provider.capabilities
        assert "embeddings" in provider.capabilities

    def test_complete_fallback(self):
        provider = LocalProvider()
        result = provider.complete("Hello")
        assert "error" in result
        assert not provider.available

    def test_embed_fallback(self):
        provider = LocalProvider()
        result = provider.embed(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 128
        assert all(v == 0.0 for v in result[0])

    def test_analyze_image_fallback(self):
        provider = LocalProvider()
        result = provider.analyze_image("/fake/path.jpg")
        assert "error" in result

    def test_transcribe_audio_fallback(self):
        provider = LocalProvider()
        result = provider.transcribe_audio("/fake/path.wav")
        assert "error" in result

    def test_detect_objects_fallback(self):
        provider = LocalProvider()
        result = provider.detect_objects("/fake/path.jpg")
        assert "error" in result[0]

    def test_extract_text_fallback(self):
        provider = LocalProvider()
        result = provider.extract_text("/fake/path.jpg")
        assert "error" in result

    def test_available_and_error_properties(self):
        provider = LocalProvider()
        assert provider.available is False
        assert isinstance(provider.error, str)

    def test_backend_default_empty(self):
        provider = LocalProvider()
        assert provider.backend == ""

