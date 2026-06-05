# ShopStack Credits, Compute, and Parallel Track README

This README explains how the available credits and account resources should be used for ShopStack without confusing the main Build Small submission, the optional bonus quests, and the parallel Codex track.

## Project

**ShopStack** — a small-model shopping copilot and household inventory memory layer.

ShopStack helps a household before, during, and after shopping: voice-built shopping lists, home inventory memory, market/shelf photo or short-video understanding, buy/skip decisions, receipt/label OCR, item grounding, expiry and quantity tracking, and fridge/pantry/household location memory.

## Available resources

| Resource | Amount / status | Intended use | Runtime dependency? |
|---|---:|---|---|
| Modal credits | USD 280 total | GPU experiments, fine-tuning, model evals, batch processing, quantization/conversion, trace generation | No, not if claiming Off the Grid |
| Hugging Face credits | USD 20 | GPU Space testing, HF Jobs, model/dataset hosting, temporary inference experiments | Prefer no for Off the Grid path |
| ChatGPT Pro | Available | product planning, architecture, review, Codex workflows, documentation | No |
| Codex credits | Hackathon parallel-track credit | build/test/refactor/document public repo using Codex | No direct product dependency |

## Main hackathon lane vs Codex lane

### Main Build Small / Backyard AI lane

The product must stand on its own as a useful Gradio Space for a real household user. The primary judging story should be:

- real household shopping/inventory pain;
- small-model fit under the 32B total-parameter constraint;
- local/open model architecture;
- polished Gradio app;
- real user testing and Field Notes.

### OpenAI Codex parallel lane

Codex is a separate evidence lane. It should be used to build and improve the product, not define the product. Maintain:

- public GitHub repo;
- Codex-attributed commits or PRs where possible;
- `AGENTS.md`;
- `docs/codex-build-log.md`;
- README section: `Built with Codex`;
- link to GitHub repo from the Space README.

Never commit credit codes, API keys, HF tokens, private household photos, raw voice clips, exact addresses, personal phone numbers, or private receipts.

## Modal usage plan

Use Modal credits for build-time and research-time work:

1. **Voice model bench**
   - Compare Qwen3-ASR, Parakeet/Nemotron, Voxtral, SenseVoice, Whisper baseline.
   - Compare MOSS-TTS, VoxCPM2, Qwen3-TTS, Higgs Audio, Kokoro fallback.
   - Test Hinglish and Indian household shopping phrases.

2. **Vision and OCR bench**
   - Evaluate object grounding/detection on grocery, shelf, fridge, pantry, receipt, and packet-label images.
   - Test segmentation/crop quality for item cards.
   - Test OCR on expiry, MRP, weight, nutrition labels, receipts.

3. **Well-Tuned model**
   - Generate or curate household command examples.
   - Fine-tune a small parser for Indian household shopping utterances.
   - Evaluate JSON/tool-call accuracy.

4. **Trace generation**
   - Run anonymized sample scenarios.
   - Export traces for Sharing is Caring.

Modal should not be required to run the submitted app path if claiming Off the Grid.

## Hugging Face credit usage plan

Use HF credits for Hub-native delivery:

1. Test the Gradio Space with GPU/ZeroGPU where useful.
2. Publish the fine-tuned parser model.
3. Publish the household utterance dataset if appropriate.
4. Publish anonymized agent traces as a dataset.
5. Host screenshots, cards, and README assets.

Keep the Space README explicit about which models are local/open and whether any temporary hosted experiments were used outside the submitted path.

## Well-Tuned target

Fine-tune a small command parser for Indian household shopping utterances. The task is not general chat. It is structured conversion:

```json
{
  "intent": "add_item",
  "item_raw": "aadha kilo tamatar",
  "canonical_item": "tomato",
  "quantity": 0.5,
  "unit": "kg",
  "location": "fridge",
  "tool_call": "add_inventory_item"
}
```

Target intents:

- add item;
- skip item;
- remove from shopping list;
- correct detected item;
- correct quantity;
- correct price;
- consume item;
- move item;
- find item;
- check expiry;
- ask next buy;
- ask what can be cooked;
- ask whether to buy visible item.

Include Indian household item vocabulary and variants: tamatar/tomato, aloo/potato, pyaaz/onion, doodh/milk, dahi/curd, atta, chawal/rice, dal, dhaniya/coriander, mirchi/chilli, bread/pav, Surf Excel/detergent, Vim/dishwash, Harpic/toilet cleaner, Colgate/toothpaste, etc.

## Llama Champion target

Run the parser/planner through llama.cpp with a GGUF model. Good candidates:

- `unsloth/LFM2.5-8B-A1B-GGUF` — strong local edge-style planner/parser candidate.
- `unsloth/Llama-3.2-3B-Instruct-GGUF` — small, practical parser candidate.
- `unsloth/gpt-oss-20b-GGUF` — stronger but heavier.

The app should expose this clearly in README and logs: which GGUF file, what quantization, how llama.cpp was invoked, and which task it performs.

## Sharing is Caring target

Export anonymized agent traces, not private raw household data. A good trace contains:

```json
{
  "scenario": "market_photo_plus_voice",
  "redacted_request": "Do we need this item?",
  "detected_items": ["bread", "milk", "tomato"],
  "inventory_context": {"bread": "not_available", "milk": "low", "tomato": "available"},
  "decision": "buy bread and milk, skip tomato",
  "proposed_tool_calls": [{"tool": "add_to_shopping_list", "args": {"item": "bread"}}],
  "confirmation": "accepted",
  "final_answer": "Buy bread and milk. Skip tomato."
}
```

Redact names, phone numbers, addresses, receipts, prices that identify a person/store, raw voice, and private photos. Use synthetic or heavily anonymized examples for public datasets.

## Submission notes

For the credit claim form, describe the project as:

> ShopStack — a small-model shopping copilot and household inventory memory layer. It helps Indian households create shopping lists by voice, check what is already at home, scan market/shelf/purchase photos or short videos, identify household items, estimate quantity/expiry, suggest buy/skip decisions, and update a fridge/pantry/household inventory. The app is planned as a Gradio Hugging Face Space using local/open models under the 32B parameter limit, with voice, vision, OCR, item grounding/segmentation, inventory tool calls, price/freshness memory, and a custom UI.

For the link field:

> No public link yet — Space and GitHub repo coming during the hackathon window.
