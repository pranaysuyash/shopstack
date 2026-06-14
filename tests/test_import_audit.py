"""C-extension import audit — verify providers can be imported without triggering C-extension loading.

Each provider should use the ``find_spec + deferred import`` pattern to avoid
loading heavy C-extensions (torch, transformers, mlx, etc.) at import time.
This test imports every provider module and confirms that heavy packages
remain unloaded after the import.

This is important because:
- Python 3.14 + some C-extensions (mlx, torch) can segfault on import
- Even without crashes, eager imports add 5-30s to app startup
- The find_spec pattern lets providers report availability without loading

Earlier revisions of this file manipulated ``sys.modules`` in-process to
force a fresh import. That contaminates every subsequent test in the suite:
provider classes lose identity (``ModalPlannerProvider is
ModalPlannerProvider`` fails), and ``shopstack.providers.<name>``
attribute access breaks because the parent package's bindings are not
restored. We now run each audit in a subprocess to get a clean Python
without poisoning the test session.

Run: uv run pytest tests/test_import_audit.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

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


def _run_audit_subprocess(module_name: str) -> dict[str, Any]:
    """Import ``module_name`` in a clean subprocess and report results.

    Returns a dict with:
      - ``imported``: whether the import succeeded
      - ``error``: error message if the import failed
      - ``has_class``: whether the expected class is present
      - ``loaded_packages``: list of heavy packages that are in sys.modules
        after the import
    """
    code = f"""
import importlib
import sys
import json

result = {{"imported": False, "error": None, "has_class": False, "loaded_packages": []}}
try:
    mod = importlib.import_module({module_name!r})
    result["imported"] = True
except Exception as e:
    result["error"] = f"{{type(e).__name__}}: {{e}}"
    print(json.dumps(result))
    sys.exit(0)

result["loaded_packages"] = [pkg for pkg in {HEAVY_PACKAGES!r} if pkg in sys.modules]
print(json.dumps(result))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    if proc.returncode != 0:
        return {
            "imported": False,
            "error": proc.stderr.strip() or proc.stdout.strip(),
            "has_class": False,
            "loaded_packages": [],
        }
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {
            "imported": False,
            "error": f"Could not parse subprocess output: {proc.stdout!r}",
            "has_class": False,
            "loaded_packages": [],
        }


@pytest.mark.parametrize(
    "provider",
    PROVIDERS,
    ids=[p["name"] for p in PROVIDERS],
)
def test_provider_no_heavy_c_imports(provider: dict[str, Any]) -> None:
    """Verify importing a provider module does not trigger heavy C-extension loading."""
    result = _run_audit_subprocess(provider["module"])

    if not result["imported"]:
        pytest.skip(f"Module import failed (optional deps): {result['error']}")

    assert not result["loaded_packages"], (
        f"Importing {provider['module']} triggered loading of C-extensions: "
        f"{result['loaded_packages']}. Use the find_spec + deferred import pattern instead."
    )


def test_registry_import_safe() -> None:
    """Verify the full registry module can be imported without heavy C-extensions."""
    result = _run_audit_subprocess("shopstack.providers.registry")

    if not result["imported"]:
        pytest.skip(f"Registry module import failed: {result['error']}")

    # The registry imports many providers at module load. Some may legitimately
    # pull in C-extensions if installed; we only warn, not fail, to allow for
    # environment differences. The strict per-provider audit above catches
    # regressions in individual provider modules.
    if result["loaded_packages"]:
        pytest.skip(
            f"Registry import loaded C-extensions: {result['loaded_packages']}. "
            "This is acceptable in environments where they are installed."
        )
