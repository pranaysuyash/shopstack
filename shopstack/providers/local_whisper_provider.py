from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MLX_MODEL = "mlx-community/whisper-tiny-mlx"
DEFAULT_WHISPER_SIZE = "tiny"


class LocalWhisperProvider:
    name = "local_whisper"
    capabilities: set[str] = {"stt"}

    def __init__(
        self,
        model_dir: str = "",
        model_size: str = DEFAULT_WHISPER_SIZE,
        mlx_model: str = DEFAULT_MLX_MODEL,
        device: str = "auto",
        compute_type: str = "default",
        auto_unload: bool = True,
    ):
        self._model_dir = model_dir or str(
            Path(__file__).resolve().parent.parent.parent / "data" / "models" / "whisper"
        )
        self._model_size = model_size
        self._mlx_model = mlx_model
        self._device = device
        self._compute_type = compute_type
        self._available = False
        self._error: str | None = None
        self._backend: str = ""
        self._model: Any = None
        self._auto_unload = auto_unload
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        self._init_mlx()
        if self._available:
            return
        self._init_faster_whisper()

    def _init_mlx(self) -> None:
        try:
            import mlx_whisper  # noqa: F401
        except ImportError:
            self._error = "mlx-whisper not installed. Run: uv pip install mlx-whisper"
            return
        self._backend = "mlx"
        self._available = True
        self._error = None
        logger.info("Local Whisper provider loaded via mlx-whisper (size=%s)", self._model_size)

    def _init_faster_whisper(self) -> None:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError:
            self._error = (
                "No local Whisper engine available. "
                "Install one: uv pip install mlx-whisper (Apple Silicon) "
                "or uv pip install faster-whisper (cross-platform)"
            )
            self._available = False
            return
        try:
            from faster_whisper import WhisperModel  # noqa: F401

            device = self._device
            if device == "auto":
                import platform
                device = "cpu" if platform.machine() == "arm64" else "cpu"

            compute = self._compute_type
            if compute == "default":
                compute = "int8" if device == "cpu" else "float16"

            local_dir = os.path.join(self._model_dir, self._model_size)
            self._backend = "faster-whisper"
            self._model_path = local_dir
            self._compute_type = compute
            self._device = device
            self._available = True
            self._error = None
            logger.info(
                "Local Whisper provider loaded via faster-whisper (size=%s, device=%s, compute=%s)",
                self._model_size, device, compute,
            )
        except Exception as e:
            self._error = f"Failed to init faster-whisper: {e}"
            self._available = False
            logger.warning("faster-whisper provider init failed", exc_info=True)

    def _init_faster_model(self) -> bool:
        if self._model is not None:
            return True
        if self._backend != "faster-whisper":
            return False
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._model_path,
            )
            return True
        except Exception as e:
            self._error = f"Failed to initialize faster-whisper runtime: {e}"
            logger.warning("faster-whisper runtime init failed", exc_info=True)
            return False

    def _maybe_unload_model(self) -> None:
        if not self._auto_unload:
            return
        self._model = None

    def transcribe(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        if not self._available:
            return {"text": "", "error": self._error or "Local Whisper not available"}

        if not os.path.isfile(audio_path):
            return {"text": "", "error": f"Audio file not found: {audio_path}"}

        try:
            if self._backend == "faster-whisper" and self._model is None:
                if not self._init_faster_model():
                    return {"text": "", "error": self._error or "Local Whisper runtime not available"}
            t0 = time.monotonic()

            if self._backend == "mlx":
                import mlx_whisper

                result: dict[str, Any] = mlx_whisper.transcribe(
                    audio_path,
                    path_or_hf_repo=self._mlx_model,
                    language=language,
                )
                text = result.get("text", "")
                segments = result.get("segments", [])
                avg_logprob = None
                if segments:
                    probs = [s.get("avg_logprob", 0) for s in segments if s.get("avg_logprob") is not None]
                    avg_logprob = sum(probs) / len(probs) if probs else None

                elapsed = time.monotonic() - t0
                self._last_latency_ms = round(elapsed * 1000, 1)

                return {
                    "text": text.strip() if isinstance(text, str) else str(text).strip(),
                    "language": language,
                    "confidence": round(avg_logprob, 4) if avg_logprob is not None else None,
                    "model": self._mlx_model,
                    "backend": "mlx",
                    "segments": len(segments),
                    "latency_ms": self._last_latency_ms,
                }
            else:
                assert self._model is not None
                segments, info = self._model.transcribe(
                    audio_path,
                    language=language,
                    beam_size=5,
                    vad_filter=True,
                )

                text_parts = []
                segment_list = []
                for segment in segments:
                    text_parts.append(segment.text)
                    segment_list.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text,
                        "confidence": segment.avg_logprob if hasattr(segment, "avg_logprob") else None,
                    })

                elapsed = time.monotonic() - t0
                self._last_latency_ms = round(elapsed * 1000, 1)

                return {
                    "text": " ".join(text_parts).strip(),
                    "language": info.language if info else language,
                    "confidence": round(info.language_probability, 4) if info else None,
                    "model": f"whisper-{self._model_size}",
                    "backend": "faster-whisper",
                    "segments": len(segment_list),
                    "latency_ms": self._last_latency_ms,
                }
        except Exception as e:
            logger.warning("Local Whisper transcription failed", exc_info=True)
            return {"text": "", "error": str(e), "model": self.name}
        finally:
            self._maybe_unload_model()

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
