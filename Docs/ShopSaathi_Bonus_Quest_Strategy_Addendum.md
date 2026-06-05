# ShopSaathi / GharStock AI — Bonus Quest Strategy Addendum

This addendum turns the Build Small Hackathon bonus quests into explicit product and engineering requirements for ShopSaathi. The bonus quests are optional, but each can add points. ShopSaathi should be designed so the extras feel like natural parts of the product rather than badges pasted on at the end.

## 1. Bonus quests as product requirements

### 🔌 Off the Grid — Local-first

**Hackathon requirement:** No cloud APIs. The whole thing runs on the model in front of you.

**ShopSaathi interpretation:** The user can run the app without sending household photos, receipts, voice notes, inventory, or shopping history to hosted model APIs.

**Implementation stance:**

- Use local/open model inference inside the Hugging Face Space runtime or local machine.
- Do not use OpenAI API, Gemini API, hosted HF Inference Providers, cloud OCR APIs, cloud TTS APIs, or online price-comparison APIs for the submitted product path.
- Keep price comparison as local price memory and optional sample price tables, not live scraping.
- Make all external/network calls visible and disabled by default.
- Include a README section called `Off the Grid mode` explaining which models run locally and what data stays local.

**Product features that support this:**

- Household inventory stored in SQLite.
- Voice processed by local ASR.
- Item detection, OCR, segmentation, and planning performed by local models.
- Shopping recommendations generated from local inventory, local rules, and local household history.

**Evidence to include:**

- Screenshot of app running without API keys.
- `.env.example` showing no required cloud model keys.
- README model table with local model names, parameter counts, licenses, and runtime notes.
- A simple `OFF_THE_GRID=true` configuration flag.

---

### 🎯 Well-Tuned — Fine-tuned model published on Hugging Face

**Hackathon requirement:** The app uses a fine-tuned model published on Hugging Face.

**ShopSaathi interpretation:** Publish a small fine-tuned model or adapter for a narrow household-shopping task.

**Best fine-tuning target:** A small intent/entity extraction model for shopping voice/text commands.

The model should convert household shopping utterances into structured actions:

```json
{
  "intent": "add_item",
  "items": [
    {
      "name": "tomato",
      "quantity": 0.5,
      "unit": "kg",
      "location": "fridge",
      "notes": "use soon"
    }
  ],
  "language_mix": "hinglish",
  "needs_confirmation": true
}
```

**Training data shape:**

- 100–500 synthetic and manually edited examples.
- Hinglish, Hindi-English, Indian English, and optionally Kannada/Tamil/Telugu transliterated phrases.
- Commands for add, remove, consume, correct, ask, skip, buy, expire, move, find, and compare.
- Include noisy real-user phrasing from parents/neighbours where possible, but do not publish private data.

**Candidate base models:**

- MiniCPM5-1B
- Qwen3-0.6B / Qwen3-1.7B
- Qwen2.5-0.5B/1.5B-Instruct
- LFM2.5-8B-A1B if fine-tuning pipeline is practical

**Evidence to include:**

- Public HF model/adaptor repo.
- Training data card or small public synthetic dataset.
- README section: what was fine-tuned, why, examples before/after, limitations.
- App code path showing the fine-tuned model is actually used for command parsing.

**Fallback if fine-tuning becomes heavy:**

- Publish a small LoRA/adaptor for command classification/entity extraction.
- Keep the rest of the app modular so the fine-tuned model handles one meaningful narrow task rather than the entire system.

---

### 🎨 Off-Brand — Custom UI beyond default Gradio

**Hackathon requirement:** A custom frontend that pushes past the default Gradio look.

**ShopSaathi interpretation:** The app should feel like a household shopping cockpit, not a standard Gradio form.

**Visual language:**

- Warm Indian-home palette.
- Large readable controls for parents.
- Card-based inventory.
- Annotated photo review.
- Fridge/pantry/shelf sections.
- Shopping list pinned like a paper note.
- “Use soon” urgency ribbons.
- Voice-first market mode with large mic button.

**Custom UI elements:**

- Market Lens screen: uploaded image/video frame on left, detected item cards on right.
- Confirm Basket screen: AI-proposed tool calls presented as friendly item cards.
- Home Stock screen: fridge, pantry, cleaning shelf, bathroom, medicine box, and misc sections.
- Find-It Map screen: household location cards and last-seen item history.
- Price Memory screen: last paid, usual range, recent change.
- Agent Trace drawer: compact view of perception → extraction → decision → tool call → confirmation.

**Implementation options:**

- Gradio Blocks with custom CSS.
- Custom HTML components inside Gradio.
- `gr.HTML`, `gr.Image`, custom cards, and CSS grids.
- If using `gr.Server` / custom frontend, document why and how.

**Evidence to include:**

- Screenshots in README.
- Short video showing polished flow.
- Custom CSS file committed in repo.
- Avoid default plain vertical Gradio layout as the main experience.

---

### 🦙 Llama Champion — llama.cpp runtime

**Hackathon requirement:** Your model runs through the llama.cpp runtime.

**ShopSaathi interpretation:** At least one meaningful model path should run through llama.cpp/GGUF.

**Best use:** Use llama.cpp for the text planner / command parser / inventory question-answering model, not necessarily for vision/audio.

**Candidate GGUF models:**

- MiniCPM5-1B GGUF
- LFM2.5-8B-A1B-GGUF
- Qwen3 small GGUF variants
- Qwen2.5 small instruct GGUF variants

**Product usage:**

- Parse shopping commands.
- Generate concise household answers.
- Plan tool calls against inventory.
- Summarize “what to buy” and “what to use soon.”

**Runtime design:**

- Add a `LlamaCppPlannerProvider` behind the same planner interface.
- Keep a standard Transformers provider and a mock provider for tests.
- Add configuration: `PLANNER_BACKEND=llamacpp|transformers|mock`.
- Include GGUF model path instructions in README.

**Evidence to include:**

- README section: “Llama Champion path.”
- Screenshot/log showing llama.cpp provider loaded.
- Space config or local run command.
- Agent trace showing llama.cpp-generated tool plan.

---

### 📡 Sharing is Caring — Open trace

**Hackathon requirement:** Share your agent trace on the Hub for everyone to learn from.

**ShopSaathi interpretation:** Publish anonymized traces showing how the app reasons from input to tool calls.

**Trace schema:**

```json
{
  "trace_id": "sample-market-001",
  "input_type": "image_plus_voice",
  "user_goal": "decide whether to buy visible items",
  "perception": {
    "visible_items": ["tomato", "onion", "coriander"],
    "ocr": [],
    "confidence_notes": ["quantity uncertain"]
  },
  "inventory_context": {
    "already_have": [{"name": "onion", "quantity": 1.5, "unit": "kg"}],
    "low_items": ["tomato"]
  },
  "decision": {
    "buy": ["tomato"],
    "skip": ["onion"],
    "optional": ["coriander"]
  },
  "proposed_tool_calls": [
    {
      "tool": "add_shopping_decision",
      "args": {"item": "tomato", "decision": "buy"}
    }
  ],
  "human_confirmation": "accepted",
  "final_response": "Buy tomatoes. Skip onions; you already have enough."
}
```

**Privacy rules:**

- Do not publish real phone numbers, addresses, bills, private family photos, medical labels, payment details, or exact store details unless intentionally sanitized.
- Use synthetic or redacted images for public traces.
- Publish a small curated dataset of 5–20 traces.

**Where to publish:**

- Hugging Face dataset repo such as `shopsaathi-agent-traces`.
- Link dataset in Space README.

**Evidence to include:**

- Dataset card explaining trace fields.
- App option to export trace JSON.
- Field Notes section explaining failures and corrections.

---

### 📓 Field Notes — Blog/report

**Hackathon requirement:** Write a blog post or report about what you built and what you learned.

**ShopSaathi interpretation:** Write a short product-and-technical report focused on real household usage, small-model fit, multimodal tradeoffs, and failure modes.

**Suggested structure:**

1. Problem: households lack reliable memory for shopping and supplies.
2. Real user: parent/neighbour/family household context.
3. Product loop: before shopping, during shopping, after purchase, home memory.
4. Model stack: vision, audio, OCR, planning, storage, llama.cpp path.
5. What worked: list creation, inventory memory, confirmation, use-soon logic.
6. What failed: quantity estimation, overlapping objects, noisy market audio, labels in bad lighting.
7. Why small models were enough: narrow tasks + confirmation + local DB + rules.
8. Privacy and local-first design.
9. What comes next: household map, shelf memory, price memory, family multi-user mode.
10. Lessons from Codex: what it built, what needed human review, how traces/tests helped.

**Evidence to include:**

- Screenshots.
- Redacted real-user examples.
- Voice command examples.
- Model comparison table.
- Agent traces.
- Honest limitations.

---

## 2. Priority order for ShopSaathi

The bonus quests should be pursued in this order because they align naturally with the product:

1. **Off-Brand** — essential for user trust and judge impression. The app should not look like a default form.
2. **Field Notes** — easy to produce and strongly supports Backyard AI credibility.
3. **Sharing is Caring** — traces are already useful for debugging and Codex evaluation.
4. **Off the Grid** — central to privacy and small-model spirit; may require careful model/runtime choices.
5. **Llama Champion** — very achievable for the text planner if using a GGUF model.
6. **Well-Tuned** — valuable, but should stay narrow: command/entity extraction or item normalization.

## 3. Badge-aware architecture

Design the codebase so the badges are supported by architecture rather than one-off hacks.

```text
shopsaathi/
  app.py
  providers/
    stt/
      base.py
      qwen_asr.py
      parakeet.py
      whisper_baseline.py
      mock.py
    tts/
      base.py
      qwen_tts.py
      moss_tts.py
      kokoro.py
      mock.py
    planner/
      base.py
      llamacpp.py
      transformers.py
      finetuned_parser.py
      mock.py
    vision/
      grounding.py
      segmentation.py
      ocr.py
      mock.py
  inventory/
    schema.py
    store.py
    rules.py
    tools.py
  traces/
    schema.py
    export.py
  ui/
    styles.css
    cards.py
  scripts/
    voice_bench.py
    export_traces.py
    prepare_finetune_data.py
  docs/
    field-notes.md
    codex-build-log.md
    model-table.md
```

## 4. README badge section template

```markdown
## Build Small Bonus Quests

### Off the Grid
This Space does not use cloud model APIs in the submitted path. ASR, planning, OCR/vision, and TTS run through local/open model providers. Household data is stored in SQLite.

### Well-Tuned
The command parser uses a fine-tuned adapter published at: <HF model link>. It maps household shopping utterances into structured inventory actions.

### Off-Brand
The UI uses custom Gradio Blocks, CSS, card layouts, annotated images, and a household inventory dashboard rather than the default Gradio layout.

### Llama Champion
The planner can run through llama.cpp using a GGUF model. See `PLANNER_BACKEND=llamacpp` instructions below.

### Sharing is Caring
Anonymized agent traces are published at: <HF dataset link>. Traces show perception, inventory context, proposed tool calls, human confirmation, and final answer.

### Field Notes
The build report is available at: <blog/report link>. It covers real-user testing, model choices, failures, and lessons learned.
```

## 5. Agent instruction block

Use this block when assigning implementation work to Codex or another coding agent:

```text
Implement ShopSaathi in a badge-aware way for the Build Small Hackathon.

Do not treat bonus quests as decorative. Build explicit support for:
- Off the Grid: no cloud model APIs in the submitted path; local/open model providers only.
- Well-Tuned: a provider slot for a published fine-tuned command parser.
- Off-Brand: custom Gradio Blocks UI with CSS, cards, annotated images, and household dashboard.
- Llama Champion: llama.cpp/GGUF planner provider behind a common interface.
- Sharing is Caring: trace export schema and sample anonymized traces.
- Field Notes: docs/field-notes.md with real-user testing structure.

Keep providers swappable. Include mock providers for tests. Do not commit secrets, personal credit codes, private photos, or private household data.
```
