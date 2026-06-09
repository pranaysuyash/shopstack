from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RuntimeType = Literal["transformers", "llama.cpp", "gguf", "onnx", "diffusers", "custom", "mock", "mlx"]
BadgeRelevance = Literal["llama_champion", "well_tuned", "off_the_grid", "none"]
ModelStatus = Literal["candidate", "active", "deprecated", "rejected"]
MAX_ACTIVE_MODEL_PARAMS_B = 32.0


@dataclass
class ModelEntry:
    provider_group: str
    model_id: str
    hf_model: str
    params_b: float
    license_note: str
    runtime: RuntimeType
    status: ModelStatus
    badge_relevance: BadgeRelevance = "none"
    python_requires: str = ">=3.10"
    notes: str = ""


MODEL_REGISTRY: list[ModelEntry] = [
    # STT
    ModelEntry(
        provider_group="stt",
        model_id="qwen3-asr-1.7b",
        hf_model="Qwen/Qwen3-ASR-1.7B",
        params_b=1.7,
        license_note="Apache-2.0",
        runtime="transformers",
        status="active",
        notes="top candidate for household commands — provider wired as qwen3_asr backend",
    ),
    ModelEntry(
        provider_group="stt",
        model_id="parakeet-0.6b",
        hf_model="nvidia/parakeet-ctc-0.6b",
        params_b=0.6,
        license_note="CC-BY-4.0",
        runtime="transformers",
        status="active",
        notes="lightweight streaming ASR — provider wired as parakeet backend",
    ),
    ModelEntry(
        provider_group="stt",
        model_id="sense-voice-small",
        hf_model="iic/SenseVoiceSmall",
        params_b=0.2,
        license_note="MIT",
        runtime="transformers",
        status="active",
        notes="very fast, multilingual — wired as sensevoice backend (default)",
    ),
    ModelEntry(
        provider_group="stt",
        model_id="whisper-large-v3-turbo",
        hf_model="openai/whisper-large-v3-turbo",
        params_b=0.8,
        license_note="MIT",
        runtime="transformers",
        status="candidate",
        notes="baseline only",
    ),
    # TTS
    ModelEntry(
        provider_group="tts",
        model_id="qwen3-tts-0.6b",
        hf_model="Qwen/Qwen3-TTS-0.6B",
        params_b=0.6,
        license_note="Apache-2.0",
        runtime="transformers",
        status="active",
        notes="lightweight TTS candidate — provider wired as qwen3_tts backend",
    ),
    ModelEntry(
        provider_group="tts",
        model_id="kokoro-82m",
        hf_model="",
        params_b=0.082,
        license_note="Apache-2.0",
        runtime="custom",
        status="active",
        badge_relevance="off_the_grid",
        notes="extremely lightweight — KokoroTTSProvider wired as kokoro backend",
    ),
    # TTS — CosyVoice 2 (higher quality, Hindi support)
    ModelEntry(
        provider_group="tts",
        model_id="cosyvoice2-0.5b",
        hf_model="FunAudioLLM/CosyVoice2-0.5B",
        params_b=0.5,
        license_note="Apache-2.0",
        runtime="custom",
        status="active",
        badge_relevance="off_the_grid",
        notes="higher quality TTS with Hindi support. Downloaded (19 files, 3.5GB). Custom architecture — needs CosyVoice repo for inference. Not yet wired as provider.",
    ),
    # Vision
    ModelEntry(
        provider_group="vision",
        model_id="minicpm-v-8b",
        hf_model="openbmb/MiniCPM-V-2_6",
        params_b=8.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="active",
        badge_relevance="llama_champion",
        notes="strong VLM for household items — provider wired as minicpmv backend",
    ),
    # Vision — Qwen2.5-VL-3B (lighter alternative via MLX)
    ModelEntry(
        provider_group="vision",
        model_id="qwen2.5-vl-3b",
        hf_model="Qwen/Qwen2.5-VL-3B-Instruct",
        params_b=3.0,
        license_note="Apache-2.0",
        runtime="mlx",
        status="active",
        badge_relevance="off_the_grid",
        notes="3B params, 0.9s load via MLX. Excellent throughput (43-80 tok/s) at 1/3 the params of MiniCPM-V. Use for high-volume vision tasks.",
    ),
    # Planner
    ModelEntry(
        provider_group="planner",
        model_id="minicpm5-1b",
        hf_model="openbmb/MiniCPM5-1B",
        params_b=1.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="active",
        badge_relevance="well_tuned",
        notes="lightweight planner / parser — provider wired as minicpm5 backend",
    ),
    ModelEntry(
        provider_group="planner",
        model_id="lfm2.5-8b-a1b-gguf",
        hf_model="unsloth/LFM2.5-8B-A1B-GGUF",
        params_b=8.3,
        license_note="Apache-2.0",
        runtime="gguf",
        status="candidate",
        badge_relevance="llama_champion",
        notes="GGUF planner for llama.cpp path",
    ),
    ModelEntry(
        provider_group="planner",
        model_id="llama-3.2-3b-gguf",
        hf_model="unsloth/Llama-3.2-3B-Instruct-GGUF",
        params_b=3.0,
        license_note="Llama 3.2 Community",
        runtime="gguf",
        status="candidate",
        badge_relevance="none",
        notes="downloaded & tested: 493ms for 49 tokens via llama.cpp. Superseded by qwen3.5-4b for planner (better tool-calling accuracy).",
    ),
    # Planner — Qwen3.5-4B (full bf16 variant, cached, used for accuracy-critical tasks)
    ModelEntry(
        provider_group="planner",
        model_id="qwen3.5-4b",
        hf_model="Qwen/Qwen3.5-4B",
        params_b=4.0,
        license_note="Apache-2.0",
        runtime="mlx",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Full bf16 precision variant (8.9GB). ~18 tok/s via MLX. Demoted to candidate because config now defaults to 4-bit variant. Keep cached for quality-benchmarking (97.5% accuracy).",
    ),
    # Planner — Qwen3.5-4B-4bit (deployment variant, ~2.3GB, same accuracy)
    ModelEntry(
        provider_group="planner",
        model_id="qwen3.5-4b-4bit",
        hf_model="mlx-community/Qwen3.5-4B-4bit",
        params_b=4.0,
        license_note="Apache-2.0",
        runtime="mlx",
        status="active",
        badge_relevance="llama_champion",
        notes="4-bit quantized variant of Qwen3.5-4B. ~2.3GB vs 8.9GB for full bf16. Should match accuracy (~97.5%) at 4x less memory. Config default. Not yet cached — download: mlx_lm.load(\"mlx-community/Qwen3.5-4B-4bit\")",
    ),
    # Planner — Gemma 3 4B (strong architecture, needs prompt engineering)
    ModelEntry(
        provider_group="planner",
        model_id="gemma-3-4b-it-4bit",
        hf_model="mlx-community/gemma-3-4b-it-4bit",
        params_b=4.0,
        license_note="Gemma Terms of Use",
        runtime="mlx",
        status="candidate",
        badge_relevance="none",
        notes="Google Gemma 3 4B Instruct, 4-bit MLX quantized. Strong architecture but requires more prompt engineering for JSON output. Not yet downloaded or benchmarked.",
    ),
    # Planner — DeepSeek-R1-Distill-Qwen-7B (higher accuracy, heavier)
    ModelEntry(
        provider_group="planner",
        model_id="deepseek-r1-distill-qwen-7b-4bit",
        hf_model="mlx-community/DeepSeek-R1-Distill-Qwen-7B-abliterated-4bit",
        params_b=7.0,
        license_note="MIT",
        runtime="mlx",
        status="candidate",
        badge_relevance="none",
        notes="DeepSeek R1 Distill Qwen 7B, 4-bit MLX quantized. Higher accuracy potential but 7B params (~4GB). Not yet downloaded or benchmarked. Add to active only after verification.",
    ),
    # OCR / extraction
    ModelEntry(
        provider_group="ocr",
        model_id="glm-ocr-0.9b",
        hf_model="zai-org/GLM-OCR",
        params_b=1.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="active",
        badge_relevance="off_the_grid",
        notes="Specialized 0.9B document/receipt OCR model. Current SOTA for small OCR (June 2026). Loaded & verified: 1016M params on Apple Silicon.",
    ),
    # OCR / extraction
    ModelEntry(
        provider_group="ocr",
        model_id="nuextract3-4b",
        hf_model="nuance/NuExtract3-4B",
        params_b=4.0,
        license_note="CC-BY-NC-4.0",
        runtime="transformers",
        status="candidate",
        notes="strong receipt extraction, non-commercial. Superseded by glm-ocr-0.9b (1B params, purpose-built for OCR).",
    ),
    # Segmentation
    ModelEntry(
        provider_group="segmentation",
        model_id="rmbg-1.4",
        hf_model="briaai/RMBG-1.4",
        params_b=0.3,
        license_note="Apache-2.0",
        runtime="transformers",
        status="active",
        notes="background removal for item cards — provider wired as rmbg backend",
    ),
    # Embeddings
    ModelEntry(
        provider_group="embeddings",
        model_id="bge-m3",
        hf_model="BAAI/bge-m3",
        params_b=0.6,
        license_note="MIT",
        runtime="transformers",
        status="active",
        notes="multilingual embeddings — provider wired as bge_m3 backend",
    ),
    # Fine-tuned
    ModelEntry(
        provider_group="planner",
        model_id="shopstack-parser-lora",
        hf_model="",
        params_b=0.0,
        license_note="Apache-2.0 (planned)",
        runtime="transformers",
        status="candidate",
        badge_relevance="well_tuned",
        notes="future fine-tuned command parser",
    ),
    # Image generation
    ModelEntry(
        provider_group="image_edit",
        model_id="flux.2-klein-4b",
        hf_model="black-forest-labs/FLUX.2-klein-4B",
        params_b=4.0,
        license_note="FLUX.2-dev Non-Commercial",
        runtime="diffusers",
        status="active",
        badge_relevance="llama_champion",
        notes="visual card generation — FluxImageProvider wired as image_gen backend",
    ),
]


def get_registry(group: str | None = None) -> list[ModelEntry]:
    if group:
        return [m for m in MODEL_REGISTRY if m.provider_group == group]
    return list(MODEL_REGISTRY)


def get_active(group: str) -> list[ModelEntry]:
    return [m for m in MODEL_REGISTRY if m.provider_group == group and m.status == "active"]


def get_active_models() -> list[ModelEntry]:
    return [m for m in MODEL_REGISTRY if m.status == "active"]


def total_active_params() -> float:
    return sum(m.params_b for m in MODEL_REGISTRY if m.status == "active")


def total_candidate_only_params() -> float:
    return total_candidate_params()


def total_loaded_params() -> float:
    return total_active_params()


def total_candidate_params() -> float:
    return sum(m.params_b for m in MODEL_REGISTRY if m.status == "candidate")


def total_selected_params(include_candidates: bool = False) -> float:
    if include_candidates:
        return sum(m.params_b for m in MODEL_REGISTRY if m.status in ("active", "candidate"))
    return total_active_params()


def validate_active_model_budget(max_params_b: float = MAX_ACTIVE_MODEL_PARAMS_B) -> None:
    total = total_loaded_params()
    if total > max_params_b:
        raise ValueError(
            f"Active model stack is {total}B, which exceeds the {max_params_b}B cap"
        )


def get_status_summary() -> dict[str, int]:
    counts: dict[str, int] = {"active": 0, "candidate": 0, "deprecated": 0, "rejected": 0}
    for model in MODEL_REGISTRY:
        counts[model.status] += 1
    return counts
