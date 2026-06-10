"""Tests for local_provider.py — targeting 80%+ coverage."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Avoid module-level imports from shopstack.providers.local_provider here because
# other tests in the suite may reload or clear shopstack modules. Local imports
# inside each test maintain the current import state.

# ── Helpers ────────────────────────────────────────────────────────────

_NONEXISTENT_MODEL_DIR = "/tmp/shopstack_test_nonexistent_models"


def _get_local_provider(**kwargs):
    from shopstack.providers.local_provider import LocalProvider

    return LocalProvider(**kwargs)


def _provider_without_model(**kwargs):
    """Create a LocalProvider pointing at a non-existent model path."""
    base = dict(
        model_dir=_NONEXISTENT_MODEL_DIR,
        model_repo="nonexistent/repo",
        model_file="nonexistent.gguf",
        allow_download=False,
    )
    base.update(kwargs)
    with patch.dict("sys.modules", {"mlx_lm": None, "llama_cpp": None}, clear=False):
        return _get_local_provider(**base)


def _has_downloaded_model() -> bool:
    """Check if the default GGUF model exists at the expected path."""
    p = (
        Path(__file__).resolve().parent.parent
        / "shopstack" / "data" / "models"
        / "Llama-3.2-3B-Instruct-GGUF"
        / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    )
    return p.is_file()


# ── Helper function tests ──────────────────────────────────────────────


class TestDownloadFile:
    def test_download_file_creates_parent_dir(self):
        """_download_file should create parent directories."""
        from shopstack.providers.local_provider import _download_file

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "sub" / "model.gguf"
            url = "file:///dev/null"
            try:
                _download_file(url, dest)
            except Exception:
                pass  # may fail trying to download, but dir was created
            assert dest.parent.is_dir(), "Parent directory should exist"

    def test_download_file_urlretrieve_called(self):
        """_download_file calls urlretrieve with correct args."""
        from shopstack.providers.local_provider import _download_file

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "model.gguf"
            with patch("urllib.request.urlretrieve") as mock_retrieve:
                _download_file("https://example.com/model.gguf", dest)
            mock_retrieve.assert_called_once_with("https://example.com/model.gguf", str(dest))


class TestEnsureGgufModel:
    def test_ensure_gguf_returns_local_path_if_exists(self):
        """_ensure_gguf_model returns local path when file already exists."""
        from shopstack.providers.local_provider import _ensure_gguf_model

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "MyRepo"
            repo_dir.mkdir(parents=True)
            model_file = repo_dir / "model.gguf"
            model_file.write_text("fake model data")
            result = _ensure_gguf_model(tmp, "org/MyRepo", "model.gguf")
            assert result == str(model_file)

    def test_ensure_gguf_downloads_if_missing(self):
        """_ensure_gguf_model downloads when file doesn't exist."""
        from shopstack.providers.local_provider import _ensure_gguf_model

        with tempfile.TemporaryDirectory() as tmp:
            with patch("shopstack.providers.local_provider._download_file") as mock_dl:
                result = _ensure_gguf_model(tmp, "org/MyRepo", "missing.gguf")
            expected_path = str(Path(tmp) / "MyRepo" / "missing.gguf")
            mock_dl.assert_called_once()
            assert result == expected_path


# ── Initialization tests ───────────────────────────────────────────────


class TestLocalProviderInit:
    def test_name(self):
        provider = _provider_without_model()
        assert provider.name == "local"

    def test_capabilities(self):
        provider = _provider_without_model()
        assert "text" in provider.capabilities
        assert "planning" in provider.capabilities
        assert "embeddings" in provider.capabilities

    def test_not_available_when_no_model(self):
        provider = _provider_without_model()
        assert not provider.available
        assert provider.error is not None

    def test_not_available_no_inference_engine(self):
        """When both MLX and llama.cpp imports fail, error mentions engine."""
        with patch.dict(
            "sys.modules",
            {"mlx_lm": None, "llama_cpp": None},
            clear=False,
        ):
            provider = _get_local_provider(model_dir=_NONEXISTENT_MODEL_DIR)
            assert not provider.available
            err = (provider.error or "").lower()
            assert "inference engine" in err

    def test_init_custom_parameters(self):
        """Custom __init__ parameters propagate correctly."""
        provider = _get_local_provider(
            model_dir="/custom/path",
            model_repo="custom/repo",
            model_file="custom.gguf",
            mlx_model="mlx-community/custom-4bit",
            n_ctx=2048,
            n_gpu_layers=0,
            verbose=True,
            allow_download=True,
        )
        assert provider._model_dir == "/custom/path"
        assert provider._model_repo == "custom/repo"
        assert provider._model_file == "custom.gguf"
        assert provider._mlx_model == "mlx-community/custom-4bit"
        assert provider._n_ctx == 2048
        assert provider._n_gpu_layers == 0
        assert provider._verbose is True
        assert provider._allow_download is True

    def test_default_model_dir(self):
        """Default model_dir resolves to shopstack/data/models/."""
        provider = _get_local_provider(model_dir="", allow_download=False)
        assert "data" in provider._model_dir
        assert "models" in provider._model_dir

    def test_llamacpp_allow_download_no_model(self):
        """With allow_download=True but no model, provider attempts download."""
        # Mock so that MLX import fails and llama.cpp import succeeds
        import sys
        orig_modules = dict(sys.modules)
        mock_llamacpp = MagicMock()
        mock_llm = MagicMock()
        mock_llamacpp.Llama.return_value = mock_llm
        modules = {
            "mlx_lm": None,
            "llama_cpp": mock_llamacpp,
        }
        try:
            # Setting sys.modules directly so the dynamic import finds them
            for k, v in modules.items():
                if v is None:
                    sys.modules.pop(k, None)
                    sys.modules[k] = None
                else:
                    sys.modules[k] = v

            with patch("shopstack.providers.local_provider._ensure_gguf_model") as mock_ensure:
                mock_ensure.return_value = "/tmp/fake/model.gguf"
                _ = _get_local_provider(
                    model_dir=_NONEXISTENT_MODEL_DIR,
                    model_repo="org/MyRepo",
                    model_file="test.gguf",
                    allow_download=True,
                )
                mock_ensure.assert_called_once()
        finally:
            # Restore original modules
            for k in modules:
                if k in orig_modules:
                    sys.modules[k] = orig_modules[k]
                else:
                    sys.modules.pop(k, None)

    def test_available_when_model_present(self):
        """When model exists at default path, provider loads successfully."""
        if not _has_downloaded_model():
            pytest.skip("Default model not found, skipping availability test")
        default_dir = str(Path(__file__).resolve().parent.parent / "shopstack" / "data" / "models")
        provider = _get_local_provider(model_dir=default_dir, allow_download=False)
        assert provider.available
        assert provider.backend in ("mlx", "llama.cpp")
        assert provider.error is None


# ── Properties ─────────────────────────────────────────────────────────


class TestLocalProviderProperties:
    def test_available_property_false(self):
        provider = _provider_without_model()
        assert provider.available is False

    def test_error_property_not_none(self):
        provider = _provider_without_model()
        assert isinstance(provider.error, str)

    def test_backend_property(self):
        provider = _provider_without_model()
        assert isinstance(provider.backend, str)

    def test_last_latency_default(self):
        provider = _provider_without_model()
        assert provider.last_latency_ms is None

    def test_last_token_count_default(self):
        provider = _provider_without_model()
        assert provider.last_token_count is None

    def test_model_id_empty_when_unavailable(self):
        provider = _provider_without_model()
        assert provider.model_id == ""

    def test_runtime_report_unavailable_is_operator_readable(self):
        provider = _provider_without_model()
        report = provider.runtime_report()
        assert report["provider"] == "local"
        assert report["available"] is False
        assert report["backend"] == "unavailable"
        assert report["model_id"] == ""
        assert report["model_dir"] == _NONEXISTENT_MODEL_DIR
        assert "error" in report and report["error"]
        assert report["last_latency_ms"] is None
        assert report["last_token_count"] is None

    def test_last_latency_set_after_complete(self):
        """last_latency_ms is set after a successful completion."""
        if not _has_downloaded_model():
            pytest.skip("Model needed for this test")
        default_dir = str(Path(__file__).resolve().parent.parent / "shopstack" / "data" / "models")
        provider = _get_local_provider(model_dir=default_dir, allow_download=False)
        assert provider.available
        _result = provider.complete("Say hi", max_tokens=5, temperature=0.1)
        assert provider.last_latency_ms is not None
        assert isinstance(provider.last_latency_ms, (int, float))

    def test_last_token_count_set_after_complete(self):
        """last_token_count is set after a successful completion."""
        if not _has_downloaded_model():
            pytest.skip("Model needed for this test")
        default_dir = str(Path(__file__).resolve().parent.parent / "shopstack" / "data" / "models")
        provider = _get_local_provider(model_dir=default_dir, allow_download=False)
        assert provider.available
        _result = provider.complete("Say hi", max_tokens=5, temperature=0.1)
        assert provider.last_token_count is not None
        assert isinstance(provider.last_token_count, int)


# ── complete() ─────────────────────────────────────────────────────────


class TestLocalProviderComplete:
    def test_complete_unavailable(self):
        provider = _provider_without_model()
        result = provider.complete("Hello")
        assert "error" in result
        assert not provider.available

    def test_complete_with_data(self):
        """complete() returns valid data when model is loaded."""
        if not _has_downloaded_model():
            pytest.skip("Model needed for this test")
        default_dir = str(Path(__file__).resolve().parent.parent / "shopstack" / "data" / "models")
        provider = _get_local_provider(model_dir=default_dir, allow_download=False)
        assert provider.available
        result = provider.complete("What is 2+2? Answer in one word.", max_tokens=10, temperature=0.1)
        assert "error" not in result
        assert "text" in result
        assert result["text"]
        assert "model" in result
        assert "usage" in result




# ── embed() ────────────────────────────────────────────────────────────


class TestLocalProviderEmbed:
    def test_embed_unavailable(self):
        provider = _provider_without_model()
        result = provider.embed(["hello"])
        assert result == []

    def test_embed_mlx_backend(self):
        """embed returns empty for MLX backend (not implemented)."""
        provider = _provider_without_model()
        provider._available = True
        provider._backend = "mlx"
        result = provider.embed(["hello"])
        assert result == []

    def test_embed_error(self):
        """embed returns empty when llama.cpp backend fails."""
        provider = _provider_without_model()
        provider._available = True
        provider._backend = "llama.cpp"
        provider._llm = MagicMock()
        provider._llm.create_embedding.side_effect = RuntimeError("embedding failed")
        result = provider.embed(["hello"])
        assert result == []


# ── Vision / Audio fallbacks ───────────────────────────────────────────


class TestLocalProviderFallbacks:
    def test_analyze_image_unavailable(self):
        provider = _provider_without_model()
        result = provider.analyze_image("/fake.jpg")
        assert "error" in result

    def test_analyze_image_available(self):
        """analyze_image returns error even when available (not supported)."""
        provider = _provider_without_model()
        provider._available = True
        result = provider.analyze_image("/fake.jpg")
        assert "error" in result
        assert "does not support vision" in result["error"]

    def test_transcribe_audio_unavailable(self):
        provider = _provider_without_model()
        result = provider.transcribe_audio("/fake.wav")
        assert "error" in result

    def test_transcribe_audio_available(self):
        """transcribe_audio returns error even when available (not supported)."""
        provider = _provider_without_model()
        provider._available = True
        result = provider.transcribe_audio("/fake.wav")
        assert "error" in result
        assert "does not support STT" in result["error"]

    def test_detect_objects(self):
        provider = _provider_without_model()
        result = provider.detect_objects("/fake.jpg")
        assert "error" in result[0]

    def test_extract_text(self):
        provider = _provider_without_model()
        result = provider.extract_text("/fake.jpg")
        assert "error" in result


# ─── llama.cpp init failure ────────────────────────────────────────────


class TestLocalProviderLlamaCppFailure:
    def test_llamacpp_init_exception(self):
        """When llama.cpp model loading raises, provider is unavailable."""
        with patch.dict("sys.modules", {"mlx_lm": None}, clear=False):
            # We can't easily mock llama_cpp.Llama constructor failure
            # since it needs a real model path. Test the exception handler
            # by making _ensure_gguf_model raise.
            with patch(
                "shopstack.providers.local_provider._ensure_gguf_model",
                side_effect=RuntimeError("download failed"),
            ):
                with patch(
                    "shopstack.providers.local_provider.llama_cpp",
                    create=True,
                ):
                    provider = _get_local_provider(
                        model_dir="/nonexistent",
                        model_repo="org/repo",
                        model_file="model.gguf",
                        allow_download=True,
                    )
                    assert not provider.available
                    assert provider.error is not None
                    assert "download failed" in provider.error


# ── MLX completion path ───────────────────────────────────────────────


class TestLocalProviderMlxComplete:
    def _make_mlx_env(self):
        """Build mock mlx_lm module with load/generate/sample_utils."""
        import sys as _sys
        from unittest.mock import MagicMock

        mock_mlx_lm = MagicMock()
        mock_llm = MagicMock()
        mock_tokenizer = MagicMock()
        mock_mlx_lm.load.return_value = (mock_llm, mock_tokenizer)
        mock_mlx_lm.generate.return_value = "Yes."

        mock_sample_utils = MagicMock()
        mock_sampler = MagicMock()
        mock_sample_utils.make_sampler.return_value = mock_sampler

        _sys.modules["mlx_lm"] = mock_mlx_lm
        _sys.modules["mlx_lm.sample_utils"] = mock_sample_utils
        return mock_mlx_lm, mock_llm

    def _restore_modules(self, orig_modules):
        import sys as _sys
        for k in list(_sys.modules):
            if k.startswith("mlx_lm") and k not in orig_modules:
                _sys.modules.pop(k, None)
            elif k in orig_modules:
                _sys.modules[k] = orig_modules[k]

    def test_mlx_local_path_check(self):
        """Line 90: MLX checks local cached directory before HF."""
        import sys as _sys
        import tempfile
        from pathlib import Path

        orig_modules = dict(_sys.modules)
        try:
            self._make_mlx_env()
            with tempfile.TemporaryDirectory() as tmp:
                # Fake local MLX model directory
                mlx_dir = Path(tmp) / "Llama-3.2-3B-Instruct-4bit"
                mlx_dir.mkdir(parents=True)
                (mlx_dir / "config.json").write_text("{}")

                provider = _get_local_provider(
                    model_dir=tmp,
                    mlx_model="mlx-community/Llama-3.2-3B-Instruct-4bit",
                )
                assert provider.available
                assert provider.backend == "mlx"
        finally:
            self._restore_modules(orig_modules)

    def test_mlx_completion_path(self):
        """Lines 169-177: MLX completion path produces correct result."""
        import sys as _sys

        orig_modules = dict(_sys.modules)
        try:
            self._make_mlx_env()
            provider = _get_local_provider(model_dir=_NONEXISTENT_MODEL_DIR)
            assert provider.available
            assert provider.backend == "mlx"

            result = provider.complete("What is 2+2?", max_tokens=10, temperature=0.1)
            assert "error" not in result
            assert result["text"] == "Yes."
            assert "model" in result
            assert result["usage"]["total_tokens"] == 10
            assert provider.last_latency_ms is not None
            assert provider.last_token_count == 10
        finally:
            self._restore_modules(orig_modules)


# ── llama.cpp init paths ──────────────────────────────────────────────


class TestLocalProviderLlamaCpp:
    def test_llamacpp_successful_init(self):
        """Lines 115-122: llama.cpp successful initialization sets backend, clears error."""
        import sys as _sys
        from unittest.mock import MagicMock, patch

        orig_modules = dict(_sys.modules)
        mock_llamacpp = MagicMock()
        mock_llm = MagicMock()
        mock_llamacpp.Llama.return_value = mock_llm
        modules = {"mlx_lm": None, "llama_cpp": mock_llamacpp}
        try:
            for k, v in modules.items():
                _sys.modules.pop(k, None)
                _sys.modules[k] = v

            with patch("shopstack.providers.local_provider._ensure_gguf_model") as mock_ensure:
                mock_ensure.return_value = "/tmp/fake/model.gguf"
                provider = _get_local_provider(
                    model_dir=_NONEXISTENT_MODEL_DIR,
                    model_repo="org/MyRepo",
                    model_file="test.gguf",
                    allow_download=True,
                )
                assert provider.available
                assert provider.backend == "llama.cpp"
                assert provider.error is None
        finally:
            for k in modules:
                if k in orig_modules:
                    _sys.modules[k] = orig_modules[k]
                else:
                    _sys.modules.pop(k, None)

    def test_llamacpp_completion_path(self):
        """llama.cpp complete() sets latency/token counts (lines 187-189)."""
        import sys as _sys
        from unittest.mock import MagicMock, patch

        orig_modules = dict(_sys.modules)
        mock_llamacpp = MagicMock()
        mock_llm = MagicMock()
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "Four."}}],
            "usage": {"total_tokens": 5},
        }
        mock_llamacpp.Llama.return_value = mock_llm
        modules = {"mlx_lm": None, "llama_cpp": mock_llamacpp}
        try:
            for k, v in modules.items():
                _sys.modules.pop(k, None)
                _sys.modules[k] = v

            with patch("shopstack.providers.local_provider._ensure_gguf_model") as mock_ensure:
                mock_ensure.return_value = "/tmp/fake/model.gguf"
                provider = _get_local_provider(
                    model_dir=_NONEXISTENT_MODEL_DIR,
                    model_repo="org/MyRepo",
                    model_file="test.gguf",
                    allow_download=True,
                )
                result = provider.complete("What is 2+2?")
                assert "error" not in result
                assert result["text"] == "Four."
                assert provider.last_latency_ms is not None
                assert provider.last_token_count == 5
        finally:
            for k in modules:
                if k in orig_modules:
                    _sys.modules[k] = orig_modules[k]
                else:
                    _sys.modules.pop(k, None)

    def test_complete_exception_handler(self):
        """Lines 200-201: complete() except handler catches errors gracefully."""
        import sys as _sys
        from unittest.mock import MagicMock, patch

        orig_modules = dict(_sys.modules)
        mock_llamacpp = MagicMock()
        mock_llm = MagicMock()
        mock_llm.create_chat_completion.side_effect = RuntimeError("GPU OOM")
        mock_llamacpp.Llama.return_value = mock_llm
        modules = {"mlx_lm": None, "llama_cpp": mock_llamacpp}
        try:
            for k, v in modules.items():
                _sys.modules.pop(k, None)
                _sys.modules[k] = v

            with patch("shopstack.providers.local_provider._ensure_gguf_model") as mock_ensure:
                mock_ensure.return_value = "/tmp/fake/model.gguf"
                provider = _get_local_provider(
                    model_dir=_NONEXISTENT_MODEL_DIR,
                    model_repo="org/MyRepo",
                    model_file="test.gguf",
                    allow_download=True,
                )
                result = provider.complete("What is 2+2?")
                assert "error" in result
                assert "GPU OOM" in result["error"]
        finally:
            for k in modules:
                if k in orig_modules:
                    _sys.modules[k] = orig_modules[k]
                else:
                    _sys.modules.pop(k, None)


# ── End-to-end test with model ─────────────────────────────────────────


class TestLocalProviderEndToEnd:
    """Tests that require the downloaded model."""

    def test_complete_empty_prompt(self):
        if not _has_downloaded_model():
            pytest.skip("Model needed")
        default_dir = str(Path(__file__).resolve().parent.parent / "shopstack" / "data" / "models")
        provider = _get_local_provider(model_dir=default_dir, allow_download=False)
        result = provider.complete("", max_tokens=5)
        assert "text" in result
