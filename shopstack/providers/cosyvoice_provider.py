"""CosyVoice2 TTS provider using the FunAudioLLM/CosyVoice inference framework.

CosyVoice2-0.5B is a higher-quality TTS model with Hindi support, using
a generative speech transformer architecture. Unlike Kokoro (82M params),
CosyVoice2 (500M params) produces richer prosody and supports zero-shot
voice cloning and cross-lingual synthesis.

Usage requires:
  1. CosyVoice repo cloned and pip-installed::
       git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
       cd CosyVoice && pip install -e .

  2. Model weights downloaded::
       huggingface-cli download FunAudioLLM/CosyVoice2-0.5B --local-dir pretrained_models/CosyVoice2-0.5B

The provider falls back gracefully when the cosyvoice package is not
available or model weights are missing.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import tempfile
from typing import Any

from shopstack.providers.interfaces import TTSProvider

logger = logging.getLogger(__name__)

# ── CosyVoice default model path (relative to current working dir) ─────
DEFAULT_MODEL_DIR = "pretrained_models/CosyVoice2-0.5B"


class CosyVoiceTTSProvider(TTSProvider):
    """Text-to-speech provider using CosyVoice2-0.5B.

    Uses the ``cosyvoice.cli.cosyvoice.AutoModel`` API for inference.
    Supports zero-shot voice cloning, cross-lingual synthesis, and
    instruction-based speech generation.

    Primary path: ``AutoModel(model_dir).inference_zero_shot(text, prompt_text, prompt_wav)``.

    Fallback: Uses gTTS when CosyVoice deps are unavailable.
    """

    name = "cosyvoice"
    model_id = "cosyvoice2-0.5b"
    parameter_count = 0.5
    license_note = "Apache-2.0"
    runtime_type = "custom"
    supports_off_grid = True
    capabilities: set[str] = {"tts"}

    SAMPLE_RATE = 22050

    def __init__(
        self,
        model_dir: str = DEFAULT_MODEL_DIR,
        cache_dir: str | None = None,
        prefer_gtts_fallback: bool = True,
    ):
        self._model_dir = model_dir
        self._cache_dir = cache_dir or os.path.join(
            tempfile.gettempdir(), "shopstack_cosyvoice_cache"
        )
        self._prefer_gtts_fallback = prefer_gtts_fallback
        self._model: Any = None
        self._available = False
        self._gtts_available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    # ── Initialisation ────────────────────────────────────────────────

    def _init(self) -> None:
        self._init_cosyvoice()
        if not self._available and self._prefer_gtts_fallback:
            self._init_gtts()

    def _init_cosyvoice(self) -> None:
        """Check if the cosyvoice package and model dir are available."""
        try:
            from cosyvoice.cli.cosyvoice import AutoModel  # noqa: F401
        except ImportError:
            self._error = (
                "CosyVoice not installed. Clone and install: "
                "git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git "
                "&& cd CosyVoice && pip install -e ."
            )
            logger.warning(self._error)
            return

        # Check if the model directory exists
        model_path = os.path.expanduser(self._model_dir)
        if not os.path.isdir(model_path):
            # Also try relative to HF cache
            hf_home = os.environ.get(
                "HF_HOME", os.path.expanduser("~/.cache/huggingface")
            )
            hf_model_path = os.path.join(
                hf_home, "hub", "models--FunAudioLLM--CosyVoice2-0.5B", "snapshots"
            )
            if not os.path.isdir(hf_model_path):
                self._error = (
                    f"CosyVoice2-0.5B model not found at {model_path} or {hf_model_path}. "
                    "Download: huggingface-cli download FunAudioLLM/CosyVoice2-0.5B "
                    "--local-dir pretrained_models/CosyVoice2-0.5B"
                )
                logger.warning(self._error)
                return
            # Use the snapshots subdir
            snapshots = sorted(os.listdir(hf_model_path))
            model_path = os.path.join(hf_model_path, snapshots[-1]) if snapshots else hf_model_path

        self._model_path = model_path
        self._available = True
        self._error = None
        logger.info(
            "CosyVoice TTS provider initialised (model_dir=%s)", self._model_path
        )

    def _init_gtts(self) -> None:
        try:
            import gtts  # noqa: F401
            self._gtts_available = True
            self._error = None
            logger.info("gTTS fallback available for CosyVoiceTTSProvider")
        except ImportError:
            self._gtts_available = False
            self._error = (
                "CosyVoice not available and gTTS fallback not installed. "
                "Run: uv pip install gtts"
            )
            logger.warning(self._error)

    # ── Synthesis ─────────────────────────────────────────────────────

    def _synthesize_cosyvoice(self, text: str, language: str) -> bytes:
        """Synthesize speech using CosyVoice AutoModel.

        Uses ``inference_zero_shot`` with a built-in neutral prompt voice
        when no reference audio is configured, or ``inference_instruct``
        for direct text-to-speech with language instruction.
        """
        import time

        import torch

        from cosyvoice.cli.cosyvoice import AutoModel

        # Lazy-load the model on first use
        if self._model is None:
            logger.info("Loading CosyVoice2 model from %s ...", self._model_path)
            t0 = time.monotonic()
            self._model = AutoModel(model_dir=self._model_path)
            elapsed = time.monotonic() - t0
            logger.info("CosyVoice2 model loaded in %.1fs", elapsed)

        # Map language code to instruct prompt
        lang_prompt = _LANGUAGE_INSTRUCT.get(language, _LANGUAGE_INSTRUCT.get("en", ""))

        # CosyVoice supports multiple inference modes:
        # 1. inference_instruct(text, spk_id, instruct) — direct TTS with instruction
        # 2. inference_zero_shot(text, prompt_text, prompt_wav) — voice cloning
        # 3. inference_cross_lingual(text, prompt_wav) — cross-lingual

        # Use inference_instruct for direct TTS (no reference audio needed)
        # The model provides built-in speakers for zero-shot mode
        chunks: list[torch.Tensor] = []
        for result in self._model.inference_instruct(
            text,
            spk_id="female-cs",  # built-in speaker
            instruct=f"{lang_prompt} {text}" if lang_prompt else text,
        ):
            speech = result.get("tts_speech")
            if speech is not None:
                chunks.append(speech)

        if not chunks:
            logger.warning("CosyVoice produced no audio chunks for: %s", text[:60])
            return b""

        # Concatenate all audio chunks
        audio = torch.cat(chunks, dim=-1)

        # Convert to numpy for WAV encoding
        import numpy as np

        audio_np = audio.cpu().numpy().flatten()

        # Normalize
        max_val = float(np.max(np.abs(audio_np)))
        if max_val > 1.0 and max_val > 0:
            audio_np = audio_np / max_val

        # Convert to 16-bit PCM WAV
        audio_int16 = (audio_np * 32767).astype(np.int16)

        buf = io.BytesIO()
        import wave
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())
        buf.seek(0)
        return buf.read()

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
            f"{text}:{language}:cosyvoice2".encode()
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

        # Primary path: CosyVoice SDK
        if self._available:
            try:
                audio_bytes = self._synthesize_cosyvoice(text, language)
                if audio_bytes:
                    try:
                        with open(cache_path, "wb") as f:
                            f.write(audio_bytes)
                    except OSError:
                        pass
                    return audio_bytes
            except Exception:
                logger.warning(
                    "CosyVoice synthesis failed, trying fallback", exc_info=True
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

    # ── Provider interface ────────────────────────────────────────────

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

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms


# Language instruction prompts for CosyVoice instruct mode
_LANGUAGE_INSTRUCT: dict[str, str] = {
    "en": "Speak in English",
    "hi": "हिंदी में बोलें",
    "ta": "தமிழில் பேசவும்",
    "te": "తెలుగులో మాట్లాడండి",
    "bn": "বাংলায় কথা বলুন",
    "gu": "ગુજરાતીમાં બોલો",
    "mr": "मराठीत बोला",
    "kn": "ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಿ",
    "ml": "മലയാളത്തിൽ സംസാരിക്കുക",
    "pa": "ਪੰਜਾਬੀ ਵਿੱਚ ਬੋਲੋ",
    "or": "ଓଡ଼ିଆରେ କୁହନ୍ତୁ",
    "ur": "اردو میں بولیں",
    "zh": "用中文说话",
    "ja": "日本語で話してください",
    "ko": "한국어로 말하세요",
    "fr": "Parlez en français",
    "de": "Sprechen Sie auf Deutsch",
    "es": "Hable en español",
    "ru": "Говорите по-русски",
    "ar": "تحدث بالعربية",
    "pt": "Fale em português",
}
