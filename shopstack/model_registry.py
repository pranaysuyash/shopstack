from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RuntimeType = Literal["transformers", "llama.cpp", "gguf", "onnx", "diffusers", "custom", "mock"]
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
        status="candidate",
        notes="top candidate for household commands",
    ),
    ModelEntry(
        provider_group="stt",
        model_id="parakeet-0.6b",
        hf_model="nvidia/parakeet-ctc-0.6b",
        params_b=0.6,
        license_note="CC-BY-4.0",
        runtime="custom",
        status="candidate",
        notes="lightweight streaming ASR",
    ),
    ModelEntry(
        provider_group="stt",
        model_id="sense-voice-small",
        hf_model="funasr/SenseVoiceSmall",
        params_b=0.2,
        license_note="MIT",
        runtime="transformers",
        status="candidate",
        notes="very fast, multilingual",
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
        status="candidate",
        notes="lightweight TTS candidate",
    ),
    ModelEntry(
        provider_group="tts",
        model_id="kokoro-82m",
        hf_model="",
        params_b=0.082,
        license_note="Apache-2.0",
        runtime="custom",
        status="candidate",
        badge_relevance="off_the_grid",
        notes="extremely lightweight",
    ),
    # Vision
    ModelEntry(
        provider_group="vision",
        model_id="minicpm-v-8b",
        hf_model="openbmb/MiniCPM-V-2_6",
        params_b=8.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        notes="strong VLM for household items",
    ),
    # Planner
    ModelEntry(
        provider_group="planner",
        model_id="minicpm5-1b",
        hf_model="openbmb/MiniCPM5-1B",
        params_b=1.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        notes="lightweight planner / parser",
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
        badge_relevance="llama_champion",
        notes="small GGUF parser candidate",
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
        notes="strong receipt extraction, non-commercial",
    ),
    # Segmentation
    ModelEntry(
        provider_group="segmentation",
        model_id="rmbg-1.4",
        hf_model="briaai/RMBG-1.4",
        params_b=0.3,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        notes="background removal for item cards",
    ),
    # Embeddings
    ModelEntry(
        provider_group="embeddings",
        model_id="bge-m3",
        hf_model="BAAI/bge-m3",
        params_b=0.6,
        license_note="MIT",
        runtime="transformers",
        status="candidate",
        notes="multilingual embeddings",
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
        status="candidate",
        notes="visual card generation",
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
