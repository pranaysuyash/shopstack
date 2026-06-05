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

