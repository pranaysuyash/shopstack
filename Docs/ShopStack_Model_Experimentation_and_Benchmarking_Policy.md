# ShopStack — Model Experimentation and Benchmarking Policy

## Purpose

ShopStack should not be anchored to any single model choice made during the hackathon window. The product is intentionally designed as a **swappable small-model system**: vision, audio, OCR, segmentation, planning, tool-calling, TTS, and image-editing modules can be benchmarked, replaced, combined, or fine-tuned as better models appear.

This document gives agents and contributors a standing rule:

> **Model choices are implementation details. The product loop, data contracts, and evaluation harness are the durable architecture.**

The product loop remains:

> **Know what is at home → help while shopping → understand what was bought → update inventory → track freshness, price, quantity, and location → answer by voice.**

---

## Non-Negotiable Product Constraints

For the Build Small Hackathon submission path:

1. **Total model parameters must stay at or under 32B.**
2. **The user-facing app must be a Gradio app hosted as a Hugging Face Space.**
3. **The app should avoid cloud model APIs when claiming Off the Grid.**
4. **Model licenses may include research/non-commercial terms for the hackathon artifact, but the README must disclose this clearly.**
5. **No private household data, receipts, raw voice clips, exact addresses, phone numbers, or credit codes should be committed to the repo.**

---

## Design Rule: Model Providers, Not Model Lock-In

Every model-backed capability should sit behind a provider interface.

### Provider groups

- `SpeechToTextProvider`
- `TextToSpeechProvider`
- `VisionUnderstandingProvider`
- `ObjectGroundingProvider`
- `SegmentationProvider`
- `OCRProvider`
- `PlannerProvider`
- `ToolCallParserProvider`
- `ImageEditProvider`
- `VideoUnderstandingProvider`
- `NutritionProvider`
- `PriceMemoryProvider`

### Required provider behavior

Each provider should expose:

- `name`
- `model_id`
- `parameter_count`
- `license_note`
- `runtime_type` — local transformers, llama.cpp, ONNX, GGUF, diffusers, custom, mock, etc.
- `supports_off_grid_runtime`
- `load()`
- `predict()` / `transcribe()` / `synthesize()` / `extract()` / `detect()`
- `healthcheck()`
- `benchmark_sample()`

Agents should not hardcode a single model directly inside the Gradio UI or business logic. The UI calls ShopStack services. ShopStack services call providers.

---

## Model Registry

Maintain a local model registry file:

```yaml
models:
  stt:
    - id: qwen3-asr-1.7b
      hf_model: Qwen/Qwen3-ASR-1.7B
      params_b: 1.7
      status: candidate
      runtime: transformers
      notes: candidate for Indian household commands

  planner:
    - id: lfm2.5-8b-a1b-gguf
      hf_model: unsloth/LFM2.5-8B-A1B-GGUF
      params_b: 8.3
      status: candidate
      runtime: llama.cpp
      badge_relevance: Llama Champion

  object_grounding:
    - id: locateanything-3b
      hf_model: nvidia/LocateAnything-3B
      params_b: 3
      status: candidate
      runtime: transformers/custom
      license_note: research/non-commercial; disclose in README
```

Suggested path:

```text
configs/model_registry.yaml
```

The registry should be edited as models are tested, promoted, replaced, or rejected.

---

## Benchmarking Philosophy

Benchmarks should be product-specific. Do not rely only on leaderboard scores. A model is useful for ShopStack if it improves one of these real household workflows:

1. Creating a shopping list by voice.
2. Understanding Hinglish/Indian household item names.
3. Looking at a shelf/market photo and identifying relevant items.
4. Reading packet labels, MRP, quantity, and expiry.
5. Turning uncertain detections into reviewable item cards.
6. Producing safe, short, useful buy/skip decisions.
7. Updating inventory through structured tool calls.
8. Answering where something is kept or when it may run out.
9. Speaking back clearly enough for a household user.
10. Running acceptably in the Hugging Face Space setup.

---

## Benchmark Suites

Create a `benchmarks/` directory with fixed test cases and scripts.

```text
benchmarks/
  voice_commands/
    shopstack_voice_phrases.jsonl
    noisy_market_variants/
  vision_market/
    shelf_photos.jsonl
    vegetable_stall_photos.jsonl
  purchase_capture/
    shopping_bag_photos.jsonl
    kitchen_table_photos.jsonl
  receipts_labels/
    receipt_ocr_cases.jsonl
    expiry_label_cases.jsonl
  planner_tool_calls/
    inventory_context_cases.jsonl
    expected_tool_calls.jsonl
  tts/
    response_texts.jsonl
  video_scan/
    short_market_clips.jsonl
  traces/
    anonymized_trace_cases.jsonl
```

Each benchmark case should include:

- input path or redacted text
- expected structured output
- acceptable alternatives
- reviewer notes
- product severity if wrong

---

## Voice Benchmark

ShopStack voice should be evaluated on household phrases, not generic dictation.

### Example STT phrases

```text
Doodh ghar pe hai kya?
Aaj kya kharidna hai?
Yeh tamatar aadha kilo add karo.
Nahi, yeh aloo nahi pyaaz hai.
Bread expiry kal ka hai, skip kar do.
Surf Excel already ghar pe hai kya?
Is packet ka MRP kitna hai?
Fridge mein dahi kab expire hoga?
Kal breakfast ke liye kya hai?
List se chawal hata do.
Aloo do kilo hai, pyaaz ek kilo hai.
Dhaniya free mila, add kar do.
Isko pantry mein daal do.
Yeh bathroom shelf pe rakha hai.
Colgate khatam hone wala hai kya?
```

### STT scorecard

Score 1–5 for:

- transcription accuracy
- intent preservation
- item-name accuracy
- quantity/unit accuracy
- Hinglish/Hindi tolerance
- noisy-market tolerance
- latency
- memory/runtime fit
- Hugging Face Space deployment effort

### STT candidate families

- Qwen3-ASR
- NVIDIA Parakeet / Nemotron ASR
- Voxtral realtime / mini variants
- SenseVoice
- VibeVoice ASR
- Cohere Transcribe style local/released models if available
- Whisper as a baseline, not the default ambition

---

## TTS Benchmark

TTS should be evaluated on short household answers, not long narration.

### Example TTS lines

```text
Buy milk and bread. Skip onions because you already have enough at home.
Tamatar aadha kilo add kar diya. Use within four days.
Bread expires tomorrow, so use it first.
Dahi fridge ke second shelf par last seen hai.
Aapke paas detergent abhi enough hai. Is baar mat kharidiye.
```

### TTS scorecard

Score 1–5 for:

- clarity
- speed
- Hindi/Hinglish pronunciation
- Indian household item pronunciation
- warmth/trustworthiness
- generation latency
- runtime complexity
- Space compatibility

### TTS candidate families

- MOSS-TTS
- VoxCPM2
- Qwen3-TTS
- Higgs Audio TTS
- Kokoro as lightweight fallback
- CosyVoice / FunAudioLLM family
- Other new small multilingual TTS models as discovered

---

## Vision and Shopping Scan Benchmark

ShopStack should benchmark models on practical shopping scenes:

- vegetable cart photo
- supermarket shelf photo
- kirana counter photo
- fridge shelf photo
- pantry shelf photo
- final purchase table photo
- shopping bag photo
- packet close-up
- receipt close-up

### Vision scorecard

Score 1–5 for:

- detects relevant item
- avoids hallucinating unseen items
- handles Indian household categories
- produces useful confidence
- localizes object if asked
- gives crop/box/mask usable for review UI
- works with blurry/low-light photos
- runtime/memory fit

### Candidate families

- Gemma multimodal variants under 32B
- LocateAnything-style grounding models
- RF-DETR / YOLO-style detectors
- Qwen-VL / similar VLMs under 32B
- NuExtract/PaddleOCR-VL for document/label/receipt heavy cases
- segmentation and background-removal models for item card crops

---

## OCR and Document Extraction Benchmark

OCR/document models should be judged on labels and receipts:

- expiry date
- MRP
- quantity/weight
- brand
- manufacturing date
- receipt line items
- total amount
- store name
- packet nutrition panel

### OCR scorecard

Score 1–5 for:

- date extraction accuracy
- amount/price extraction accuracy
- quantity/unit extraction accuracy
- brand/item extraction accuracy
- table/receipt handling
- resistance to partial/rotated/blurry text
- structured JSON validity
- latency/runtime fit

---

## Tool-Call Parser Benchmark

This is the strongest Well-Tuned target.

### Input

Natural language household utterance + optional current inventory context.

### Output

A structured tool call:

```json
{
  "intent": "add_inventory_item",
  "tool": "add_inventory_item",
  "args": {
    "canonical_name": "tomato",
    "display_name": "tamatar",
    "quantity": 0.5,
    "unit": "kg",
    "location": "fridge",
    "expiry_hint_days": 4
  },
  "confidence": 0.88,
  "requires_confirmation": true
}
```

### Parser scorecard

Score 1–5 for:

- correct intent
- item canonicalization
- quantity/unit parsing
- date/expiry parsing
- location parsing
- safe confirmation behavior
- JSON validity
- no hidden mutation
- deterministic behavior

---

## Well-Tuned Strategy

Fine-tune a compact parser model for Indian household shopping utterances.

### Fine-tuning target

**ShopStack Command Parser**

Task:

> Indian household shopping utterance → validated JSON tool call.

### Dataset content

Include:

- Hinglish/Hindi/English household utterances
- item synonyms and regional names
- brand names
- quantities and units
- storage locations
- expiry hints
- buy/skip/correct/find/move/consume intents
- ambiguous cases requiring confirmation

### Published artifacts

- dataset on Hugging Face
- fine-tuned model or adapter on Hugging Face
- README explaining schema, examples, limitations, and evaluation
- app integration proving the model is actually used

---

## Llama.cpp / GGUF Strategy

For Llama Champion, run a planner/parser through llama.cpp.

### Candidate GGUF models to evaluate

- `unsloth/LFM2.5-8B-A1B-GGUF`
- `unsloth/Llama-3.2-3B-Instruct-GGUF`
- `unsloth/gpt-oss-20b-GGUF`
- other newly discovered GGUF models under 32B

### llama.cpp responsibilities

Use llama.cpp for one clearly visible product function:

- command parser
- buy/skip decision planner
- inventory Q&A planner
- trace explanation generator

Do not use llama.cpp as a hidden side experiment. The Space README and UI trace should show that the planner/parser path runs through GGUF + llama.cpp.

---

## Replacement Rules

A model can replace the current provider if it improves one or more metrics without harming product constraints.

### Promote a model when

- it improves benchmark score by at least 10% on product cases, or
- it reduces latency/memory by at least 20% with similar quality, or
- it unlocks a badge path such as Off the Grid or Llama Champion, or
- it simplifies deployment significantly, or
- it improves Indian household language behavior materially.

### Reject or demote a model when

- it fails to run reliably in Space/local setup,
- it exceeds the 32B total parameter budget,
- it needs cloud APIs for the submission runtime path,
- it has unacceptable hallucination in shopping/inventory contexts,
- it cannot produce structured outputs where required,
- it creates license disclosure risk that is not worth the gain,
- it slows the UI enough that the product feels broken.

---

## Experiment Log

Every serious model experiment should be logged.

Suggested path:

```text
docs/model-experiments/YYYY-MM-DD-model-name.md
```

Template:

```markdown
# Model Experiment: <model name>

## Capability
STT / TTS / Vision / OCR / Planner / Segmentation / Image Edit / Video

## Why tested

## Runtime setup

## Parameter count

## License note

## Test cases

## Results

## Product fit

## Problems

## Decision
Promote / Keep candidate / Reject / Re-test later

## Follow-up
```

---

## Modal and Hugging Face Credit Usage

ShopStack has credits available for experimentation. Use them intentionally.

### Modal credits

Use for:

- model benchmarking jobs
- fine-tuning experiments
- batch image/audio/video evaluation
- synthetic dataset generation
- quantization trials
- trace generation
- temporary heavier GPU tasks

Avoid making Modal a required runtime dependency for the Off the Grid submission path.

### Hugging Face credits

Use for:

- GPU Space testing
- Jobs for training/evaluation
- hosting published model/dataset artifacts
- temporary inference endpoints during comparison
- private storage while preparing public-safe examples

Avoid making hosted inference endpoints mandatory if claiming Off the Grid.

---

## Trace-Based Evaluation

Every agent/model decision should optionally emit a structured trace:

```json
{
  "input_type": "market_photo_plus_voice",
  "redacted_user_request": "Do we need this item?",
  "perception": {
    "detected_items": ["bread", "milk", "tomato"],
    "confidence": "medium"
  },
  "inventory_context": {
    "bread": "not_available",
    "milk": "low",
    "tomato": "available_0.5kg"
  },
  "decision": "buy bread and milk, skip tomato",
  "proposed_tool_calls": [
    {
      "tool": "add_to_shopping_list",
      "args": {"item": "bread"}
    }
  ],
  "user_confirmation": "accepted",
  "final_answer": "Buy bread and milk. Skip tomato."
}
```

These traces support:

- Sharing is Caring badge
- debugging
- benchmark replay
- model comparison
- Field Notes
- Codex review

Only publish anonymized/synthetic/redacted traces.

---

## Agent Instruction Block

Use this block when asking Codex or another coding agent to work on model integration:

```text
ShopStack must remain model-swappable. Do not hardcode one model into the product flow.

Add or preserve provider interfaces for STT, TTS, vision, grounding, segmentation, OCR, planner, parser, image-editing, and video understanding.

Add benchmark scripts and fixtures for household shopping commands, market/shelf images, purchase photos, receipts/labels, planner tool calls, and TTS responses.

When evaluating a new model, log parameter count, license note, runtime requirements, benchmark results, latency, memory, Space compatibility, and a promote/reject decision.

Keep the Build Small constraints visible: total model parameters under 32B, Gradio Space runtime, no cloud model APIs for the Off the Grid path, and clear license disclosure for research/non-commercial models.

Use Modal and Hugging Face credits for experiments, training, evaluation, quantization, and trace generation, but do not make them mandatory runtime dependencies for the local-first submission path.
```

---

## Final Principle

ShopStack should keep improving as the small-model ecosystem changes.

The product should not be remembered as “the app that used Model X.”

It should be remembered as:

> **the household shopping memory system with a disciplined small-model evaluation loop.**
