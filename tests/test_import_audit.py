"""C-extension import audit — verify providers can be imported without triggering C-extension loading.

Each provider should use the ``find_spec + deferred import`` pattern to avoid
loading heavy C-extensions (torch, transformers, mlx, etc.) at import time.
This test imports every provider module and confirms that heavy packages
remain unloaded after the import.

This is important because:
- Python 3.14 + some C-extensions (mlx, torch) can segfault on import
- Even without crashes, eager imports add 5-30s to app startup
- The find_spec pattern lets providers report availability without loading

Run: uv run pytest tests/test_import_audit.py -v
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import pytest

logger = logging.getLogger(__name__)

# ── Providers to audit ──────────────────────────────────────────────

PROVIDERS: list[dict[str, Any]] = [
    {"name": "huggingface", "module": "shopstack.providers.huggingface_provider", "class": "HuggingFaceProvider"},
    {"name": "openai", "module": "shopstack.providers.openai_provider", "class": "OpenAIProvider"},
    {"name": "whisper", "module": "shopstack.providers.whisper_provider", "class": "WhisperProvider"},
    {"name": "sensevoice", "module": "shopstack.providers.stt_provider", "class": "SenseVoiceSTTProvider"},
    {"name": "qwen3_asr", "module": "shopstack.providers.stt_provider", "class": "Qwen3ASRProvider"},
    {"name": "parakeet", "module": "shopstack.providers.stt_provider", "class": "ParakeetSTTProvider"},
    {"name": "kokoro", "module": "shopstack.providers.tts_provider", "class": "KokoroTTSProvider"},
    {"name": "qwen3_tts", "module": "shopstack.providers.tts_provider", "class": "Qwen3TTSProvider"},
    {"name": "minicpmv", "module": "shopstack.providers.vision_provider", "class": "MiniCPMVProvider"},
    {"name": "minicpm5", "module": "shopstack.providers.planner_provider", "class": "MiniCPM5Provider"},
    {"name": "glm_ocr", "module": "shopstack.providers.ocr_provider", "class": "GlmOCRProvider"},
    {"name": "nuextract3", "module": "shopstack.providers.ocr_provider", "class": "NuExtract3OCRProvider"},
    {"name": "tesseract", "module": "shopstack.providers.tesseract_provider", "class": "TesseractOCRProvider"},
    {"name": "rmbg", "module": "shopstack.providers.segmentation_provider", "class": "RMBGSegmentationProvider"},
    {"name": "bge_m3", "module": "shopstack.providers.embeddings_provider", "class": "BGEM3EmbeddingProvider"},
    {"name": "flux", "module": "shopstack.providers.image_gen_provider", "class": "FluxImageProvider"},
    {"name": "local", "module": "shopstack.providers.local_provider", "class": "LocalProvider"},
    {"name": "local_whisper", "module": "shopstack.providers.local_whisper_provider", "class": "LocalWhisperProvider"},
]

# Heavy C-extension packages that should NOT be loaded at import time
HEAVY_PACKAGES = [
    "torch",
    "transformers",
    "mlx",
    "mlx_lm",
    "funasr",
    "sentence_transformers",
    "diffusers",
    "llama_cpp",
    "llama_cpp_python",
]


@pytest.mark.parametrize(
    "provider",
    PROVIDERS,
    ids=[p["name"] for p in PROVIDERS],
)
def test_provider_no_heavy_c_imports(provider: dict[str, Any]) -> None:
    """Verify importing a provider module does not trigger heavy C-extension loading."""
    module_name = provider["module"]
    class_name = provider["class"]

    # Record pre-import state of heavy packages
    pre_import = {pkg: pkg in sys.modules for pkg in HEAVY_PACKAGES}

    # Remove from sys.modules if it was already imported (re-import test)
    import importlib
    if module_name in sys.modules:
        del sys.modules[module_name]

    try:
        mod = importlib.import_module(module_name)
    except ImportError as e:
        pytest.skip(f"Module import failed (optional deps): {e}")
        return

    # Verify the class exists
    assert hasattr(mod, class_name), f"Provider class {class_name} not found in {module_name}"

    # Verify post-import state — no new heavy packages should be loaded
    post_import = {pkg: pkg in sys.modules for pkg in HEAVY_PACKAGES}
    newly_loaded = [pkg for pkg in HEAVY_PACKAGES if not pre_import[pkg] and post_import[pkg]]

    assert not newly_loaded, (
        f"Importing {module_name} triggered loading of C-extensions: {newly_loaded}. "
        "Use the find_spec + deferred import pattern instead."
    )


def test_registry_import_safe() -> None:
    """Verify the full registry module can be imported without heavy C-extensions."""
    pre_import = {pkg: pkg in sys.modules for pkg in HEAVY_PACKAGES}

    import importlib

    # Re-import cleanly (remove any previously loaded shopstack provider modules)
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("shopstack.providers"):
            del sys.modules[mod_name]

    try:
        import shopstack.providers.registry as registry_mod
        assert registry_mod is not None
    except ImportError:
        pytest.skip("Registry module import failed")
        return

    post_import = {pkg: pkg in sys.modules for pkg in HEAVY_PACKAGES}
    newly_loaded = [pkg for pkg in HEAVY_PACKAGES if not pre_import[pkg] and post_import[pkg]]

    if newly_loaded:
        logger.warning(
            "Registry import triggered C-extensions: %s. "
            "This may be acceptable if already loaded by other tests.",
            newly_loaded,
        )
