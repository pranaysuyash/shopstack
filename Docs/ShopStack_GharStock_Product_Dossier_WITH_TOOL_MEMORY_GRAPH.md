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
---

## Appendix — Model Experimentation and Benchmarking Policy


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


---

# ShopStack — Hugging Face, Gradio, Hub, Spaces, Models, Datasets, and Deployment Operations Guide

This guide is for agents and collaborators building **ShopStack** for the Hugging Face Build Small Hackathon. It explains how to use Hugging Face and Gradio as first-class product infrastructure, not merely as a final hosting target.

ShopStack is a Gradio-based Hugging Face Space, supported by Hub model repos, dataset repos, trace datasets, fine-tuned models, benchmark artifacts, and field notes.

---

## 1. Why Hugging Face and Gradio matter for ShopStack

The hackathon requires a Gradio app hosted as a Hugging Face Space. Hugging Face Spaces are Git-backed repositories; when code changes are pushed, the Space rebuilds and restarts automatically. Gradio Spaces are configured by choosing `gradio` as the Space SDK and setting the relevant YAML metadata in `README.md`.

For ShopStack, Hugging Face should hold:

- The public Gradio Space.
- The Space README / product card.
- The model registry and model cards for any fine-tuned model.
- The dataset repo for anonymized agent traces.
- The dataset repo for household command-parser training/evaluation examples.
- Benchmark result artifacts.
- Field Notes / report links.

---

## 2. Repository map

Recommended public artifact layout:

```text
GitHub repo: shopstack-ai/shopstack
  app.py
  requirements.txt
  README.md
  AGENTS.md
  src/shopstack/
  tests/
  configs/model_registry.yaml
  docs/
    codex-build-log.md
    field-notes.md
    model-benchmark-report.md
    privacy-and-redaction.md
    hf-space-submission-checklist.md

Hugging Face Space: build-small-hackathon/shopstack
  app.py
  requirements.txt
  README.md
  src/shopstack/...
  sample_assets/...

Hugging Face model repo: <user-or-org>/shopstack-command-parser
  adapter/model files
  tokenizer/config
  README.md model card
  eval_results.json

Hugging Face dataset repo: <user-or-org>/shopstack-household-commands
  train.jsonl
  eval.jsonl
  README.md dataset card

Hugging Face dataset repo: <user-or-org>/shopstack-agent-traces
  traces.jsonl
  README.md dataset card
```

Use the Build Small organization Space if hackathon rules require it; keep GitHub public for the Codex parallel track.

---

## 3. Creating the Hugging Face Space

### Web flow

1. Open Hugging Face Spaces.
2. Create a new Space.
3. Name: `shopstack` or `shopstack-ai`.
4. SDK: `Gradio`.
5. Visibility: public for the final submission. Private/protected can be used while preparing, if available.
6. License: choose according to the code and model dependency stance. For hackathon artifact, disclose any non-commercial/research-only model modules separately.
7. Add `app.py`, `requirements.txt`, source files, and README.

### README metadata

At the top of the Space README, include a YAML block similar to:

```yaml
---
title: ShopStack
emoji: 🛒
colorFrom: green
colorTo: indigo
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: true
license: mit
models:
  - openbmb/MiniCPM5-1B-GGUF
  - openbmb/MiniCPM-V-4.6
  - nvidia/LocateAnything-3B
  - black-forest-labs/FLUX.2-klein-4B
datasets:
  - <user-or-org>/shopstack-household-commands
  - <user-or-org>/shopstack-agent-traces
---
```

Only list models and datasets that are actually used or directly linked.

---

## 4. Gradio app structure

Use `gr.Blocks`, not a basic `gr.Interface`, because ShopStack needs a multi-screen product surface.

Recommended screens:

1. **Home / Product Loop** — what ShopStack does.
2. **Shopping List** — voice/text list creation.
3. **Market Lens** — upload photo or short video and ask “do I need this?”
4. **Purchase Capture** — upload final purchase photo or receipt.
5. **Review & Confirm** — detected item cards, crops, quantities, expiry, storage location.
6. **Inventory** — fridge/pantry/household stock.
7. **Find-It Map** — household location memory.
8. **Ask ShopStack** — voice/text query layer.
9. **Trace Drawer** — anonymized perception → decision → tool calls → confirmation trail.
10. **Field Notes** — real usage, failures, model choices, constraints.

Use custom CSS/HTML components for the Off-Brand badge: card grids, market scan panels, fridge zones, shelf map, status badges, and item chips.

---

## 5. Space dependencies

Minimum files:

```text
app.py
requirements.txt
README.md
src/shopstack/...
```

A starter `requirements.txt` can be:

```text
gradio
pydantic
pandas
pillow
opencv-python-headless
numpy
sqlite-utils
python-dateutil
huggingface_hub
transformers
accelerate
sentencepiece
protobuf
```

Add model-specific dependencies only when needed. Keep optional heavy providers behind provider interfaces so the app can still launch with mock/lightweight providers.

---

## 6. Secrets, variables, and privacy

The app should not require cloud model APIs in the submitted local-first path. If any optional provider uses a token during experimentation, store it in Hugging Face Space settings, not in code.

Rules:

- Never hardcode tokens, API keys, credit codes, passwords, private receipts, phone numbers, or home addresses.
- Use Space Variables for non-sensitive configuration.
- Use Space Secrets for tokens or credentials.
- Keep `OFFLINE_MODE=true` or equivalent for the Off the Grid runtime path.
- Include a redaction layer before exporting traces.

Recommended environment variables:

```text
SHOPSTACK_MODE=local
SHOPSTACK_TRACE_EXPORT=anonymized
SHOPSTACK_ALLOW_PRIVATE_UPLOAD_SAVE=false
SHOPSTACK_MODEL_PROFILE=local_gguf
SHOPSTACK_MAX_TOTAL_PARAMS_B=32
```

---

## 7. Hardware choices and credit usage

Default free Spaces provide CPU, memory, and ephemeral storage limits. Paid hardware can be selected in Space settings. Use HF credits for Space GPU testing only when the model stack needs it.

Recommended resource posture:

- CPU path: mock providers, lightweight parser, SQLite, PIL poster/cards, sample mode.
- Small GPU path: vision model, segmentation, OCR, TTS.
- Jobs path: fine-tuning, benchmarking, synthetic data generation, batch model comparisons.

Avoid making cloud-hosted inference essential if claiming Off the Grid.

---

## 8. Uploading models

Use a separate model repo for any fine-tuned parser.

Recommended model repo name:

```text
<user-or-org>/shopstack-command-parser
```

Model card must include:

- Base model.
- Training data description.
- Languages and dialects covered.
- Intended use: household shopping command parsing.
- Output schema.
- Evaluation metrics.
- Safety/privacy notes.
- License.
- Hackathon context.

The model does not need to be a general chatbot. It can be a small adapter or fine-tuned model that maps Indian household shopping utterances to JSON tool calls.

---

## 9. Uploading datasets

Create two dataset repos if possible:

### 9.1 Household command dataset

Repo:

```text
<user-or-org>/shopstack-household-commands
```

Example row:

```json
{
  "utterance": "doodh list mein add karo, kal khatam ho jayega",
  "language_mix": "hinglish",
  "intent": "add_to_shopping_list",
  "tool_call": {
    "tool": "add_shopping_list_item",
    "args": {
      "canonical_item": "milk",
      "display_name": "doodh",
      "quantity": null,
      "unit": null,
      "reason": "running_out"
    }
  }
}
```

### 9.2 Agent trace dataset

Repo:

```text
<user-or-org>/shopstack-agent-traces
```

Trace rows must be anonymized.

Example row:

```json
{
  "trace_id": "trace_001",
  "input_type": "market_photo_plus_voice",
  "redacted_user_request": "Do we need this item?",
  "visible_items": ["bread", "milk", "tomato"],
  "inventory_context": {
    "bread": "not_available",
    "milk": "low",
    "tomato": "available_0.5kg"
  },
  "decision": "buy bread and milk; skip tomato",
  "proposed_tool_calls": [
    {
      "tool": "add_shopping_list_item",
      "args": {"item": "bread", "reason": "not_available"}
    }
  ],
  "confirmation": "accepted",
  "final_answer": "Buy bread and milk. Skip tomato."
}
```

No raw household images, voice clips, receipts, phone numbers, addresses, or private names should be published.

---

## 10. HF Jobs usage

Use HF Jobs or Modal for heavy workflows:

- Fine-tuning command parser.
- Running voice benchmark suites.
- Running market/photo recognition benchmarks.
- Batch-generating synthetic Indian household utterances.
- Quantization / GGUF conversion trials.
- Creating evaluation reports.
- Generating redacted trace datasets.

Outputs from Jobs should be pushed to model, dataset, or artifact repos.

---

## 11. Gradio API and internal testing

Gradio apps can expose API endpoints. Name important events with `api_name` so Codex and benchmark scripts can call them.

Recommended endpoint names:

```text
/create_list
/analyze_market_image
/analyze_market_video
/parse_voice_correction
/propose_inventory_updates
/confirm_inventory_updates
/ask_inventory
/export_trace
```

This helps automated testing, Codex review, and repeatable benchmark runs.

---

## 12. Deployment checklist

Before submission:

- [ ] Space is public and runs without private credentials.
- [ ] README clearly states model parameter counts and total under 32B.
- [ ] README lists which models are local/runtime and which were only used for build-time experiments.
- [ ] README discloses any non-commercial/research model usage.
- [ ] Gradio app launches from `app.py`.
- [ ] `requirements.txt` is sufficient.
- [ ] Space has custom UI beyond default Gradio styling.
- [ ] Sample assets are synthetic, public, or explicitly safe to share.
- [ ] No secrets or credit codes are committed.
- [ ] Trace export is anonymized.
- [ ] Model and dataset repos are linked in README metadata.
- [ ] GitHub repo link is in Space README for Codex parallel track.
- [ ] Field Notes are linked.
- [ ] Walkthrough video and social post are ready.

---

## 13. Source notes

This guide was prepared from current Hugging Face and Gradio documentation and should be refreshed during implementation because Spaces, Jobs, hardware, and Gradio APIs can change.

Key source pages:

- https://huggingface.co/docs/hub/spaces-overview
- https://huggingface.co/docs/hub/spaces-sdks-gradio
- https://huggingface.co/docs/huggingface_hub/guides/upload
- https://huggingface.co/docs/hub/en/models-uploading
- https://huggingface.co/docs/hub/en/jobs-overview
- https://www.gradio.app/guides/sharing-your-app


---

# ShopStack — Sponsor Alignment Strategy

This document maps ShopStack’s product and engineering choices to the Build Small Hackathon sponsors without forcing artificial integrations. The product must still stand on its own as a Backyard AI entry: a real household shopping and inventory problem solved with small models in a polished Gradio Space.

Sponsor alignment should strengthen the story, not distract from it.

---

## 1. Core principle

Use sponsors where they genuinely fit:

- **Gradio / Hugging Face**: canonical app surface, Hub-hosted Space, model/dataset/trace publishing.
- **OpenBMB**: small/on-device models, MiniCPM text/VLM/audio options, OpenBMB special category.
- **OpenAI**: Codex parallel track and engineering quality, not runtime dependence.
- **NVIDIA**: vision grounding, ASR, GPU acceleration, optional NVIDIA-model lane.
- **Modal**: build-time compute for evaluation, fine-tuning, batch runs, trace generation.
- **Cohere**: optional ASR/text lane if a Cohere model proves useful; do not depend on a cloud API in the submitted local-first path.
- **Black Forest Labs**: image generation/editing, visual summaries, shelf/location maps, item cards.
- **JetBrains**: optional coding/tooling narrative if used; no forced product integration.

---

## 2. Hugging Face + Gradio lane

ShopStack is a Hugging Face-native artifact:

- Gradio app as the main user interface.
- Space as the public hosted product surface.
- Hub model repo for the fine-tuned command parser.
- Hub dataset repo for household command examples.
- Hub dataset repo for anonymized agent traces.
- Model cards, dataset cards, Space README, Field Notes.

This supports the main constraints and several bonus quests:

- Built on Gradio.
- Off-Brand custom UI.
- Well-Tuned published model.
- Sharing is Caring trace dataset.
- Field Notes report.

---

## 3. OpenBMB lane

OpenBMB is especially relevant because ShopStack is explicitly small-model and household-local.

Candidate uses:

- **MiniCPM5-1B** as planner/parser/tool-calling model.
- **MiniCPM5-1B-GGUF** for llama.cpp runtime and Llama Champion.
- **MiniCPM-V-4.6** for market/shelf/purchase image understanding.
- **MiniCPM-V-4.6-gguf** for local multimodal experiments if runtime permits.
- **MiniCPM-o-4_5** for future any-to-any voice/vision experiments.
- **VoxCPM2** for multilingual TTS / voice-design experiments.

Best narrative:

> ShopStack uses OpenBMB-style small/on-device models to create a household shopping assistant that runs locally and respects the 32B cap.

Strong OpenBMB special-category angle:

- Use MiniCPM5-1B or MiniCPM-V in the main path.
- Publish a small command parser fine-tune or adapter.
- Use the OpenBMB model explicitly in model registry and README.
- Compare MiniCPM against Qwen/LFM/Gemma alternatives in the benchmark report.

---

## 4. OpenAI / Codex lane

Codex is a parallel track. The ShopStack product should not depend on OpenAI runtime APIs for the main hackathon path.

Codex evidence:

- Public GitHub repo.
- Codex-attributed commits or PRs.
- `AGENTS.md` with constraints and coding standards.
- `docs/codex-build-log.md` with prompt/task history.
- Tests and reviews generated or improved with Codex.
- README section: “Built with Codex.”

Codex tasks:

- Gradio app skeleton.
- Provider interfaces.
- SQLite schema.
- Inventory tools.
- Trace exporter.
- Benchmark harness.
- Test suite.
- HF deployment checklist.
- README and Space card.

Do not commit Codex credit codes or private tokens.

---

## 5. NVIDIA lane

NVIDIA alignment can be very strong because ShopStack is vision-heavy and voice-aware.

Candidate uses:

- **LocateAnything-3B** for grounding market/shelf items. Research/non-commercial license is acceptable for hackathon artifact if disclosed.
- **Parakeet / Nemotron ASR** for streaming or short-command speech recognition.
- NVIDIA GPU hardware through HF/Modal for benchmarking and visual model runs.
- Optional CUDA-accelerated inference notes.

Best narrative:

> NVIDIA vision and speech models help ShopStack understand what the user sees and says while shopping.

Cautions:

- Clearly disclose non-commercial/research model status where applicable.
- Avoid making NVIDIA-only heavy hardware required for basic app launch.

---

## 6. Modal lane

Modal credits support experimentation and build-time compute.

Use Modal for:

- Fine-tuning command parser.
- Running benchmark batches.
- Evaluating STT/TTS candidates.
- Running segmentation/VLM experiments.
- Generating synthetic household utterances.
- Creating redacted trace datasets.
- Quantization and GGUF experiments.

Do not make Modal a required runtime dependency if claiming Off the Grid.

Best narrative:

> Modal was used as build-time compute for model evaluation and fine-tuning, while the submitted app keeps a local-first runtime path.

---

## 7. Cohere lane

Cohere is a supporting sponsor. Use it only if a Cohere model or tool genuinely improves the product.

Possible uses:

- Compare Cohere ASR/transcription if available and suitable.
- Compare command parsing or semantic classification against local models.
- Use Cohere for build-time labeling or analysis only if it does not conflict with Off the Grid claims.

Do not make Cohere cloud APIs required in the submitted runtime if pursuing Off the Grid.

---

## 8. Black Forest Labs lane

Black Forest Labs fits ShopStack’s visual layer.

Candidate uses:

- **FLUX.2-klein-4B** for image editing/generation under a small parameter budget.
- **FLUX.2-klein-9B** for richer visual edits if runtime permits.
- **FLUX.1-schnell** for permissive fast generation experiments.

Product uses:

- Generate clean “use soon” cards.
- Generate fridge/pantry visual maps.
- Generate annotated shopping summaries.
- Generate household shelf labels.
- Create visual comparison cards for buy/skip decisions.

Best narrative:

> Black Forest Labs image models turn ShopStack’s inventory and shopping decisions into visual, shareable household artifacts.

Avoid making image generation mandatory for core correctness; it should enhance clarity and polish.

---

## 9. Badge strategy by sponsor

### Off the Grid

Use local models and local SQLite. Use Modal/HF Jobs for build-time work only.

### Well-Tuned

Fine-tune and publish the ShopStack command parser. OpenBMB MiniCPM5-1B is a good candidate.

### Off-Brand

Custom Gradio UI: market lens, item cards, household map, trace drawer, visual inventory.

### Llama Champion

Run MiniCPM5-1B-GGUF or another selected GGUF parser through llama.cpp.

### Sharing is Caring

Publish anonymized trace dataset to the Hub.

### Field Notes

Write a serious product/technical report: real household workflow, model experiments, failures, small-model fit, privacy, sponsor model comparisons, and Codex build notes.

---

## 10. Recommended sponsor-aligned model stack to evaluate

### Lightweight OpenBMB-first stack

- Planner/parser: `openbmb/MiniCPM5-1B` or `openbmb/MiniCPM5-1B-GGUF`
- Vision: `openbmb/MiniCPM-V-4.6`
- TTS: `openbmb/VoxCPM2`
- Runtime badge: llama.cpp with MiniCPM GGUF

### NVIDIA vision/audio stack

- Grounding: `nvidia/LocateAnything-3B`
- ASR: Parakeet/Nemotron ASR candidates
- GPU acceleration: HF/Modal GPU runs

### Black Forest Labs visual polish stack

- Image edit/generation: `black-forest-labs/FLUX.2-klein-4B`
- Optional richer image edit: `black-forest-labs/FLUX.2-klein-9B`

### Codex engineering lane

- Codex for implementation, tests, docs, benchmark harness, Space deployment, and reviews.

---

## 11. Submission README sponsor section

Recommended README wording:

```text
Sponsor-aligned build notes:

- Gradio/Hugging Face: ShopStack is built as a Gradio Space, with model, dataset, and trace artifacts published on the Hub.
- OpenBMB: the app evaluates MiniCPM-family models for local planning, multimodal understanding, and/or TTS; MiniCPM GGUF is used for the llama.cpp path where applicable.
- OpenAI Codex: Codex was used as the coding agent for implementation, tests, docs, and review in a public GitHub repo with attributed commits/PRs.
- NVIDIA: the app evaluates NVIDIA vision/audio models for item grounding and voice capture where they improve the market-lens workflow.
- Modal: Modal credits are used for build-time evaluation/fine-tuning/benchmarking, not required as the local-first runtime path.
- Black Forest Labs: FLUX-family image models are evaluated for visual inventory cards, shelf maps, and shopping summaries.
```

---

## 12. What not to do

- Do not force every sponsor into the runtime path.
- Do not exceed the 32B total parameter constraint.
- Do not use cloud APIs in the submitted path if claiming Off the Grid.
- Do not hide non-commercial/research-only licenses.
- Do not make image generation more important than household shopping utility.
- Do not make Codex the product; Codex is the parallel engineering track.

---

## 13. Final narrative

ShopStack is a sponsor-native but product-first entry:

> A Gradio/Hugging Face Space that uses small, local, sponsor-aligned models to help Indian households remember what is at home while shopping. OpenBMB supports the small/on-device intelligence path, NVIDIA supports vision/audio perception, Black Forest Labs supports visual outputs, Modal/HF credits support experimentation, and Codex supports the public engineering story.


---

# ShopStack — Tool Calls, Live Search, Browser/Scraper, Memory Graph, and Embeddings Addendum

## 0. Purpose

This addendum expands ShopStack beyond perception + inventory into a household commerce intelligence system. The product should not only see items and store them. It should be able to call tools, compare against household memory, search or scrape live sources when allowed, build a graph of item relationships, and retrieve relevant history through embeddings.

This must be implemented without weakening the hackathon constraints:

- The submitted Gradio Space must remain model-stack documented and within the 32B parameter limit.
- The app should keep a local-first path for the Off the Grid bonus quest.
- Any cloud, browser, live-search, pricing, or external connector capability must be clearly separated as optional or build-time/connected mode.
- User confirmation should sit between model decisions and irreversible inventory updates.

---

## 1. Three operating modes

ShopStack should support three clear modes so agents do not accidentally break the local-first promise.

### 1.1 Local-first mode

The user-facing app runs only from local/open models and local state. No cloud model APIs, no live external pricing APIs, no remote scraping as a required path.

Local-first capabilities:

- shopping list creation;
- home inventory memory;
- image/video frame inspection with local models;
- OCR if the model/tool runs locally;
- item grounding/segmentation if local;
- voice input/output through local models;
- local price memory from prior household purchases;
- local nutrition/shelf-life tables;
- local embeddings/vector search;
- SQLite/duckdb/lance/chroma-style local stores.

This is the path to claim **Off the Grid**.

### 1.2 Connected research mode

Used during development, evaluation, and Field Notes. This mode can call external resources using Modal/HF credits or browser automation. It should produce artifacts, benchmarks, traces, and cached datasets that the local-first app can later use.

Connected research capabilities:

- compare live online prices across sites for a sample item list;
- collect public price examples into a local evaluation table;
- generate benchmark datasets;
- run cloud GPU jobs for model comparisons;
- validate OCR/model outputs against online reference pages;
- prepare anonymized trace datasets.

This mode should not be required for the submitted product path if claiming Off the Grid.

### 1.3 Connected assistant mode

A future product mode where the user intentionally enables browser/search/connectors. This can provide live prices, stock availability, delivery comparisons, recipe lookup, and nutrition APIs.

Connected assistant mode must be explicit:

- user enables it;
- app displays source and timestamp;
- app states that prices/availability may change;
- app does not scrape logged-in carts or accounts without explicit permission;
- app does not auto-purchase;
- app keeps user confirmation before any action.

---

## 2. Tool-call architecture

ShopStack should be built around typed tools rather than free-form assistant messages. The model should propose tool calls, the app validates them, and the user confirms when state changes.

### 2.1 Tool call lifecycle

1. User asks or uploads input.
2. Perception modules extract visible/text/audio information.
3. Planner forms a tool-call proposal.
4. Validator checks schema, units, confidence, safety, and conflicts.
5. UI shows proposed changes.
6. User accepts, rejects, or edits.
7. Tool executes.
8. Trace is saved.

### 2.2 Core inventory tools

```python
def add_inventory_item(
    canonical_name: str,
    display_name: str,
    category: str,
    quantity: float,
    unit: str,
    storage_location: str,
    purchase_date: str,
    estimated_expiry_date: str | None = None,
    price: float | None = None,
    currency: str = "INR",
    source_event_id: str | None = None,
    confidence: float = 0.0,
): ...


def update_inventory_item(
    item_id: str,
    quantity: float | None = None,
    unit: str | None = None,
    storage_location: str | None = None,
    estimated_expiry_date: str | None = None,
    status: str | None = None,
): ...


def consume_inventory_item(
    canonical_name: str,
    quantity: float,
    unit: str,
    reason: str | None = None,
): ...


def move_inventory_item(
    item_id: str,
    from_location: str,
    to_location: str,
    confidence: float = 1.0,
): ...
```

### 2.3 Shopping decision tools

```python
def create_shopping_list(title: str, household_context: str | None = None): ...

def add_to_shopping_list(item: str, quantity: float | None, unit: str | None, reason: str): ...

def remove_from_shopping_list(item: str, reason: str): ...

def evaluate_visible_item_for_purchase(
    visible_item: str,
    inventory_snapshot: dict,
    shopping_list: list,
    price: float | None = None,
    expiry: str | None = None,
): ...

def generate_next_buy_list(days_ahead: int = 7): ...
```

### 2.4 Perception tools

```python
def detect_items_in_image(image_path: str, query: str | None = None): ...

def segment_or_crop_item(image_path: str, item_name: str, box: list | None = None): ...

def extract_text_from_receipt_or_label(image_path: str): ...

def sample_video_frames(video_path: str, fps: float = 0.5): ...

def summarize_market_scan(frames: list[str], shopping_list: list, inventory_snapshot: dict): ...
```

### 2.5 Voice tools

```python
def transcribe_voice(audio_path: str, language_hint: str | None = None): ...

def synthesize_answer(text: str, voice: str | None = None, language: str = "hinglish"): ...

def parse_household_command(transcript: str, context: dict): ...
```

### 2.6 Live pricing and search tools

These should be separated from local-first mode.

```python
def search_public_price_web(item: str, location_hint: str | None = None): ...

def compare_price_against_memory(item: str, current_price: float, unit: str): ...

def ingest_public_price_snapshot(item: str, source_name: str, price: float, unit: str, timestamp: str): ...
```

Rules:

- Prefer household price memory over brittle live scraping.
- Use live search/browser mode only when explicitly enabled.
- Always show timestamp/source for live prices.
- Never represent live prices as guaranteed.
- Never scrape logged-in carts or payment pages for the hackathon artifact.

---

## 3. Live pricing and browser/search strategy

### 3.1 Product value

Live pricing can answer:

- “Is ₹60/kg for tomatoes expensive today?”
- “Is this detergent cheaper than last time?”
- “Should I buy this now or wait?”
- “Which item in my list has become expensive?”
- “What is the price memory for this household?”

### 3.2 Price intelligence hierarchy

Use this order:

1. User-entered price from current purchase.
2. OCR from receipt/label.
3. Household price memory from past purchases.
4. Local cached reference price table.
5. Optional connected search/browser price lookup.
6. Optional user-provided store quote.

### 3.3 Browser/scraper options

Possible technical lanes:

- **Playwright** for deterministic browser automation and testable scraping flows.
- **browser-use-style agents** for experimental browser automation, if compatible with local/open models and safety constraints.
- **Crawl4AI-style crawlers** for extracting public pages into clean markdown/structured data.
- Simple requests/BeautifulSoup only for stable pages; avoid brittle dynamic commerce pages.

### 3.4 Safety and reliability rules

- Do not auto-purchase.
- Do not log into user accounts by default.
- Do not bypass site restrictions or captchas.
- Do not store private cookies, sessions, addresses, or payment data.
- Cache only normalized public price snapshots.
- Show source and timestamp.
- Fall back to household price memory when live search fails.

### 3.5 Hackathon stance

For the submitted path, live price search should be positioned as optional/experimental unless it can run locally without cloud APIs. The stronger product story is **price memory**, not brittle universal price comparison.

---

## 4. Memory architecture

ShopStack needs multiple memory layers.

### 4.1 Operational memory

Structured state required for the app to work:

- inventory items;
- shopping lists;
- purchase events;
- consumption events;
- movement/location events;
- expiration/use-soon status;
- price history;
- household preferences;
- trace logs.

Use SQLite first, with clear migrations.

### 4.2 Semantic memory

Natural-language memories that help the assistant answer better:

- “Family prefers Amul milk.”
- “Mother buys coriander whenever tomatoes are bought.”
- “Detergent usually lasts about 30 days.”
- “Rice is stored in the lower pantry tin.”
- “Dad prefers not to buy bread near expiry.”

Use embeddings to retrieve these when relevant.

### 4.3 Spatial memory

Where items are usually kept or last seen:

- fridge door;
- top shelf;
- vegetable drawer;
- pantry left shelf;
- under-sink cleaning area;
- bathroom cabinet;
- medicine box;
- balcony crate.

Represent this as both structured locations and a graph.

### 4.4 Episodic memory

What happened at a point in time:

- “June 5: user bought 1L milk and 0.5kg tomatoes.”
- “June 7: bread moved to fridge.”
- “June 8: user asked if detergent was needed and skipped it.”
- “June 9: curd was marked consumed.”

This supports Field Notes and trace datasets.

---

## 5. Graph and linkage model

A graph helps ShopStack reason about relationships beyond flat inventory.

### 5.1 Node types

- `Household`
- `Person`
- `Item`
- `ItemLot`
- `Category`
- `StorageLocation`
- `ShoppingList`
- `PurchaseEvent`
- `ConsumptionEvent`
- `PriceObservation`
- `RecipeOrUseCase`
- `Store`
- `Trace`

### 5.2 Edge types

- `stored_in`
- `moved_to`
- `bought_in`
- `consumed_by`
- `substitutes`
- `usually_bought_with`
- `expires_before`
- `preferred_by`
- `available_at`
- `price_observed_at`
- `used_for`
- `detected_in_image`
- `mentioned_in_voice`

### 5.3 Example graph facts

```json
[
  {"from": "tomato", "edge": "stored_in", "to": "fridge_vegetable_drawer"},
  {"from": "bread", "edge": "expires_before", "to": "2026-06-09"},
  {"from": "milk", "edge": "usually_bought_with", "to": "bread"},
  {"from": "surf_excel", "edge": "stored_in", "to": "bathroom_cleaning_shelf"},
  {"from": "dhaniya", "edge": "used_for", "to": "pav_bhaji"}
]
```

### 5.4 Graph-backed answers

- “Where is the spare toothpaste?”
- “What do we usually buy with dosa batter?”
- “Which items are stored in the fridge door?”
- “What moved since yesterday?”
- “Which items often expire before being used?”
- “What should I buy for pav bhaji that we do not already have?”

### 5.5 Implementation options

Start with SQLite tables and graph-like query helpers. A graph database is not required to make graph reasoning work. Later, the graph can move to NetworkX, DuckDB, SQLite recursive queries, or a lightweight graph store.

---

## 6. Embeddings and retrieval

Embeddings help map messy language to household memory.

### 6.1 Use cases

- synonym matching: “doodh” → “milk”;
- brand matching: “Surf” → “detergent”;
- item canonicalization: “hara dhaniya” → “coriander”;
- semantic memory retrieval;
- trace similarity;
- shopping-list matching against visible items;
- receipt item normalization;
- “find similar past purchases.”

### 6.2 Embedding indexes

Create separate indexes:

- `item_alias_index`
- `household_memory_index`
- `purchase_history_index`
- `trace_index`
- `location_memory_index`
- `recipe_or_usecase_index`

### 6.3 Embedding model candidates

Prefer small local embedding models. Candidate families:

- Qwen embedding models;
- BGE-style embedding models;
- MiniLM/E5-style compact embeddings;
- multilingual embedding models for Hindi/Hinglish/Indian household terms.

The embedding provider must be swappable under the model experimentation policy.

### 6.4 Retrieval policy

- Retrieve structured facts first.
- Retrieve semantic memories second.
- Retrieve traces/examples third.
- Show uncertainty when retrieval is weak.
- Never let fuzzy retrieval directly mutate inventory.

---

## 7. Agent trace schema

Traces should become a first-class artifact for the Sharing is Caring badge.

```json
{
  "trace_id": "trace_001",
  "mode": "local_first",
  "input_summary": "user asked whether to buy visible bread",
  "perception": {
    "detected_items": ["bread", "milk"],
    "ocr_text": ["expiry: 09 Jun 2026"],
    "confidence": 0.82
  },
  "retrieved_context": {
    "inventory": ["milk: low", "bread: not available"],
    "shopping_list": ["bread", "tomato", "milk"],
    "price_memory": ["bread last bought: INR 45"]
  },
  "decision": {
    "recommendation": "buy bread",
    "reason": "bread is on the list and not currently available"
  },
  "proposed_tool_calls": [
    {"tool": "mark_item_seen_in_market", "args": {"item": "bread"}}
  ],
  "user_confirmation": "accepted",
  "final_answer": "Buy bread. Check expiry before billing."
}
```

Trace export rules:

- Redact names, phone numbers, exact addresses, payment data, raw receipts, raw photos, and raw voice.
- Keep normalized facts and reasoning steps.
- Publish a small anonymized trace dataset on Hugging Face if pursuing Sharing is Caring.

---

## 8. Open tool registry proposal

Create `configs/tools.yaml`:

```yaml
inventory:
  - add_inventory_item
  - update_inventory_item
  - consume_inventory_item
  - move_inventory_item

shopping:
  - create_shopping_list
  - add_to_shopping_list
  - remove_from_shopping_list
  - evaluate_visible_item_for_purchase
  - generate_next_buy_list

perception:
  - detect_items_in_image
  - segment_or_crop_item
  - extract_text_from_receipt_or_label
  - sample_video_frames
  - summarize_market_scan

voice:
  - transcribe_voice
  - synthesize_answer
  - parse_household_command

memory:
  - retrieve_item_aliases
  - retrieve_household_memory
  - retrieve_similar_traces
  - retrieve_location_memory

connected_optional:
  - search_public_price_web
  - compare_public_prices
  - ingest_public_price_snapshot
```

Each tool should declare:

- input schema;
- output schema;
- whether it mutates state;
- whether user confirmation is required;
- whether it is allowed in local-first mode;
- whether it can access external network;
- whether it stores trace data.

---

## 9. Agent instructions

When asking Codex or another coding agent to build this layer, use:

```text
Add ShopStack tool-call, memory, graph, search, and embedding architecture without hardcoding any external provider.

Requirements:
- Keep local-first mode separate from connected research and connected assistant modes.
- Add typed tool definitions for inventory, shopping, perception, voice, memory, and optional connected pricing.
- Add SQLite tables for inventory events, movement events, price observations, traces, and semantic memories.
- Add a graph helper layer over SQLite rather than requiring a graph database.
- Add embedding provider interfaces and local vector index stubs.
- Add trace export with redaction.
- Add browser/search provider interfaces, but do not make live scraping required for the main app path.
- Add tests for tool validation, confirmation-required mutations, trace redaction, and local-first mode enforcement.
- Do not commit tokens, cookies, credit codes, private receipts, private household photos, raw voice clips, or addresses.
```

---

## 10. Product principle

ShopStack should not chase every possible external data source. The durable product value is household memory plus contextual shopping decisions.

External search and live pricing are useful only when they improve a decision. The product should always be able to answer from local inventory, price memory, household preferences, and user confirmation.

