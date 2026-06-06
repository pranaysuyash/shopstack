from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL_REPO = "unsloth/Llama-3.2-3B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
DEFAULT_MLX_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"


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
        self._available = False
        self._error: str | None = None
        self._llm: Any = None
        self._tokenizer: Any = None
        self._init()

    def _init(self) -> None:
        self._init_mlx()
        if self._available:
            return
        self._init_llamacpp()

    def _init_mlx(self) -> None:
        try:
            import mlx_lm  # noqa: F401
        except ImportError:
            self._error = "mlx-lm not installed. Run: uv pip install mlx-lm"
            return
        try:
            from mlx_lm import load

            model_path = self._mlx_model
            # Try local path first, then HF model ID
            local_path = Path(self._model_dir) / self._mlx_model.split("/")[-1]
            if local_path.is_dir():
                model_path = str(local_path)

            self._llm, self._tokenizer = load(model_path)
            self._backend = "mlx"
            self._available = True
            logger.info("Local provider loaded via MLX: %s", model_path)
        except Exception as e:
            logger.info("MLX init failed (%s), trying llama.cpp fallback", e)

    def _init_llamacpp(self) -> None:
        try:
            import llama_cpp  # noqa: F401
        except ImportError:
            self._error = (
                "No local inference engine available. "
                "Install one: uv pip install mlx-lm  (Apple Silicon) "
                "or uv pip install 'shopstack[local]' (llama-cpp-python)"
            )
            self._available = False
            return
        try:
            import llama_cpp

            model_path = _ensure_gguf_model(self._model_dir, self._model_repo, self._model_file)
            self._llm = llama_cpp.Llama(
                model_path=model_path,
                n_ctx=self._n_ctx,
                n_gpu_layers=self._n_gpu_layers,
                verbose=self._verbose,
            )
            self._backend = "llama.cpp"
            self._available = True
            logger.info(
                "Local provider loaded via llama.cpp: %s/%s (ctx=%d, gpu_layers=%s)",
                self._model_repo, self._model_file, self._n_ctx,
                "all" if self._n_gpu_layers < 0 else self._n_gpu_layers,
            )
        except Exception as e:
            self._error = f"Failed to init llama.cpp provider: {e}"
            self._available = False
            logger.warning("llama.cpp provider init failed", exc_info=True)

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"error": self._error or "Local provider not available", "model": self.name}
        try:
            max_tokens = kwargs.get("max_tokens", 512)
            temperature = kwargs.get("temperature", 0.3)
            stop = kwargs.get("stop", [])

            if self._backend == "mlx":
                from mlx_lm import generate

                messages = [{"role": "user", "content": prompt}]
                text = generate(
                    self._llm,
                    self._tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return {"text": text, "model": self._mlx_model, "usage": {"total_tokens": max_tokens}}
            else:
                response = self._llm.create_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop or None,
                )
                text = response["choices"][0]["message"]["content"]
                return {
                    "text": text,
                    "model": f"{self._model_repo}/{self._model_file}",
                    "usage": {"total_tokens": response.get("usage", {}).get("total_tokens", 0)},
                }
        except Exception as e:
            logger.warning("Local completion failed", exc_info=True)
            return {"error": str(e), "model": self.name}

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._available:
            return [[0.0] * 128 for _ in texts]
        if self._backend == "mlx":
            return [[0.0] * 128 for _ in texts]
        try:
            results = []
            for text in texts:
                embedding = self._llm.create_embedding(input=text)
                results.append(embedding["data"][0]["embedding"])
            return results
        except Exception as e:
            logger.warning("Local embedding failed", exc_info=True)
            return [[0.0] * 128 for _ in texts]

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

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def backend(self) -> str:
        return self._backend
