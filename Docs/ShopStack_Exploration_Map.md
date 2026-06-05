# ShopStack Exploration Map

**Project:** ShopStack / GharStock  
**Purpose:** A living exploration map for agents and collaborators.  
**Rule:** Keep adding to this file whenever a model, product angle, dataset, architecture pattern, evaluation method, market idea, or risk deserves future investigation.

---

## 0. Product Summary

ShopStack is a small-model shopping copilot and household commerce memory layer.

It helps a household:

- know what is already at home,
- build shopping lists,
- scan shelves, markets, receipts, packets, fridges, and pantry spaces,
- ask questions by voice,
- decide buy / skip / compare / replace,
- add purchases into inventory,
- track freshness, expiry, price, quantity, and location,
- remember where items are stored,
- learn which stores are cheaper/better,
- understand travel, weather, timing, and convenience,
- create anonymized traces and field notes for the Build Small Hackathon.

The product is intentionally broad long-term, but every exploration should connect back to household shopping, inventory, market intelligence, or daily-use memory.

---

## 1. Capability Map

### 1.1 Language + Reasoning

Current / possible capabilities:

- NER for item, brand, unit, quantity, store, price, location, date.
- Intent classification.
- Command parsing.
- Tool-call planning.
- Natural-language inventory query.
- Shopping decision explanation.
- Multilingual / Hinglish / Indian household phrasing.
- Synonym and alias normalization.
- Structured JSON extraction.
- RAG over household memory.
- Safety disclaimers for nutrition/medicine/price uncertainty.

Exploration questions:

- Which small model is best at Indian household command parsing?
- Can a tiny fine-tuned parser outperform a larger general model on our exact commands?
- How much can rules + schema validation reduce model errors?
- Which model produces the cleanest JSON tool calls locally?
- Should we separate command parser and answer generator?

Candidate model families:

- MiniCPM / OpenBMB
- Qwen
- LFM / LiquidAI
- Gemma
- GPT-OSS
- Granite
- GLM
- Mistral / Voxtral for speech-heavy flows
- Llama / Phi GGUF models for llama.cpp badge

---

### 1.2 NER / Entity Extraction

Entities to extract:

- item name
- canonical item name
- item category
- brand
- local alias
- quantity
- unit
- price
- normalized unit price
- expiry date
- manufacturing date
- store
- location at home
- storage instruction
- nutrition facts
- household member preference
- purchase timestamp
- travel context
- weather context

Exploration questions:

- Should NER be rule-based, model-based, or hybrid?
- Can a fine-tuned small model map Hinglish utterances to canonical items?
- How do we handle ambiguous items like “Surf,” “Vim,” “Maggi,” “bread,” “pav,” “dahi,” “curd,” “yogurt”?
- Can we build a household-specific lexicon that improves over time?
- Should item names be canonicalized using embeddings?

Dataset ideas:

- Indian household item alias dataset.
- Grocery command dataset.
- Receipt-line-to-canonical-item dataset.
- Hinglish quantity normalization dataset.
- Expiry and storage instruction dataset.

---

### 1.3 Time Series

Time-series capabilities:

- consumption rate estimation,
- days-until-stockout,
- restock interval prediction,
- price trend by item,
- price trend by store,
- day-of-week price patterns,
- seasonality,
- freshness decay,
- expiry forecasting,
- travel effort over time,
- store quality over time,
- household category spend.

Exploration questions:

- Which items have predictable restock cycles?
- How much history is needed for useful next-buy predictions?
- Can we estimate stockout without exact daily consumption?
- What is the right confidence language: “likely low,” “probably enough,” “uncertain”?
- How do we handle multiple lots of the same item?
- Should predictions be rule-based initially and learned later?

Possible models / tools:

- statsmodels / Prophet-like approaches,
- DuckDB time-series queries,
- simple rolling averages,
- exponential smoothing,
- Bayesian inventory estimates,
- local notebooks / HF Jobs / Modal experiments.

---

### 1.4 Spatial Intelligence

Spatial layers:

- fridge shelf memory,
- pantry shelf memory,
- household location map,
- item last-seen memory,
- item movement events,
- room/shelf heatmap,
- “find this item” assistant,
- storage recommendation,
- household location graph,
- future AR/SLAM-like map.

Exploration questions:

- Can shelf/fridge photos become stable “location snapshots”?
- How do we identify the same item across days?
- Can we track “milk moved from shopping bag → fridge door”?
- How much user confirmation is needed?
- Should locations be user-defined first: fridge top shelf, pantry shelf 2, bathroom cabinet?
- Is a heatmap useful before AR/SLAM exists?
- Can we use image embeddings for “this looks like the same shelf”?

Possible tools:

- OpenCV,
- object detection,
- image embeddings,
- segmentation,
- H3/geospatial only for external market map,
- graph DB or SQLite graph tables,
- future WebAR / mobile capture.

---

### 1.5 Voice: STT, TTS, Audio

Voice capabilities:

- voice shopping list creation,
- voice correction,
- voice ask while shopping,
- voice answer in noisy market mode,
- voice-based item movement,
- voice-based price logging,
- Indian-language / Hinglish UX,
- audio confidence and retry UX.

STT candidates to evaluate:

- Qwen3-ASR-1.7B
- NVIDIA Parakeet / Nemotron 0.6B streaming ASR
- Mistral Voxtral Mini Realtime
- SenseVoiceSmall
- VibeVoice ASR
- Cohere Transcribe model
- Granite Speech
- Whisper large-v3-turbo baseline

TTS candidates to evaluate:

- MOSS-TTS-v1.5
- VoxCPM2
- Qwen3-TTS 0.6B / 1.7B
- Higgs Audio v3 TTS
- Kokoro-82M
- CosyVoice
- OmniVoice
- Chatterbox / XTTS-style models if useful

Exploration questions:

- Which model best handles Hinglish grocery commands?
- Can the response voice be short, warm, and market-friendly?
- Should we use browser/device TTS as fallback?
- How do we handle noisy market audio?
- Can audio be processed locally in the Space without cloud APIs?
- How do we benchmark STT/TTS quickly?

Benchmark phrases:

- “Doodh ghar pe hai kya?”
- “Tamatar aadha kilo add karo.”
- “Nahi, yeh pyaaz hai aloo nahi.”
- “Bread expiry kal ka hai, skip karo.”
- “Surf Excel already ghar pe hai kya?”
- “Isko pantry mein move karo.”
- “Kal breakfast ke liye kya hai?”

---

### 1.6 Vision Understanding

Vision capabilities:

- item detection,
- item classification,
- visual grounding,
- shelf/market scan,
- packet understanding,
- receipt understanding,
- fridge/pantry scan,
- freshness/ripeness hints,
- damaged/spoiled item detection,
- visual confirmation cards,
- annotated photos.

Candidate models / tools:

- Gemma multimodal models
- MiniCPM-V
- LocateAnything
- Qwen VL / image models
- RF-DETR
- YOLO variants
- Marlin-2B for video
- TimeLens / video grounding models
- OpenCV + OCR hybrids
- CLIP/embedding-based matching

Exploration questions:

- Which model works best on Indian market photos?
- Can open-vocabulary grounding identify “dhaniya,” “pav,” “dahi,” “atta”?
- Does a general VLM beat object detection for household goods?
- Can we use image crops + text model instead of one large VLM?
- How do we show uncertainty without frustrating users?

---

### 1.7 OCR / Extraction

OCR targets:

- receipts,
- packet labels,
- expiry dates,
- MRP,
- quantity,
- brand,
- nutrition facts,
- store name,
- receipt totals,
- bill line items,
- handwritten notes.

Candidate tools:

- PaddleOCR / PaddleOCR-VL
- NuExtract3
- Tesseract fallback
- Donut-like document models
- DocTR / LayoutLM-style pipelines
- OCR + LLM extraction hybrid

Exploration questions:

- Can receipt OCR handle local Indian store bills?
- How do we normalize quantities from OCR?
- Can we reliably detect expiry dates from packets?
- How do we distinguish MRP from sale price?
- Should packet OCR be a separate close-up mode?

---

### 1.8 Classification

Classification tasks:

- item category,
- storage location,
- food vs household vs medicine vs cleaning,
- perishable vs shelf-stable,
- urgent vs optional,
- buy / skip / compare,
- confidence class,
- freshness class,
- trace safety/redaction class,
- price anomaly class,
- user intent class.

Exploration questions:

- Which classifications can be rules?
- Which need fine-tuning?
- Should we use a lightweight classifier before LLM calls?
- Can the fine-tuned model handle both intent and item category?
- How do we evaluate classification in Field Notes?

---

### 1.9 Segmentation / Grounding

Segmentation capabilities:

- product crop cards,
- item cutouts,
- shelf zones,
- fridge zones,
- visual confirmation,
- background removal,
- annotated maps.

Candidate tools:

- RMBG
- BiRefNet
- ClipSeg
- SAM variants if feasible
- YOLO segmentation
- RF-DETR segmentation
- LocateAnything grounding
- OpenCV masks

Exploration questions:

- Is segmentation necessary for every flow, or only review cards?
- Which model runs reliably in Spaces?
- Can segmentation improve user trust?
- Can shelf-zone segmentation power household spatial memory?
- How should we handle overlapping groceries?

---

### 1.10 Image Generation / Editing

Use cases:

- annotated shopping photos,
- item cards,
- shelf maps,
- “use soon” visual cards,
- printable pantry labels,
- shopping summary posters,
- household heatmap illustrations,
- price comparison cards,
- Field Notes visuals.

Candidate models:

- Black Forest Labs FLUX.2-klein-4B
- FLUX.2-klein-9B
- Qwen Image Edit
- ControlLight
- Lightweight PIL/HTML card generation
- SVG-based generated layouts

Exploration questions:

- Is image generation useful enough for the product, or should deterministic visual cards come first?
- Can generated cards improve sharing and polish?
- How do we keep image edits from hallucinating wrong product details?
- Should all factual text be rendered by code, not generated into image pixels?

---

### 1.11 Embeddings / Retrieval

Embedding uses:

- item alias matching,
- receipt line matching,
- memory search,
- similar purchase recall,
- store note retrieval,
- trace retrieval,
- product substitute matching,
- voice phrase similarity,
- user preference retrieval,
- location snapshot matching.

Candidate embedding models:

- Qwen embeddings
- MiniLM / sentence-transformers
- multilingual E5 family
- BGE multilingual
- Jina embeddings
- small local embedding models
- CLIP / SigLIP for image similarity

Exploration questions:

- Which multilingual embedding model handles Hinglish item aliases best?
- Should text and image embeddings share one store?
- Is SQLite vector extension enough?
- Should we use FAISS, LanceDB, Chroma, or DuckDB extensions?
- Can embeddings help trace retrieval for Sharing is Caring?

---

### 1.12 Graph / Linkage Memory

Nodes:

- Item
- ItemLot
- Store
- MarketArea
- HouseholdLocation
- Shelf
- FridgeZone
- PurchaseEvent
- PriceObservation
- ShoppingTrip
- WeatherContext
- UserPreference
- Recipe
- Trace
- ModelRun

Edges:

- bought_at
- stored_in
- moved_to
- consumed_by
- expires_before
- substitutes
- usually_bought_with
- preferred_by
- cheaper_at
- best_quality_at
- seen_in_photo
- mentioned_in_voice
- derived_from_receipt
- weather_affected
- route_to
- worth_travelling_for

Exploration questions:

- Is a graph DB needed, or can SQLite edge tables do enough?
- Which queries need graph traversal?
- Can graph memory make the product feel smarter quickly?
- How do we visualize this without making it technical?

---

## 2. User Use Case Map

### 2.1 Before Shopping

Use cases:

- create list from voice,
- check what is already at home,
- predict next buys,
- suggest what to buy for meals,
- avoid buying duplicates,
- choose store based on list,
- compare travel effort,
- account for weather,
- generate shopping route,
- plan by budget.

Questions:

- “What should I buy today?”
- “What is low at home?”
- “Can we make dinner without shopping?”
- “Which store should I go to?”
- “Is the Sunday market worth it today?”

---

### 2.2 During Shopping

Use cases:

- scan shelf,
- ask if item is needed,
- compare with home inventory,
- compare price with memory,
- check expiry,
- identify unknown item,
- quantity advice,
- substitution advice,
- allergy/preference warning,
- budget warning.

Questions:

- “Do I need this?”
- “Is this price okay?”
- “Which one should I pick?”
- “Is this enough?”
- “Do we already have this?”
- “Is this near expiry?”
- “Can I skip this?”

---

### 2.3 After Shopping

Use cases:

- purchase photo ingestion,
- receipt ingestion,
- inventory update,
- expiry tracking,
- price observation logging,
- store rating,
- trip context logging,
- trace export,
- family summary.

Questions:

- “Add all this.”
- “What expires first?”
- “What did we spend?”
- “Where should this go?”
- “Did we overbuy anything?”

---

### 2.4 At Home

Use cases:

- find items,
- check stock,
- plan meals,
- use-soon reminders,
- move item location,
- consume item,
- estimate remaining quantity,
- household member asks questions,
- shelf/fridge scan,
- spatial memory.

Questions:

- “Where is the dahi?”
- “Do we have detergent?”
- “What should we use today?”
- “What is in the fridge?”
- “Move toothpaste to bathroom cabinet.”
- “How much rice is left?”

---

### 2.5 Market Intelligence

Use cases:

- price trends,
- store ranking,
- cheapest location,
- freshness/quality memory,
- travel-time decision,
- weather-aware recommendation,
- route-aware shopping,
- neighborhood price map.

Questions:

- “Where was tomato cheapest?”
- “Is this price high?”
- “Which store is better for fruits?”
- “Should I travel to the market today?”
- “What did we learn from last month’s shopping?”

---

## 3. Build Small Hackathon Constraint Map

Non-negotiables:

- total loaded model parameters must be <= 32B,
- app must be built on Gradio,
- app must be hosted as a Hugging Face Space,
- short walkthrough video and social post required,
- main track should show a real person / real problem,
- Codex is a parallel track, not the product.

Bonus quests:

- Off the Grid: no cloud APIs in runtime path.
- Well-Tuned: use a fine-tuned model published on HF.
- Off-Brand: custom frontend beyond default Gradio.
- Llama Champion: run a model through llama.cpp.
- Sharing is Caring: publish anonymized agent traces.
- Field Notes: write report/blog about what was built and learned.

Exploration questions:

- Which bonus quests are product-aligned?
- How do we claim Off the Grid while using credits for build-time jobs?
- How do we make llama.cpp visible in the app/report?
- What is the smallest useful fine-tune?
- How should traces be anonymized?

---

## 4. Sponsor Alignment Map

### Hugging Face + Gradio

Explore:

- Spaces deployment,
- Space README metadata,
- dataset/model linking,
- model publishing,
- dataset publishing,
- Jobs,
- GPU Spaces,
- custom Gradio Blocks UI,
- Gradio API endpoints,
- traces as datasets.

### OpenBMB

Explore:

- MiniCPM5-1B as parser/planner,
- MiniCPM5-1B-GGUF for llama.cpp badge,
- MiniCPM-V for vision,
- VoxCPM2 for TTS,
- OpenBMB special category angle.

### OpenAI / Codex

Explore:

- Codex-attributed commits,
- AGENTS.md,
- codex build log,
- tests and docs generated/reviewed by Codex,
- public GitHub repo,
- “Built with Codex” README section,
- Codex as engineering lane only.

### NVIDIA

Explore:

- LocateAnything for grounding,
- Parakeet/Nemotron ASR,
- GPU experiments,
- accelerated vision/audio workflows,
- possible RTX 5080 relevance in final story.

### Modal

Explore:

- fine-tuning jobs,
- benchmark jobs,
- model comparison runs,
- trace generation,
- quantization,
- batch inference,
- dataset generation.

### Black Forest Labs

Explore:

- FLUX image edit / visual cards,
- use-soon cards,
- shelf maps,
- shopping summaries,
- annotated item visuals.

### Cohere

Explore:

- ASR/transcription model comparison,
- embeddings/reranking comparisons if available,
- not required for local-first runtime.

---

## 5. Dataset Exploration Map

Potential datasets to create/publish:

1. Indian household shopping utterances.
2. Hinglish grocery command parser dataset.
3. Item alias/canonicalization dataset.
4. Purchase photo annotation dataset.
5. Receipt OCR/extraction dataset.
6. Packet label/expiry extraction dataset.
7. Inventory tool-call traces.
8. Market decision traces.
9. Price observation synthetic dataset.
10. Shelf/fridge location memory dataset.
11. Voice benchmark dataset.
12. TTS pronunciation phrase set.
13. Store memory schema examples.
14. Redacted agent trace dataset for Sharing is Caring.
15. Field Notes dataset with examples and failure modes.

Dataset quality questions:

- What can be public?
- What must be synthetic?
- What must be anonymized?
- What needs user consent?
- Which datasets help Well-Tuned most?
- Which datasets help judges understand the product?

---

## 6. Evaluation Map

### Product Evaluations

- Can the user create a list by voice?
- Can the app detect relevant visible items?
- Can the app correctly say buy/skip?
- Can it add confirmed purchases?
- Can it answer inventory questions?
- Can it find item locations?
- Can it explain uncertainty?

### Model Evaluations

- STT exactness and intent retention.
- TTS clarity and warmth.
- OCR field extraction accuracy.
- object detection recall.
- segmentation usability.
- tool-call JSON validity.
- parser intent accuracy.
- latency.
- memory use.
- parameter count.
- install/deploy pain.
- local-first compatibility.

### Trace Evaluations

- trace completeness,
- privacy redaction,
- reproducibility,
- educational value,
- tool-call correctness.

### Field Notes Evaluations

- real user used it,
- what worked,
- what failed,
- what changed after feedback,
- small-model fit,
- honest limitations.

---

## 7. Marketing / Positioning Exploration

Possible positioning:

- “Remember what’s at home while you shop.”
- “A shopping copilot for Indian homes.”
- “Photo + voice inventory for everyday shopping.”
- “Your fridge, pantry, market, and shopping list in one memory.”
- “Small models for small household decisions.”
- “The home commerce memory layer.”
- “Not another grocery app — a memory for what you buy, where it goes, and when to buy again.”

Potential audiences:

- Indian families,
- parents,
- students/hostels,
- shared flats,
- home cooks,
- small kirana shoppers,
- apartment households,
- elderly users,
- caregivers,
- domestic helpers managing stock,
- local sellers later as adjacent market.

Potential channels:

- hackathon demo,
- YouTube build stream,
- Twitter/X build thread,
- LinkedIn product post,
- HF Space leaderboard,
- Gradio Discord,
- Indian tech/ProductHunt style launch,
- Reddit India/frugal/mealprep communities,
- WhatsApp family-group proof-of-use story.

Exploration questions:

- Is “ShopStack” too general or perfect for scaling?
- Should the India-local layer be in the tagline, not name?
- Can demo be recorded with real household shopping?
- What short video moment makes people immediately understand?
- Which poster/screenshot is most shareable?

---

## 8. Risk / Constraint Exploration

Risks:

- too broad,
- over-reliance on imperfect vision,
- noisy market audio,
- privacy concerns,
- live price unreliability,
- too many models in one Space,
- 32B parameter accounting,
- non-commercial model licenses,
- Gradio UI becoming complex,
- agent anchoring to a reduced scope,
- overclaiming accuracy,
- app feeling like a demo instead of product direction.

Mitigations:

- confirmation-first UX,
- model registry,
- local-first mode,
- connected modes clearly separated,
- visible uncertainty,
- trace redaction,
- field notes,
- provider interfaces,
- benchmark scripts,
- privacy-first README,
- no auto-purchase,
- no medical/diet/legal claims,
- no private data in repo.

---

## 9. Open Questions

Agents should keep adding questions here.

1. Which model stack gives the best local-first performance under 32B?
2. Which model is easiest to run through llama.cpp for the parser?
3. What exact fine-tuned model should be published for Well-Tuned?
4. How much real household data can be safely used?
5. What is the first public trace dataset schema?
6. How should we count parameters when multiple models are optional but not loaded together?
7. Can Gradio handle the desired custom UI without too much friction?
8. Which STT model handles Hinglish best?
9. Which TTS model sounds warm enough for household use?
10. Should we use OCR or VLM-first for receipts?
11. How do we estimate quantity from photos without overclaiming?
12. Should price intelligence be mostly manual-memory-first?
13. How much map/heatmap functionality belongs in the app surface?
14. What is the simplest useful household map?
15. How do we benchmark live market/shelf scans?
16. What should be in the walkthrough video?
17. What should the social post emphasize?
18. What should the Field Notes title be?
19. How can Codex involvement be made obvious and authentic?
20. What is the strongest sponsor-alignment story?

---

## 10. Parking Lot

Use this for anything that may be interesting later.

- AR mode for finding items at home.
- Barcode scanning.
- Local store loyalty memory.
- Recipe planning from inventory.
- Waste tracking.
- Family member preferences.
- Domestic helper voice workflow.
- Shared household mode.
- WhatsApp integration.
- Calendar/reminder integration.
- Price community map.
- Privacy-preserving neighborhood price sharing.
- Offline mobile app.
- Browser extension for online grocery carts.
- Email receipt ingestion.
- Smart label printing.
- Shelf-life prediction from images.
- Freshness/ripeness model.
- Food waste report.
- Shopping carbon/effort score.
- Festival shopping planning.
- Monthly household budget intelligence.
- Elder-friendly voice-only mode.
- Accessibility mode for low-vision shoppers.
- Agentic shopping comparison, with user confirmation only.
- Local-language onboarding.
- Synthetic data generation pipeline.
- Human review UI for fine-tune data.
- Public leaderboard for household command parsing models.
- Sponsor-specific benchmark tables.
- Model replacement changelog.

---

## 11. Agent Contribution Protocol

When an agent adds an exploration item:

1. Add it under the relevant section.
2. Include why it matters for ShopStack.
3. Add model/tool links if known.
4. Mark whether it affects:
   - product,
   - model stack,
   - dataset,
   - evaluation,
   - UI,
   - privacy,
   - sponsor alignment,
   - bonus quest,
   - marketing.
5. Do not delete old ideas unless they are unsafe or clearly obsolete.
6. Move rejected ideas to a “rejected/paused” note with reason.
7. Keep this map broad; implementation tasks belong in task docs, not here.
8. Avoid anchoring language that frames the product as temporary or small.
9. Keep hackathon constraints visible.
10. Prefer swappable interfaces over hardcoded models.

Template:

```md
### Idea / Model / Tool / Angle

**Category:** model / product / dataset / marketing / eval / privacy / sponsor / UI  
**Why it matters:**  
**How to test:**  
**Risks:**  
**Links:**  
**Status:** explore / test / adopt / pause / reject  
```

---

## 12. Current Strongest Directions

1. Voice-first shopping list and correction.
2. Vision-based market/shelf scan.
3. Purchase photo ingestion.
4. Inventory and freshness memory.
5. Household spatial memory.
6. Price and store memory.
7. Fine-tuned Indian household command parser.
8. llama.cpp parser/planner.
9. Anonymized trace dataset.
10. Field Notes with real household use.
11. Off-brand custom Gradio UI.
12. Model benchmarking and replacement policy.

---

_Last updated: 2026-06-05_
