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
    # STT — Voxtral-Mini-4B-Realtime-2602 (Jan 2026, 1.1M downloads, Mistral's new SOTA)
    ModelEntry(
        provider_group="stt",
        model_id="voxtral-mini-4b-realtime",
        hf_model="mistralai/Voxtral-Mini-4B-Realtime-2602",
        params_b=4.0,
        license_note="Apache-2.0",
        runtime="vllm",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Voxtral-Mini-4B-Realtime-2602 (Jan 2026, 1.1M downloads). Mistral's new SOTA STT. Apache-2.0. STT bench in flight on Modal A10G with 20 Hinglish audios.",
    ),
    # STT — parakeet-tdt-0.6b-v3 (Aug 2025, 120k downloads, newer than v2)
    ModelEntry(
        provider_group="stt",
        model_id="parakeet-tdt-0.6b-v3",
        hf_model="nvidia/parakeet-tdt-0.6b-v3",
        params_b=0.6,
        license_note="CC-BY-4.0",
        runtime="nemo",
        status="candidate",
        notes="parakeet-tdt-0.6b-v3 (Aug 2025, 120k downloads). Newer than the v2 already in registry. STT bench in flight.",
    ),
    # STT — Fun-ASR-Nano-2512 (Dec 2025, FunAudioLLM)
    ModelEntry(
        provider_group="stt",
        model_id="fun-asr-nano-2512",
        hf_model="FunAudioLLM/Fun-ASR-Nano-2512",
        params_b=0.5,
        license_note="Apache-2.0",
        runtime="funasr",
        status="candidate",
        notes="Fun-ASR-Nano-2512 (Dec 2025, FunAudioLLM). Multilingual + streaming + diarization. STT bench pending.",
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
    ModelEntry(
        provider_group="stt",
        model_id="qwen3-asr-0.6b",
        hf_model="Qwen/Qwen3-ASR-0.6B",
        params_b=0.6,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        notes="smaller/newer Qwen ASR variant to benchmark against Qwen3-ASR-1.7B; good for low-cost voice sweeps and short commands.",
    ),
    # TTS
    ModelEntry(
        provider_group="tts",
        model_id="qwen3-tts-0.6b",
        hf_model="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        params_b=0.6,
        license_note="Apache-2.0",
        runtime="custom",
        status="active",
        notes="lightweight TTS candidate — uses qwen_tts SDK (not transformers). Default voice Ryan.",
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
    # TTS — CosyVoice 2 (higher quality, Hindi support) — SUPERSEDED by CosyVoice 3
    ModelEntry(
        provider_group="tts",
        model_id="cosyvoice2-0.5b",
        hf_model="FunAudioLLM/CosyVoice2-0.5B",
        params_b=0.5,
        license_note="Apache-2.0",
        runtime="custom",
        status="rejected",
        badge_relevance="off_the_grid",
        notes="REJECTED 13-Jun-2026: superseded by Fun-CosyVoice3-0.5B-2512. CosyVoice 2 was blocked on Python 3.14 (matcha-tts/numpy 1.24.3/distutils). Use CosyVoice 3 instead.",
    ),
    # TTS — Fun-CosyVoice3-0.5B-2512 (Dec 2025, REPLACES CosyVoice 2)
    ModelEntry(
        provider_group="tts",
        model_id="fun-cosyvoice3-0.5b-2512",
        hf_model="FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        params_b=0.5,
        license_note="Apache-2.0",
        runtime="custom",
        status="candidate",
        badge_relevance="off_the_grid",
        notes="Fun-CosyVoice3-0.5B-2512 (Dec 2025, 81k downloads). Apache-2.0. REPLACES CosyVoice 2. Multilingual (zh, en, ja, ko, de, fr, ru, it, es). MLX mirror available (mlx-community/Fun-CosyVoice3-0.5B-2512-fp16). Unblocks local Hindi TTS.",
    ),
    # TTS — Qwen3-TTS-12Hz-1.7B-CustomVoice (Jan 2026, 1.9M downloads)
    ModelEntry(
        provider_group="tts",
        model_id="qwen3-tts-1.7b-customvoice",
        hf_model="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        params_b=1.7,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Qwen3-TTS-1.7B-CustomVoice (Jan 2026, 1.9M downloads). Apache-2.0. Most popular Qwen TTS. TTS bench pending.",
    ),
    # TTS — Qwen3-TTS-12Hz-1.7B-VoiceDesign
    ModelEntry(
        provider_group="tts",
        model_id="qwen3-tts-1.7b-voicedesign",
        hf_model="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        params_b=1.7,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        notes="Qwen3-TTS-1.7B-VoiceDesign (Jan 2026, 686k downloads). Voice design variant. TTS bench pending.",
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
    # Vision — MiniCPM-V-4.6 (NEW MID-2026 SOTA, VLM bench candidate)
    ModelEntry(
        provider_group="vision",
        model_id="minicpm-v-4.6",
        hf_model="openbmb/MiniCPM-V-4.6",
        params_b=4.6,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="MiniCPM-V-4.6 (Apr 2026, 660k downloads). On-device VLM. REPLACES MiniCPM-V-2_6 (Aug 2024). VLM bench in flight.",
    ),
    # Vision — Molmo2-8B (Dec 2025, Allen AI, 645k downloads)
    ModelEntry(
        provider_group="vision",
        model_id="molmo2-8b",
        hf_model="allenai/Molmo2-8B",
        params_b=8.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Molmo2-8B (Dec 2025, 645k downloads). Allen AI. custom_code required. VLM bench in flight.",
    ),
    # Vision — Qwen2.5-VL-7B-Instruct (Jan 2025, 6.5M downloads, still very popular)
    ModelEntry(
        provider_group="vision",
        model_id="qwen2.5-vl-7b",
        hf_model="Qwen/Qwen2.5-VL-7B-Instruct",
        params_b=7.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Qwen2.5-VL-7B-Instruct (Jan 2025, 6.5M downloads). Still very popular. VLM bench in flight.",
    ),
    # Vision — Kimi-VL-A3B-Thinking (Apr 2025, MoE vision reasoning)
    ModelEntry(
        provider_group="vision",
        model_id="kimi-vl-a3b-thinking",
        hf_model="moonshotai/Kimi-VL-A3B-Thinking",
        params_b=16.0,
        license_note="MIT",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Kimi-VL-A3B-Thinking (Apr 2025). MoE 16B/3B active, vision + reasoning. custom_code. VLM bench pending.",
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
        status="candidate",
        badge_relevance="llama_champion",
        notes="4-bit quantized variant of Qwen3.5-4B. ~2.3GB vs 8.9GB for full bf16. 70% on Modal A100 int4 production bench (13-Jun-2026). Superseded by Ministral-8B-Instruct (90%). Demoted.",
    ),
    # Planner — Ministral-8B-Instruct (NEW WINNER, 13-Jun-2026)
    ModelEntry(
        provider_group="planner",
        model_id="ministral-8b-instruct",
        hf_model="mistralai/Ministral-8B-Instruct-2410",
        params_b=8.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Run 1+2 winner on Modal A100 int4 (13-Jun-2026): 90% (10 prompts) / 95% (20 prompts), 4.08s mean latency, 5.75GB GPU. Tied with Gemma-3-4B (also 95%). Oct 2024 release. SUPERSEDED by Ministral-3-8B-Instruct-2512 (Run 3 candidate).",
    ),
    # Planner — Ministral-3-8B-Instruct-2512 (NEW MID-2026 SOTA, Run 3 candidate)
    ModelEntry(
        provider_group="planner",
        model_id="ministral-3-8b-instruct-2512",
        hf_model="mistralai/Ministral-3-8B-Instruct-2512",
        params_b=8.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Mistral's Oct 2025 release. 169k downloads. mistral3 arch. REPLACES the older Ministral-8B-Instruct-2410. Run 3 Modal bench in flight.",
    ),
    # Planner — Ministral-3-3B-Instruct-2512 (NEW MID-2026 SOTA, Run 3 candidate)
    ModelEntry(
        provider_group="planner",
        model_id="ministral-3-3b-instruct-2512",
        hf_model="mistralai/Ministral-3-3B-Instruct-2512",
        params_b=3.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Mistral's Oct 2025 3B variant. 669k downloads. Smallest serious Mistral. Run 3 bench in flight.",
    ),
    # Planner — Ministral-3-14B-Instruct-2512 (NEW MID-2026 SOTA, Run 3 candidate)
    ModelEntry(
        provider_group="planner",
        model_id="ministral-3-14b-instruct-2512",
        hf_model="mistralai/Ministral-3-14B-Instruct-2512-BF16",
        params_b=14.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Mistral's Oct 2025 14B variant. Bigger brother of Ministral-3-8B. Run 3 bench in flight.",
    ),
    # Planner — Qwen2.5-7B-Instruct (NEW CANDIDATE, 13-Jun-2026)
    ModelEntry(
        provider_group="planner",
        model_id="qwen2.5-7b-instruct",
        hf_model="Qwen/Qwen2.5-7B-Instruct",
        params_b=7.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Modal A100 int4 (13-Jun-2026): 80% tool-calling, 3.17s mean (FASTEST of all 8 candidates), 5.56GB GPU. Beats Qwen3.5-4B on speed by 9×. Strong runner-up. Pending: MLX port + 30+ prompt re-validation.",
    ),
    # Planner — Qwen3.5-9B (HF frontier candidate, 13-Jun-2026)
    ModelEntry(
        provider_group="planner",
        model_id="qwen3.5-9b",
        hf_model="Qwen/Qwen3.5-9B",
        params_b=9.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Qwen3.5-9B (Feb 2026, 8.5M downloads). Most popular Qwen text+vision. Run 3 bench in flight on Modal A100.",
    ),
    # Planner — Qwen3.6-27B-FP8 (Apr 2026, 4.7M downloads, under 32B cap)
    ModelEntry(
        provider_group="planner",
        model_id="qwen3.6-27b-fp8",
        hf_model="Qwen/Qwen3.6-27B-FP8",
        params_b=27.0,
        license_note="Apache-2.0",
        runtime="transformers-fp8",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Qwen3.6-27B FP8 (Apr 2026, 4.7M downloads). Best under-32B MoE. Run 3 bench in flight.",
    ),
    # Planner — Qwen3-Coder-Next (Jan 2026, 912k downloads, code specialist)
    ModelEntry(
        provider_group="planner",
        model_id="qwen3-coder-next",
        hf_model="Qwen/Qwen3-Coder-Next",
        params_b=32.0,
        license_note="Apache-2.0",
        runtime="transformers-int4",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Qwen3-Coder-Next (Jan 2026, 912k downloads). Code specialist, strong tool-calling. Run 3 bench in flight.",
    ),
    # Planner — Gemma 4 31B QAT (May 2026, Google's latest, 4-bit QAT)
    ModelEntry(
        provider_group="planner",
        model_id="gemma-4-31b-qat",
        hf_model="google/gemma-4-31B-it-qat-q4_0-unquantized-assistant",
        params_b=31.0,
        license_note="Apache-2.0",
        runtime="transformers-q4",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Gemma 4 31B QAT q4_0 (May 2026, 9.9M downloads). Google's latest, Apache-2.0. Run 3 bench in flight.",
    ),
    # Planner — Qwen3.6-35B-A3B (HF frontier heavy candidate, 13-Jun-2026)
    ModelEntry(
        provider_group="planner",
        model_id="qwen3.6-35b-a3b",
        hf_model="Qwen/Qwen3.6-35B-A3B",
        params_b=35.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="HF Inference live-check (13-Jun-2026): available and responsive; 0.94s wall-clock for a 16-token smoke call. Remote frontier candidate for Modal/HF Pro sweeps only.",
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
    ModelEntry(
        provider_group="ocr",
        model_id="deepseek-ocr-2",
        hf_model="deepseek-ai/DeepSeek-OCR-2",
        params_b=3.0,
        license_note="MIT",
        runtime="transformers",
        status="candidate",
        notes="HF frontier OCR candidate (2026). Exact receipt/label sweep pending; promoted to registry so Modal/HF jobs can benchmark it against GLM-OCR and Tesseract.",
    ),
    # OCR — PaddleOCR-VL-1.6 (May 2026, Apache-2.0, multilingual OCR, unblocks Hindi)
    ModelEntry(
        provider_group="ocr",
        model_id="paddleocr-vl-1.6",
        hf_model="PaddlePaddle/PaddleOCR-VL-1.6",
        params_b=0.9,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="PaddleOCR-VL-1.6 (May 2026, 67k downloads). Apache-2.0. Multilingual OCR (109 langs incl Hindi). Custom PaddlePaddle code. OCR bench in flight. May unblock the long-standing Hindi OCR gap.",
    ),
    # OCR — PaddleOCR-VL-1.6-GGUF (May 2026, GGUF for llama.cpp)
    ModelEntry(
        provider_group="ocr",
        model_id="paddleocr-vl-1.6-gguf",
        hf_model="PaddlePaddle/PaddleOCR-VL-1.6-GGUF",
        params_b=0.9,
        license_note="Apache-2.0",
        runtime="gguf",
        status="candidate",
        notes="PaddleOCR-VL-1.6 GGUF (May 2026, 67k downloads). BYPASSES the PaddlePaddle Python dep blocker. Can run via llama.cpp on Apple Silicon + Modal. THIS is the path to local Hindi OCR.",
    ),
    # OCR — dots.ocr (Jul 2025, 260k downloads, MIT, most popular)
    ModelEntry(
        provider_group="ocr",
        model_id="dots-ocr",
        hf_model="rednote-hilab/dots.ocr",
        params_b=3.0,
        license_note="MIT",
        runtime="transformers",
        status="candidate",
        notes="dots.ocr (Jul 2025, 260k downloads). Most popular modern OCR. Custom code. OCR bench in flight.",
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
    # Segmentation — BiRefNet (Jul 2024, 683k downloads, SOTA)
    ModelEntry(
        provider_group="segmentation",
        model_id="birefnet",
        hf_model="ZhengPeng7/BiRefNet",
        params_b=0.3,
        license_note="MIT",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="BiRefNet (Jul 2024, 683k downloads). SOTA background removal. Bench pending.",
    ),
    ModelEntry(
        provider_group="segmentation",
        model_id="rmbg-2.0",
        hf_model="briaai/RMBG-2.0",
        params_b=0.2,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        notes="HF frontier segmentation candidate (2026). Use for better shelf/item masks and video frame sweeps; benchmark pending.",
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
        notes="multilingual embeddings — provider wired as bge_m3 backend (28.7M downloads, still most popular)",
    ),
    # Embeddings — Qwen3-Embedding-0.6B (Jun 2025, 8.7M downloads, most popular Qwen)
    ModelEntry(
        provider_group="embeddings",
        model_id="qwen3-embedding-0.6b",
        hf_model="Qwen/Qwen3-Embedding-0.6B",
        params_b=0.6,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        badge_relevance="llama_champion",
        notes="Qwen3-Embedding-0.6B (Jun 2025, 8.7M downloads). Most popular Qwen embedding. Embedding bench pending.",
    ),
    # Embeddings — Qwen3-Embedding-8B (Jun 2025, 1.9M downloads)
    ModelEntry(
        provider_group="embeddings",
        model_id="qwen3-embedding-8b",
        hf_model="Qwen/Qwen3-Embedding-8B",
        params_b=8.0,
        license_note="Apache-2.0",
        runtime="transformers",
        status="candidate",
        notes="Qwen3-Embedding-8B (Jun 2025, 1.9M downloads). Higher-quality. Embedding bench pending.",
    ),
    # Embeddings — Jina v5 text-nano (Jan 2026, 543k downloads, multimodal)
    ModelEntry(
        provider_group="embeddings",
        model_id="jina-embeddings-v5-text-nano",
        hf_model="jinaai/jina-embeddings-v5-text-nano",
        params_b=0.2,
        license_note="CC-BY-NC-4.0",
        runtime="transformers",
        status="candidate",
        notes="Jina v5 text-nano (Jan 2026, 543k downloads). Multilingual MTEB. Embedding bench pending.",
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
