# Model Registry

The model registry in `shopstack/model_registry.py` catalogs candidate models for each provider capability. All entries are **candidate-only** — no model binaries are bundled with ShopStack.

## Constraint

Total parameters across all *active* models must not exceed **32 billion** (enforced by `total_active_params()`).

## Categories

| Category | Candidate Models | Target Provider |
|----------|-----------------|-----------------|
| STT | 3 (Whisper variants) | STT interface |
| TTS | 2 (OuteTTS, Edge-TTS) | TTS interface |
| Vision | 2 (Florence-2, PaliGemma-2) | Vision interface |
| OCR | 1 (TrOCR) | OCR interface |
| Embeddings | 3 (bge-m3, nomic-embed, E5) | Embeddings interface |
| Planner | 1 (Qwen 2.5 7B Instruct) | Planner interface |
| ToolCall + Grounding | 3 (Qwen 2.5 3B/7B, Granite) | ToolCallParser / Grounding |
| ImageEdit | 1 (Florence-2) | ImageEdit interface |

## Active Model Selection

To activate a model, create a real provider implementation that loads the model (e.g., via llama.cpp, GGUF, or transformers) and register it with `ProviderRegistry`. Update `_get_active_status()` in the registry to mark entries as active when their provider is loaded.

## Parameter Budget

| Model | Params (B) | Cumulative |
|-------|-----------|------------|
| whisper-small | 0.25 | 0.25 |
| whisper-medium | 0.77 | 1.02 |
| Granite 3B | 3.0 | 4.02 |
| Qwen 2.5 3B | 3.0 | 7.02 |
| Qwen 2.5 7B | 7.0 | 14.02 |
| bge-m3 | 0.57 | 14.59 |
| TrOCR | 0.33 | 14.92 |
| Florence-2 | 0.23 | 15.15 |

The ≤32B constraint allows running multiple models simultaneously (e.g., STT + Planner + Embeddings).
