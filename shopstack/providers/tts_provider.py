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
    """TTS provider using Qwen3-TTS-0.6B via the official qwen-tts SDK.

    Qwen3-TTS uses a discrete multi-codebook language model architecture
    for end-to-end speech synthesis. It uses a 12Hz acoustic tokenizer
    and does **not** require a separate neural vocoder.

    The correct API is the ``qwen_tts`` SDK (``Qwen3TTSModel``), not
    standard ``transformers`` ``model.generate()`` which would produce
    text tokens, not audio.

    Primary path: ``qwen_tts.Qwen3TTSModel.from_pretrained()`` +
    ``model.generate_custom_voice()`` returning ``(wavs, sr)``.

    Fallback: Uses gTTS when qwen_tts SDK is unavailable.
    """

    name = "qwen3_tts"
    model_id = "qwen3-tts-0.6b"
    parameter_count = 0.6
    license_note = "Apache-2.0"
    runtime_type = "custom"
    supports_off_grid = True
    capabilities: set[str] = {"tts"}

    SAMPLE_RATE = 24000
    VOICES = ["Ryan", "Alex", "Emma", "Bella", "Ava", "Luke"]
    DEFAULT_VOICE = "Ryan"

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        device: str = "auto",
        cache_dir: str | None = None,
        voice: str = DEFAULT_VOICE,
        prefer_gtts_fallback: bool = True,
    ):
        self._model_name = model_name
        self._device = device
        self._cache_dir = cache_dir or os.path.join(
            tempfile.gettempdir(), "shopstack_qwen3tts_cache"
        )
        self._voice = voice if voice in self.VOICES else self.DEFAULT_VOICE
        self._prefer_gtts_fallback = prefer_gtts_fallback
        self._model: Any = None
        self._available = False
        self._gtts_available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        self._init_qwen_sdk()
        if not self._available and self._prefer_gtts_fallback:
            self._init_gtts()

    def _init_qwen_sdk(self) -> None:
        """Try loading via the official qwen-tts SDK."""
        try:
            from qwen_tts import Qwen3TTSModel  # noqa: F401
            self._available = True
            self._error = None
            logger.info(
                "Qwen3-TTS provider initialised (model=%s, voice=%s)",
                self._model_name, self._voice,
            )
        except ImportError:
            self._error = (
                "qwen-tts SDK not installed. Run: uv pip install qwen-tts"
            )
            logger.warning(self._error)

    def _init_gtts(self) -> None:
        try:
            import gtts  # noqa: F401
            self._gtts_available = True
            self._error = None
            logger.info("gTTS fallback available for Qwen3TTSProvider")
        except ImportError:
            self._gtts_available = False
            self._error = (
                "qwen-tts not installed and gTTS fallback not available. "
                "Run: uv pip install qwen-tts"
            )
            logger.warning(self._error)

    def _gtts_synthesize(self, text: str, language: str) -> bytes:
        try:
            from gtts import gTTS
            import io

            fp = io.BytesIO()
            tts = gTTS(text=text, lang=language, slow=False)
            tts.write_to_fp(fp)
            fp.seek(0)
            return fp.read()
        except Exception as e:
            logger.warning("gTTS synthesis failed: %s", e)
            return b""

    def _synthesize_qwen_sdk(self, text: str, language: str) -> bytes:
        """Synthesize speech using the qwen-tts SDK."""
        import io

        from qwen_tts import Qwen3TTSModel

        # Map language code to full language name
        lang_map = {
            "en": "English",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "fr": "French",
            "de": "German",
            "es": "Spanish",
            "pt": "Portuguese",
            "it": "Italian",
            "ru": "Russian",
            "ar": "Arabic",
            "hi": "Hindi",
        }
        full_lang = lang_map.get(language, "English")

        # Lazy-load the model on first use
        if self._model is None:
            import torch
            logger.info("Loading Qwen3-TTS model %s ...", self._model_name)
            self._model = Qwen3TTSModel.from_pretrained(
                self._model_name,
                device_map=self._device if self._device != "auto" else None,
                dtype=torch.bfloat16,
            )
            logger.info("Qwen3-TTS model loaded")

        # Generate speech — returns (list_of_wavs, sample_rate)
        wavs, sr = self._model.generate_custom_voice(
            text=text,
            language=full_lang,
            speaker=self._voice,
        )

        if not wavs:
            logger.warning("Qwen3-TTS produced no audio for: %s", text[:60])
            return b""

        import numpy as np

        audio = wavs[0] if isinstance(wavs, list) else wavs
        if isinstance(audio, np.ndarray):
            audio_np = audio
        elif hasattr(audio, "numpy"):
            audio_np = audio.numpy()
        else:
            audio_np = np.array(audio, dtype=np.float32)

        # Normalize
        max_val = float(np.max(np.abs(audio_np)))
        if max_val > 1.0:
            audio_np = audio_np / max_val

        sample_rate = sr or self.SAMPLE_RATE

        # Convert to 16-bit PCM WAV in memory
        try:
            import soundfile as sf
            buf = io.BytesIO()
            sf.write(buf, audio_np, sample_rate, format="wav")
            buf.seek(0)
            return buf.read()
        except ImportError:
            # soundfile not installed — write raw PCM via wave module
            import wave
            max_int16 = np.iinfo(np.int16).max
            audio_int16 = (audio_np * max_int16).astype(np.int16)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_int16.tobytes())
            buf.seek(0)
            return buf.read()

    def load(self) -> None:
        pass

    def _cache_path(self, text: str, language: str) -> str:
        key = hashlib.md5(
            f"{text}:{language}:{self._voice}:{self._model_name}".encode()
        ).hexdigest()
        os.makedirs(self._cache_dir, exist_ok=True)
        return os.path.join(self._cache_dir, f"{key}.wav")

    def synthesize(self, text: str, language: str = "en") -> bytes | str:
        if not text:
            return b""

        cache_path = self._cache_path(text, language)
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return f.read()
            except OSError:
                pass

        # Primary path: qwen-tts SDK
        if self._available:
            try:
                audio_bytes = self._synthesize_qwen_sdk(text, language)
                if audio_bytes:
                    # Cache the result
                    try:
                        with open(cache_path, "wb") as f:
                            f.write(audio_bytes)
                    except OSError:
                        pass
                    return audio_bytes
            except Exception:
                logger.warning(
                    "Qwen3-TTS SDK synthesis failed, trying fallback", exc_info=True
                )

        # Fallback: gTTS
        if self._gtts_available:
            audio_bytes = self._gtts_synthesize(text, language)
            if audio_bytes:
                try:
                    with open(cache_path, "wb") as f:
                        f.write(audio_bytes)
                except OSError:
                    pass
                return audio_bytes

        return b""

    def healthcheck(self) -> bool:
        return self._available or self._gtts_available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms
