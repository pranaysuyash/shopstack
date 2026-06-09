from __future__ import annotations

import importlib.util
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from shopstack.cost_tracker import estimate_cost_usd, estimate_model_tier

logger = logging.getLogger(__name__)

DEFAULT_MODEL_REPO = "unsloth/Llama-3.2-3B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
DEFAULT_MLX_MODEL = "Qwen/Qwen3.5-4B"


def _download_file(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s to %s ...", url, dest)
    urllib.request.urlretrieve(url, str(dest))
    logger.info("Download complete: %s", dest)


def _ensure_gguf_model(model_dir: str, repo: str, filename: str) -> str:
    parts = repo.split("/")
    local_path = Path(model_dir) / parts[-1] / filename
    if local_path.is_file():
        return str(local_path)

    # Try HF Mirror, then HuggingFace
    url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
    _download_file(url, local_path)
    return str(local_path)


class LocalProvider:
    name = "local"
    capabilities: set[str] = {"text", "planning", "embeddings"}
    _backend: str = ""

    def __init__(
        self,
        model_dir: str = "",
        model_repo: str = DEFAULT_MODEL_REPO,
        model_file: str = DEFAULT_MODEL_FILE,
        mlx_model: str = DEFAULT_MLX_MODEL,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,
        verbose: bool = False,
        allow_download: bool = False,
        auto_unload: bool = True,
    ):
        self._model_dir = model_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models"
        )
        self._model_repo = model_repo
        self._model_file = model_file
        self._mlx_model = mlx_model
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._verbose = verbose
        self._allow_download = allow_download
        self._auto_unload = auto_unload
        self._available = False
        self._error: str | None = None
        self._llm: Any = None
        self._tokenizer: Any = None
        self._model_path: str | None = None
        self._last_latency_ms: float | None = None
        self._last_token_count: int | None = None
        self._init()

    def _init(self) -> None:
        self._init_mlx()
        if self._available:
            return
        self._init_llamacpp()

    def _init_mlx(self) -> None:
        # Respect sys.modules mocking used in tests to simulate a missing
        # package (patch.dict("sys.modules", {"mlx_lm": None})).
        if "mlx_lm" in sys.modules and sys.modules["mlx_lm"] is None:
            self._error = "mlx-lm not installed. Run: uv pip install mlx-lm"
            return
        # Use find_spec to check for the package without importing it.
        # Direct import of mlx_lm triggers mlx.core which can segfault
        # on Python 3.14+ when multiple modules are initialised concurrently
        # (common during pytest collection). A segfault is not catchable
        # with try/except, so we avoid the import entirely until needed.
        try:
            spec = importlib.util.find_spec("mlx_lm")
        except ValueError:
            # find_spec can raise ValueError when a module is in sys.modules
            # but __spec__ is not set (common in test mocking scenarios).
            # Fall back to sys.modules check as an availability signal.
            spec = None if "mlx_lm" not in sys.modules else sys.modules["mlx_lm"]
        if spec is None:
            self._error = "mlx-lm not installed. Run: uv pip install mlx-lm"
            return
        try:
            model_path = self._mlx_model
            # Try local path first, then HF model ID
            local_path = Path(self._model_dir) / self._mlx_model.split("/")[-1]
            if local_path.is_dir():
                model_path = str(local_path)
            else:
                # Check the HF hub cache (respects HF_HOME env var).
                # If the model isn't cached locally, only return early
                # (fall through to llama.cpp GGUF) when auto-download is
                # disabled. With auto-download enabled, claim MLX availability
                # and let _init_mlx_model() download via mlx_lm.load().
                if not self._allow_download:
                    hf_home = os.environ.get(
                        "HF_HOME",
                        os.path.expanduser("~/.cache/huggingface"),
                    )
                    hf_cache = Path(hf_home) / "hub"
                    model_dir_name = "models--" + self._mlx_model.replace("/", "--")
                    hf_model_dir = hf_cache / model_dir_name
                    if not hf_model_dir.is_dir():
                        logger.info(
                            "MLX model %s not cached locally, "
                            "falling through to llama.cpp GGUF path",
                            self._mlx_model,
                        )
                        return
                else:
                    logger.info(
                        "MLX model %s not cached locally, will auto-download on first use",
                        self._mlx_model,
                    )

            self._model_path = model_path
            self._backend = "mlx"
            self._available = True
            self._error = None
            logger.info("Local provider prepared for MLX: %s", self._model_path)
        except Exception as e:
            logger.info("MLX init failed (%s), trying llama.cpp fallback", e)

    def _init_llamacpp(self) -> None:
        if "llama_cpp" in sys.modules and sys.modules["llama_cpp"] is None:
            self._error = (
                "No local inference engine available. "
                "Install one: uv pip install mlx-lm  (Apple Silicon) "
                "or uv pip install 'shopstack[local]' (llama-cpp-python)"
            )
            self._available = False
            return
        try:
            spec = importlib.util.find_spec("llama_cpp")
        except ValueError:
            spec = None if "llama_cpp" not in sys.modules else sys.modules["llama_cpp"]
        if spec is None:
            self._error = (
                "No local inference engine available. "
                "Install one: uv pip install mlx-lm  (Apple Silicon) "
                "or uv pip install 'shopstack[local]' (llama-cpp-python)"
            )
            self._available = False
            return
        try:
            import llama_cpp  # noqa: F401 — availability check for optional dep

            local_path = Path(self._model_dir) / self._model_repo.split("/")[-1] / self._model_file
            if not local_path.is_file():
                if not self._allow_download:
                    self._error = (
                        f"Local GGUF model not found at {local_path}. "
                        "Set SHOPSTACK_LOCAL_AUTO_DOWNLOAD=true and provide model assets,"
                        " or place the file at this location first."
                    )
                    self._available = False
                    logger.warning("Local model unavailable: %s", self._error)
                    return
                try:
                    self._model_path = _ensure_gguf_model(self._model_dir, self._model_repo, self._model_file)
                except Exception as e:
                    self._error = f"Failed to download llama.cpp model: {e}"
                    self._available = False
                    logger.warning("Local model download failed: %s", exc_info=True)
                    return
            else:
                self._model_path = str(local_path)

            self._error = None
            self._backend = "llama.cpp"
            self._available = True
            logger.info(
                "Local provider prepared for llama.cpp: %s/%s (ctx=%d, gpu_layers=%s)",
                self._model_repo, self._model_file, self._n_ctx,
                "all" if self._n_gpu_layers < 0 else self._n_gpu_layers,
            )
        except Exception as e:
            self._error = f"Failed to init llama.cpp provider: {e}"
            self._available = False
            logger.warning("llama.cpp provider init failed", exc_info=True)

    def _ensure_model(self) -> bool:
        if not self._available:
            return False
        if self._llm is not None:
            return True
        if self._backend == "mlx":
            if self._init_mlx_model():
                return True
            return self._init_llamacpp_model()
        if self._backend == "llama.cpp":
            return self._init_llamacpp_model()
        return False

    def _init_mlx_model(self) -> bool:
        try:
            from mlx_lm import load
            model_path = self._model_path or self._mlx_model
            loaded = load(model_path)
            self._llm = loaded[0]
            self._tokenizer = loaded[1]
            logger.info("Local provider loaded via MLX: %s", model_path)
            return True
        except Exception as e:
            self._error = f"Failed to initialize MLX runtime: {e}"
            self._available = False
            logger.warning("MLX model load failed", exc_info=True)
            return False

    def _init_llamacpp_model(self) -> bool:
        try:
            import llama_cpp
            if not self._model_path:
                return False
            if not Path(self._model_path).is_file():
                model_path = _ensure_gguf_model(self._model_dir, self._model_repo, self._model_file)
            else:
                model_path = self._model_path
            self._llm = llama_cpp.Llama(
                model_path=model_path,
                n_ctx=self._n_ctx,
                n_gpu_layers=self._n_gpu_layers,
                verbose=self._verbose,
            )
            self._model_path = model_path
            logger.info(
                "Local provider loaded via llama.cpp: %s/%s (ctx=%d, gpu_layers=%s)",
                self._model_repo, self._model_file, self._n_ctx,
                "all" if self._n_gpu_layers < 0 else self._n_gpu_layers,
            )
            return True
        except Exception as e:
            self._error = f"Failed to initialize llama.cpp runtime: {e}"
            self._available = False
            logger.warning("llama.cpp model load failed", exc_info=True)
            return False

    def _maybe_unload_model(self) -> None:
        if not self._auto_unload or self._llm is None:
            return
        try:
            close = getattr(self._llm, "close", None)
            if callable(close):
                close()
        except Exception:
            logger.debug("Failed to close local LLM instance cleanly", exc_info=True)
        self._llm = None
        self._tokenizer = None

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        from shopstack.tracing import trace_call

        if not self._available:
            return {"error": self._error or "Local provider not available", "model": self.name}
        model_name = self._mlx_model if self._backend == "mlx" else f"{self._model_repo}/{self._model_file}"
        tier = estimate_model_tier(len(prompt))
        with trace_call("llm.complete", attributes={
            "model": model_name,
            "tier": tier,
            "provider": self.name,
            "backend": self._backend,
            "prompt_length": len(prompt),
        }) as span:
            try:
                max_tokens = kwargs.get("max_tokens", 512)
                temperature = kwargs.get("temperature", 0.3)
                stop = kwargs.get("stop", [])
                if not self._ensure_model():
                    return {"error": self._error or "Local provider not available", "model": self.name}
                if not prompt:
                    return {"text": "", "model": model_name, "usage": {"total_tokens": 0}}

                t0 = time.monotonic()

                if self._backend == "mlx":
                    from mlx_lm import generate
                    from mlx_lm.sample_utils import make_sampler

                    sampler = make_sampler(temp=temperature)
                    text = generate(
                        self._llm,
                        self._tokenizer,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        sampler=sampler,
                    )
                    token_count = max_tokens
                    result = {"text": text, "model": self._mlx_model, "usage": {"total_tokens": token_count}}
                else:
                    response = self._llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stop=stop or None,
                    )
                    text = response["choices"][0]["message"]["content"]
                    token_count = response.get("usage", {}).get("total_tokens", 0)
                    result = {
                        "text": text,
                        "model": f"{self._model_repo}/{self._model_file}",
                        "usage": {"total_tokens": token_count},
                    }

                elapsed = time.monotonic() - t0
                elapsed_ms = round(elapsed * 1000, 1)
                self._last_latency_ms = elapsed_ms
                self._last_token_count = token_count

                cost = estimate_cost_usd(model_name, 0, token_count)
                span.set_attribute("input_tokens", 0)
                span.set_attribute("output_tokens", token_count)
                span.set_attribute("cost_usd", cost)
                span.set_attribute("latency_ms", elapsed_ms)
                result["cost"] = {"usd": cost, "tier": tier, "latency_ms": elapsed_ms}
                return result
            except Exception as e:
                logger.warning("Local completion failed", exc_info=True)
                span.record_exception(e)
                return {"error": str(e), "model": self.name}
            finally:
                self._maybe_unload_model()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._available:
            logger.warning("embed() called but local provider unavailable; returning empty list")
            return []
        if not self._ensure_model():
            logger.warning("embed() called but model could not be loaded; returning empty list")
            return []
        if self._backend == "mlx":
            logger.warning("MLX backend does not support embeddings; use BGE-M3 provider instead")
            return []
        try:
            results = []
            for text in texts:
                embedding = self._llm.create_embedding(input=text)
                results.append(embedding["data"][0]["embedding"])
            return results
        except Exception:
            logger.warning("Local embedding failed", exc_info=True)
            return []
        finally:
            self._maybe_unload_model()

    def analyze_image(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        if not self._available:
            return {"error": self._error or "Local provider not available"}
        return {"error": "Local provider does not support vision. Use OpenAI or a multimodal GGUF.", "model": self.name}

    def transcribe_audio(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        if not self._available:
            return {"error": self._error or "Local provider not available"}
        return {"error": "Local provider does not support STT. Use Whisper or a dedicated ASR model.", "model": self.name}

    def detect_objects(self, image_path: str) -> list[dict[str, Any]]:
        return [{"error": "Local provider does not support object detection."}]

    def extract_text(self, image_path: str) -> dict[str, Any]:
        return {"error": "Local provider does not support OCR. Use a dedicated OCR model.", "model": self.name}

    def _format_chat_prompt(self, system_prompt: str, question: str) -> str | None:
        """Format system + user messages using the tokenizer's chat template.

        Chat-based models like Qwen3.5 require the chat template to correctly
        interpret system/user message boundaries. Without it, the model
        generates conversation continuations (multiple turns) that break
        JSON parsing and waste token budget on thinking.

        Returns the formatted prompt string, or None if the tokenizer
        isn't loaded or doesn't have a chat_template (e.g., GGUF backend).
        """
        if self._tokenizer is None:
            return None
        chat_template = getattr(self._tokenizer, "chat_template", None)
        if not chat_template:
            return None
        if not question:
            return None
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"USER REQUEST: {question}\n\nJSON tool calls:"},
        ]
        try:
            return self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception as exc:
            logger.debug("Chat template formatting failed: %s", exc)
            return None

    def plan(self, context: dict[str, Any] | str) -> list[dict[str, Any]]:
        from shopstack.planner.parser import parse_tool_calls

        if not self._available:
            return [{"tool": "respond", "args": {"message": self._error or "Local provider not available"}}]

        if isinstance(context, str):
            # Direct provider.plan() calls with a raw prompt string.
            # Treat the string as the prompt and delegate to complete() + parse.
            prompt = context
            result = self.complete(prompt, max_tokens=64, temperature=0.0)
            text = result.get("text", "")
            if not text:
                return [{"tool": "respond", "args": {"message": ""}}]
            tool_calls = parse_tool_calls(text)
            if (len(tool_calls) == 1
                and tool_calls[0]["tool"] == "respond"
                and "No structured data" in tool_calls[0]["args"].get("message", "")):
                return [{"tool": "respond", "args": {"message": text.strip()}}]
            return tool_calls

        prompt = context.get("prompt") or context.get("question") or ""
        max_tokens = context.get("max_tokens", 512)
        temperature = context.get("temperature", 0.0)

        if not prompt:
            return [{"tool": "respond", "args": {"message": ""}}]

        # Apply chat template for chat-based MLX models (e.g., Qwen3.5).
        # This prevents the model from generating conversation continuations
        # that break JSON parsing.
        system_prompt = context.get("system", "")
        question = context.get("question", "")
        if self._backend == "mlx" and system_prompt and question:
            if self._ensure_model():
                formatted = self._format_chat_prompt(system_prompt, question)
                if formatted is not None:
                    prompt = formatted

        # Reuse complete() for planning; this returns a raw model response.
        result = self.complete(prompt, max_tokens=max_tokens, temperature=temperature)
        text = result.get("text", "")
        if not text:
            return [{"tool": "respond", "args": {"message": ""}}]

        # Try to parse structured tool calls from model output.
        # If no JSON is found, wrap the raw text as a respond message.
        tool_calls = parse_tool_calls(text)
        if (len(tool_calls) == 1
            and tool_calls[0]["tool"] == "respond"
            and "No structured data" in tool_calls[0]["args"].get("message", "")):
            return [{"tool": "respond", "args": {"message": text.strip()}}]
        return tool_calls

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms

    @property
    def last_token_count(self) -> int | None:
        return self._last_token_count

    @property
    def model_id(self) -> str:
        if self._backend == "mlx":
            return self._mlx_model
        if self._backend == "llama.cpp":
            return f"{self._model_repo}/{self._model_file}"
        return ""

    def runtime_report(self) -> dict[str, Any]:
        """Return operator-facing local runtime health without loading a model."""
        return {
            "provider": self.name,
            "available": self._available,
            "backend": self._backend or "unavailable",
            "model_id": self.model_id,
            "model_path": self._model_path or "",
            "model_dir": self._model_dir,
            "allow_download": self._allow_download,
            "auto_unload": self._auto_unload,
            "context_length": self._n_ctx,
            "gpu_layers": self._n_gpu_layers,
            "last_latency_ms": self._last_latency_ms,
            "last_token_count": self._last_token_count,
            "error": self._error or "",
        }
