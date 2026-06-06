# ShopStack — Agent Workspace

## Repo
`/Users/pranay/Projects/shopstock`

## Ground Rules
- **Git read-only.** Never commit, push, reset, or checkout without explicit permission.
- **Extend existing routes.** No duplicate API routes or parallel systems.
- **Preserve docs.** Never delete documentation files without permission.
- **Test every mutation path.** All DB write operations must have corresponding tests.
- **Local-first always.** No cloud API dependencies for core functionality.
- **Bold, long-term, first-principles engineering** — governed by `motto_v2.md` as the active operating rules.

## Architecture
   
```
app.py (Gradio Blocks)
  → shopstack.ui (views, components/cards — HTML rendering)
  → ToolRegistry (11 tools, validates args, calls DB)
    → Database (SQLite, WAL mode, 10 tables)
  → ProviderRegistry (wired from config)
    → MockProviders (default, 11 interfaces)
    → LocalProvider (MLX + llama.cpp fallback, capability-optional)
  → settings (pydantic-settings, env overridable)
  → model_registry (16 candidates, not loaded by default)
  → Planners (engine → parser → prompt builder)
     ↓ calls ProviderRegistry.get_completion()
```

## Key Files

| File | Purpose |
|------|---------|
| `motto_v2.md` | **Active operating rules** — boldness, supersession, validation, documentation |
| `shopstack/config.py` | Central Settings with `SHOPSTACK_` env prefix |
| `shopstack/schemas/models.py` | All Pydantic domain models |
| `shopstack/persistence/database.py` | SQLite Database, CRUD, 18 seeded locations |
| `shopstack/providers/interfaces.py` | 11 abstract provider ABCs |
| `shopstack/providers/mock_providers.py` | Mock implementations for all providers |
| `shopstack/providers/local_provider.py` | Local provider (MLX + llama.cpp, capability-optional) |
| `shopstack/providers/registry.py` | Provider factory |
| `shopstack/tools/registry.py` | 11 tool implementations |
| `shopstack/traces/export.py` | Trace redaction, JSONL export |
| `shopstack/model_registry.py` | 16 candidate model entries |
| `shopstack/planner/prompts.py` | Prompt builder for LLM tool-calling |
| `shopstack/planner/parser.py` | Robust JSON + tool-call extraction for local model output |
| `shopstack/planner/engine.py` | PlannerEngine — orchestrates completion → parse → execute |
| `shopstack/ui/__init__.py` | UI package — re-exports views + components |
| `shopstack/ui/views.py` | Price memory, field notes view builders (dataclass returns) |
| `shopstack/ui/components/cards.py` | HTML rendering helpers (badge, card, decision card, metric) |
| `app.py` | Gradio Blocks UI entry point (872 lines, 10 tabs) |

### Package map

```
shopstack/
  __init__.py           (empty — namespace marker)
  config.py
  model_registry.py
  persistence/
    database.py         (SQLite, check_same_thread=False)
  planner/
    prompts.py          (system prompt builder for tool-calling)
    parser.py           (robust JSON + tool_call extraction)
    engine.py           (PlannerEngine — complete → parse → execute)
  providers/
    interfaces.py       (11 ABCs)
    mock_providers.py   (all mock)
    local_provider.py   (MLX + llama.cpp, capability-optional)
    registry.py
  schemas/
    models.py           (all Pydantic domain models)
  tools/
    registry.py         (11 tools)
  traces/
    export.py           (PII redaction, JSONL)
  market/               (market intelligence — Swiggy + future sources)
    __init__.py         (public API exports)
    schema.py           (NormalizedMarketRecord, MarketSnapshot)
    normalization.py    (size parser, unit prices, canonical mapping, combo detection)
    analytics.py        (snapshot analytics, cheapest option finder)
    basket.py           (basket builder, canonical matching from user input)
    metadata.py         (produce shelf-life, waste-risk, storage hints)
    sources/
      swiggy.py         (Swiggy loader, normalizer, snapshot loader)
  ui/                   (consolidated UI package)
    __init__.py         (re-exports views + components)
    views.py            (PriceMemoryView, FieldNotesView, build_price_memory_view, load_field_notes, save_field_notes)
    components/
      __init__.py       (re-exports cards)
      cards.py          (badge_html, card, empty_state, render_rows, render_decision_card, render_grouped_cards, render_metric)
    screens/            (screen builders for each tab)
      __init__.py       (re-exports all screen functions)
      dashboard.py      (today_dashboard with 6-value return)
      shopping.py       (shopping list create/view/complete + cards + mark purchased)
      market_lens.py    (barcode scan + buy/skip/save + barcode add)
      ask.py            (voice add commands + ask ShopStack)
      inventory.py      (add purchase, consume, batch ops, seed demo, use-soon)
      traces.py         (trace list, detail, export)
      model_stack.py    (model budget view, provider badge)
      other.py          (price memory, price intelligence, map, field notes, Swiggy market + basket estimator)
      portability.py    (JSON/CSV export/import)
      _utils.py         (workflow header, steps, shared UI helpers)
```

## Active Decisions

- Schemas in single file (models are interconnected, share enums).
- Mock providers for all capabilities — app runs fully without model deps.
- 18 seeded household locations (hierarchical: Home → Kitchen → Fridge → Fridge Door → ...).
- Database seeds locations on every init (safe via COUNT check).
- Trace redaction: phone numbers (10+ digits), emails, addresses, names in tool args.
- Total parameter limit across active models: ≤32B params (enforced in model_registry).
- No auto-purchase or payment scraping — design-level constraint.
- UI render logic consolidated in `shopstack.ui` package (not orphan modules).
- Dataclass return types for view functions (`PriceMemoryView`, `FieldNotesView`) — never raw tuples.
- HTML escaping with `html.escape()` for all user/data-derived content in UI output.
- Unit price normalization (kg/g/L/mL → per-base-unit) for price intelligence.
- Pre-launch: no backward-compat shims, no legacy IDs, canonical paths only.

## Engineering Operating Rules

The project follows `motto_v2.md` as its active engineering mandate. Key sections:

| Section | Principle |
|---------|-----------|
| 0 | Boldness — build the best app, not the safest small change |
| 0.1 | Missed-Anything Sweep — re-check everything before done |
| 0.2 | Confidence Honesty — explicit evidence for claims |
| 0.3 | Documentation Continuity — update durable docs in same pass |
| 6 | Pre-existing is not an excuse — fix known issues in blast radius |
| 7 | Supersession — use canonical paths, migrate to them |
| 10 | Pattern Search — systemic fixes, not one-off patches |
| 11 | Engineering Standards — first principles, root cause |
| 13 | Analysis Expectations — hidden coupling, architectural drift |
| 14 | Validation — tests, edge cases, failure scenarios |
| 18 | Communication — explicit what/why/risk before action |

## Development

```bash
uv pip install -e ".[dev]"
uv run python app.py        # Launch Gradio UI on :7860
uv run pytest tests/ -v     # Run all tests
uv run pytest benchmarks/ -v -m benchmark  # Run benchmarks
```

## Pre-commit

A hook at `.git/hooks/pre-commit` runs `tools/sync-readme-stats` which extracts live test/benchmark counts from `pytest -q` output and updates README.md. On every commit, README test counts stay current automatically.

## Test Inventory

| File | Tests | Scope |
|------|-------|-------|
| `tests/test_config.py` | 6 | Settings defaults, env overrides, aliases |
| `tests/test_database.py` | 32 | All 10 tables: CRUD, edge cases, seeds, deprecated wrappers |
| `tests/test_schemas.py` | 19 | Model validation, defaults, edge cases |
| `tests/test_tools.py` | 22 | All 11 tools, arg validation, list tools, prefix resolution |
| `tests/test_traces.py` | 12 | PII redaction, trace creation, JSONL export |
| `tests/test_provider_registry.py` | 2 | Mock fallback for custom backends, local backend fallback |
| `tests/test_model_registry.py` | 4 | Parameter limit enforcement, budget validation |
| `tests/test_ui_support.py` | 19 | PriceMemoryView, FieldNotesView, escaping, sort, unit price, list_to_table |
| `tests/test_views.py` | 47 | All view functions: dashboard, shopping, add (inc. neg validation), inventory, cards, consume (inc. prefix), use-soon, map, traces, field notes |
| `tests/test_app.py` | 5 | App smoke tests (build_app, imports, dashboard shape, tabs) |
| `tests/test_portability.py` | 18 | JSON + CSV export/import, dedup, validation, summary HTML |
| `tests/test_local_provider.py` | 10 | Local provider init, graceful fallback, capability checks |
| `tests/test_planner.py` | 26 | JSON extraction, tool-call parsing, inventory formatting, planner engine |
| `tests/test_market.py` | 52 | Swiggy loader, size parser, unit prices, canonical matching, analytics, basket, produce metadata |
| `tests/test_decisions.py` | 20 | Decision engine: BUY/SKIP/USE_SOON classification, market basket, Swiggy integration |
| `tests/test_cadence_waste.py` | 15 | Purchase cadence detection, waste patterns, Swiggy availability checks |
| `tests/test_safe_render.py` | 4 | Error boundary decorator: pass-through, catch, args, name preservation |
| `tests/test_runtime.py` | 5 | Runtime diagnostics: provider status, model info |
| `tests/test_swiggy_data_source.py` | 4 | Swiggy data source validation |
| `tests/test_voice_add.py` | 14 | Voice add commands, price intelligence |
| **Total** | **339** | (growing) |

## Next Work

- Live deployment test, load testing, performance benchmarking
- Seed demo data for walkthroughs
- CI pipeline (GitHub Actions + test suite)
- HF Inference API provider for fallback when local models aren't installed
- Modal provider for cloud GPU inference

## Addendum (2026-06-06) — Current Verified State

This file is a project guidance snapshot; current source of truth remains code/runtime/tests at the time of work.

- Primary app UI no longer exposes `Load Demo Data` on the Today tab; seed utilities remain developer/walkthrough tooling only.
- Header runtime badge is derived from provider runtime state instead of hardcoded `Mock`/version copy.
- Swiggy views, shopping-list enrichment, and Market Lens price cross-references now label Swiggy data as point-in-time and surface freshness.
- Verified counts: `uv run pytest tests/ -q` → 348 passed; `uv run pytest tests/ benchmarks/ -q` → 357 passed.
