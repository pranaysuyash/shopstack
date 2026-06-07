# Model Catalog — Usage-Based View

> **Purpose:** Map every model in `shopstack/model_registry.py` to the product
> workflows it powers. This is the decision maker's view: given a workflow,
> which model handles it, and what are the alternatives?

---

## 1. Provider Capability Map

Models enter the app through **provider backends**, each wired by
`ShopStack.config.SHOPSTACK_*_BACKEND`. The table below shows which backend
handles which capability group.

| Backend Config                  | Provider Class          | Capabilities                                             | Runtime        | Status          |
|---------------------------------|-------------------------|----------------------------------------------------------|----------------|-----------------|
| `SHOPSTACK_PLANNER_BACKEND`     | `LocalProvider`         | Text generation, planning, embeddings                    | `mlx`/`llama.cpp` | Active         |
| `SHOPSTACK_PLANNER_BACKEND`     | `OpenAIProvider`        | Text generation, vision, embeddings                      | Cloud (API)    | Available       |
| `SHOPSTACK_PLANNER_BACKEND`     | `MockPlannerProvider`   | Mock text, planning                                      | Mock           | Default (dev)   |
| `SHOPSTACK_STT_BACKEND`         | `LocalWhisperProvider`  | Speech-to-text                                           | `mlx`/`faster-whisper` | Active    |
| `SHOPSTACK_STT_BACKEND`         | `WhisperProvider`       | Speech-to-text (cloud)                                   | Cloud (API)    | Available       |
| `SHOPSTACK_STT_BACKEND`         | `MockSTTProvider`       | Mock STT                                                 | Mock           | Default (dev)   |
| `SHOPSTACK_VISION_BACKEND`      | `OpenAIProvider`        | Vision understanding (object detection, grounding)       | Cloud (API)    | Available       |
| `SHOPSTACK_VISION_BACKEND`      | `MockVisionProvider`    | Mock vision, detection                                   | Mock           | Default (dev)   |
| `SHOPSTACK_OCR_BACKEND`         | `MockOCRProvider`       | OCR/extraction                                           | Mock           | Default (dev)   |
| `SHOPSTACK_SEGMENTATION_BACKEND`| `MockSegmentationProvider` | Image segmentation                                    | Mock           | Default (dev)   |
| `SHOPSTACK_TTS_BACKEND`         | `MockTTSProvider`       | Text-to-speech                                           | Mock           | Default (dev)   |
| `SHOPSTACK_EMBEDDINGS_BACKEND`  | `LocalProvider` / `OpenAIProvider` | Embeddings (planned fallback)               | Shared         | Inherited       |
| `SHOPSTACK_IMAGE_EDIT_BACKEND`  | `MockImageEditProvider` | Image generation, annotation                             | Mock           | Default (dev)   |

> **Key:** "Active" = wired to real local inference. "Available" = dependencies
> installable. "Default (dev)" = mock provider used during development.

---

## 2. Full Model Registry

All entries from `shopstack/model_registry.py`, organized by provider group.

### 2a. STT — Speech-to-Text

| Model ID                | HF ID                                   | Params | License      | Runtime       | Status     | Notes                                |
|-------------------------|-----------------------------------------|--------|--------------|---------------|------------|--------------------------------------|
| `local-whisper-tiny`    | `mlx-community/whisper-tiny-mlx`        | 0.04B  | MIT          | `mlx`         | **Active** | Default local Whisper backend        |
| `qwen3-asr-1.7b`        | `Qwen/Qwen3-ASR-1.7B`                   | 1.7B   | Apache-2.0   | `transformers`| Candidate  | Top candidate for household commands |
| `parakeet-0.6b`         | `nvidia/parakeet-ctc-0.6b`              | 0.6B   | CC-BY-4.0    | `custom`      | Candidate  | Lightweight streaming ASR            |
| `sense-voice-small`     | `funasr/SenseVoiceSmall`                | 0.2B   | MIT          | `transformers`| Candidate  | Very fast, multilingual              |
| `whisper-large-v3-turbo`| `openai/whisper-large-v3-turbo`         | 0.8B   | MIT          | `transformers`| Candidate  | Baseline only                        |

### 2b. TTS — Text-to-Speech

| Model ID         | HF ID                      | Params  | License    | Runtime       | Status    | Notes                              |
|------------------|----------------------------|---------|------------|---------------|-----------|------------------------------------|
| `qwen3-tts-0.6b` | `Qwen/Qwen3-TTS-0.6B`      | 0.6B    | Apache-2.0 | `transformers`| Candidate | Lightweight TTS candidate          |
| `kokoro-82m`     | —                          | 0.082B  | Apache-2.0 | `custom`      | Candidate | Extremely lightweight (`off_grid`) |

### 2c. Vision / Object Detection / Grounding

| Model ID            | HF ID                            | Params | License    | Runtime       | Status    | Notes                              |
|---------------------|----------------------------------|--------|------------|---------------|-----------|------------------------------------|
| `minicpm-v-8b`      | `openbmb/MiniCPM-V-2_6`          | 8.0B   | Apache-2.0 | `transformers`| Candidate | Strong VLM for household items     |

### 2d. Planner — LLM / Text Generation

| Model ID                | HF ID                                      | Params | License            | Runtime       | Status     | Notes                                    |
|-------------------------|---------------------------------------------|--------|--------------------|---------------|------------|------------------------------------------|
| `llama-3.2-3b-instruct` | `mlx-community/Llama-3.2-3B-Instruct-4bit`  | 3.0B   | Llama 3.2 Community| `mlx`         | **Active** | Default MLX backend (auto-downloaded)    |
| `llama-3.2-3b-gguf`     | `unsloth/Llama-3.2-3B-Instruct-GGUF`        | 3.0B   | Llama 3.2 Community| `gguf`        | **Active** | Downloaded GGUF, llama.cpp fallback      |
| `minicpm5-1b`           | `openbmb/MiniCPM5-1B`                       | 1.0B   | Apache-2.0         | `transformers`| Candidate  | Lightweight planner / parser              |
| `lfm2.5-8b-a1b-gguf`   | `unsloth/LFM2.5-8B-A1B-GGUF`               | 8.3B   | Apache-2.0         | `gguf`        | Candidate  | GGUF planner for llama.cpp path          |
| `shopstack-parser-lora` | —                                           | —      | Apache-2.0 (planned)| `transformers`| Candidate  | Future fine-tuned command parser (`well_tuned`) |

### 2e. OCR — Optical Character Recognition

| Model ID            | HF ID                          | Params | License      | Runtime       | Status    | Notes                              |
|---------------------|--------------------------------|--------|--------------|---------------|-----------|------------------------------------|
| `nuextract3-4b`     | `nuance/NuExtract3-4B`         | 4.0B   | CC-BY-NC-4.0 | `transformers`| Candidate | Strong receipt extraction (non-commercial) |

### 2f. Segmentation

| Model ID    | HF ID                    | Params | License    | Runtime       | Status    | Notes                                  |
|-------------|--------------------------|--------|------------|---------------|-----------|----------------------------------------|
| `rmbg-1.4`  | `briaai/RMBG-1.4`        | 0.3B   | Apache-2.0 | `transformers`| Candidate | Background removal for item cards      |

### 2g. Embeddings

| Model ID  | HF ID              | Params | License | Runtime       | Status    | Notes                              |
|-----------|--------------------|--------|---------|---------------|-----------|------------------------------------|
| `bge-m3`  | `BAAI/bge-m3`      | 0.6B   | MIT     | `transformers`| Candidate | Multilingual embeddings            |

### 2h. Image Generation

| Model ID              | HF ID                                    | Params | License                | Runtime     | Status    | Notes                              |
|-----------------------|------------------------------------------|--------|------------------------|-------------|-----------|------------------------------------|
| `flux.2-klein-4b`     | `black-forest-labs/FLUX.2-klein-4B`      | 4.0B   | FLUX.2-dev NC          | `diffusers` | Candidate | Visual card generation             |

---

## 3. Workflow → Model Mapping

Each product workflow requires one or more model capabilities. The table below
shows the mapping, the **default** model that powers it, and **alternatives**
for tradeoffs (speed vs. quality, local vs. cloud).

| Product Workflow            | Capabilities Required            | Default Model (Local)               | Alternatives                                                            |
|-----------------------------|----------------------------------|-------------------------------------|-------------------------------------------------------------------------|
| **Today Dashboard**         | Planning (text gen)              | `llama-3.2-3b` (MLX)               | `llama-3.2-3b-gguf` (llama.cpp), `minicpm5-1b` (faster, lighter)       |
| **Shopping List**           | Planning, tool-call parsing      | `llama-3.2-3b` (MLX)               | `lfm2.5-8b-a1b-gguf` (higher quality), `shopstack-parser-lora` (future)|
| **Market Lens**             | Vision, object detection, OCR, barcode | `minicpm-v-8b` (vision — candidate) | GPT-4o (cloud, best quality), Mock (dev fallback)                       |
| **Voice Commands (Ask)**    | STT → Planning → Tool-call parse | `local-whisper-tiny` (STT) + `llama-3.2-3b` (planning) | `sense-voice-small` (faster STT), `qwen3-asr-1.7b` (higher quality STT)|
| **Add Purchase**            | Planning (classification)        | `llama-3.2-3b`                     | `minicpm5-1b` (lighter), Mock (no model needed for form mode)           |
| **Price Intelligence**      | Planning (analysis)              | `llama-3.2-3b`                     | — (primarily SQL + heuristic, model optional)                           |
| **Inventory View/Search**   | Embeddings (semantic search)     | `bge-m3` (candidate)               | `LocalProvider.embed()` (zero-vector fallback)                          |
| **Use Soon / Alerts**       | Heuristic (no model)             | —                                   | —                                                                       |
| **Household Map**           | Heuristic (no model)             | —                                   | —                                                                       |
| **Field Notes**             | Planning (summarization)         | `llama-3.2-3b`                     | —                                                                       |
| **Trace Export**            | Heuristic (no model)             | —                                   | —                                                                       |
| **Barcode Decoding**        | `pyzbar` / `zbarimg`             | System `zbar`                      | —                                                                       |

### 3a. Detailed Workflow Flow

```
Voice Command
  └─ SHOPSTACK_STT_BACKEND → transcribe audio
       └─ SHOPSTACK_PLANNER_BACKEND → parse intent, execute action
            └─ SHOPSTACK_PLANNER_BACKEND (tool-call parsing if enabled)

Market Lens Scan
  ├─ SHOPSTACK_VISION_BACKEND → detect objects in image
  ├─ System zbar → decode barcode
  ├─ SHOPSTACK_OCR_BACKEND → extract text (receipts, labels)
  └─ SHOPSTACK_PLANNER_BACKEND → classify buy/skip decisions

Shopping List Creation
  └─ SHOPSTACK_PLANNER_BACKEND → classify items (buy/skip/use_soon)
       └─ Swiggy price enrichment (external data, no model)

Price Intelligence
  └─ SHOPSTACK_PLANNER_BACKEND → optional analysis
       └─ DB query → heuristic comparison (no model required)
```

---

## 4. Active Stack — Budget & Status

The **total active model parameter budget** is capped at **32B params**
(`MAX_ACTIVE_MODEL_PARAMS_B`).

### Currently Active

| Model                          | Group      | Params | Runtime   | Backend Config           | Notes                              |
|--------------------------------|------------|--------|-----------|--------------------------|------------------------------------|
| `llama-3.2-3b-instruct` (MLX)  | Planner    | 3.0B   | `mlx`     | `SHOPSTACK_PLANNER_BACKEND=local` | Default on Apple Silicon          |
| `llama-3.2-3b-gguf`            | Planner    | 3.0B   | `gguf`    | (llama.cpp fallback)     | 493 ms / 49 tokens via llama.cpp   |
| `local-whisper-tiny` (MLX)     | STT        | 0.04B  | `mlx`     | `SHOPSTACK_STT_BACKEND=local_whisper` | On-demand model loading           |
| **Total active**               |            | **≤ 6.04B** |         |                          | Well within 32B cap                |

### Candidate Pipeline

| Priority | Model                          | Group      | Params | Runtime       | Why                               |
|----------|--------------------------------|------------|--------|---------------|-----------------------------------|
| P0       | `minicpm-v-8b`                 | Vision     | 8.0B   | `transformers`| Enables local Market Lens         |
| P0       | `bge-m3`                       | Embeddings | 0.6B   | `transformers`| Semantic search for inventory     |
| P1       | `qwen3-asr-1.7b`               | STT        | 1.7B   | `transformers`| Higher quality local STT          |
| P1       | `sense-voice-small`            | STT        | 0.2B   | `transformers`| Faster multilingual STT           |
| P1       | `nuextract3-4b`                | OCR        | 4.0B   | `transformers`| Receipt scanning (non-commercial) |
| P2       | `qwen3-tts-0.6b`               | TTS        | 0.6B   | `transformers`| Text-to-speech responses          |
| P2       | `kokoro-82m`                   | TTS        | 0.082B | `custom`      | Ultra-lightweight TTS             |
| P2       | `minicpm5-1b`                  | Planner    | 1.0B   | `transformers`| Lightweight planner               |
| P3       | `lfm2.5-8b-a1b-gguf`           | Planner    | 8.3B   | `gguf`        | Higher-quality planning           |
| P3       | `parakeet-0.6b`                | STT        | 0.6B   | `custom`      | Streaming ASR                     |
| P3       | `whisper-large-v3-turbo`       | STT        | 0.8B   | `transformers`| Baseline STT benchmark            |
| P3       | `rmbg-1.4`                     | Segmentation| 0.3B  | `transformers`| Item card polish                  |
| P3       | `flux.2-klein-4b`              | Image Edit | 4.0B   | `diffusers`   | Visual card generation            |
| P4       | `shopstack-parser-lora`        | Planner    | ~0.1B  | `transformers`| Fine-tuned command parser         |

### Budget Projection

```
Active (P0 deployed):    6.04B params
P0 candidates:           + 8.6B  =  14.6B  ← next milestone target
P1 candidates:           + 5.9B  =  20.5B
P2 candidates:           + 1.68B =  22.2B
P3 candidates:           + 5.7B  =  27.9B
P4 fine-tune:            + 0.1B  ≈  28.0B  ← still under 32B cap
```

---

## 5. Env Configuration Reference

```bash
# ── Planner (text gen / planning) ─────────────
SHOPSTACK_PLANNER_BACKEND=local    # LocalProvider (MLX or llama.cpp)
# SHOPSTACK_PLANNER_BACKEND=openai # Cloud fallback (requires API key)

# ── STT (speech-to-text) ─────────────────────
# SHOPSTACK_STT_BACKEND=local_whisper  # On-device whisper
# SHOPSTACK_LOCAL_WHISPER_SIZE=tiny    # tiny / base / small / medium / large

# ── Cloud fallback (optional) ────────────────
# SHOPSTACK_OPENAI_API_KEY=sk-...

# ── Model paths ──────────────────────────────
# SHOPSTACK_LOCAL_MODEL_DIR=              # default: shopstack/data/models/
# SHOPSTACK_LOCAL_MODEL_REPO=unsloth/Llama-3.2-3B-Instruct-GGUF
# SHOPSTACK_LOCAL_MODEL_FILE=Llama-3.2-3B-Instruct-Q4_K_M.gguf
# SHOPSTACK_LOCAL_AUTO_DOWNLOAD=false     # auto-download GGUF if missing

# ── Off-the-grid (mock mode) ────────────────
SHOPSTACK_OFF_THE_GRID=false  # false = allow real backends
```

---

## 6. Adding a New Model

1. Add a `ModelEntry` to `shopstack/model_registry.py`
2. If the model powers a new capability, add a provider class + backend wiring
   in `shopstack/providers/registry.py`
3. If the model replaces an existing backend, update the `SHOPSTACK_*_BACKEND`
   env default in `shopstack/config.py`
4. Update this catalog with the new model's row and workflow mapping
5. Verify the parameter budget: `total_active_params() <= 32B`
