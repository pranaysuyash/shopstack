from __future__ import annotations

from unittest.mock import MagicMock, patch


from shopstack.config import Settings
from shopstack.providers.registry import ProviderRegistry


def _mock_missing_huggingface_hub():
    """Simulate missing huggingface_hub package."""
    return patch.dict("sys.modules", {"huggingface_hub": None}, clear=False)


def _mock_missing_api_key():
    """Simulate missing API key by clearing env."""
    return patch.dict("os.environ", {}, clear=True)


# ── Helpers ────────────────────────────────────────────────────────────


def _get_hf_provider(**kwargs):
    from shopstack.providers.huggingface_provider import HuggingFaceProvider

    return HuggingFaceProvider(**kwargs)


# ── Init / availability ────────────────────────────────────────────────


class TestHuggingFaceProviderInit:
    def test_not_available_when_package_missing(self):
        """HuggingFaceProvider should not be available when huggingface_hub is not installed."""
        with _mock_missing_huggingface_hub():
            provider = _get_hf_provider()
            assert not provider.available
            assert provider.error is not None
            assert "huggingface_hub" in (provider.error or "").lower()

    def test_not_available_when_api_key_missing(self):
        """HuggingFaceProvider should not be available without an API key."""
        with patch("shopstack.providers.huggingface_provider._huggingface_available", return_value=(True, "")):
            with _mock_missing_api_key():
                provider = _get_hf_provider()
                assert not provider.available
                assert provider.error is not None
                assert "api key" in (provider.error or "").lower()

    def test_available_with_key_and_deps(self):
        """HuggingFaceProvider should be available with API key and package installed."""
        mock_client = MagicMock()
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="hf_test_key")
                assert provider.available
                assert provider.error is None

    def test_custom_model(self):
        """Custom model propagates correctly."""
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=MagicMock()):
                provider = _get_hf_provider(api_key="key", model="meta-llama/Llama-3.2-3B")
                assert provider._model == "meta-llama/Llama-3.2-3B"

    def test_capabilities(self):
        """HuggingFaceProvider exposes text and planning capabilities."""
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=MagicMock()):
                provider = _get_hf_provider(api_key="key")
                assert "text" in provider.capabilities
                assert "planning" in provider.capabilities

    def test_name_and_defaults(self):
        """Name, model_id, parameter_count are set."""
        from shopstack.providers.huggingface_provider import HuggingFaceProvider, DEFAULT_MODEL

        assert HuggingFaceProvider.name == "huggingface"
        assert DEFAULT_MODEL == "microsoft/Phi-3-mini-4k-instruct"
        assert HuggingFaceProvider.model_id == DEFAULT_MODEL
        assert HuggingFaceProvider.parameter_count == 3.8

    def test_healthcheck(self):
        """healthcheck() mirrors available."""
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=MagicMock()):
                provider = _get_hf_provider(api_key="key")
                assert provider.healthcheck() is True

    def test_load_is_noop(self):
        """load() should not raise."""
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=MagicMock()):
                provider = _get_hf_provider(api_key="key")
                provider.load()  # should not raise


# ── complete() ─────────────────────────────────────────────────────────


class TestHuggingFaceProviderComplete:
    def test_complete_returns_error_when_not_available(self):
        """complete() returns error dict when not available."""
        with _mock_missing_huggingface_hub():
            provider = _get_hf_provider()
            result = provider.complete("Say hi")
            assert "error" in result
            assert result["model"] == "huggingface"

    def test_complete_success(self):
        """complete() returns text from the HF API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage.total_tokens = 8
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="hf_test_key")
                result = provider.complete("Say hi", max_tokens=10, temperature=0.5)
                assert "error" not in result
                assert result["text"] == "Hello!"
                assert result["model"] == provider._model
                assert result["usage"]["total_tokens"] == 8

    def test_complete_retry_on_failure(self):
        """complete() retries on transient errors."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("Rate limited"),
            RuntimeError("Timeout"),
            RuntimeError("API error"),
        ]

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key", max_retries=2)
                result = provider.complete("Say hi")
                # After exhausting retries, returns error
                # max_retries=2 means 3 total attempts (range(3))
                assert "error" in result
                assert "API error" in result["error"]
                assert mock_client.chat.completions.create.call_count == 3

    def test_complete_succeeds_on_retry(self):
        """complete() succeeds on second attempt after first failure."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage.total_tokens = 8
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("Rate limited"),
            mock_response,
        ]

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key", max_retries=2)
                result = provider.complete("Say hi")
                assert "error" not in result
                assert result["text"] == "Hello!"
                assert mock_client.chat.completions.create.call_count == 2

    def test_complete_default_kwargs(self):
        """complete() uses sensible defaults for max_tokens and temperature."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi"
        mock_response.usage.total_tokens = 3
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                provider.complete("Say hi")
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["max_tokens"] == 512
                assert call_kwargs["temperature"] == 0.3

    def test_complete_returns_error_on_exception(self):
        """complete() returns error dict on exception."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key", max_retries=0)
                result = provider.complete("Say hi")
                assert "error" in result
                assert "API down" in result["error"]


# ── plan() ─────────────────────────────────────────────────────────────


class TestHuggingFaceProviderPlan:
    def test_plan_returns_error_when_not_available(self):
        """plan() returns error dict when not available."""
        with _mock_missing_huggingface_hub():
            provider = _get_hf_provider()
            result = provider.plan({"prompt": "What's in my fridge?"})
            assert "error" in result

    def test_plan_with_string_context(self):
        """plan() with a string returns empty text (same pattern as LocalProvider)."""
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=MagicMock()):
                provider = _get_hf_provider(api_key="key")
                result = provider.plan("plain string")
                assert result == {"text": "", "model": provider.name}

    def test_plan_with_empty_prompt(self):
        """plan() with empty prompt returns empty text."""
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=MagicMock()):
                provider = _get_hf_provider(api_key="key")
                result = provider.plan({"prompt": ""})
                assert result == {"text": "", "model": provider.name}

    def test_plan_delegates_to_complete(self):
        """plan() with a valid prompt delegates to complete()."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "You have milk and bread."
        mock_response.usage.total_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                result = provider.plan({
                    "prompt": "What's in my fridge?",
                    "max_tokens": 100,
                    "temperature": 0.2,
                })
                assert "error" not in result
                assert result["text"] == "You have milk and bread."

    def test_plan_uses_structured_chat_when_system_provided(self):
        """plan() sends system + user as structured messages when ``system`` key is present."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Check inventory."
        mock_response.usage.total_tokens = 12
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                result = provider.plan({
                    "system": "You are a helpful assistant.",
                    "question": "Do we have milk?",
                    "prompt": "You are a helpful assistant.\n\nUSER REQUEST: Do we have milk?\n\nJSON tool calls:",
                })
                assert "error" not in result
                assert result["text"] == "Check inventory."
                # Verify the API received structured messages
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                messages = call_kwargs["messages"]
                assert len(messages) == 2
                assert messages[0]["role"] == "system"
                assert messages[0]["content"] == "You are a helpful assistant."
                assert messages[1]["role"] == "user"
                assert "Do we have milk?" in messages[1]["content"]

    def test_plan_uses_system_for_custom_model(self):
        """plan() routes through structured chat for any model when system is provided."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_response.usage.total_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key", model="microsoft/Phi-3-mini-4k-instruct")
                provider.plan({
                    "system": "System instruction.",
                    "question": "User question.",
                    "prompt": "combined",
                })
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["model"] == "microsoft/Phi-3-mini-4k-instruct"
                assert len(call_kwargs["messages"]) == 2

    def test_plan_falls_back_to_flat_prompt_when_no_system(self):
        """plan() falls back to flat prompt when ``system`` key is absent."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Fallback."
        mock_response.usage.total_tokens = 3
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                result = provider.plan({"prompt": "flat prompt"})
                assert result["text"] == "Fallback."
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert len(call_kwargs["messages"]) == 1
                assert call_kwargs["messages"][0]["role"] == "user"


# ── chat() ────────────────────────────────────────────────────────────


class TestHuggingFaceProviderChat:
    def test_chat_returns_error_when_not_available(self):
        """chat() returns error dict when not available."""
        with _mock_missing_huggingface_hub():
            provider = _get_hf_provider()
            result = provider.chat([{"role": "user", "content": "Hi"}])
            assert "error" in result

    def test_chat_sends_messages(self):
        """chat() sends the given messages to the HF API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage.total_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Say hi"},
        ]

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                result = provider.chat(messages, max_tokens=100, temperature=0.5)
                assert "error" not in result
                assert result["text"] == "Hello!"
                assert result["usage"]["total_tokens"] == 5

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["messages"] == messages
                assert call_kwargs["max_tokens"] == 100
                assert call_kwargs["temperature"] == 0.5

    def test_chat_retries_on_failure(self):
        """chat() retries on transient errors."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Down")

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key", max_retries=1)
                result = provider.chat([{"role": "user", "content": "Hi"}])
                assert "error" in result
                assert mock_client.chat.completions.create.call_count == 2

    def test_chat_tracks_latency(self):
        """chat() sets last_latency_ms after a successful call."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi"
        mock_response.usage.total_tokens = 3
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                provider.chat([{"role": "user", "content": "Hi"}])
                assert provider.last_latency_ms is not None
                assert provider.last_latency_ms >= 0


# ── Registry wiring ────────────────────────────────────────────────────


class TestHuggingFaceRegistryWiring:
    def test_registry_falls_back_to_mock_for_unknown_backend(self):
        """Registry gracefully falls back to mock for backends not handled by _try_real_provider."""
        settings = Settings(
            _env_file=None,
            off_the_grid=False,
            planner_backend="nonexistent_backend_xyz",
        )
        registry = ProviderRegistry(settings)
        # Falls back to MockPlannerProvider for unknown backends
        assert registry.planner is not None
        assert registry.planner.available
        assert "Mock" in type(registry.planner).__name__

    def test_huggingface_backend_resolves_in_registry(self):
        """HuggingFace backend resolves to HuggingFaceProvider in registry."""
        settings = Settings(
            _env_file=None,
            off_the_grid=False,
            planner_backend="huggingface",
        )
        registry = ProviderRegistry(settings)
        planner = registry.planner
        assert planner is not None
        # _load_huggingface() imports the class (not huggingface_hub),
        # so the registry always creates a HuggingFaceProvider
        assert planner.name == "huggingface"

    def test_huggingface_backend_uses_real_provider_when_available(self):
        """HuggingFace backend should use real provider when deps and key exist."""
        mock_client = MagicMock()
        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                settings = Settings(
                    _env_file=None,
                    off_the_grid=False,
                    planner_backend="huggingface",
                    hf_api_key="hf_test_key",
                )
                registry = ProviderRegistry(settings)
                planner = registry.planner
                assert planner is not None
                assert planner.available
                assert planner.name == "huggingface"


# ── env_key() ──────────────────────────────────────────────────────────


class TestHuggingFaceEnvKey:
    def test_reads_shopstack_env_var(self):
        """_env_key() reads SHOPSTACK_HF_API_KEY env var."""
        from shopstack.providers.huggingface_provider import HuggingFaceProvider

        with patch.dict("os.environ", {"SHOPSTACK_HF_API_KEY": "shopstack_key"}, clear=True):
            assert HuggingFaceProvider._env_key() == "shopstack_key"

    def test_falls_back_to_hf_api_key(self):
        """_env_key() falls back to HF_API_KEY env var."""
        from shopstack.providers.huggingface_provider import HuggingFaceProvider

        with patch.dict("os.environ", {"HF_API_KEY": "hf_fallback_key"}, clear=True):
            assert HuggingFaceProvider._env_key() == "hf_fallback_key"

    def test_prefers_shopstack_over_hf(self):
        """_env_key() prefers SHOPSTACK_HF_API_KEY over HF_API_KEY."""
        from shopstack.providers.huggingface_provider import HuggingFaceProvider

        with patch.dict(
            "os.environ",
            {"SHOPSTACK_HF_API_KEY": "shopstack_key", "HF_API_KEY": "hf_key"},
            clear=True,
        ):
            assert HuggingFaceProvider._env_key() == "shopstack_key"

    def test_returns_empty_when_no_key(self):
        """_env_key() returns empty string when no key is set."""
        from shopstack.providers.huggingface_provider import HuggingFaceProvider

        with patch.dict("os.environ", {}, clear=True):
            assert HuggingFaceProvider._env_key() == ""


# ── Latency / last_token_count ─────────────────────────────────────────


class TestHuggingFaceProviderLatency:
    def test_latency_set_after_complete(self):
        """last_latency_ms should be set after a successful complete()."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi"
        mock_response.usage.total_tokens = 3
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                provider.complete("Say hi")
                # Latency may be 0 if the mock response is instant
                assert provider.last_latency_ms is not None
                assert provider.last_latency_ms >= 0

    def test_last_token_count_after_complete(self):
        """last_token_count should be set after a successful complete()."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi"
        mock_response.usage.total_tokens = 7
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "shopstack.providers.huggingface_provider._huggingface_available",
            return_value=(True, ""),
        ):
            with patch("huggingface_hub.InferenceClient", return_value=mock_client):
                provider = _get_hf_provider(api_key="key")
                provider.complete("Say hi")
                assert provider.last_token_count == 7
