"""Tests for the OpenAI API provider."""

from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

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
        "shopstack.providers.openai_provider._check_deps",
        return_value=(True, ""),
    )


# ── Helpers ────────────────────────────────────────────────────────────


def _get_openai_provider(**kwargs):
    from shopstack.providers.openai_provider import OpenAIProvider
    return OpenAIProvider(**kwargs)


# ── Init / availability ────────────────────────────────────────────────


class TestOpenAIProviderInit:
    def test_not_available_when_package_missing(self):
        """OpenAIProvider should not be available when openai is not installed."""
        with _mock_missing_openai_package():
            provider = _get_openai_provider()
            assert not provider.available
            assert provider.error is not None
            assert "openai" in (provider.error or "").lower()

    def test_not_available_when_api_key_missing(self):
        """OpenAIProvider should not be available without an API key."""
        with _mock_openai_available(), _mock_missing_api_key():
            provider = _get_openai_provider()
            assert not provider.available
            assert provider.error is not None
            assert "api key" in (provider.error or "").lower()

    def test_available_with_key_and_deps(self):
        """OpenAIProvider should be available with API key and package installed."""
        mock_client = MagicMock()
        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                assert provider.available
                assert provider.error is None

    def test_custom_model(self):
        """Custom model propagates correctly."""
        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=MagicMock()):
                provider = _get_openai_provider(
                    api_key="sk-test-key",
                    model="gpt-4o-mini",
                    embedding_model="text-embedding-3-large",
                )
                assert provider._model == "gpt-4o-mini"
                assert provider._embedding_model == "text-embedding-3-large"

    def test_capabilities(self):
        """OpenAIProvider exposes text, vision, OCR, and embeddings capabilities."""
        from shopstack.providers.openai_provider import OpenAIProvider
        assert "text" in OpenAIProvider.capabilities
        assert "vision" in OpenAIProvider.capabilities
        assert "ocr" in OpenAIProvider.capabilities
        assert "embeddings" in OpenAIProvider.capabilities

    def test_name_and_defaults(self):
        """Name, default model, and default embedding model are set."""
        from shopstack.providers.openai_provider import OpenAIProvider
        assert OpenAIProvider.name == "openai"
        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=MagicMock()):
                provider = _get_openai_provider(api_key="sk-test-key")
                assert provider._model == "gpt-4o"
                assert provider._embedding_model == "text-embedding-3-small"

    def test_client_init_failure(self):
        """OpenAIProvider handles client init failure gracefully."""
        with _mock_openai_available():
            with patch("openai.OpenAI", side_effect=RuntimeError("Connection refused")):
                provider = _get_openai_provider(api_key="sk-test-key")
                assert not provider.available
                assert "Connection refused" in (provider.error or "")


# ── complete() ─────────────────────────────────────────────────────────


class TestOpenAIProviderComplete:
    def test_complete_returns_error_when_not_available(self):
        """complete() returns error dict when not available."""
        with _mock_missing_openai_package():
            provider = _get_openai_provider()
            result = provider.complete("Say hi")
            assert "error" in result
            assert result["model"] == "openai"

    def test_complete_success(self):
        """complete() returns text from the OpenAI API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 8
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                result = provider.complete("Say hi", max_tokens=50, temperature=0.5)
                assert "error" not in result
                assert result["text"] == "Hello!"
                assert result["model"] == "gpt-4o"
                assert "usage" in result
                assert "cost" in result
                assert provider.last_completion_meta["model"] == "gpt-4o"
                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["max_tokens"] == 50
                assert call_kwargs["temperature"] == 0.5

    def test_complete_custom_model(self):
        """complete() respects the model kwarg override."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 2
        mock_response.usage.completion_tokens = 3
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                result = provider.complete("Hi", model="gpt-4o-mini")
                assert result["model"] == "gpt-4o-mini"

    def test_complete_gpt5_uses_completion_token_parameter(self):
        """GPT-5 family models use the current completion token parameter."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 2
        mock_response.usage.completion_tokens = 3
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                provider.complete("Hi", model="gpt-5.6-luna", max_tokens=64)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_completion_tokens"] == 64
        assert "max_tokens" not in call_kwargs
        assert "temperature" not in call_kwargs

    def test_plan_preserves_parser_diagnostics_for_compatibility_response(self):
        """A prose fallback remains list-compatible but is diagnosable upstream."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "plain prose, not an action plan"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 2
        mock_response.usage.completion_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                result = provider.plan({"prompt": "plan", "question": "plan"})

        assert result == [{"tool": "respond", "args": {"message": "plain prose, not an action plan"}}]
        assert provider.last_plan_diagnostics["status"] == "fallback_respond"

    def test_plan_uses_bounded_budget_for_nested_tool_arguments(self):
        """Planner output budget leaves room for nested shopping-list JSON."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '[{"tool":"create_or_update_shopping_list","args":{"items":[]}}]'
        )
        mock_response.usage = MagicMock(prompt_tokens=2, completion_tokens=3)
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key", model="gpt-5.6-luna")
                provider.plan({"prompt": "plan", "question": "plan"})

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_completion_tokens"] == 512

    def test_complete_api_error(self):
        """complete() returns error dict on API failure."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Rate limit exceeded")

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                result = provider.complete("Say hi")
                assert "error" in result
                assert "Rate limit exceeded" in result["error"]


# ── analyze_image() ────────────────────────────────────────────────────


class TestOpenAIProviderAnalyzeImage:
    def test_analyze_image_returns_error_when_not_available(self):
        """analyze_image() returns error dict when not available."""
        with _mock_missing_openai_package():
            provider = _get_openai_provider()
            result = provider.analyze_image("/tmp/test.jpg")
            assert "error" in result

    def test_analyze_image_success(self):
        """analyze_image() sends base64 image to OpenAI API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I see a tomato and an onion."
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                with patch("builtins.open", mock_open(read_data=b"fake_image_data")):
                    provider = _get_openai_provider(api_key="sk-test-key")
                    result = provider.analyze_image("/tmp/test.jpg")
                    assert "error" not in result
                    assert result["description"] == "I see a tomato and an onion."
                    assert result["model"] == "gpt-4o"
                    # Verify base64 was included
                    call_kwargs = mock_client.chat.completions.create.call_args[1]
                    content = call_kwargs["messages"][0]["content"]
                    assert len(content) == 2
                    assert content[1]["type"] == "image_url"
                    assert "base64" in content[1]["image_url"]["url"]

    def test_analyze_image_custom_prompt(self):
        """analyze_image() sends custom prompt text."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Nothing."
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                with patch("builtins.open", mock_open(read_data=b"img")):
                    provider = _get_openai_provider(api_key="sk-test-key")
                    provider.analyze_image("/tmp/test.jpg", prompt="List all items")
                    call_kwargs = mock_client.chat.completions.create.call_args[1]
                    content = call_kwargs["messages"][0]["content"]
                    assert content[0]["text"] == "List all items"

    def test_analyze_image_gpt5_uses_image_mime_and_completion_budget(self):
        """GPT-5 vision calls preserve the fixture MIME type and API contract."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"products": []}'
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                with patch("builtins.open", mock_open(read_data=b"png-data")):
                    provider = _get_openai_provider(api_key="sk-test-key", model="gpt-5.6-luna")
                    provider.analyze_image("/tmp/test.png", max_tokens=256, reasoning_effort="high")
                    call_kwargs = mock_client.chat.completions.create.call_args[1]
                    assert call_kwargs["max_completion_tokens"] == 256
                    assert call_kwargs["reasoning_effort"] == "high"
                    assert "max_tokens" not in call_kwargs
                    image_url = call_kwargs["messages"][0]["content"][1]["image_url"]["url"]
                    assert image_url.startswith("data:image/png;base64,")


class TestOpenAIProviderReceiptExtraction:
    def test_extract_returns_raw_text_for_the_ocr_pipeline(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Demo Mart\nMilk 2 L 120\nTotal: 120.00"
        mock_response.usage = MagicMock(prompt_tokens=12, completion_tokens=18, total_tokens=30)
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                with patch("builtins.open", mock_open(read_data=b"receipt-image")):
                    provider = _get_openai_provider(api_key="sk-test-key", model="gpt-5.6-luna")
                    result = provider.extract("/tmp/receipt.png")

        assert result["text"].startswith("Demo Mart")
        assert result["raw_text"] == result["text"]
        assert result["model"] == "gpt-5.6-luna"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_completion_tokens"] == 1024
        assert call_kwargs["reasoning_effort"] == "high"
        assert "receipt image" in call_kwargs["messages"][0]["content"][0]["text"]


# ── embed() ────────────────────────────────────────────────────────────


class TestOpenAIProviderEmbed:
    def test_embed_returns_error_when_not_available(self):
        """embed() returns zero vectors when not available."""
        with _mock_missing_openai_package():
            provider = _get_openai_provider()
            result = provider.embed(["hello"])
            assert len(result) == 1
            assert len(result[0]) == 128
            assert all(v == 0.0 for v in result[0])

    def test_embed_success(self):
        """embed() returns embeddings from the API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [0.1, 0.2, 0.3]
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                result = provider.embed(["test text"])
                assert len(result) == 1
                assert result[0] == [0.1, 0.2, 0.3]
                mock_client.embeddings.create.assert_called_once()
                call_kwargs = mock_client.embeddings.create.call_args[1]
                assert call_kwargs["input"] == ["test text"]
                assert call_kwargs["model"] == "text-embedding-3-small"

    def test_embed_multiple_texts(self):
        """embed() handles multiple text inputs."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2]),
            MagicMock(embedding=[0.3, 0.4]),
        ]
        mock_client.embeddings.create.return_value = mock_response

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                result = provider.embed(["text a", "text b"])
                assert len(result) == 2
                assert result[0] == [0.1, 0.2]
                assert result[1] == [0.3, 0.4]

    def test_embed_api_error(self):
        """embed() handles API errors gracefully."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = RuntimeError("API error")

        with _mock_openai_available():
            with patch("openai.OpenAI", return_value=mock_client):
                provider = _get_openai_provider(api_key="sk-test-key")
                result = provider.embed(["test"])
                # Returns zero vectors on error
                assert len(result) == 1
                assert all(v == 0.0 for v in result[0])


# ── env_key() ──────────────────────────────────────────────────────────


class TestOpenAIProviderEnvKey:
    def test_reads_shopstack_env_var(self):
        """_env_key() reads SHOPSTACK_OPENAI_API_KEY env var."""
        from shopstack.providers.openai_provider import OpenAIProvider

        with patch.dict("os.environ", {"SHOPSTACK_OPENAI_API_KEY": "shopstack_key"}, clear=True):
            assert OpenAIProvider._env_key() == "shopstack_key"

    def test_falls_back_to_openai_api_key(self):
        """_env_key() falls back to OPENAI_API_KEY env var."""
        from shopstack.providers.openai_provider import OpenAIProvider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "openai_fallback"}, clear=True):
            assert OpenAIProvider._env_key() == "openai_fallback"

    def test_prefers_shopstack_over_openai(self):
        """_env_key() prefers SHOPSTACK_OPENAI_API_KEY over OPENAI_API_KEY."""
        from shopstack.providers.openai_provider import OpenAIProvider

        with patch.dict("os.environ",
                        {"SHOPSTACK_OPENAI_API_KEY": "shopstack_key", "OPENAI_API_KEY": "openai_key"},
                        clear=True):
            assert OpenAIProvider._env_key() == "shopstack_key"

    def test_returns_empty_when_no_key(self):
        """_env_key() returns empty string when no key is set."""
        from shopstack.providers.openai_provider import OpenAIProvider

        with patch.dict("os.environ", {}, clear=True):
            assert OpenAIProvider._env_key() == ""


# ── Registry wiring ────────────────────────────────────────────────────


class TestOpenAIRegistryWiring:
    def test_openai_backend_resolves_in_registry(self):
        """OpenAI backend resolves to OpenAIProvider in registry."""
        settings = Settings(
            _env_file=None,
            off_the_grid=False,
            planner_backend="openai",
        )
        registry = ProviderRegistry(settings)
        planner = registry.planner
        assert planner is not None
        assert planner.name == "openai"

    def test_openai_backend_not_available_without_key(self):
        """OpenAI backend is not available when key is missing (deps mocked)."""
        with _mock_openai_available(), _mock_missing_api_key():
            settings = Settings(
                _env_file=None,
                off_the_grid=False,
                planner_backend="openai",
            )
            registry = ProviderRegistry(settings)
            planner = registry.planner
            assert planner is not None
            assert not planner.available
            assert "api key" in (planner.error or "").lower()
