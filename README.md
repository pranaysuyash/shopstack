---
title: ShopStack
emoji: 🛒
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: "6.17.3"
app_file: app.py
pinned: false
tags: [shopstack, gradio, inventory, shopping, offline-first, household]
---

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
uv run pytest tests/ -v
uv run pytest benchmarks/ -v -m benchmark
```

Run `uv run pytest tests/ --collect-only -q` for the current test count.

## Current Verified by Code Inspection

As of the current code inspection, the following metrics are verified:
- **25 Database Tables, 2 Views, 2 Triggers, 9 Indexes**: `app_config`, `condition_events`, `find_feedback`, `household_locations`, `household_members`, `household_objects`, `households`, `inventory_events`, `inventory_lots`, `market_record_components`, `market_records`, `market_snapshots`, `movement_events`, `negative_memory`, `object_notes`, `object_sightings`, `person_associations`, `preference_signals`, `price_observations`, `purchase_events`, `reconciliation_events`, `shopping_list_items`, `shopping_lists`, `stores`, `traces` (Tables), `price_history`, `agent_traces` (Views).
- **12 Tools**: Including `semantic_find_item`.

*Note: For the canonical current-state metrics, run `python3 scripts/repo_truth.py`. The README is updated when new tables/tabs/tools are added; do not hand-maintain these numbers.*

**Engineering Mandate:** Do not narrow scope to hackathon/MVP. ShopStack is designed as a long-term, bold, and comprehensive intelligence platform. Follow `motto_v3.md` principles exactly.

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
    database.py             # SQLite Database (WAL, 25 tables, 2 views, 2 triggers, 9 indexes, full CRUD)
  services/                 # Business logic services (decision engine, shopping, dashboard, preferences, freshness)
  tools/
    registry.py             # ToolRegistry — 12 tools executing against Database
  traces/
    export.py               # Trace creation, JSONL export, PII redaction
  data_sources/             # Data source adapters for market snapshots and external feeds
  ui/                       # (reserved)
  configs/                  # (reserved)

app.py                      # Gradio Blocks UI entry point (workflow-first tabs, custom warm CSS)
tests/                      # pytest test suite (run `pytest tests/ --collect-only -q` for current count)
benchmarks/                 # pytest benchmark suite (9 latency markers)
```

## Architecture

```
Gradio Blocks (app.py)
  → ToolRegistry (12 tools, validates args, calls Database)
    → Database (SQLite WAL, 25 tables, 2 views, 2 triggers, 9 indexes)
  → ProviderRegistry (wired from Settings)
    → MockProviders (default — 11 interfaces, all offline)
    → Market services (market source registry load + snapshot status helpers in `shopstack.services.market_sources`)
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

### 12 Tools

| Tool | Purpose |
|------|---------|
| `add_inventory_item` | Add a new item to household inventory |
| `update_inventory_item` | Update details of an existing inventory item |
| `consume_inventory_item` | Record consumption (partial or full) |
| `move_inventory_item` | Move an item to a different storage location |
| `find_item` | Search for an item across inventory and locations |
| `semantic_find_item` | Search for an item using exact, prefix, and semantic embedding search with match quality scores |
| `create_or_update_shopping_list` | Create/update the active shopping list |
| `compare_visible_item_to_inventory` | Compare detected item against current stock |
| `record_price_observation` | Record a price observation for an item |
| `get_use_soon_items` | Get items expiring or aging soon |
| `get_next_buy_suggestions` | Get suggestions for what to buy next |
| `export_anonymized_trace` | Export an anonymized agent trace |

### 10 Database Tables

`inventory_lots`, `purchase_events`, `shopping_lists`, `shopping_list_items`, `household_locations`, `movement_events`, `price_observations`, `stores`, `traces`, `app_config`

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

Operational resource guards are documented in **[`Docs/RESOURCE_OPTIMIZATION_POLICY.md`](Docs/RESOURCE_OPTIMIZATION_POLICY.md)**.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOPSTACK_DB_PATH` | `data/shopstack.db` | SQLite database file path |
| `SHOPSTACK_APP_PORT` | `7860` | Gradio server port |
| `SHOPSTACK_OFF_THE_GRID` | `true` | Use mock providers (no cloud) |
| `SHOPSTACK_LOCAL_AUTO_UNLOAD` | `true` | Unload local model runtime after each local provider call |
| `SHOPSTACK_LOCAL_WHISPER_AUTO_UNLOAD` | `true` | Unload local STT model after each transcription |
| `SHOPSTACK_TRACE_MAX_ROWS` | `2000` | Maximum number of trace rows to retain |
| `SHOPSTACK_TRACE_TTL_DAYS` | `30` | Delete traces older than this many days |
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

## Deployment

ShopStack can run via Docker or on any of the supported platforms.

### Docker (local)

```bash
docker compose up --build
# Open http://localhost:7860
```

Data persists in a Docker volume (`shopstack_data`).

### Docker (standalone)

```bash
docker build -t shopstack .
docker run -p 7860:7860 -v shopstack_data:/app/data shopstack
```

### Railway

1. Push your repo to GitHub.
2. Create a new project on [Railway](https://railway.app) → **Deploy from GitHub repo**.
3. Railway auto-detects `Dockerfile` and `railway.json`.
4. Add a **Volume** with mount path `/app/data` (1 GB) for SQLite persistence.
5. (Optional) Set `SHOPSTACK_HF_API_KEY` and `SHOPSTACK_PLANNER_BACKEND=huggingface` for cloud-backed planning.

### Render

1. Push your repo to GitHub.
2. Create a new **Web Service** on [Render](https://render.com) → **Deploy from Dockerfile**.
3. Select the **Starter** plan ($7/mo) — required for persistent disk.
4. Add a **Disk** mount at `/app/data` with 1 GB.
5. `render.yaml` is auto-detected if you connect via Blueprint.

### Fly.io

```bash
# Install flyctl first: https://fly.io/docs/hands-on/install-flyctl/
flyctl launch --dockerfile ./Dockerfile
flyctl volumes create shopstack_data --region <your-region> --size 1
flyctl deploy
```

See `fly.toml` for configuration reference.

## License

MIT
