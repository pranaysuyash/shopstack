# ShopStack / GharStock AI — Product Dossier

## 0. Working Title

**ShopStack**  
**Subtitle:** A small-model shopping copilot and household inventory memory layer.  
**Inventory layer:** GharStock AI.  
**Long-term product sentence:** ShopStack remembers what is already at home, helps a household decide what to buy while shopping, understands purchases from photos, receipts, packets, and short videos, tracks freshness, quantity, price, and location, and answers by voice in Indian-language-first workflows.

---

## 1. Hackathon Context and Constraints

### Main hackathon track

The product should be submitted under **Backyard AI**, because the product is for a real parent, neighbour, family member, or household. The judging criteria for Backyard AI are:

- The problem is specific and real.
- The person actually used it.
- There is an honest fit between the problem and the small-model constraint.
- The Gradio app is polished.

### Core constraints

- **Total model parameters must be ≤ 32B.** Treat this as a product architecture constraint, not an afterthought. The model stack should be documented in the README with parameter counts and licenses.
- **The app must be built on Gradio and hosted as a Hugging Face Space.**
- **Submission includes a short walkthrough video and a social-media post.**

### Bonus quests to design around

- **Off the Grid:** no cloud model APIs; the app runs from local/open models in the Space/runtime.
- **Well-Tuned:** a small fine-tuned model published on Hugging Face.
- **Off-Brand:** custom frontend beyond default Gradio.
- **Llama Champion:** model runs through llama.cpp.
- **Sharing is Caring:** share agent trace on the Hub.
- **Field Notes:** write a report/blog post about what was built and learned.

### Parallel Codex track

Based on the email details shared in the conversation, the Codex track is a parallel track, not the same as the main HF/Gradio judging lane. The product must stand on its own for Backyard AI. Codex should be used to build, test, refactor, document, and review the codebase, with evidence in a public GitHub repo and the Space README.

Codex artifacts to maintain:

- Public GitHub repo.
- Codex-attributed commits or PRs.
- `AGENTS.md` with project rules.
- `docs/codex-build-log.md` describing prompts, accepted changes, rejected changes, test runs, and human review.
- README section: “Built with Codex.”
- Link to the GitHub repo in the Hugging Face Space README.
- Never commit personal credit codes, API keys, HF tokens, screenshots containing secrets, or private household data.

---

## 1B. Credits, Compute, and Account Resources

This project has three separate resource lanes. Agents should not confuse them.

### Available resources

- **Modal credits:** **USD 280 total** available for build-time experimentation. This includes USD 30 already available earlier plus additional hackathon credits.
- **Hugging Face credits:** **USD 20** available for Hub/Space-related compute and hosting experiments.
- **ChatGPT Pro:** available for planning, review, Codex access, product documentation, and agentic coding workflows.
- **Codex hackathon credits:** parallel-track resource for building the public GitHub repo. Keep credit codes private and never commit them.

### How to use Modal credits

Modal credits should be used for work that helps create the submitted artifact but does not become a hidden cloud dependency in the final product path. Good uses:

- fine-tuning the household command parser;
- running STT/TTS/VLM comparisons;
- evaluating object grounding, segmentation, OCR, and short-video frame sampling;
- generating and validating synthetic Indian household utterance data;
- running batch model tests over sample shopping photos, receipts, labels, and voice clips;
- preparing quantized/converted artifacts;
- producing anonymized evaluation traces and reports.

If targeting **Off the Grid**, Modal should not be required at runtime for the submitted Space path. Modal is a build/evaluation/training resource, not the primary user-facing inference dependency.

### How to use Hugging Face credits

HF credits should support Hub-native delivery:

- GPU Space testing for the Gradio app;
- HF Jobs or other Hub compute for fine-tuning/evaluation;
- temporary hosted inference experiments while comparing models;
- storing the published fine-tuned model;
- storing the anonymized trace dataset;
- testing ZeroGPU/GPU Space viability.

If claiming **Off the Grid**, the README must clearly distinguish temporary HF experiments from the submitted local/open model runtime path.

### How to use ChatGPT Pro and Codex

ChatGPT Pro and Codex should be treated as engineering leverage and parallel-track evidence:

- use Codex to scaffold, implement, test, refactor, and review;
- keep Codex-attributed commits or PRs where possible;
- maintain `docs/codex-build-log.md`;
- maintain `AGENTS.md`;
- link the public GitHub repo from the Space README;
- document what Codex built, what the human reviewed, and what was rejected or changed.

Do not put Codex credits, personal codes, tokens, or private household data into the repo, Space, README screenshots, logs, traces, or social posts.

---

## 1A. Bonus Quest Strategy


This addendum turns the Build Small Hackathon bonus quests into explicit product and engineering requirements for ShopStack. The bonus quests are optional, but each can add points. ShopStack should be designed so the extras feel like natural parts of the product rather than badges pasted on at the end.

## 1. Bonus quests as product requirements

### 🔌 Off the Grid — Local-first

**Hackathon requirement:** No cloud APIs. The whole thing runs on the model in front of you.

**ShopStack interpretation:** The user can run the app without sending household photos, receipts, voice notes, inventory, or shopping history to hosted model APIs.

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

**ShopStack interpretation:** Publish a small fine-tuned model or adapter for a narrow household-shopping task.

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

**ShopStack interpretation:** The app should feel like a household shopping cockpit, not a standard Gradio form.

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

**ShopStack interpretation:** At least one meaningful model path should run through llama.cpp/GGUF.

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

**ShopStack interpretation:** Publish anonymized traces showing how the app reasons from input to tool calls.

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

**ShopStack interpretation:** Write a short product-and-technical report focused on real household usage, small-model fit, multimodal tradeoffs, and failure modes.

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

## 2. Priority order for ShopStack

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
Implement ShopStack in a badge-aware way for the Build Small Hackathon.

Do not treat bonus quests as decorative. Build explicit support for:
- Off the Grid: no cloud model APIs in the submitted path; local/open model providers only.
- Well-Tuned: a provider slot for a published fine-tuned command parser.
- Off-Brand: custom Gradio Blocks UI with CSS, cards, annotated images, and household dashboard.
- Llama Champion: llama.cpp/GGUF planner provider behind a common interface.
- Sharing is Caring: trace export schema and sample anonymized traces.
- Field Notes: docs/field-notes.md with real-user testing structure.

Keep providers swappable. Include mock providers for tests. Do not commit secrets, personal credit codes, private photos, or private household data.
```


---

## 2. Product Thesis

Indian homes do not have a reliable memory for groceries and household supplies. People buy vegetables, milk, snacks, staples, cleaning items, toiletries, pet supplies, baby supplies, and medicines from multiple places: kirana stores, street markets, supermarkets, quick-commerce apps, apartment vendors, and local delivery people.

The recurring problems are simple but persistent:

- “Do we already have this?”
- “How much is left?”
- “What is expiring?”
- “What should we buy today?”
- “Can we skip this?”
- “When did we buy detergent?”
- “Where did someone keep the spare toothpaste?”
- “What can we cook from what is already there?”
- “Which items are repeatedly wasted?”
- “Are we paying more than usual?”

ShopStack becomes a household copilot that combines **home memory**, **shopping context**, and **voice/vision interaction**.

The small-model fit is honest: the product does not need a huge general-purpose model. It needs narrow perception, structured extraction, confirmation, inventory math, household memory, and language-friendly interaction.

---

## 3. Product Positioning

### Not a generic grocery list app

A normal grocery app stores manually typed lists. ShopStack sees, hears, remembers, and confirms.

### Not a pure receipt scanner

Receipt scanning is only one input. ShopStack also understands fridge photos, pantry shelves, market photos, packet labels, shopping bags, and voice corrections.

### Not a diet app

Calories and nutrition are supporting signals, not the core. Avoid medical claims.

### Not a live-commerce scraper

Price comparison can start from household price memory and optional manually entered prices. Live e-commerce scraping across multiple platforms is not necessary for the product to be valuable and can create reliability/legal friction.

### Not a fully automated decision-maker

AI proposes. The household confirms. That is the correct experience for small models and family trust.

---

## 4. Core Product Loops

### A. Home memory loop

The app maintains a structured household inventory:

- item name
- category
- quantity
- unit
- storage location
- purchase date
- estimated use-by date
- actual expiry date when visible
- price paid
- source
- photo/crop
- confidence
- status

The household can ask:

- “What is in the fridge?”
- “Do we have milk?”
- “How much atta is left?”
- “What is expiring this week?”
- “What did we buy yesterday?”
- “What should be used first?”

### B. Shopping-list loop

The app turns needs into an intelligent list.

Inputs:

- voice: “We need vegetables for pav bhaji and breakfast items.”
- text: typed list
- inventory state
- family preferences
- upcoming meal/event
- use-soon items
- previous buying patterns

Outputs:

- buy list
- skip list
- optional list
- quantity suggestions
- reason for each item

Example:

> “Buy milk, bread, tomatoes, and capsicum. Skip onions; you already have enough. Use bananas today, so do not buy more unless needed.”

### C. In-market visual loop

The user points camera/takes a photo/records a short clip in the market or store and asks:

- “What from this should I buy?”
- “Do we need this?”
- “What is this vegetable?”
- “Is this on my list?”
- “Which packet is better for us?”
- “Is this enough for 4 people?”
- “Is this near expiry?”
- “What can I make with this?”

The app compares visible items against:

- shopping list
- home inventory
- use-soon items
- family preferences
- storage capacity
- purchase history

Output format:

- buy / skip / maybe
- reason
- suggested quantity
- confidence
- follow-up question when uncertain

Example:

> “I see tomatoes, onions, cauliflower, coriander, and green chilli. Buy tomatoes and coriander. Skip onions because the pantry already has about 1.5 kg. Cauliflower is optional for tomorrow.”

### D. Purchase understanding loop

After shopping, the user uploads:

- one table photo of purchased items
- shopping-bag photo
- receipt photo
- packet label photo
- short video scan
- voice note: “Milk 1 litre, tomato half kilo, bread one pack.”

The app creates proposed inventory updates:

- item cards with crops/boxes
- guessed quantities
- storage suggestions
- expiry/use-by estimates
- price when detected
- confidence
- correction controls

The user confirms or corrects by voice/text.

### E. Freshness and use-soon loop

The app tracks perishable items:

- dairy
- bread
- fruits
- vegetables
- leftovers
- opened packets
- medicines/reminder-only items

The app says:

- “Use bread by tomorrow.”
- “Tomatoes are 4 days old; use soon.”
- “Do not buy bananas today; 5 are already ripe.”
- “Curd expires on June 8.”

It can suggest non-medical, non-diet meal ideas:

- “Use tomatoes, onion, and bread for toast.”
- “Use bananas in milkshake today.”
- “Use leftover rice for lemon rice.”

### F. Price memory loop

The app stores what the household paid before.

Examples:

- “You paid ₹48 for bread last time and ₹55 today.”
- “Tomato price is higher than your last entry.”
- “Milk has been stable.”
- “You usually buy detergent every 35–45 days.”

This avoids brittle live scraping while still giving useful comparative pricing.

### G. Household map / spatial memory loop

This is the spatial layer the product can grow into.

The app learns where items live and where they move:

- fridge top shelf
- fridge door
- freezer
- vegetable drawer
- pantry shelf 1
- pantry shelf 2
- bathroom cabinet
- cleaning shelf
- medicine box
- under-sink storage
- balcony crate
- car boot
- office drawer

Inputs:

- user labels a location photo: “This is the pantry shelf.”
- app detects repeated objects in that location.
- user says: “Toothpaste moved to bathroom cabinet.”
- user scans a room/shelf and asks: “Where is the spare soap?”

Outputs:

- location map
- item heatmap
- last-seen time
- movement history
- probable location
- “look here first” suggestions

Example:

> “The spare toothpaste was last seen in the bathroom cabinet on June 3. Before that it was in the pantry toiletries basket. Check bathroom cabinet first.”

This can later use SLAM-like thinking, but for the Gradio product it can start as user-labeled locations + shelf/fridge images + object-memory events.

---

## 5. Modalities

### 5.1 Voice input

Voice is the main convenience layer, especially for parents and while shopping.

Use cases:

- create shopping list
- ask questions hands-free
- correct detections
- add quantities
- confirm proposed tool calls
- mark consumption
- search inventory
- update location

Example utterances:

- “Aaj kya kharidna hai?”
- “Doodh hai kya ghar pe?”
- “Tamatar half kilo add karo.”
- “Nahi, ye aloo nahi, pyaaz hai.”
- “Bread kal expire ho raha hai kya?”
- “Surf Excel last kab kharida?”
- “Ye packet lena chahiye kya?”
- “Isko fridge ke door mein rakha hai.”

Language targets:

- English
- Hinglish
- Hindi
- optional Kannada/Tamil/Telugu/Marathi/Bengali depending on the real household

Design rule:

- The app should preserve household language, not force everything into formal English.
- Responses should be short enough to hear while shopping.
- Corrections should be easy: “yes,” “no,” “change quantity,” “skip,” “add,” “move to pantry.”

### 5.2 Voice output

Useful in market mode, kitchen mode, and for elder-friendly use.

Response styles:

- short voice answer
- detailed text answer
- spoken confirmation
- warning tone for use-soon/expired items
- multilingual readout

Examples:

- “Buy milk and bread. Skip onions.”
- “This packet is on your list. Check expiry date.”
- “Tomatoes are already at home. Buy only half kilo.”

### 5.3 Still image input

Image inputs are the product’s main perception surface.

Image types:

- vegetable stall photo
- supermarket shelf photo
- fridge photo
- pantry shelf photo
- shopping-bag photo
- purchase-on-table photo
- receipt photo
- packet front photo
- packet back label photo
- expiry/MRP close-up
- item location photo

Image outputs:

- detected item cards
- annotated photo
- cropped item thumbnails
- “buy / skip / maybe” overlay
- location heatmap
- use-soon badges

### 5.4 Short video input

Short video helps when the market shelf or fridge cannot fit in one photo.

Video types:

- pan across a vegetable stall
- pan across a supermarket shelf
- fridge scan
- pantry scan
- location scan while searching for an item

Processing approach:

- sample frames
- detect repeated items
- merge duplicate detections
- preserve timestamp/frame reference
- answer the user’s question over the scan

Video questions:

- “What from this do I need?”
- “Where is the ketchup?”
- “Which items here are on my list?”
- “What did I miss?”
- “What has moved since last time?”

### 5.5 Object detection and segmentation

Detection answers “what is where?”  
Segmentation helps turn visible products into manipulable inventory cards.

Uses:

- crop grocery items from purchase photos
- create clickable cards
- separate foreground from messy background
- identify shelf zones
- mark fridge compartments
- visually show “these are the items I’m adding”
- produce before/after correction experience

Important behavior:

- detection confidence must be visible
- ambiguous items must ask questions
- user correction must be first-class

### 5.6 OCR and document extraction

OCR/document extraction is important for packaged products and bills.

Fields:

- brand
- product name
- weight/volume
- MRP
- price paid
- expiry date
- manufacturing date
- batch number
- ingredients
- nutrition label
- receipt line items
- store name
- purchase date
- total

Use cases:

- scan receipt to add many items
- scan packet label for expiry
- scan nutrition label for approximate calories
- scan invoice/bill for price memory

### 5.7 Image generation and image editing

This should support utility, not distract from it.

Useful image/edit outputs:

- clean annotated shopping photo
- shelf/fridge map with item labels
- “use-soon” visual cards
- item icons for inventory
- family-friendly shopping checklist image
- printable pantry/fridge label sheet
- visual “where it lives” map
- monthly waste/price report card

Image editing should not be used to fake product evidence. It should only create helpful visualizations and labels.

### 5.8 Text and structured data

The product lives or dies by structured data quality.

Everything perceptual should become structured state:

- shopping list item
- inventory lot
- storage location
- purchase event
- price event
- expiry event
- movement event
- consumption event
- user correction

The LLM should be treated as a planner/parser that proposes structured tool calls, not as the database itself.

---

## 6. Use Case Catalog

### Before shopping

- generate shopping list from inventory
- remove items already at home
- warn about use-soon items
- suggest quantities
- plan for meals/events
- remember recurring staples
- create a list for a specific store/market

### While shopping

- identify unfamiliar vegetables/products
- compare visible items against list
- check whether an item is needed
- suggest quantity
- warn when similar item is already at home
- read expiry date/MRP from packet
- identify cheaper/familiar brand from price history
- answer in voice

### After shopping

- add purchase from table photo
- add purchase from receipt
- add purchase from voice summary
- segment items into inventory cards
- confirm quantities
- suggest storage location
- estimate use-by dates
- update price memory

### Cooking and meal planning

- “What can I make now?”
- “What should I use first?”
- “Breakfast for 4?”
- “Lunch using leftover rice?”
- “What should not be bought because it will go waste?”

### Household supplies

- track detergent, soap, toothpaste, shampoo, tissue, garbage bags
- estimate next buy from usage interval
- compare price paid last time
- find storage location

### Medicine and health-adjacent inventory

Only inventory/reminder behavior:

- “Where is the thermometer?”
- “Do we have ORS?”
- “This strip expires in August.”
- “Add cough syrup to medicine box.”

Avoid dosage, diagnosis, treatment advice, or medical recommendations.

### Waste reduction

- use-soon dashboard
- repeated-waste report
- “don’t buy more” warnings
- stale inventory cleanup
- old item reminders

### Budgeting

- weekly grocery spend
- price changes across purchases
- category spend
- suspicious jumps
- manual paid-price entry when OCR fails

### Family coordination

- “Mom bought milk already.”
- “Do not buy onions.”
- “Dad moved detergent to balcony shelf.”
- shared list export
- WhatsApp-ready shopping list

### Spatial memory

- “Where is the extra oil packet?”
- “What is in the top shelf?”
- “What moved from fridge to pantry?”
- “Show all items last seen in bathroom cabinet.”

---

## 7. Data Model

### 7.1 Item catalog

```python
ItemCatalog:
    canonical_name: str
    aliases: list[str]
    category: str
    default_unit: str
    typical_storage: list[str]
    typical_shelf_life_days: dict[str, int]
    is_perishable: bool
    nutrition_reference: dict | None
    notes: str | None
```

### 7.2 Inventory lot

```python
InventoryLot:
    lot_id: str
    canonical_name: str
    display_name: str
    category: str
    quantity: float
    unit: str
    storage_location_id: str
    purchase_date: date
    estimated_use_by_date: date | None
    label_expiry_date: date | None
    opened_date: date | None
    price_paid: float | None
    currency: str
    source_event_id: str
    confidence: float
    image_crop_path: str | None
    status: str  # active, low, used, expired, discarded
```

### 7.3 Purchase event

```python
PurchaseEvent:
    event_id: str
    timestamp: datetime
    source_type: str  # photo, video, receipt, voice, manual
    raw_text: str | None
    source_file_path: str | None
    detected_store: str | None
    total_amount: float | None
    confirmed: bool
```

### 7.4 Detection event

```python
DetectionEvent:
    detection_id: str
    event_id: str
    frame_id: str | None
    bounding_box: tuple | None
    mask_path: str | None
    crop_path: str | None
    predicted_name: str
    confidence: float
    user_corrected_name: str | None
    final_name: str | None
```

### 7.5 Shopping list item

```python
ShoppingListItem:
    list_item_id: str
    canonical_name: str
    requested_quantity: float | None
    unit: str | None
    priority: str  # must_buy, optional, avoid_buying
    reason: str
    status: str  # pending, seen, bought, skipped
    linked_inventory_lots: list[str]
```

### 7.6 Household location

```python
HouseholdLocation:
    location_id: str
    name: str
    parent_location_id: str | None
    location_type: str  # fridge, pantry, shelf, cabinet, room, drawer
    photo_path: str | None
    notes: str | None
```

### 7.7 Item movement event

```python
ItemMovementEvent:
    movement_id: str
    lot_id: str
    from_location_id: str | None
    to_location_id: str
    timestamp: datetime
    source: str  # user_voice, image_scan, manual
    confidence: float
```

### 7.8 Price history

```python
PriceHistory:
    price_event_id: str
    canonical_name: str
    quantity: float
    unit: str
    price: float
    store: str | None
    date: date
    source_event_id: str
```

---

## 8. Tool-Calling Contracts

The LLM proposes tool calls. The app shows them before applying changes where user confirmation matters.

```python
def create_shopping_list(goal: str, household_id: str) -> list[ShoppingListItem]: ...

def get_inventory(query: str, filters: dict | None = None) -> list[InventoryLot]: ...

def propose_purchase_from_image(image_path: str, context: dict) -> list[dict]: ...

def propose_purchase_from_receipt(image_path: str, context: dict) -> list[dict]: ...

def add_inventory_item(
    canonical_name: str,
    display_name: str,
    quantity: float,
    unit: str,
    storage_location_id: str,
    purchase_date: str,
    estimated_use_by_date: str | None,
    label_expiry_date: str | None,
    price_paid: float | None,
    source_event_id: str,
    confidence: float,
) -> InventoryLot: ...

def update_inventory_item(lot_id: str, updates: dict) -> InventoryLot: ...

def consume_item(canonical_name: str, quantity: float, unit: str, reason: str | None = None) -> dict: ...

def move_item(lot_id: str, to_location_id: str) -> ItemMovementEvent: ...

def get_expiring_items(days: int = 3) -> list[InventoryLot]: ...

def get_next_buy_list(days: int = 7) -> list[ShoppingListItem]: ...

def compare_price(canonical_name: str, quantity: float, unit: str, current_price: float) -> dict: ...

def estimate_shelf_life(canonical_name: str, storage_location_id: str, opened: bool = False) -> dict: ...

def estimate_calories(canonical_name: str, quantity: float, unit: str) -> dict: ...

def find_item_location(canonical_name: str) -> dict: ...
```

Safety rules:

- No direct DB mutation from ambiguous model outputs.
- All low-confidence detections require user confirmation.
- Expiry/date extraction must distinguish “label seen” vs “estimated.”
- Calories are approximate.
- Price comparison must state the source: household memory, OCR, manual entry, or external data.
- Medicine support is inventory-only.

---

## 9. Model Stack Options Under 32B

### Stack A: Unified multimodal-heavy stack

Purpose: fewer moving pieces, strong multimodal product feel.

- Gemma 4 12B-it — image/audio/video/text understanding and structured reasoning.
- NuExtract3 4B — receipts, packet labels, structured extraction.
- FLUX.2-klein-4B or Qwen-Image-Edit — visual report cards, shelf maps, annotated assets.
- MiniCPM5-1B — lightweight planner / tool assistant / fallback local reasoning.

Approximate total: around 21B before counting any additional segmentation model. Keep the README honest by listing exact parameter counts from model cards and selected files.

### Stack B: Modular local stack

Purpose: each modality gets a focused model.

- Swappable STT provider — evaluate Qwen3-ASR-1.7B, NVIDIA Parakeet/Nemotron 0.6B streaming ASR, Voxtral Mini Realtime, SenseVoiceSmall, and Whisper large-v3-turbo as a baseline.
- Qwen3-4B-Instruct-2507 — tool planning, structured parsing, multilingual text.
- NuExtract3 — receipt/label extraction.
- Marlin-2B — short video understanding when needed.
- FLUX.2-klein-4B — image generation/editing for visual outputs.
- Segmentation model with compatible license and known parameter count.

Approximate total with the listed models before segmentation: about 14.8B if Qwen3-4B is used, leaving room for segmentation and small helpers. Exact count must be documented.

### Stack C: llama.cpp-aligned stack

Purpose: target Llama Champion / local-first story.

- LFM2.5-8B-A1B GGUF or MiniCPM5-1B GGUF for text/tool planning.
- Swappable ASR provider for voice; do not hardcode Whisper as the only path.
- Lightweight OCR and segmentation components.
- Avoid large image-generation model unless runtime supports it comfortably.

This is the best route for the local-first/llama.cpp narrative.

### License cautions

- For the hackathon artifact, non-commercial or research-only grounding/segmentation/voice models may be used when they materially improve the experience. The README and Space card must disclose license scope clearly, and commercial use would require replacing or relicensing those modules.
- Prefer Apache-2.0/MIT-compatible models when possible.
- Do not make production claims if any core model is research-only/non-commercial.

---

## 10. Product Screens

### 10.1 Home

- “What should we buy?” voice button
- “Scan shelf/fridge” upload
- “Add purchase” upload
- use-soon cards
- next-buy cards
- recent movements

### 10.2 Shopping List

- voice/text goal input
- list grouped by must-buy / optional / skip
- reasons for each item
- quantity suggestions
- export to WhatsApp-style text

### 10.3 Market Lens

- image/video upload
- voice question
- visible item list
- buy/skip/maybe decision
- explanation
- shopping-list match
- inventory match

### 10.4 Add Purchase

- table/bag/receipt/packet upload
- voice note
- detected item cards
- crop/box/mask view
- quantity editor
- storage editor
- expiry editor
- confirm changes

### 10.5 Inventory

- fridge
- pantry
- household supplies
- bathroom/toiletries
- cleaning
- medicine box inventory-only
- low stock
- use soon
- expired
- search

### 10.6 Ask

- voice/text chat
- structured answer cards
- “show evidence” option
- tool-call trace option

### 10.7 Household Map

- location list
- last-seen item list
- item movement history
- heatmap view
- “where is X?” search
- scan/update location

### 10.8 Field Notes

- who used it
- real household problem
- sample interactions
- what worked
- what failed
- corrections made
- small-model fit
- privacy decisions
- parameter count table
- model licenses

---

## 11. Spatial Memory / Household Map

### Product idea

The app gradually builds a household map of where products are usually kept and where they move.

This does not require full robotic SLAM at the beginning. The useful product starts from:

- user-defined zones
- shelf/fridge/pantry photos
- repeated scans
- item-location events
- voice updates

### Spatial data model

Locations form a tree:

```text
Home
  Kitchen
    Fridge
      Door shelf
      Top shelf
      Vegetable drawer
      Freezer
    Pantry
      Top shelf
      Middle shelf
      Spice box
  Bathroom
    Cabinet
    Under sink
  Balcony
    Cleaning shelf
  Bedroom
    Medicine drawer
```

### Heatmap logic

A heatmap is not just visual. It can be generated from events:

- last seen in location
- frequency of item appearing in location
- confidence from image detection
- recency decay
- user corrections

Example answer:

> “The extra toothpaste is most likely in Bathroom Cabinet with 0.72 confidence. It was last seen there two scans ago. Second likely location: Pantry toiletries basket.”

### Movement tracking

Movements can be explicit:

> “Moved oil to pantry shelf.”

Or inferred:

- item appears in pantry after being previously seen in shopping bag
- item no longer appears in fridge scan but appears in table scan
- user confirms movement

### Future SLAM-like direction

If this becomes a mobile app later, the product can use:

- AR room scanning
- visual-inertial mapping
- object landmarks
- shelf zone recognition
- persistent spatial anchors
- “guide me to item” AR overlays

For the hackathon Space, represent this as a **household spatial memory layer** with photos, zones, and item events.

---

## 12. Judging Alignment

### Backyard AI strength

The product is for a real household, not a generic abstract user. It can be tested with the builder’s parents/neighbours immediately.

Evidence to collect:

- real shopping list before using the app
- real fridge/pantry photo
- real purchase photo
- real correction transcript from parent/neighbour
- “before/after” time or confusion reduction
- number of items correctly added
- number of corrections required
- one real quote from user

### Small-model fit

This is not a giant-model problem. The product needs:

- bounded object recognition
- structured extraction
- voice transcription
- simple planning
- database updates
- household-specific memory
- clear uncertainty

The app should show that small models work well when supported by:

- confirmation UI
- structured schemas
- tool calls
- household context
- visible confidence
- correction loop

### Gradio polish

Use Gradio Blocks with a custom layout:

- large mobile-friendly cards
- item crops
- buy/skip badges
- fridge/pantry tabs
- voice buttons
- sticky confirm panel
- clear empty states
- custom theme/CSS
- annotated images
- export buttons

### Bonus quest targeting

Most realistic badges:

- **Off-Brand:** custom UI.
- **Field Notes:** product report.
- **Sharing is Caring:** Codex/agent trace or build trace.
- **Llama Champion:** if the planner runs through llama.cpp.
- **Off the Grid:** if no cloud model APIs are used at runtime.
- **Well-Tuned:** if a small item-normalization or quantity-extraction model is fine-tuned and published.

---

## 13. First Shipped Slice

The first shipped slice should feel like the complete product loop, even if the long-term product has many more layers.

It should include:

1. Household inventory database.
2. Shopping list from voice/text.
3. “Do I need this?” over a shop/market photo.
4. Purchase photo or receipt to proposed inventory additions.
5. Voice/text correction.
6. Use-soon and next-buy intelligence.
7. Spatial location field for each item.
8. A simple household map screen with locations and last-seen items.
9. Field Notes page.
10. Parameter/license table.

---

## 14. Agent-Ready Build Instructions

Use this with Codex or another coding agent.

```text
Build a Hugging Face Spaces Gradio app called ShopStack.

Product:
A small-model shopping copilot for Indian homes. It remembers household inventory, helps create shopping lists, answers “do I need this?” from market/shelf photos, adds purchases from photos/receipts/voice, tracks freshness and quantities, and maintains a household location map for where items are stored.

Hackathon constraints:
- Gradio app hosted as a Hugging Face Space.
- Total model parameters under 32B; document parameter counts in README.
- Prefer no cloud model APIs in runtime.
- Backyard AI track: real household user, measurable usefulness, polished Gradio app.
- Include a short walkthrough video link and social post link placeholders.
- Keep Codex track evidence separate in docs/codex-build-log.md.
- Never commit secrets, tokens, credit codes, or private household photos.

Core screens:
1. Home dashboard: use-soon, next-buy, quick voice ask.
2. Shopping List: voice/text input, inventory-aware list, buy/skip/optional reasons.
3. Market Lens: upload image/short video + voice/text question; answer what to buy/skip based on list and inventory.
4. Add Purchase: upload purchase photo/receipt + voice note; show item cards with crops, quantities, storage, expiry, confidence; confirm updates.
5. Inventory: fridge, pantry, household, toiletries, cleaning, medicine inventory-only.
6. Household Map: locations, last-seen items, move item, find item.
7. Ask ShopStack: voice/text chat over inventory with visible tool trace.
8. Field Notes/About: model table, constraints, real user story, limitations.

Architecture:
- Python package structure with app.py and modules.
- SQLite database.
- Pydantic schemas for inventory, shopping list, events, detections, locations.
- Model wrapper interfaces with mock implementations for development.
- Tool-call planner that proposes structured operations before mutation.
- Tests for database logic, date parsing, quantity normalization, shopping-list reasoning, and movement/location logic.

UI:
- Use gr.Blocks.
- Custom CSS.
- Mobile-friendly large cards.
- Item crop thumbnails.
- Buy/skip/maybe badges.
- Confirmation screen for proposed inventory changes.

Deliverables:
- app.py
- requirements.txt
- README.md with Space metadata, product description, model parameter table, license notes, Codex track notes.
- AGENTS.md
- docs/codex-build-log.md
- docs/field-notes.md
- tests/
- sample_data/ with synthetic examples only.
```

---

## 15. README Structure

```markdown
# ShopStack — Small-Model Shopping Copilot for Indian Homes

## What it does

## Who it is for

## Backyard AI story

## Product loop

## Screens

## Models and parameter counts

| Component | Model | Params | License | Role |
|---|---:|---:|---|---|

## Why this fits ≤32B

## Local/off-grid behavior

## How to run locally

## How to deploy to Hugging Face Spaces

## Codex track evidence

## Privacy and safety

## Limitations

## Field notes

## Social/walkthrough links
```

---

## 16. Safety and Trust

### Food and nutrition

- calories are approximate
- nutrition estimates are not medical advice
- label OCR is preferred when available
- portion estimates should be visibly uncertain

### Medicines

- inventory/reminder only
- no diagnosis
- no dosage advice
- no treatment recommendation
- show a “verify with doctor/pharmacist” disclaimer

### Purchases and pricing

- do not claim live best price unless actually sourced
- price memory is household-specific
- show source of price comparison

### Privacy

- household photos can contain private information
- default should be non-persistent uploads unless saved by user
- sample data should be synthetic
- README should disclose storage behavior

### Model uncertainty

- low-confidence detections ask questions
- expiry estimates distinguish label-read vs estimated
- all DB changes are reviewable

---

## 17. Differentiation

Compared with a generic inventory app:

- voice-first correction
- image/video market understanding
- item cards from segmentation
- household-specific price and location memory
- Indian-language workflow
- inventory-aware shopping decisions

Compared with a generic vision chatbot:

- persistent inventory state
- tool calls
- structured household memory
- use-soon/next-buy logic
- spatial location map

Compared with a retail/shop assistant:

- designed for homes, not store owners
- covers food, cleaning, toiletries, household supplies, and medicine inventory
- helps decide whether to buy, not just what is on the shelf

---

## 18. Walkthrough Story

A strong walkthrough should show one household problem becoming simpler.

Storyline:

1. Parent asks: “What should we buy today?”
2. App checks inventory and creates a list.
3. In the market, user shows a vegetable stall and asks: “What from this do we need?”
4. App says buy tomatoes/coriander, skip onions.
5. Back home, user uploads purchase photo and speaks corrections.
6. App adds items to fridge/pantry with dates and quantities.
7. App shows “use soon” and “next buy.”
8. User asks: “Where is the spare toothpaste?”
9. App opens household map and says where it was last seen.

The video should make the app feel like a real household memory, not a toy classifier.

---

## 19. Field Notes Questions

Use these questions for the report:

- Who used it?
- What household problem did they have before?
- What did they try to do with the app?
- Which inputs worked best: voice, image, receipt, video?
- What did the model get wrong?
- How many corrections were needed?
- What was faster or clearer after using it?
- What did the user ask for next?
- Why were small models enough?
- What would improve with a fine-tuned item catalog?

---

## 20. Final Product Decision

Build **ShopStack**, with **GharStock** as the inventory and household-memory layer.

The most compelling promise:

> ShopStack remembers your home while you shop.

The strongest product loop:

> Ask what to buy → scan what you see → decide buy/skip → add purchases → track use-soon/next-buy → find where things are kept.

The most important design principle:

> AI proposes; the household confirms; the database becomes trusted memory.
---

## 17. Audio + License Addendum


## 1. Hackathon license stance

For the Build Small Hackathon submission, non-commercial or research-only models may be used when they materially improve the experience, especially for grounding, segmentation, image understanding, or voice.

The README and Space card must disclose the scope clearly:

> Some model weights are used under research/non-commercial terms for hackathon evaluation. Commercial use would require replacing or relicensing those modules.

This means the product can use attractive research models such as LocateAnything-style grounding or RMBG-style segmentation for the hackathon artifact, while still documenting commercially compatible alternatives for a later production path.

Do not hide license limits. Treat them as transparent product notes, not blockers.

## 2. Do not anchor the voice layer to Whisper

Whisper remains a useful baseline, but ShopStack should not be described as “using Whisper for voice.” Voice is central to the product: parents, neighbours, and household members should be able to ask while shopping, correct detections hands-free, and hear short answers.

The product should be described as having a swappable voice layer:

> ShopStack includes a model-swappable voice layer. The submitted build benchmarks current small STT/TTS models and uses the best-performing local stack for household shopping commands.

## 3. Voice requirements for ShopStack

The voice layer should optimize for:

- short household commands
- noisy market/shop environments
- Indian English, Hinglish, Hindi, and optionally Kannada/Tamil/Telugu/Marathi/Bengali
- correction phrases
- low latency
- local/off-grid operation when possible
- ≤32B total model parameter accounting
- Gradio/Hugging Face Space deployability

Representative utterances:

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
```

## 4. STT model candidates to evaluate

### Qwen3-ASR-1.7B

Strong candidate for current small-model ASR. It should be tested for short Indian household commands, Hinglish, Hindi, and correction utterances.

Use cases:

- shopping list creation
- quantity corrections
- inventory search
- packet/list commands

### NVIDIA Nemotron / Parakeet 0.6B streaming ASR

Attractive for market-mode and near-live shopping interaction because the model family is streaming-oriented and small. Test install/runtime friction in Spaces before relying on it.

Use cases:

- quick spoken market questions
- short confirmations
- low-latency voice flows

### Mistral Voxtral Mini Realtime

Useful to test if we want voice-agent behavior rather than only plain transcription. Potentially good for direct speech understanding and voice command interpretation.

### FunAudioLLM SenseVoiceSmall

Worth testing as a compact Whisper alternative. It may be useful for short commands, real-time interaction, and richer audio cues.

### VibeVoice ASR / Cohere Transcribe / Granite Speech

Secondary evaluation candidates. Include them if setup and runtime are comfortable.

### Whisper large-v3-turbo

Keep as the reliable baseline, not the default ambition. If newer models fail install/runtime/quality tests, Whisper can still carry the voice layer.

## 5. TTS model candidates to evaluate

### OpenMOSS MOSS-TTS-v1.5

Strong current multilingual TTS candidate. Good fit if voice output needs warmth and language coverage.

### VoxCPM2

Attractive because OpenBMB is an anchor sponsor and the model family aligns with the hackathon ecosystem. Good candidate for multilingual voice and voice-design behavior.

### Qwen3-TTS 0.6B / 1.7B

Strong if we want a Qwen-centered stack. The 0.6B version is appealing for parameter budget; the 1.7B version should be tested for better voice quality.

### Higgs Audio v3 TTS 4B

Interesting for expressive voice-agent output. Use only if setup and latency are acceptable.

### Kokoro-82M

Tiny, useful fallback. Not the most ambitious, but good for fast local responses and reliability.

### CosyVoice / other FunAudioLLM TTS

Evaluate if multilingual output quality and deployment are good.

## 6. Voice-to-voice architecture

```text
Voice input
  → STT provider
  → intent parser / tool-call planner
  → inventory + shopping-list + household-map tools
  → short answer generator
  → TTS provider
```

Voice should not be a gimmick. The product feature is hands-free shopping conversation.

Example:

User says:

> Yeh packet lena chahiye kya?

The system checks:

- visible item from image/video
- shopping list
- home inventory
- expiry/OCR if visible
- price memory if available

Then answers:

> Agar yeh bread hai, lo. Bread list mein hai. Expiry date check kar lo — photo mein clear nahi dikh raha.

## 7. ShopStack Voice Bench

Create a small benchmark script and report so the voice choice is evidence-based.

Suggested file:

```text
scripts/voice_bench.py
```

Benchmark inputs:

- recorded voice clips from the actual household user
- clean microphone clips
- noisy market-like clips
- text fixtures for expected intent

Score STT on:

- transcription accuracy
- intent preservation
- Hindi/Hinglish handling
- noisy audio tolerance
- latency
- memory use
- install/runtime pain
- Space compatibility

Score TTS on:

- clarity
- pronunciation of Indian grocery words and names
- Hinglish comfort
- warmth/trust
- speed
- install/runtime pain
- Space compatibility

## 8. Provider interfaces for agents

Do not hardcode a single speech model.

Implementation should include:

```text
shopsaathi/voice/base.py
shopsaathi/voice/providers/mock_stt.py
shopsaathi/voice/providers/qwen_asr.py
shopsaathi/voice/providers/parakeet_asr.py
shopsaathi/voice/providers/whisper_baseline.py
shopsaathi/voice/providers/mock_tts.py
shopsaathi/voice/providers/kokoro_tts.py
shopsaathi/voice/providers/qwen_tts.py
shopsaathi/voice/providers/moss_tts.py
scripts/voice_bench.py
```

Provider interface sketch:

```python
class STTProvider:
    name: str
    model_id: str
    parameter_count: int | None
    license: str | None

    def transcribe(self, audio_path: str, language_hint: str | None = None) -> dict:
        ...

class TTSProvider:
    name: str
    model_id: str
    parameter_count: int | None
    license: str | None

    def synthesize(self, text: str, language_hint: str | None = None, voice: str | None = None) -> str:
        ...
```

The app should support environment or config selection:

```text
SHOPSAATHI_STT_PROVIDER=qwen_asr
SHOPSAATHI_TTS_PROVIDER=moss_tts
```

Tests should use mock providers.

## 9. README update

Add a dedicated section:

```markdown
## Voice model evaluation

ShopStack does not assume Whisper is the best voice layer. The submitted build includes a swappable STT/TTS provider interface and a small household-shopping voice benchmark. Whisper is retained as a baseline, while Qwen3-ASR, Parakeet/Nemotron, Voxtral, SenseVoice, MOSS-TTS, VoxCPM2, Qwen3-TTS, and Kokoro are considered or tested based on deployability.
```

## 10. Updated model philosophy

The product should say:

> ShopStack is model-modular. Perception, speech, reasoning, OCR, segmentation, image editing, and TTS can be swapped as the small-model ecosystem improves.

Not:

> ShopStack uses Whisper and a chatbot.

This matters because the hackathon is partly about showing how capable the new small-model ecosystem is.

