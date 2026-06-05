# ShopStack — Agent Workspace

## Repo
`/Users/pranay/Projects/shopstock`

## Ground Rules
- **Git read-only.** Never commit, push, reset, or checkout without explicit permission.
- **Extend existing routes.** No duplicate API routes or parallel systems.
- **Preserve docs.** Never delete documentation files without permission.
- **Test every mutation path.** All DB write operations must have corresponding tests.
- **Local-first always.** No cloud API dependencies for core functionality.

## Architecture

```
app.py (Gradio Blocks)
  → ToolRegistry (10 tools, validates args, calls DB)
    → Database (SQLite, WAL mode, 9 tables)
  → ProviderRegistry (wired from config)
    → MockProviders (default, 11 interfaces)
  → settings (pydantic-settings, env overridable)
  → model_registry (16 candidates, not loaded by default)
```

## Key Files

| File | Purpose |
|------|---------|
| `shopstack/config.py` | Central Settings with `SHOPSTACK_` env prefix |
| `shopstack/schemas/models.py` | All Pydantic domain models |
| `shopstack/persistence/database.py` | SQLite Database, CRUD, 18 seeded locations |
| `shopstack/providers/interfaces.py` | 11 abstract provider ABCs |
| `shopstack/providers/mock_providers.py` | Mock implementations for all providers |
| `shopstack/providers/registry.py` | Provider factory |
| `shopstack/tools/registry.py` | 10+ tool implementations |
| `shopstack/traces/export.py` | Trace redaction, JSONL export |
| `shopstack/model_registry.py` | 16 candidate model entries |
| `app.py` | Gradio Blocks UI entry point |

## Active Decisions

- Schemas in single file (models are interconnected, share enums).
- Mock providers for all capabilities — app runs fully without model deps.
- 18 seeded household locations (hierarchical: Home → Kitchen → Fridge → Fridge Door → ...).
- Database seeds locations on every init (safe via COUNT check).
- Trace redaction: phone numbers (10+ digits), emails, addresses, names in tool args.
- Total parameter limit across active models: ≤32B params (enforced in model_registry).
- No auto-purchase or payment scraping — design-level constraint.

## Development

```bash
pip install -e .
python app.py           # Launch Gradio UI on :7860
pytest tests/ -v        # Run all tests
pytest benchmarks/ -v -m benchmark  # Run benchmarks
```

## Next Work

- Real provider implementations (GGUF/llama.cpp wrappers, Whisper.cpp STT, etc.)
- Export/import inventory data
- Multi-user support
- Mobile-friendly UI refinements
- Time-series price trend visualization
- Barcode/QR scanning via Market Lens
