"""Tests for the OpenAI Whisper API provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shopstack.config import Settings
from shopstack.providers.registry import ProviderRegistry


def _mock_missing_openai_package():
    """Simulate missing openai package."""
    return patch.dict("sys.modules", {"openai": None}, clear=False)


def _mock_missing_api_key():
    """Simulate missing API key by clearing env."""
    return patch.dict("os.environ", {}, clear=True)


def _mock_openai_available():
    """Simulate openai package being installed."""
    return patch(
        "shopstack.providers.whisper_provider._check_deps",
        return_value=(True, ""),
    )


# ── Helpers ────────────────────────────────────────────────────────────


def _get_whisper_provider(**kwargs):
    from shopstack.providers.whisper_provider import WhisperProvider
    return WhisperProvider(**kwargs)


# ── Init / availability ────────────────────────────────────────────────


class TestWhisperProviderInit:
    def test_not_available_when_package_missing(self):
        """WhisperProvider should not be available when openai is not installed."""
        with _mock_missing_openai_package():
            provider = _get_whisper_provider()
            assert not provider.available
            assert provider.error is not None
            assert "openai" in (provider.error or "").lower()

    def test_not_available_when_api_key_missing(self):
        """WhisperProvider should not be available without an API key."""
        with _mock_openai_available():
            with _mock_missing_api_key():
                provider = _get_whisper_provider()
                assert not provider.available
                assert provider.error is not None
                assert "api key" in (provider.error or "").lower()

    def test_available_with_key_and_deps(self):
        """WhisperProvider should be available with API key and package installed."""
        mock_client = MagicMock()
        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_whisper_provider(api_key="sk-test-key")
                assert provider.available
                assert provider.error is None

    def test_custom_model(self):
        """Custom model propagates correctly."""
        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=MagicMock()):
                provider = _get_whisper_provider(api_key="sk-test-key", model="whisper-large-v3")
                assert provider._model == "whisper-large-v3"

    def test_capabilities(self):
        """WhisperProvider exposes stt capability."""
        from shopstack.providers.whisper_provider import WhisperProvider
        assert "stt" in WhisperProvider.capabilities

    def test_name_and_defaults(self):
        """Name and default model are set."""
        from shopstack.providers.whisper_provider import WhisperProvider
        assert WhisperProvider.name == "whisper"
        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=MagicMock()):
                provider = _get_whisper_provider(api_key="sk-test-key")
                assert provider._model == "whisper-1"

    def test_client_init_failure(self):
        """WhisperProvider handles client init failure gracefully."""
        with _mock_openai_available():
            with patch("openai.OpenAI", side_effect=RuntimeError("Connection refused")):
                provider = _get_whisper_provider(api_key="sk-test-key")
                assert not provider.available
                assert "Connection refused" in (provider.error or "")


# ── transcribe() ───────────────────────────────────────────────────────


class TestWhisperProviderTranscribe:
    def test_transcribe_returns_error_when_not_available(self):
        """transcribe() returns error dict when not available."""
        with _mock_missing_openai_package():
            provider = _get_whisper_provider()
            result = provider.transcribe("/tmp/test.wav")
            assert "error" in result
            assert result["text"] == ""

    def test_transcribe_success(self):
        """transcribe() returns transcribed text from Whisper API."""
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Hello world, this is a test."
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                with patch("builtins.open", MagicMock()):
                    provider = _get_whisper_provider(api_key="sk-test-key")
                    result = provider.transcribe("/tmp/test.wav", language="en")
                    assert "error" not in result
                    assert result["text"] == "Hello world, this is a test."
                    assert result["language"] == "en"
                    assert result["model"] == "whisper-1"
                    # Verify the API call
                    call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
                    assert call_kwargs["model"] == "whisper-1"
                    assert call_kwargs["language"] == "en"

    def test_transcribe_custom_model(self):
        """transcribe() uses custom model when specified."""
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Test."
        mock_client.audio.transcriptions.create.return_value = mock_transcript

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                with patch("builtins.open", MagicMock()):
                    provider = _get_whisper_provider(api_key="sk-test-key", model="whisper-large-v3")
                    result = provider.transcribe("/tmp/test.wav")
                    call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
                    assert call_kwargs["model"] == "whisper-large-v3"
                    assert result["model"] == "whisper-large-v3"

    def test_transcribe_file_not_found(self):
        """transcribe() handles file not found errors gracefully."""
        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=MagicMock()):
                provider = _get_whisper_provider(api_key="sk-test-key")
                result = provider.transcribe("/nonexistent/audio.wav")
                assert "error" in result
                assert result["text"] == ""

    def test_transcribe_api_error(self):
        """transcribe() handles API errors gracefully."""
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = RuntimeError("API quota exceeded")

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                with patch("builtins.open", MagicMock()):
                    provider = _get_whisper_provider(api_key="sk-test-key")
                    result = provider.transcribe("/tmp/test.wav")
                    assert "error" in result
                    assert "quota" in result["error"].lower()


# ── env_key() ──────────────────────────────────────────────────────────


class TestWhisperProviderEnvKey:
    def test_reads_shopstack_env_var(self):
        """_env_key() reads SHOPSTACK_OPENAI_API_KEY env var."""
        from shopstack.providers.whisper_provider import WhisperProvider

        with patch.dict("os.environ", {"SHOPSTACK_OPENAI_API_KEY": "shopstack_key"}, clear=True):
            assert WhisperProvider._env_key() == "shopstack_key"

    def test_falls_back_to_openai_api_key(self):
        """_env_key() falls back to OPENAI_API_KEY env var."""
        from shopstack.providers.whisper_provider import WhisperProvider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "openai_fallback"}, clear=True):
            assert WhisperProvider._env_key() == "openai_fallback"

    def test_prefers_shopstack_over_openai(self):
        """_env_key() prefers SHOPSTACK_OPENAI_API_KEY over OPENAI_API_KEY."""
        from shopstack.providers.whisper_provider import WhisperProvider

        with patch.dict("os.environ",
                        {"SHOPSTACK_OPENAI_API_KEY": "shopstack_key", "OPENAI_API_KEY": "openai_key"},
                        clear=True):
            assert WhisperProvider._env_key() == "shopstack_key"

    def test_returns_empty_when_no_key(self):
        """_env_key() returns empty string when no key is set."""
        from shopstack.providers.whisper_provider import WhisperProvider

        with patch.dict("os.environ", {}, clear=True):
            assert WhisperProvider._env_key() == ""


# ── Registry wiring ────────────────────────────────────────────────────


class TestWhisperRegistryWiring:
    def test_whisper_backend_resolves_in_registry(self):
        """Whisper backend resolves to WhisperProvider in registry."""
        settings = Settings(
            _env_file=None,
            off_the_grid=False,
            stt_backend="whisper",
        )
        registry = ProviderRegistry(settings)
        stt = registry.stt
        assert stt is not None
        assert stt.name == "whisper"

    def test_whisper_backend_not_available_without_key(self):
        """Whisper backend is not available when key is missing."""
        with _mock_openai_available():
            with _mock_missing_api_key():
                settings = Settings(
                    _env_file=None,
                    off_the_grid=False,
                    stt_backend="whisper",
                )
                registry = ProviderRegistry(settings)
                stt = registry.stt
                assert stt is not None
                assert not stt.available
                assert "api key" in (stt.error or "").lower()
