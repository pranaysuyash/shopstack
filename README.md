---
title: ShopStack
emoji: 🛒
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
tags: [shopstack, inventory, shopping, offline-first, household, fastapi]
---

# ShopStack

> **Doc links:** Several links in this README point to `Docs/` paths that are intentionally local-only (see `Docs/README.md`). They work in a local workspace but 404 from a clean clone. For canonical architecture, see `shopstack/module_registry.py` and the code under `shopstack/`. Git-tracked docs (`MODEL_CATALOG.md`, this README) are reachable from any clone.

Local-first, off-the-grid **shopping intelligence platform**. Know what you have, what to use soon, what to buy, what to skip, and where to buy from — without sending your data to the cloud.

ShopStack is a stack of shopping intelligence layers: home inventory (ShopStock), shopping lists and market baskets (ShopBasket), retailer price comparison (ShopCompare), scanning and import (ShopLens), price history and preferences (ShopMemory), and a reasoning agent (ShopAgent) that decides buy/skip/use-soon across all modules.

## Philosophy

ShopStack runs entirely locally — SQLite database (WAL mode), mockable provider interfaces, and an API-first FastAPI frontend shell that works offline. The "Off the Grid" path means zero cloud dependencies for core functionality.
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

See `Docs/ARCHITECTURE.md` for the full system architecture and `Docs/SERVICES_ARCHITECTURE.md` for the service layer.

## Frontend Shell

ShopStack is organized around workflow experiences in the FastAPI shell:

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
- **26 Database Tables, 2 Views, 2 Triggers, 10 Indexes**: `app_config`, `condition_events`, `correction_events`, `find_feedback`, `household_locations`, `household_members`, `household_objects`, `households`, `inventory_events`, `inventory_lots`, `market_record_components`, `market_records`, `market_snapshots`, `movement_events`, `negative_memory`, `object_notes`, `object_sightings`, `person_associations`, `preference_signals`, `price_observations`, `purchase_events`, `reconciliation_events`, `shopping_list_items`, `shopping_lists`, `stores`, `traces` (Tables), `price_history`, `agent_traces` (Views).
- **17 Tools**: Including `semantic_find_item`.

*Note: For the canonical current-state metrics, run `python3 scripts/repo_truth.py`. The README is updated when new tables/tabs/tools are added; do not hand-maintain these numbers.*

**Engineering Mandate:** Do not narrow scope to hackathon/MVP. ShopStack is designed as a long-term, bold, and comprehensive intelligence platform. Follow `motto_v5.md` principles exactly.

## Project Structure

```
shopstack/
  __init__.py
  _version.py               # v0.1.0
  config.py                 # Settings (pydantic-settings, env prefix SHOPSTACK_)
  model_registry.py         # 58 model entries (10 active / 46 candidate / 2 rejected; all ≤32B total active)
  schemas/
    models.py               # All Pydantic domain models (14+ classes, 16 enums)
  providers/
    interfaces.py           # 11 abstract provider ABCs
    mock_providers.py       # Full mock implementations for all 11 (Indian/Hinglish data)
    registry.py             # ProviderRegistry factory wired to Settings
  persistence/
    database.py             # SQLite Database (WAL, 26 tables, 2 views, 2 triggers, 10 indexes, full CRUD)
  services/                 # Business logic services (decision engine, shopping, dashboard, preferences, freshness)
  tools/
    registry.py             # ToolRegistry — 17 tools executing against Database
  traces/
    export.py               # Trace creation, JSONL export, PII redaction
  market/sources/           # Data source adapters for market snapshots and external feeds
  ui/                       # (reserved)
  configs/                  # (reserved)

app.py                      # FastAPI entry shim (launches the backend host)
tests/                      # pytest test suite (run `pytest tests/ --collect-only -q` for current count)
benchmarks/                 # pytest benchmark suite (9 latency markers)
```

## Architecture

```
FastAPI host (shopstack/server.py)
  → ToolRegistry (17 tools, validates args, calls Database)
    → Database (SQLite WAL, 26 tables, 2 views, 2 triggers, 10 indexes)
  → ProviderRegistry (wired from Settings)
    → MockProviders (default — 11 interfaces, all offline)
    → Market services (market source registry load + snapshot status helpers in `shopstack.services.market_sources`)
  → Settings (pydantic-settings, env-overridable)
  → ModelRegistry (58 entries, not loaded by default)
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

### 17 Tools

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
| `undo_last_inventory_change` | Undo the most recent change (add, consume, or move) to an inventory item |
| `calculate_nutrition` | Look up nutrition (calories, protein, carbs, fat) for a food item by name |
| `check_price_drop` | Report items whose current market price is 15%+ below their historical median |
| `find_substitute` | Suggest category or ingredient substitutes for a sold-out or unavailable item |
| `get_weather_recommendation` | Recommend whether to shop in-store, order delivery, or delay based on weather |

### 26 Database Tables

Core tables (the full set of 26 is enumerated in *Current Verified by Code Inspection* above): `inventory_lots`, `purchase_events`, `shopping_lists`, `shopping_list_items`, `household_locations`, `movement_events`, `price_observations`, `stores`, `traces`, `app_config`

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

## FastAPI /api/v1 REST API

ShopStack exposes a **versioned HTTP API** under `/api/v1/*` for the mobile app and other HTTP clients. The API is mounted directly on the FastAPI host at startup, alongside the HTML shell served at `/`.

### Architecture

```
HTTP Client (shopstack-mobile, curl, etc.)
  │
  ├── GET  /api/v1/meta/...           ← public (no auth)
  ├── POST /api/v1/auth/...           ← public (bootstraps sessions)
  ├── POST /api/v1/sms/...            ← public (Twilio webhooks)
  │
  └── ALL /api/v1/{inventory,shopping,dashboard,
                  search,intelligence,account,traces,
                  corrections,command,household}/*  ← Bearer token required
```

### Auth model

| Concept | Implementation |
|---------|---------------|
| **Device identity** | `device_id` + `device_secret` generated client-side, registered via `POST /auth/register` |
| **Token** | Opaque bearer token (40-char hex), returned on register/login, refreshed via `POST /auth/refresh` |
| **Transport** | `Authorization: Bearer <token>` header |
| **Storage** | `expo-secure-store` (iOS/Android) or `localStorage` (web fallback) |
| **Household scoping** | Authenticated operations are scoped to the user's household |

### Endpoints

| Router | Endpoints | Description |
|--------|-----------|-------------|
| **`/meta`** | `whoami`, `health`, `runtime` | Server identity, health check, model runtime status |
| **`/auth`** | `register`, `login`, `refresh`, `logout` | Device registration, authentication, session management |
| **`/inventory`** | `list lots`, `get lot`, `add lot`, `consume lot` | Household inventory CRUD |
| **`/household`** | `list`, `create`, `switch` | Multi-household support |
| **`/shopping`** | `get active`, `create list`, `add items`, `complete`, `mark-purchased` | Shopping list management |
| **`/dashboard`** | `today` | Today's snapshot: pantry count, use-soon, low items, recent purchases |
| **`/command`** | `preview`, `execute`, `recent` | Natural language command processing |
| **`/search`** | `global`, `inventory`, `voice-intent` | Text + semantic search across inventory |
| **`/traces`** | `list`, `get`, `export` | Workflow audit trail with PII-redacted export |
| **`/intelligence`** | `decision explain`, `recurring plan`, `meal plan` | AI-powered insights |
| **`/account`** | `privacy` (purge, retention), `undo`, `store-mode toggle` | Account management |
| **`/corrections`** | `list`, `create` | Correction event management |
| **`/sms`** | `webhook` | Twilio SMS webhook handler (Twilio-signed) |

### OpenAPI schema

The full OpenAPI 3.0 schema is auto-generated from route declarations:

```bash
python -c "from shopstack.api.v1.openapi import openapi_schema_json; print(openapi_schema_json())"
```

The schema is the **canonical API contract** between the backend and the mobile client. Contract tests in `tests/test_api_v1_openapi_schema.py` assert schema structure. TypeScript types in `shopstack-mobile/src/api/types.ts` are hand-mapped from the Python Pydantic schemas.

## shopstack-mobile (React Native / Expo)

`shopstack-mobile/` is a **React Native (Expo) app** that consumes the `/api/v1` REST API — giving ShopStack a native mobile interface alongside the FastAPI frontend shell. It is the **primary household-facing entry point**: used in kitchens and stores, offline-first, and designed around decisions (buy/skip/use-soon/compare) rather than data tables.

### Architecture

```
shopstack-mobile/
├── app/                          # expo-router file-based navigation
│   ├── _layout.tsx               # Root: persisted React Query + auth gate
│   ├── (auth)/                   # Login, Register
│   ├── (tabs)/                   # Home, Pantry, Shop, Cook, Trips, More
│   │   ├── index.tsx             # Decision-first dashboard
│   │   ├── inventory.tsx         # Pantry quick-add + staple chips
│   │   ├── shopping.tsx          # Active list + completion
│   │   ├── recipes.tsx           # Cook tonight + missing-to-list
│   │   ├── trips.tsx             # Trip signals + low/use-soon items
│   │   ├── more.tsx              # Settings + account
│   │   └── search.tsx            # Search page reached via floating action
│   ├── login.tsx                 # Token-aligned auth
│   └── register.tsx              # Token-aligned auth
└── src/
    ├── theme/tokens.ts           # Warm Pantry design tokens
    ├── components/               # Primitives + composites
    │   ├── primitives/
    │   └── composite/
    ├── hooks/                    # TanStack Query data layer
    ├── api/
    │   ├── types.ts              # TypeScript interfaces (70+ types)
    │   ├── client.ts             # HTTP client with Bearer token injection
    │   ├── auth.ts               # Device registration & auth
    │   └── *.ts                  # Endpoint modules
    └── storage/
        └── token.ts              # expo-secure-store wrapper
```

### Primary navigation (6 tabs)

| Tab | Purpose |
|-----|---------|
| Home | Decision banner: today's dominant action + 3 story tiles |
| Pantry | Quick-add, offline status, staple chips, pantry rows |
| Shop | Active shopping list, check-off, complete |
| Cook | Meal-plan / recipe cards; add missing ingredients to list |
| Trips | Trip recommendations, ranked low/use-soon items |
| More | Settings, account, privacy, traces |

### Key decisions

| Decision | Choice |
|---|---|
| Framework | Expo managed workflow (no bare RN needed for HTTP CRUD) |
| Nav | expo-router (file-based, deep links built-in) |
| Caching | TanStack React Query + secure offline persistence |
| Auth tokens | expo-secure-store (hardware-backed on iOS/Android) |
| Design system | Warm Pantry Intelligence: cream paper, olive, terracotta, amber; system fonts; light-first |
| Quick-add intelligence | `/api/v1/command/execute` when online, local fallback offline |
| Search | Floating action button across all tabs, not a top-level tab |

### Setup

```bash
cd shopstack-mobile
npm install
npm run typecheck     # Verify TypeScript before running
npx expo start        # Scan QR with Expo Go, or press 'w' for web
```

See `shopstack-mobile/README.md` for full details.

## Frontend Shell (FastAPI HTML UI)

`shopstack/ui/frontend_shell.py` renders a **standalone HTML/CSS frontend** served by FastAPI. It now shares the same Warm Pantry token system as `shopstack-mobile` (light-first with dark mode support, system fonts, olive/amber/terracotta palette) and provides:

- Full auth flow (login, register, device management)
- Dashboard view (today's snapshot)
- Inventory browser with add/consume actions
- Shopping list creation and management
- Global + inventory search
- Intelligence panels (recurring plan, meal plan, decision explain)
- Privacy controls (retention, purge, undo)
- Trace history viewer
- Store mode (check-off items while shopping)
- Mobile-responsive light-first theme with system fonts only

The frontend shell is loaded through FastAPI routes and communicates entirely through the `/api/v1/*` REST endpoints.

## Configuration

All settings are pydantic-settings with `SHOPSTACK_` env prefix:

Operational resource guards are documented in **[`Docs/RESOURCE_OPTIMIZATION_POLICY.md`](Docs/RESOURCE_OPTIMIZATION_POLICY.md)**.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHOPSTACK_DB_PATH` | `data/shopstack.db` | SQLite database file path |
| `SHOPSTACK_APP_PORT` | `7860` | FastAPI server port |
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

See **[`MODEL_CATALOG.md`](MODEL_CATALOG.md)** for the full living model catalog — including downloaded & tested models, parameter budget tracking, runtime backends (MLX, llama.cpp/GGUF, transformers), HF Pro and Modal Labs credit resources, and experiment logs.

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
