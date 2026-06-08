from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class SenseVoiceSTTProvider:
    name = "sensevoice"
    capabilities: set[str] = {"stt"}

    def __init__(
        self,
        model_id: str = "iic/SenseVoiceSmall",
        fallback_whisper: bool = True,
    ):
        self._model_id = model_id
        self._model: Any = None
        self._available = False
        self._error: str | None = None
        self._fallback_whisper = fallback_whisper
        self._whisper_provider: Any = None
        self._init()

    def _init(self) -> None:
        try:
            from funasr import AutoModel  # noqa: F401
            self._available = True
            self._error = None
            logger.info("SenseVoice STT provider initialised (model=%s)", self._model_id)
        except ImportError:
            self._error = (
                "funasr not installed. Run: uv pip install funasr"
            )
            self._available = False

        if self._fallback_whisper:
            try:
                from shopstack.providers.local_whisper_provider import (
                    LocalWhisperProvider,
                )
                self._whisper_provider = LocalWhisperProvider()
                if self._whisper_provider.available:
                    logger.info(
                        "SenseVoice provider has Whisper fallback (%s)",
                        self._whisper_provider.backend,
                    )
            except ImportError:
                pass

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            from funasr import AutoModel
            logger.info("Loading SenseVoice model %s ...", self._model_id)
            self._model = AutoModel(model=self._model_id)
            logger.info("SenseVoice model loaded")
            return True
        except Exception as e:
            self._error = f"Failed to load SenseVoice model: {e}"
            logger.warning("SenseVoice model load failed", exc_info=True)
            return False

    def transcribe(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        if not os.path.isfile(audio_path):
            return {"text": "", "error": f"Audio file not found: {audio_path}"}

        if self._available and self._load_model():
            try:
                t0 = time.monotonic()
                result = self._model.generate(input=audio_path, language=language)
                elapsed = time.monotonic() - t0

                if isinstance(result, list) and len(result) > 0:
                    text = result[0].get("text", "")
                elif isinstance(result, dict):
                    text = result.get("text", "")
                else:
                    text = str(result) if result else ""

                return {
                    "text": text.strip(),
                    "language": language,
                    "confidence": None,
                    "model": self._model_id,
                    "backend": "sensevoice",
                    "latency_ms": round(elapsed * 1000, 1),
                }
            except Exception:
                logger.warning("SenseVoice transcription failed, trying fallback", exc_info=True)

        if self._whisper_provider and self._whisper_provider.available:
            lang = language if language != "auto" else "en"
            return self._whisper_provider.transcribe(audio_path, lang)

        return {"text": "", "error": self._error or "No STT backend available"}

    @property
    def available(self) -> bool:
        return self._available or (
            self._whisper_provider is not None and self._whisper_provider.available
        )

    @property
    def error(self) -> str | None:
        return self._error


class Qwen3ASRProvider:
    name = "qwen3_asr"
    capabilities: set[str] = {"stt"}

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3-ASR-1.7B",
        fallback_whisper: bool = True,
    ):
        self._model_id = model_id
        self._model: Any = None
        self._processor: Any = None
        self._available = False
        self._error: str | None = None
        self._fallback_whisper = fallback_whisper
        self._whisper_provider: Any = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForCTC,
                AutoProcessor,
            )
            self._available = True
            self._error = None
            logger.info("Qwen3-ASR provider initialised (model=%s)", self._model_id)
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            self._available = False

        if self._fallback_whisper:
            try:
                from shopstack.providers.local_whisper_provider import (
                    LocalWhisperProvider,
                )
                self._whisper_provider = LocalWhisperProvider()
                if self._whisper_provider.available:
                    logger.info(
                        "Qwen3-ASR provider has Whisper fallback (%s)",
                        self._whisper_provider.backend,
                    )
            except ImportError:
                pass

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModelForCTC, AutoProcessor

            logger.info("Loading Qwen3-ASR model %s ...", self._model_id)
            self._processor = AutoProcessor.from_pretrained(self._model_id)
            self._model = AutoModelForCTC.from_pretrained(self._model_id)
            self._model.eval()
            if torch.cuda.is_available():
                self._model = self._model.to("cuda")
            logger.info("Qwen3-ASR model loaded")
            return True
        except Exception as e:
            self._error = f"Failed to load Qwen3-ASR model: {e}"
            logger.warning("Qwen3-ASR model load failed", exc_info=True)
            return False

    def transcribe(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        if not os.path.isfile(audio_path):
            return {"text": "", "error": f"Audio file not found: {audio_path}"}

        if self._available and self._load_model():
            try:
                import torch
                import librosa

                t0 = time.monotonic()

                audio, sr = librosa.load(audio_path, sr=16000)
                inputs = self._processor(
                    audio, sampling_rate=16000, return_tensors="pt"
                )

                if torch.cuda.is_available():
                    inputs = {k: v.to("cuda") for k, v in inputs.items()}

                with torch.no_grad():
                    logits = self._model(**inputs).logits

                predicted_ids = torch.argmax(logits, dim=-1)
                text = self._processor.batch_decode(predicted_ids)[0]

                elapsed = time.monotonic() - t0

                return {
                    "text": text.strip(),
                    "language": language,
                    "confidence": None,
                    "model": self._model_id,
                    "backend": "qwen3-asr",
                    "latency_ms": round(elapsed * 1000, 1),
                }
            except Exception:
                logger.warning(
                    "Qwen3-ASR transcription failed, trying fallback", exc_info=True
                )

        if self._whisper_provider and self._whisper_provider.available:
            return self._whisper_provider.transcribe(audio_path, language)

        return {"text": "", "error": self._error or "No STT backend available"}

    @property
    def available(self) -> bool:
        return self._available or (
            self._whisper_provider is not None and self._whisper_provider.available
        )

    @property
    def error(self) -> str | None:
        return self._error


class ParakeetSTTProvider:
    """STT provider using NVIDIA Parakeet-CTC-0.6B via transformers.

    Lightweight streaming ASR model. Falls back gracefully when deps are missing.
    """

    name = "parakeet"
    capabilities: set[str] = {"stt"}

    def __init__(
        self,
        model_id: str = "nvidia/parakeet-ctc-0.6b",
        fallback_whisper: bool = True,
    ):
        self._model_id = model_id
        self._model: Any = None
        self._processor: Any = None
        self._available = False
        self._error: str | None = None
        self._fallback_whisper = fallback_whisper
        self._whisper_provider: Any = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForCTC,
                AutoProcessor,
            )
            self._available = True
            self._error = None
            logger.info("Parakeet STT provider initialised (model=%s)", self._model_id)
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            self._available = False

        if self._fallback_whisper:
            try:
                from shopstack.providers.local_whisper_provider import (
                    LocalWhisperProvider,
                )
                self._whisper_provider = LocalWhisperProvider()
                if self._whisper_provider.available:
                    logger.info(
                        "Parakeet provider has Whisper fallback (%s)",
                        self._whisper_provider.backend,
                    )
            except ImportError:
                pass

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModelForCTC, AutoProcessor

            logger.info("Loading Parakeet model %s ...", self._model_id)
            self._processor = AutoProcessor.from_pretrained(self._model_id)
            self._model = AutoModelForCTC.from_pretrained(
                self._model_id, torch_dtype=torch.float32
            )
            self._model.eval()
            if torch.cuda.is_available():
                self._model = self._model.to("cuda")
            logger.info("Parakeet model loaded")
            return True
        except Exception as e:
            self._error = f"Failed to load Parakeet model: {e}"
            logger.warning("Parakeet model load failed", exc_info=True)
            return False

    def transcribe(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        if not os.path.isfile(audio_path):
            return {"text": "", "error": f"Audio file not found: {audio_path}"}

        if self._available and self._load_model():
            try:
                import torch
                import librosa

                t0 = time.monotonic()

                audio, sr = librosa.load(audio_path, sr=16000)
                inputs = self._processor(
                    audio, sampling_rate=16000, return_tensors="pt", padding=True
                )

                if torch.cuda.is_available():
                    inputs = {k: v.to("cuda") for k, v in inputs.items()}

                with torch.no_grad():
                    logits = self._model(**inputs).logits

                predicted_ids = torch.argmax(logits, dim=-1)
                text = self._processor.batch_decode(predicted_ids)[0]

                elapsed = time.monotonic() - t0
                self._last_latency_ms = round(elapsed * 1000, 1)

                return {
                    "text": text.strip(),
                    "language": language,
                    "confidence": None,
                    "model": self._model_id,
                    "backend": "parakeet",
                    "latency_ms": self._last_latency_ms,
                }
            except Exception:
                logger.warning(
                    "Parakeet transcription failed, trying fallback", exc_info=True
                )

        if self._whisper_provider and self._whisper_provider.available:
            return self._whisper_provider.transcribe(audio_path, language)

        return {"text": "", "error": self._error or "No STT backend available"}

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available or (
            self._whisper_provider is not None and self._whisper_provider.available
        )

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms
