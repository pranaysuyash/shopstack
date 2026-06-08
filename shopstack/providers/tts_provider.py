from __future__ import annotations

import hashlib
import io
import logging
import os
import tempfile
import wave
from typing import Any

from shopstack.providers.interfaces import TTSProvider

logger = logging.getLogger(__name__)

KOKORO_SAMPLE_RATE = 24000
DEFAULT_VOICE = "af_heart"


class KokoroTTSProvider(TTSProvider):
    name = "kokoro"
    model_id = "kokoro-82m"
    parameter_count = 0.082
    license_note = "Apache-2.0"
    runtime_type = "custom"
    supports_off_grid = True
    capabilities: set[str] = {"tts"}

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        lang_code: str = "a",
        cache_dir: str | None = None,
        prefer_gtts_fallback: bool = True,
    ):
        self._voice = voice
        self._lang_code = lang_code
        self._cache_dir = cache_dir or os.path.join(
            tempfile.gettempdir(), "shopstack_tts_cache"
        )
        self._prefer_gtts_fallback = prefer_gtts_fallback
        self._available = False
        self._kokoro_pipeline: Any = None
        self._gtts_available = False
        self._error: str | None = None
        self._init()

    def _init(self) -> None:
        self._init_kokoro()
        if not self._available and self._prefer_gtts_fallback:
            self._init_gtts()

    def _init_kokoro(self) -> None:
        try:
            from kokoro import KPipeline  # noqa: F401
        except ImportError:
            self._error = (
                "kokoro not installed. Run: uv pip install kokoro"
            )
            logger.warning(self._error)
            return
        try:
            from kokoro import KPipeline

            self._kokoro_pipeline = KPipeline(lang_code=self._lang_code)
            self._available = True
            self._error = None
            logger.info(
                "Kokoro TTS provider initialized (lang=%s, voice=%s)",
                self._lang_code,
                self._voice,
            )
        except Exception as e:
            self._error = f"Failed to init kokoro pipeline: {e}"
            logger.warning(self._error, exc_info=True)

    def _init_gtts(self) -> None:
        try:
            import gtts  # noqa: F401
            self._gtts_available = True
            self._error = None
            logger.info("gTTS fallback available for KokoroTTSProvider")
        except ImportError:
            self._gtts_available = False
            self._error = "kokoro not installed and gTTS fallback not available"
            logger.warning(self._error)

    def _gtts_synthesize(self, text: str, language: str) -> bytes:
        try:
            from gtts import gTTS

            fp = io.BytesIO()
            tts = gTTS(text=text, lang=language, slow=False)
            tts.write_to_fp(fp)
            fp.seek(0)
            return fp.read()
        except Exception as e:
            logger.warning("gTTS synthesis failed: %s", e)
            return b""

    def _cache_path(self, text: str, language: str) -> str:
        key = hashlib.md5(
            f"{text}:{language}:{self._voice}".encode()
        ).hexdigest()
        os.makedirs(self._cache_dir, exist_ok=True)
        return os.path.join(self._cache_dir, f"{key}.wav")

    def synthesize(self, text: str, language: str = "en") -> bytes | str:
        if not text:
            return b""

        if not self._available:
            if self._gtts_available:
                return self._gtts_synthesize(text, language)
            return b""

        cache_path = self._cache_path(text, language)
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return f.read()
            except OSError:
                pass

        try:
            import numpy as np

            gen = self._kokoro_pipeline(text, voice=self._voice)
            chunks: list[np.ndarray] = []
            for result in gen:
                if isinstance(result, tuple):
                    _, audio_array, _ = result
                else:
                    audio_array = result
                if isinstance(audio_array, np.ndarray):
                    chunks.append(audio_array)
                elif hasattr(audio_array, "numpy"):
                    chunks.append(audio_array.numpy())
                else:
                    chunks.append(
                        np.array(audio_array, dtype=np.float32)
                    )

            if not chunks:
                logger.warning("Kokoro produced no audio chunks for: %s", text[:60])
                return b""

            audio = np.concatenate(chunks)

            max_val = float(np.max(np.abs(audio)))
            if max_val > 1.0:
                audio = audio / max_val

            audio_int16 = (audio * 32767).astype(np.int16)

            with wave.open(cache_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(KOKORO_SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())

            with open(cache_path, "rb") as f:
                return f.read()

        except Exception:
            logger.warning("Kokoro TTS synthesis failed", exc_info=True)
            if self._gtts_available:
                return self._gtts_synthesize(text, language)
            return b""

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return self._available or self._gtts_available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error


class Qwen3TTSProvider(TTSProvider):
    """TTS provider using Qwen3-TTS-0.6B via transformers.

    Provides text-to-speech synthesis. Falls back gracefully when deps are missing.
    """

    name = "qwen3_tts"
    model_id = "qwen3-tts-0.6b"
    parameter_count = 0.6
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"tts"}

    SAMPLE_RATE = 24000

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-TTS-0.6B",
        device: str = "auto",
        cache_dir: str | None = None,
    ):
        self._model_name = model_name
        self._device = device
        self._cache_dir = cache_dir or os.path.join(
            tempfile.gettempdir(), "shopstack_qwen3tts_cache"
        )
        self._model = None
        self._processor = None
        self._available = False
        self._error: str | None = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModel,
                AutoTokenizer,
            )
            self._available = True
            self._error = None
            logger.info("Qwen3-TTS provider initialised (model=%s)", self._model_name)
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            self._available = False

    def load(self) -> None:
        if self._model is not None:
            return
        self._load_model()

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            logger.info("Loading Qwen3-TTS model %s ...", self._model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_name, trust_remote_code=True
            )
            self._model = AutoModel.from_pretrained(
                self._model_name,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16,
            )
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("Qwen3-TTS model loaded")
            return True
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            return False
        except Exception as e:
            self._error = f"Failed to load Qwen3-TTS model: {e}"
            logger.warning("Qwen3-TTS model load failed", exc_info=True)
            return False

    def _cache_path(self, text: str, language: str) -> str:
        key = hashlib.md5(
            f"{text}:{language}:{self._model_name}".encode()
        ).hexdigest()
        os.makedirs(self._cache_dir, exist_ok=True)
        return os.path.join(self._cache_dir, f"{key}.wav")

    def synthesize(self, text: str, language: str = "en") -> bytes | str:
        if not text:
            return b""

        if not self._available:
            return b""

        cache_path = self._cache_path(text, language)
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return f.read()
            except OSError:
                pass

        if self._model is None and not self._load_model():
            return b""

        if self._tokenizer is None:
            return b""

        try:
            import torch

            inputs = self._tokenizer(
                text, return_tensors="pt", padding=True, truncation=True
            )
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                inputs = {k: v.to("mps") for k, v in inputs.items()}

            with torch.no_grad():
                audio_values = self._model.generate(**inputs, max_length=4096)

            audio_np = audio_values.cpu().numpy().flatten()

            import numpy as np
            max_val = float(np.max(np.abs(audio_np)))
            if max_val > 1.0:
                audio_np = audio_np / max_val

            audio_int16 = (audio_np * 32767).astype(np.int16)

            with wave.open(cache_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())

            with open(cache_path, "rb") as f:
                return f.read()

        except Exception:
            logger.warning("Qwen3-TTS synthesis failed", exc_info=True)
            return b""

    def healthcheck(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error
