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
  → settings (pydantic-settings, env overridable)
  → model_registry (16 candidates, not loaded by default)
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
| `shopstack/providers/registry.py` | Provider factory |
| `shopstack/tools/registry.py` | 11 tool implementations |
| `shopstack/traces/export.py` | Trace redaction, JSONL export |
| `shopstack/model_registry.py` | 16 candidate model entries |
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
  providers/
    interfaces.py       (11 ABCs)
    mock_providers.py   (all mock)
    registry.py
  schemas/
    models.py           (all Pydantic domain models)
  tools/
    registry.py         (11 tools)
  traces/
    export.py           (PII redaction, JSONL)
  ui/                   (consolidated UI package)
    __init__.py         (re-exports views + components)
    views.py            (PriceMemoryView, FieldNotesView, build_price_memory_view, load_field_notes, save_field_notes)
    components/
      __init__.py       (re-exports cards)
      cards.py          (badge_html, card, empty_state, render_rows, render_decision_card, render_grouped_cards, render_metric)
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
| `tests/test_database.py` | 27 | All 10 tables: CRUD, edge cases, seeds, deprecated wrappers |
| `tests/test_schemas.py` | 17 | Model validation, defaults, edge cases |
| `tests/test_tools.py` | 20 | All 11 tools, arg validation, list tools, prefix resolution |
| `tests/test_traces.py` | 10 | PII redaction, trace creation, JSONL export |
| `tests/test_provider_registry.py` | 1 | Mock fallback for custom backends |
| `tests/test_model_registry.py` | 1 | Parameter limit enforcement |
| `tests/test_ui_support.py` | 16 | PriceMemoryView, FieldNotesView, escaping, sort, unit price, list_to_table |
| `tests/test_views.py` | 31 | All view functions: dashboard, shopping, add (inc. neg validation), inventory, cards, consume (inc. prefix), use-soon, map, traces, field notes |
| `tests/test_app.py` | 4 | App smoke tests (build_app, imports, dashboard shape) |
| **Total** | **146** | (growing) |

## Next Work

- Real provider implementations (GGUF/llama.cpp wrappers, Whisper.cpp STT, etc.)
- Export/import inventory data
- Multi-user support
- Mobile-friendly UI refinements
- Time-series price trend visualization (foundations exist in price memory view)
- Barcode/QR scanning via Market Lens
