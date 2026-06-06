"""Tests for LocalWhisperProvider.

Note: faster-whisper depends on ctranslate2/torch native libraries
that can segfault on Python 3.14. The import is deferred inside test
functions to avoid triggering torch loading during test collection.
"""

from __future__ import annotations

import struct
import sys
import math
import wave
from unittest.mock import patch

import pytest


# Create a tiny valid WAV file for testing
_TEST_WAV = "/tmp/test_whisper_provider.wav"


def _create_test_wav(path: str, duration_s: float = 1.0, sample_rate: int = 16000) -> None:
    n_samples = int(sample_rate * duration_s)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for i in range(n_samples):
            val = int(math.sin(2 * math.pi * 440 * i / sample_rate) * 8000)
            w.writeframes(struct.pack("<h", val))


@pytest.fixture(scope="module", autouse=True)
def _setup_audio():
    _create_test_wav(_TEST_WAV)
    yield


def _get_provider(**kwargs) -> object:
    """Dynamically import and create a LocalWhisperProvider."""
    from shopstack.providers.local_whisper_provider import LocalWhisperProvider
    return LocalWhisperProvider(**kwargs)


def _mock_mlx_fail():
    """Patch sys.modules so mlx_whisper import raises ImportError."""
    return patch.dict(sys.modules, {"mlx_whisper": None}, clear=False)


def _mock_faster_whisper_fail():
    """Patch sys.modules so faster_whisper import raises ImportError."""
    return patch.dict(sys.modules, {"faster_whisper": None, "ctranslate2": None}, clear=False)


class TestLocalWhisperProviderInit:
    def test_name(self):
        provider = _get_provider(model_dir="/tmp/nonexistent_whisper")
        assert provider.name == "local_whisper"

    def test_capabilities(self):
        provider = _get_provider(model_dir="/tmp/nonexistent_whisper")
        assert "stt" in provider.capabilities

    def test_backend_default(self):
        provider = _get_provider(model_dir="/tmp/nonexistent_whisper")
        assert provider.backend in ("mlx", "", "faster-whisper")


class TestLocalWhisperProviderTranscribe:
    def test_transcribe_missing_file(self):
        provider = _get_provider(model_dir="/tmp/nonexistent_whisper")
        result = provider.transcribe("/tmp/nonexistent_audio_file.wav")
        assert "error" in result
        assert result.get("text", "") == ""

    def test_transcribe_error_when_no_engine(self):
        """When both backends are masked, transcribe returns an error."""
        with _mock_mlx_fail(), _mock_faster_whisper_fail():
            provider = _get_provider(model_size="tiny", model_dir="/tmp/nonexistent")
            assert not provider.available
            result = provider.transcribe(_TEST_WAV)
            assert "error" in result
            assert result.get("text", "") == ""


class TestLocalWhisperProviderProperties:
    def test_available_property(self):
        provider = _get_provider(model_dir="/tmp/nonexistent_whisper")
        assert isinstance(provider.available, bool)

    def test_error_property(self):
        """When both backends are masked, error is a descriptive string."""
        with _mock_mlx_fail(), _mock_faster_whisper_fail():
            provider = _get_provider(model_size="tiny", model_dir="/tmp/nonexistent")
            assert isinstance(provider.error, str)

    def test_backend_property(self):
        provider = _get_provider(model_dir="/tmp/nonexistent_whisper")
        assert isinstance(provider.backend, str)

    def test_last_latency_property_default(self):
        provider = _get_provider(model_dir="/tmp/nonexistent_whisper")
        assert provider.last_latency_ms is None
