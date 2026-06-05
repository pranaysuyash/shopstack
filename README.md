# ShopStack

Local-first, off-the-grid household inventory management. Know what you have, what needs using, and what to buy next — without sending your data to the cloud.

## Philosophy

ShopStack runs entirely locally — SQLite database (WAL mode), mockable provider interfaces, and a Gradio UI that works offline. The "Off the Grid" path means zero cloud dependencies for core functionality. Model providers are swappable via a registry pattern; the default mock providers let you develop and test the full app without loading a single ML model.

**Total parameter limit:** ≤32 billion parameters across all loaded models.

## Quick Start

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
uv run python app.py
```

Open `http://localhost:7860` in your browser.

## Tests

```bash
uv run pytest tests/ -v          # 118 passed in 2.40s
uv run pytest benchmarks/ -v -m benchmark  # 9 passed in 0.05s
```

| Module | Tests | What it covers |
|--------|-------|----------------|
| `test_config.py` | 3 | Settings defaults, env overrides, provider backend defaults |
| `test_schemas.py` | 17 | All 14+ Pydantic models: validation, defaults, serialization |
| `test_database.py` | 23 | CRUD for all core tables, config storage, location seeding, edge cases |
| `test_tools.py` | 18 | All 11 tool implementations, error paths |
| `test_traces.py` | 23 | PII redaction (phone, email, Aadhar, PAN), create/export traces |
| `test_views.py` | 20 | Gradio view helpers and UI flows |
| `test_ui_support.py` | 4 | Price memory charting and field-note persistence helpers |

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
  ui/                       # (reserved)
  configs/                  # (reserved)

app.py                      # Gradio Blocks UI entry point (10 tabs, custom dark CSS)
tests/                      # pytest test suite (82 tests)
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
| **Today** | Dashboard — stats, use-soon items, shopping list, low stock alerts |
| **Shopping List** | View / create / manage the active shopping list |
| **Market Lens** | Camera / voice input → detect → compare against inventory |
| **Add Purchase** | Manual purchase recording form with store, price, item details |
| **Inventory** | Full table view, search, consume items |
| **Use Soon** | Expiring and aging items that need attention |
| **Price Memory** | Historical price observations per item |
| **Household Map** | Storage location hierarchy with item counts |
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

## Model Registry

16 candidate model entries across STT, TTS, Vision, OCR, Embeddings, and Planner categories. All entries are candidate-only — no model binaries are bundled. Replace mock providers with real model implementations by subclassing the provider interfaces and registering with the ProviderRegistry.

**Active design constraint:** Total parameter count across all simultaneously active models must not exceed 32 billion.

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
