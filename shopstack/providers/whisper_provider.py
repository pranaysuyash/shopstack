from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _check_deps() -> tuple[bool, str]:
    try:
        import openai  # noqa: F401
        return True, ""
    except ImportError:
        return False, "openai package not installed. Run: uv pip install openai"


class WhisperProvider:
    name = "whisper"
    capabilities: set[str] = {"stt"}

    def __init__(self, api_key: str = "", model: str = "whisper-1"):
        self._api_key = api_key
        self._model = model
        self._available = False
        self._error: str | None = None
        self._local_model_loaded = False
        self._init()

    def _init(self) -> None:
        deps_ok, deps_error = _check_deps()
        if not deps_ok:
            self._error = deps_error
            self._available = False
            return
        key = self._api_key or self._env_key()
        if not key:
            self._error = "OpenAI API key not found for Whisper STT. Set SHOPSTACK_OPENAI_API_KEY or OPENAI_API_KEY."
            self._available = False
            return
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=key)
            self._available = True
        except Exception as e:
            self._error = f"Failed to init Whisper client: {e}"
            self._available = False

    @staticmethod
    def _env_key() -> str:
        import os
        return os.getenv("SHOPSTACK_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")

    def transcribe(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        if not self._available:
            return {"text": "", "error": self._error or "Whisper not available"}
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self._client.audio.transcriptions.create(
                    model=self._model,
                    file=audio_file,
                    language=language,
                    response_format="json",
                )
            return {
                "text": transcript.text,
                "language": language,
                "confidence": None,
                "model": self._model,
            }
        except Exception as e:
            logger.warning("Whisper transcription failed", exc_info=True)
            return {"text": "", "error": str(e), "model": self._model}

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error
