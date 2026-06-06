# ShopStack

Local-first, off-the-grid **shopping intelligence platform**. Know what you have, what to use soon, what to buy, what to skip, and where to buy from — without sending your data to the cloud.

ShopStack is a stack of shopping intelligence layers: home inventory (ShopStock), shopping lists and market baskets (ShopBasket), retailer price comparison (ShopCompare), scanning and import (ShopLens), price history and preferences (ShopMemory), and a reasoning agent (ShopAgent) that decides buy/skip/use-soon across all modules.

## Philosophy

ShopStack runs entirely locally — SQLite database (WAL mode), mockable provider interfaces, and a Gradio workflow UI that works offline. The "Off the Grid" path means zero cloud dependencies for core functionality.
The default mock providers let you build and test the full app without loading any ML models.

**Total parameter limit:** ≤32 billion parameters across all loaded models.

## Modules

| Module | Purpose |
|--------|---------|
| **ShopStock** | Inventory, pantry, fridge, expiry, low-stock, use-soon |
| **ShopBasket** | Shopping list, cart builder, market basket optimization |
| **ShopCompare** | Retailer price comparison (Swiggy, Blinkit, Zepto, ...) |
| **ShopLens** | Scanning: barcode, photo, receipt, barcode |
| **ShopMemory** | Price history, household preferences, field notes |
| **ShopAgent** | Reasoning: buy/skip/use-soon/compare decisions |
| **Sources** | Retailer datasets (Swiggy Instamart + future) |

See `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` for full details.

## Gradio Workflows

ShopStack is organized around workflow experiences:

- **Today** — Decision-first dashboard: what to buy, skip, use soon, and compare
- **Ask ShopStack** — Natural language queries across all modules
- **Shopping List** — Create, classify (buy/skip/use-soon), and complete shopping plans
- **Market Lens** — Scan items via camera or voice, compare to inventory
- **Add Purchase** — Record what was bought (price, store, location)
- **Find Item at Home** — Search inventory by location and status
- **Use Soon** — Expiring and aging items flagged for attention
- **Price Memory Check** — Price history, trends, and best-store intelligence
- **Traces** — Workflow audit trail with redacted export
- **Field Notes** — Household notes and preferences

## Quick Start

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
uv run python app.py
```

Open `http://localhost:7860` in your browser.

## Market Snapshot Import

ShopStack can ingest the real Swiggy Instamart fresh vegetables snapshot found in `data/swiggy_fresh_vegetables_cards_6jun26.json` (or the matching CSV) into the local price observation database.

```bash
uv run python scripts/import_swiggy_snapshot.py
```

Imported observations are tagged with `source_event_id = swiggy_fresh_vegetables_20260606` so they can be filtered or audited later.

## Tests

```bash
uv run pytest tests/ -v          # 376 passed in 9.45s
uv run pytest benchmarks/ -v -m benchmark  # 9 passed in 0.04s
```

| Module | Tests | What it covers |
|--------|-------|----------------|
| `test_config.py` | 3 | Settings defaults, env overrides, provider backend defaults |
| `test_schemas.py` | 17 | All 14+ Pydantic models: validation, defaults, serialization |
| `test_database.py` | 23 | CRUD for all core tables, config storage, location seeding, edge cases |
| `test_tools.py` | 18 | All 11 tool implementations, error paths |
| `test_traces.py` | 23 | PII redaction (phone, email, Aadhar, PAN), create/export traces |
| `test_views.py` | 22 | Gradio view helpers and workflow surfaces |
| `test_ui_support.py` | 4 | Price memory charting and field-note persistence helpers |
| `tests/test_model_registry.py` | 4 | Model budget math, active/candidate accounting, cap checks |

## Project Structure

```
shopstack/
  __init__.py
  _version.py               # v0.1.0
  config.py                 # Settings (pydantic-settings, env prefix SHOPSTACK_)
  model_registry.py         # 16 candidate model entries (all ≤32B total)
  schemas/
    models.py               # All Pydantic domain models (14+ classes, 16 enums)
  providers/
    interfaces.py           # 11 abstract provider ABCs
    mock_providers.py       # Full mock implementations for all 11 (Indian/Hinglish data)
    registry.py             # ProviderRegistry factory wired to Settings
  persistence/
    database.py             # SQLite Database (WAL, 9 tables, 18 seeded locations, full CRUD)
  tools/
    registry.py             # ToolRegistry — 11 tools executing against Database
  traces/
    export.py               # Trace creation, JSONL export, PII redaction
  data_sources/             # Data source adapters for market snapshots and external feeds
  ui/                       # (reserved)
  configs/                  # (reserved)

app.py                      # Gradio Blocks UI entry point (workflow-first tabs, custom warm CSS)
tests/                      # pytest test suite (155 tests)
benchmarks/                 # pytest benchmark suite (9 latency markers)
```

## Architecture

```
Gradio Blocks (app.py)
  → ToolRegistry (11 tools, validates args, calls Database)
    → Database (SQLite WAL, 9 tables, 18 seeded locations)
  → ProviderRegistry (wired from Settings)
    → MockProviders (default — 11 interfaces, all offline)
  → Settings (pydantic-settings, env-overridable)
  → ModelRegistry (16 candidates, not loaded by default)
```

### 11 Provider Interfaces

| Interface | Mock Behavior |
|-----------|--------------|
| `STTProvider` | Returns predefined Hindi/Hinglish phrases |
| `TTSProvider` | Writes a note about what would be spoken |
| `VisionProvider` | Randomly samples from 26 common kitchen items |
| `ObjectDetectionProvider` | Returns plausible bounding boxes + confidences |
| `GroundingProvider` | Returns grounded item references |
| `SegmentationProvider` | Returns placeholder masks |
| `OCRProvider` | Returns mock extracted text |
| `PlannerProvider` | Returns structured multi-step plans |
| `ToolCallParserProvider` | Parses intent → tool call candidates |
| `EmbeddingsProvider` | Returns random 384-d vectors |
| `ImageEditProvider` | Returns a dummy edited image path |

### 11 Tools

| Tool | Purpose |
|------|---------|
| `add_inventory_item` | Add a new item to household inventory |
| `update_inventory_item` | Update details of an existing inventory item |
| `consume_inventory_item` | Record consumption (partial or full) |
| `move_inventory_item` | Move an item to a different storage location |
| `find_item` | Search for an item across inventory and locations |
| `create_or_update_shopping_list` | Create/update the active shopping list |
| `compare_visible_item_to_inventory` | Compare detected item against current stock |
| `record_price_observation` | Record a price observation for an item |
| `get_use_soon_items` | Get items expiring or aging soon |
| `get_next_buy_suggestions` | Get suggestions for what to buy next |
| `export_anonymized_trace` | Export an anonymized agent trace |

### 9 Database Tables

`inventory_lots`, `movement_events`, `purchase_events`, `price_observations`, `shopping_lists`, `shopping_list_items`, `household_locations`, `detection_events`, `traces`

Compatibility aliases: `price_history` and `agent_traces` are exposed as read/delete-compatible views for older docs, tests, and scripts.

18 hierarchical household locations seeded on every init (safe via COUNT check): Home → Kitchen → Fridge → Fridge Door → ..., Pantry → Shelf → ..., etc.

### Trace System

Every tool execution creates an agent trace stored in the database. Traces include perception snapshots, inventory context, decision rationale, proposed tool calls, and human confirmation status. On export, traces are **redacted** for PII:

- Phone numbers (10+ digits)
- Email addresses
- Aadhar numbers (12-digit pattern)
- PAN numbers (5 letters + 4 digits + 1 letter)
- Geo addresses (street patterns)

Explicitly **not** redacted: generic `name` fields, canonical item names, location names.

## Screens

| Tab | Purpose |
|-----|---------|
| **Plan Today's Shopping** | Dashboard workflow — today view, use-soon signals, and shopping recommendations |
| **Shopping List** | View / create / manage the active shopping list |
| **Market Lens: Should I Buy This?** | Camera / voice input → detect → compare vs inventory |
| **Add Purchase** | Manual purchase recording form with store, price, item details |
| **Find an Item at Home** | Search + map lookup for likely storage location |
| **Use Soon / Waste Saver** | Expiring and aging items with priority list |
| **Price Memory Check** | Historical price observations per item |
| **Find Item Location** | Storage hierarchy and item count view |
| **Model Stack** | Active model stack + budget status and candidate catalog |
| **Agent Trace** | Agent session trace viewer with redaction preview |
| **Field Notes** | Agent reasoning and decision log |

## Configuration

All settings are pydantic-settings with `SHOPSTACK_` env prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOPSTACK_DB_PATH` | `data/shopstack.db` | SQLite database file path |
| `SHOPSTACK_APP_PORT` | `7860` | Gradio server port |
| `SHOPSTACK_OFF_THE_GRID` | `true` | Use mock providers (no cloud) |
| `SHOPSTACK_STT_BACKEND` | `mock` | STT provider selection |
| `SHOPSTACK_TTS_BACKEND` | `mock` | TTS provider selection |
| `SHOPSTACK_VISION_BACKEND` | `mock` | Vision provider selection |
| `SHOPSTACK_OBJECT_DETECTION_BACKEND` | `mock` | Object detection provider |
| ... per-provider backends default to `mock` |

## Model Catalog

See **[`Docs/MODEL_CATALOG.md`](Docs/MODEL_CATALOG.md)** for the full living model catalog — including downloaded & tested models, parameter budget tracking, runtime backends (MLX, llama.cpp/GGUF, transformers), HF Pro and Modal Labs credit resources, and experiment logs.

The programmatic registry lives in `shopstack/model_registry.py` (16+ entries across STT, TTS, Vision, OCR, Embeddings, and Planner categories).

- **Active / loaded models**: actually selected at runtime.
- **Candidate models**: documented options available for future activation.
- **Budget check**: only active/loaded models are counted against the **32B** cap (enforced by `validate_active_model_budget()`).

**Active design constraint:** Total parameter count across all simultaneously active models must not exceed 32 billion. Mock mode shows an active-loaded stack of `0B`.

## Key Design Decisions

- **Single shared schemas file** — models are interconnected and share enums; a single file avoids circular imports.
- **Provider ABCs named `*Provider`** — `STTProvider`, not `STT`; mock classes named `Mock*Provider`.
- **PurchaseEvent enriched with per-item fields** — `canonical_name`, `quantity`, `unit`, `total_price` live on the event, not on a separate join table.
- **PriceObservation defaults** — `observation_date` defaults to `date.today()`.
- **PII redaction is targeted** — only phone, email, Aadhar, PAN, and address patterns are redacted. Generic `name` keys are preserved.
- **No auto-purchase or payment scraping** — design-level constraint. ShopStack tells you what to buy, it doesn't buy for you.

## Development

```bash
uv pip install -e ".[dev]"
uv run pytest tests/ -v
uv run pytest benchmarks/ -v -m benchmark
uv run python app.py
```

## License

MIT
