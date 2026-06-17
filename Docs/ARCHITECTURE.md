# ShopStack Architecture

> **Last updated:** 2026-06-15
> **Version:** 0.1.0
> **Purpose:** Comprehensive architectural reference for the ShopStack shopping intelligence platform.

---

## 1. System Overview

ShopStack is a **local-first, off-the-grid shopping intelligence platform** that helps households know what they have, what to use soon, what to buy, what to skip, and where to buy from — without sending data to the cloud.

### 1.1 Design Philosophy

| Principle | Application |
|-----------|-------------|
| **Local-first** | SQLite database (WAL mode), no cloud dependencies for core functionality |
| **Off-the-grid** | All mock providers by default; real models via optional local backends (MLX, llama.cpp) |
| **Decision-first** | Every workflow leads to a buy/skip/use-soon decision, not raw data |
| **Traceable** | Every tool execution creates an auditable trace with PII redaction |
| **Composable modules** | Six logical modules (ShopStock, ShopBasket, ShopCompare, etc.) share data through the same database |

### 1.2 Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                   FastAPI Host (shopstack/server.py)              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  GET  /  →  Frontend Shell (shopstack/ui/frontend_shell.py)│  │
│  │  GET  /api/v1/meta/*, /api/v1/auth/*  (public)             │  │
│  │  GET/POST /api/v1/{inventory,shopping,dashboard,           │  │
│  │            search,intelligence,account,traces,              │  │
│  │            corrections,command,household,sms}/*             │  │
│  │            (Bearer token required)                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    shopstack.api.v1.routers/                     │
│  13 routers: meta, auth, inventory, household, shopping,        │
│  dashboard, command, search, traces, intelligence, account,      │
│  corrections, sms                                                │
│  (Each router: FastAPI APIRouter with Depends-based auth)        │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    shopstack.services/                           │
│  shopping.py  ─  shopping list, classification, enrichment      │
│  market_lens.py ─  barcode scan, object detection, OCR, STT     │
│  dashboard.py  ─  today dashboard state assembly                │
│  find.py ─  inventory search (text + semantic)                  │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    shopstack.tools/registry.py                    │
│  12 tools: add/update/consume/move/find inventory items,        │
│  create shopping list, compare to inventory, record price,      │
│  use-soon, buy suggestions, semantic find, export trace          │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                 shopstack.persistence/database.py                 │
│  SQLite + WAL mode, 26 tables + 2 views + 2 triggers            │
│  Full CRUD across inventory, shopping, prices, traces, events   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                   shopstack.providers/                           │
│  registry.py ──  factory wired from Settings                     │
│  interfaces.py ──  11 abstract ABCs                             │
│  mock_providers.py ──  full mock implementations                │
│  local_provider.py ──  MLX + llama.cpp                          │
│  openai_provider.py ──  cloud fallback                          │
│  whisper_provider.py ──  cloud STT                              │
│  local_whisper_provider.py ──  on-device STT                    │
│  runtime.py ──  RuntimeReport dataclass                         │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                          HTTP Clients                            │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────────┐  │
│  │ shopstack-mobile│  │ Frontend Shell  │  │ curl / Postman    │  │
│  │ (React Native)  │  │ (FastAPI HTML)  │  │ (API testing)     │  │
│  └────────────────┘  └────────────────┘  └───────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Architecture

### 2.1 Module Map

| Module | Slug | Tabs | Dependencies | Service Paths |
|--------|------|------|--------------|---------------|
| **ShopStock** | `stock` | purchase, inventory, usesoon, map, portability | — | `screens.inventory`, `portability` |
| **ShopBasket** | `basket` | shopping | ShopStock | `services.shopping`, `screens.shopping` |
| **ShopCompare** | `compare` | prices | Sources | `market.analytics`, `market.normalization` |
| **ShopLens** | `lens` | market | ShopStock | `services.market_lens`, `screens.market_lens`, `scanner` |
| **ShopMemory** | `memory` | prices, notes | — | `ui.views`, `screens.other` |
| **ShopAgent** | `agent` | today, ask, trace | ShopStock, ShopBasket, ShopMemory | `planner.*`, `decisions`, `traces.export` |
| **Sources** | `sources` | (none) | — | `market.sources.swiggy` |
| **Runtime** | `runtime` | modelstack | — | `screens.model_stack`, `model_registry`, `providers.runtime` |

### 2.2 Module Registry (`shopstack/module_registry.py`)

All module metadata is defined in a single canonical registry. Every UI surface that needs module info (names, tab labels, dependencies, service paths) imports from this registry — never hardcodes strings.

Key data structures:
- `ModuleMetadata` dataclass (frozen) with slug, name, label, description, tab_ids, tab_labels, order, service_modules, depends_on, is_source
- `TAB_ORDER` dict — explicit ordering for the Gradio tab bar
- `TAB_LABELS` dict — canonical display names for every tab
- Lookup helpers: `get_by_slug()`, `get_by_tab_id()`, `tab_label()`, `tab_order()`, `navigation()`, `module_dependencies()`, `summary_table()`

---

## 3. Data Layer

### 3.1 Database (SQLite, WAL mode)

**Connection:** `check_same_thread=False` (safe for Gradio multi-threaded access)

**Tables:**

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `inventory_lots` | Home inventory items | lot_id, canonical_name, quantity, unit, storage_location_id, status, price_paid, expiry dates |
| `purchase_events` | Purchase records | event_id, canonical_name, quantity, total_price, store_name, source_type |
| `shopping_lists` | Active shopping lists | list_id, name, goal, is_active |
| `shopping_list_items` | Items within lists | item_id, list_id, canonical_name, priority, status, linked_lots |
| `household_locations` | 18 seeded storage locations | location_id, name, parent_location_id, location_type |
| `movement_events` | Item location changes | movement_id, lot_id, from/to location, source, confidence |
| `price_observations` | Price history records | price_id, canonical_name, quantity, unit, price, store_name, observation_date |
| `stores` | Store metadata | store_id, name, location, store_type |
| `traces` | Workflow audit trail | trace_id, input_type, user_goal, perception, decision, proposed_tool_calls |
| `app_config` | Key-value config storage | key, value |

**Views (backward-compat aliases):**
- `price_history` → SELECT from `price_observations`
- `agent_traces` → SELECT from `traces`

**Location Hierarchy (18 seeded):**
```
Home
├── Kitchen
│   ├── Fridge
│   │   ├── Fridge Door
│   │   ├── Fridge Top Shelf
│   │   └── Fridge Vegetable Drawer
│   ├── Freezer
│   └── Pantry
│       ├── Pantry Top Shelf
│       ├── Pantry Middle Shelf
│       └── Spice Box
├── Bathroom
│   ├── Bathroom Cabinet
│   └── Under Bathroom Sink
├── Bedroom
│   └── Medicine Drawer
└── Balcony
    └── Balcony Cleaning Shelf
```

### 3.2 Pydantic Models (`shopstack/schemas/models.py`)

All domain models are Pydantic BaseModel classes in a single file:
- `InventoryLot`, `PurchaseEvent`, `DetectionEvent`, `OcrExtraction`
- `ShoppingList`, `ShoppingListItem`
- `VoiceCommand`, `ToolCall`, `Trace`
- `Store`, `PriceObservation`, `HouseholdLocation`, `MovementEvent`
- `TripWeatherContext`, `ItemCatalog`

**Key enums:** `Currency`, `ItemStatus`, `Priority`, `ListItemStatus`, `LocationType`, `SourceType`, `MovementSource`, `RuntimeMode`

**ID generation:** `uuid4().hex[:12]` — 12-char hex IDs throughout.

### 3.3 Configuration (`shopstack/config.py`)

pydantic-settings with `SHOPSTACK_` env prefix:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SHOPSTACK_DB_PATH` | `data/shopstack.db` | Database file path |
| `SHOPSTACK_APP_PORT` | `7860` | Gradio server port |
| `SHOPSTACK_OFF_THE_GRID` | `true` | Use mock providers (no cloud) |
| `SHOPSTACK_PLANNER_BACKEND` | `mock` | Text generation/planning |
| `SHOPSTACK_STT_BACKEND` | `mock` | Speech-to-text |
| `SHOPSTACK_TTS_BACKEND` | `mock` | Text-to-speech |
| `SHOPSTACK_VISION_BACKEND` | `mock` | Vision/object detection |
| `SHOPSTACK_OCR_BACKEND` | `mock` | OCR |
| `SHOPSTACK_SEGMENTATION_BACKEND` | `mock` | Segmentation |
| `SHOPSTACK_LOCAL_MODEL_REPO` | `unsloth/Llama-3.2-3B-Instruct-GGUF` | Local model source |
| `SHOPSTACK_LOCAL_WHISPER_SIZE` | `tiny` | Local whisper model size |
| `SHOPSTACK_OPENAI_API_KEY` | `""` | Cloud fallback key |

---

## 4. Provider System

### 4.1 Provider Interfaces (`shopstack/providers/interfaces.py`)

11 abstract provider ABCs, each defining a capability:

| Interface | Key Methods | Mock Behavior |
|-----------|-------------|---------------|
| `STTProvider` | `transcribe(audio_path)` | Returns predefined Hindi/Hinglish phrases |
| `TTSProvider` | `speak(text)` | Writes note about what would be spoken |
| `VisionProvider` | `analyze(image_path, prompt)` | Random samples from 26 common kitchen items |
| `ObjectDetectionProvider` | `detect(image_path)` | Plausible bounding boxes + confidences |
| `GroundingProvider` | `ground(image_path, text)` | Returns grounded item references |
| `SegmentationProvider` | `segment(image_path)` | Returns placeholder masks |
| `OCRProvider` | `extract_text(image_path)` | Returns mock extracted text |
| `PlannerProvider` | `plan(context)` | Returns structured multi-step plans |
| `ToolCallParserProvider` | `parse(response_text)` | Parses intent → tool call candidates |
| `EmbeddingsProvider` | `embed(texts)` | Returns random 384-d vectors |
| `ImageEditProvider` | `edit(image_path, prompt)` | Returns a dummy edited image path |

### 4.2 Provider Registry (`shopstack/providers/registry.py`)

The `ProviderRegistry` is a factory wired from Settings:
- Reads `SHOPSTACK_*_BACKEND` env vars
- Backend `"mock"` → Mock*Provider (default)
- Backend `"local"` → `LocalProvider` (MLX or llama.cpp)
- Backend `"openai"` → `OpenAIProvider` (cloud)
- Backend `"local_whisper"` → `LocalWhisperProvider`
- Falls back gracefully to mock if a real backend isn't available

### 4.3 Runtime Report (`shopstack/providers/runtime.py`)

`RuntimeReport` dataclass captures:
- Provider name, backend, loaded status, capability count
- Error state if provider failed to init
- Used by the Model Stack UI tab

---

## 5. Tool System

### 5.1 Tool Registry (`shopstack/tools/registry.py`)

11 tools, each registered with name, description, args schema, and handler:

| Tool | Args | Purpose |
|------|------|---------|
| `add_inventory_item` | canonical_name, display_name, quantity, unit, storage_location, category, purchase_date, price_paid | Add new item to inventory |
| `update_inventory_item` | lot_id, updates dict | Update existing inventory item |
| `consume_inventory_item` | lot_id, quantity | Record consumption (partial or full) |
| `move_inventory_item` | lot_id, to_location, from_location | Move item between storage locations |
| `find_item` | name (prefix search) | Search inventory across names & locations |
| `create_or_update_shopping_list` | goal, items list | Create/update the active shopping list |
| `compare_visible_item_to_inventory` | item_name | Compare detected item against current stock |
| `record_price_observation` | canonical_name, price, quantity, unit, store_name | Record a price observation |
| `get_use_soon_items` | days (default 3) | Get items expiring or aging soon |
| `get_next_buy_suggestions` | — | Get suggestions for what to buy next |
| `export_anonymized_trace` | trace_id | Export an anonymized agent trace |

---

## 6. Decision Engine (`shopstack/decisions.py`)

Every household item is classified into one of 7 categories:

| Decision | Color | When |
|----------|-------|------|
| `BUY` | Green | Out of stock or running low, and needed |
| `SKIP` | Gray | Already have enough, recently bought, or high waste risk |
| `USE_SOON` | Amber | Existing stock is expiring or aging |
| `OPTIONAL` | Blue | Not urgent, good-to-have |
| `COMPARE` | Purple | Needs price/store/pack comparison |
| `CONFIRM` | Red | Uncertain data, needs human verification |
| `WATCH` | Light Gray | Not urgent, monitor |

**Classification logic (`_classify()`):**
1. If item is `use_soon` AND `quantity > 0` → USE_SOON
2. If `low_stock` AND `quantity <= 0` → BUY
3. If `low_stock` AND `quantity > 0` → BUY
4. If `on_list` AND `quantity > 0` → SKIP (already have)
5. If `quantity > 0` AND well stocked → SKIP
6. Default → WATCH

**Data sources for classification:**
- Active inventory (DB)
- Use-soon items (3-day threshold)
- Active shopping list items
- Recent purchase events (2-day window)
- Market snapshot prices (Swiggy)
- Produce metadata (shelf life, waste risk)

---

## 7. Market Intelligence System

### 7.1 Data Flow

```
Swiggy Instamart snapshot (CSV/JSON)
  → market/sources/swiggy.py (load + normalize)
    → market/schema.py (NormalizedMarketRecord, MarketSnapshot)
      → domain/unit_price.py (size parser, unit prices, combo detection)
        → market/analytics.py (price stats, cheapest finder)
          → Services (shopping.py enrichment, dashboard.py)
            → UI Screens (other.py swiggy views, shopping.py cards)
```

### 7.2 Normalization Pipeline (`domain/unit_price.py`)

Canonical business logic for size/unit normalization lives in `shopstack/domain/unit_price.py`.
The original `market/normalization.py` is now a thin re-export shim (motto_v3 §7).

Raw Swiggy records are normalized through:
1. **Size parsing** (`parse_size`) — extracts numeric quantity and unit from text like "500 g", "1 kg"
2. **Unit price calculation** (`compute_unit_prices`) — per-kg for weight-based, per-L for volume, per-unit for piece items
3. **Canonical name mapping** (`resolve_canonical`, `CANONICAL_MAP`) — e.g., "Fresh Tomatoes (Hybrid)" → "tomato"
4. **Combo detection** (`canonicalize_name`) — identifies multi-pack/assorted items

### 7.3 Produce Metadata (`market/metadata.py`)

Lookup table for ~80 common produce items with:
- Shelf life in days
- Waste risk (high/medium/low)
- Storage recommendations
- Use-first priority ranking

### 7.4 Basket Builder (`market/basket.py`)

Matches user item requests against available market records using:
- Canonical name matching
- Quantity/unit estimation
- Cheapest option selection
- Summary with total estimate

---

## 8. Planner System

### 8.1 Planner Engine (`shopstack/planner/engine.py`)

`PlannerEngine` orchestrates:
1. **Build prompt** — system prompt + tool definitions + user question
2. **Get completion** — calls ProviderRegistry planner backend
3. **Parse response** — extracts JSON tool calls from LLM output
4. **Execute tools** — runs through ToolRegistry, collects results
5. **Format response** — human-readable output

### 8.2 Parser (`shopstack/planner/parser.py`)

Robust JSON extraction from LLM output:
- Finds ````json` blocks
- Falls back to regex for `[{"tool":...,"args":{...}}]` patterns
- Returns empty list on failure (graceful degradation)

### 8.3 Prompts (`shopstack/planner/prompts.py`)

System prompt builder that generates tool-calling instructions including:
- Current inventory state summary
- Available tools with arg schemas
- Usage examples
- Output format constraints

---

## 9. UI Architecture

### 9.1 Gradio Tab Structure

13 tabs, wired in `app.py` using `module_registry.tab_label()` for canonical names:

| Tab ID | Display Label | Screen Module | Key Functions |
|--------|--------------|---------------|---------------|
| `today` | Today | `screens/dashboard.py` | `today_dashboard()` — 6-value return |
| `ask` | Ask ShopStack | `screens/ask.py` | `ask_shopstack()`, voice add commands |
| `shopping` | Shopping List | `screens/shopping.py` | Create/view/classify/complete lists |
| `market` | Market Lens | `screens/market_lens.py` | Scan, compare, buy/skip decisions |
| `purchase` | Add Purchase | `screens/inventory.py` | Form + batch purchase recording |
| `inventory` | Find Item at Home | `screens/inventory.py` | Search, cards, consume |
| `usesoon` | Use Soon | `screens/inventory.py` | Expiry alerts, consume batch |
| `prices` | Price Memory Check | `screens/price.py` | Price history, intelligence |
| `map` | Map | `screens/other.py` | Location view, move items |
| `modelstack` | Model Stack | `screens/model_stack.py` | Budget, provider status |
| `trace` | Traces | `screens/traces.py` | List, detail, export |
| `portability` | Data | `screens/portability.py` | JSON/CSV export/import |
| `notes` | Field Notes | `screens/field_notes.py` | Markdown editor |

### 9.2 UI Components (`shopstack/ui/components/cards.py`)

HTML rendering helpers:
- `badge_html()` — colored status badges
- `card()` — styled card with header/body
- `empty_state()` — empty state message
- `render_rows()` — HTML table rows from dicts
- `render_decision_card()` — decision with color-coded badge
- `render_grouped_cards()` — grouped decision cards
- `render_metric()` — metric display

### 9.3 UI Views (`shopstack/ui/views.py`)

Dataclass-returning view builders:
- `PriceMemoryView` — price history data + chart info
- `FieldNotesView` — field notes load/save
- `build_price_memory_view()` — assembles price history + chart DataFrame

### 9.4 Error Boundary (`shopstack/ui/screens/_utils.py`)

`@safe_render` decorator catches exceptions in UI render functions and returns a graceful error HTML message instead of crashing the tab.

---

## 10. Service Layer

### 10.1 Shopping Service (`shopstack/services/shopping.py`)

| Function | Purpose |
|----------|---------|
| `normalize_item_name(name)` | Normalize item names (lowercase, strip) |
| `classify_shopping_items(items, tools)` | Classify items via LLM (buy/skip/use-soon) |
| `enrich_items_with_swiggy(items)` | Add Swiggy price/availability data |
| `complete_shopping_list_service(list_id, tools)` | Complete list → add to inventory |
| `mark_items_purchased_service(item_ids_json, tools)` | Mark items purchased |

### 10.2 Market Lens Service (`shopstack/services/market_lens.py`)

| Function | Purpose |
|----------|---------|
| `analyze_market_lens(image_path, audio_path, providers, tools)` | Full pipeline: detect → compare → decide |
| `detect_barcodes(image_path)` | Decode barcodes from image |
| `analyze_visible_items(image_path, providers, tools)` | Object detection + inventory comparison |
| `enrich_market_prices(decisions)` | Add Swiggy price data to decisions |
| `transcribe_audio(audio_path, providers)` | Speech-to-text |

### 10.3 Dashboard Service (`shopstack/services/dashboard.py`)

| Function | Purpose |
|----------|---------|
| `build_dashboard_state(db, tools)` | Assemble full dashboard state: inventory stats, use-soon, market basket, low-stock, recent purchases |

---

## 11. Model Registry (`shopstack/model_registry.py`)

16 candidate model entries across 7 provider groups.

**Parameter budget:** ≤32B total active params (enforced by `validate_active_model_budget()`).

### Active Models:

| Model | Group | Params | Runtime | Backend Config |
|-------|-------|--------|---------|----------------|
| `llama-3.2-3b-instruct` (MLX) | Planner | 3.0B | mlx | `PLANNER_BACKEND=local` |
| `llama-3.2-3b-gguf` | Planner | 3.0B | gguf | (llama.cpp fallback) |
| `local-whisper-tiny` (MLX) | STT | 0.04B | mlx | `STT_BACKEND=local_whisper` |

**Total active: ≤6.04B params** — well within 32B cap.

---

## 12. Trace System (`shopstack/traces/export.py`)

Every tool execution creates an agent trace stored in the database. Traces include:
- Perception snapshots
- Inventory context before/after
- Decision rationale
- Proposed tool calls
- Human confirmation status

**PII Redaction:** Phone numbers (10+ digits), emails, Aadhar (12-digit), PAN (5+4+1), addresses. Generic `name` fields are preserved.

**Export:** JSONL format via `export_traces()`.

---

## 13. Portability (`shopstack/portability.py`)

- **JSON export:** Full inventory + price observations + purchase events + field notes
- **CSV export:** Inventory items only
- **JSON import:** Inventory + price observations + field notes (with dedup)
- **CSV import:** Inventory items only (with dedup)
- **Schema version:** 1.0

---

## 14. CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):
- Runs on push/PR to main
- Sets up Python 3.13
- Installs dependencies in dev mode
- Runs full test suite
- Runs benchmark suite

Pre-commit hook runs `tools/sync-readme-stats` to keep README test counts current.

---

## 15. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Single schemas file** | Models share enums; avoid circular imports |
| **Provider ABCs named *Provider** | Clear naming convention prevents confusion |
| **PurchaseEvent with per-item fields** | No separate join table for simple purchases |
| **12-char hex IDs** | Short enough for prefix resolution, collision-resistant |
| **WAL mode** | Concurrent read/write safe for Gradio |
| **18 seeded locations** | Hierarchical, covers typical Indian household |
| **No auto-purchase/payment scraping** | Design-level constraint; ShopStack advises, doesn't buy |
| **PII redaction targeted** | Only phone/email/Aadhar/PAN/address; generic names preserved |
| **Mock providers as default** | Full app works without any ML model loaded |
| **`_env_file=None` in tests** | Prevents `.env` from affecting test results |
| **shopstack.ui package** | All render logic consolidated; no orphan modules |
| **service boundary extraction** | Product logic lives in services/; screens are Gradio adapters |
| **module_registry canonical names** | No hardcoded tab labels anywhere in app.py |

---

## 16. FastAPI /api/v1 Layer

Pass 26 (2026-06-17) introduced a **versioned REST API** mounted on Gradio's
embedded FastAPI instance. The API lives alongside the Gradio UI on the same
server/port — no separate deployment needed.

### 16.1 Mount Point

All routes are declared as FastAPI ``APIRouter`` instances in
``shopstack/api/v1/routers/`` and mounted at startup by
``shopstack/api/v1/mount.py::mount_v1_routes()``. The mount is:

- **Idempotent** — duplicate routes are caught and logged, not raised.
- **Post-launch safe** — called both inside ``with gr.Blocks()`` and
  from the post-launch hook (Gradio recreates ``app.app`` on launch).

### 16.2 Router Map

| Prefix | Router | Auth | Purpose |
|--------|--------|------|---------|
| ``/meta`` | ``meta_router`` | Public | whoami, health, runtime |
| ``/auth`` | ``auth_router`` | Public | register, login, refresh, logout |
| ``/inventory`` | ``inventory_router`` | Bearer | list, get, add, consume lots |
| ``/household`` | ``household_router`` | Bearer | list, create, switch household |
| ``/shopping`` | ``shopping_router`` | Bearer | active list, create, complete, mark-purchased |
| ``/dashboard`` | ``dashboard_router`` | Bearer | today snapshot |
| ``/command`` | ``command_router`` | Bearer | preview, execute, recent |
| ``/search`` | ``search_router`` | Bearer | global, inventory, voice-intent |
| ``/traces`` | ``traces_router`` | Bearer | list, get, export |
| ``/intelligence`` | ``intelligence_router`` | Bearer | decision explain, recurring plan, meal plan |
| ``/account`` | ``account_router`` | Bearer | privacy, undo, store-mode toggle |
| ``/corrections`` | ``corrections_router`` | Bearer | list, create corrections |
| ``/sms`` | ``sms_router`` | Public (Twilio-signed) | webhook |

### 16.3 Auth Model

Device-scoped bearer authentication:

1. **Device registration** — Client generates ``device_id`` + ``device_secret``
   (random 64-char hex), calls ``POST /api/v1/auth/register``.
2. **Token issuance** — Server returns opaque 40-char hex bearer token.
3. **Request auth** — ``Authorization: Bearer <token>`` header on every request.
   Query-string fallback (``?token=<token>``) for Gradio-rendered clients.
4. **Refresh** — ``POST /api/v1/auth/refresh`` with valid token returns a new token.
5. **Logout** — ``POST /api/v1/auth/logout`` revokes the token server-side.

### 16.4 OpenAPI Schema

``shopstack/api/v1/openapi.py`` generates the full OpenAPI 3.0 schema using
a standalone FastAPI app (no DB, no Gradio, no middleware — routes only):

```bash
python -c "from shopstack.api.v1.openapi import openapi_schema_json; print(openapi_schema_json())"
```

Key details:
- Bearer security scheme injected post-generation (routers use ``Depends()``, not ``Security()``).
- Public paths (``/meta``, ``/auth``, ``/sms``) remain unauthenticated.
- Schema is the canonical contract for the mobile client; contract tests assert equality.

### 16.5 Frontend Shell

``shopstack/api/v1/frontend_shell.py`` renders a **standalone HTML/CSS frontend**
served by FastAPI routes (not Gradio blocks). It communicates entirely through
the ``/api/v1/*`` REST endpoints and provides:

- Full device auth flow
- Dashboard, inventory, shopping, search CRUD
- Intelligence panels, privacy controls, trace viewer
- Store mode (in-store check-off with progress bar)
- Mobile-responsive dark theme

## 17. shopstack-mobile (React Native / Expo)

``shopstack-mobile/`` is a **React Native (Expo) app** introduced in Pass 27
(2026-06-17) that consumes the ``/api/v1`` REST API.

### 17.1 Architecture

```
shopstack-mobile/
├── app/                    # expo-router file-based navigation
│   ├── _layout.tsx         # Root: auth gate + React Query provider
│   ├── (auth)/             # Login, Register
│   ├── (tabs)/             # Today, Pantry, Shopping, Search, More
│   ├── intelligence.tsx
│   ├── account.tsx
│   ├── traces.tsx
│   ├── corrections.tsx
│   └── store-mode.tsx
├── src/
│   ├── api/
│   │   ├── types.ts        # 70+ TypeScript interfaces from Pydantic schemas
│   │   ├── client.ts       # HTTP client (Bearer token, 15s timeout, caching)
│   │   ├── auth.ts
│   │   ├── inventory.ts    # 9 endpoint modules
│   │   ├── shopping.ts
│   │   ├── dashboard.ts
│   │   ├── search.ts
│   │   ├── intelligence.ts
│   │   ├── account.ts
│   │   ├── traces.ts
│   │   └── corrections.ts
│   └── storage/
│       └── token.ts        # expo-secure-store wrapper
├── app.json
├── package.json
├── tsconfig.json
├── babel.config.js
├── .gitignore
└── README.md
```

### 17.2 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Framework** | Expo managed workflow | CRUD-only app needs no native modules. EAS for OTA updates. |
| **Navigation** | expo-router (file-based) | Zero boilerplate, deep links built-in. |
| **Caching** | TanStack React Query | Stale-while-revalidate, background refetch, offline resilience. |
| **Auth storage** | expo-secure-store | Hardware-backed on iOS/Android, localStorage web fallback. |
| **API client** | Custom fetch wrapper | Bearer injection, 15s timeout, error categorization, in-memory caching. |
| **Screens** | 12 screens, full API coverage | Every /api/v1 router mapped to a screen. |

### 17.3 Auth Flow

1. **First launch:** User enters server URL → generates ``device_id`` +
   ``device_secret`` → ``POST /api/v1/auth/register`` → stores token.
2. **Subsequent launches:** Root layout checks secure store for token →
   if found, shows tabs immediately.
3. **Re-login:** Login screen reads stored device creds →
   ``POST /api/v1/auth/login`` silently.
4. **Logout:** Clears token + device creds from secure store → forces re-auth.

## 18. Future Architecture Targets


| Area | Planned Approach | Status |
|------|------------------|--------|
| **Cloud inference fallback** | HF Inference API provider | Built in `providers/huggingface_provider.py` (26 tests) |
| **Modal cloud GPU** | Modal provider for heavy models | Built in `providers/modal_provider.py` |
| **Semantic search** | BGE-M3 + Nomic embeddings | Both providers built in `providers/embeddings_provider.py`. Default is Nomic (config: `embeddings_backend=nomic`). Wired into `services/search.py` + `services/find.py`. |
| **Receipt scanning** | OCR pipeline → purchase creation | Pipeline built: `services/ocr_pipeline.py` (3-stage) + `services/receipt.py` (full pipeline). OCR provider, Tesseract provider, and dedicated receipt screen exist. |
| **Multi-retailer sources** | Blinkit, Zepto, DMart adapters | All 4 built: Swiggy `_swiggy_adapter.py`, Blinkit `_blinkit_adapter.py`, Zepto `_zepto_adapter.py`, DMart `_dmart_adapter.py`. Cross-source comparison in `_comparison.py`. |
| **Correction review UI** | Accept/reject corrections | Built: dedicated `ui/screens/corrections.py` (264 lines), wired into Memory tab, per-row inline accept/reject buttons, DB `correction_events` table. |
| **Multi-user auth** | user_id columns exist in DB | Not started |
| **Production deployment** | Docker + deployment config | Not started |
