# ShopStack — Agent Workspace

## Repo
`/Users/pranay/Projects/shopstack`

## Ground Rules
- **Git read-only.** Never commit, push, reset, or checkout without explicit permission.
- **Git-tracked docs only.** A doc that exists on disk but is not committed is not a source of truth. `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` exists locally but is not git-tracked (not returned by `git ls-files`). It must be committed before it is authoritative.
- **Extend existing routes.** No duplicate API routes or parallel systems.
- **Preserve docs.** Never delete documentation files without permission.
- **Test every mutation path.** All DB write operations must have corresponding tests.
- **Local-first always.** No cloud API dependencies for core functionality.
- **Bold, long-term, first-principles engineering** — governed by `motto_v2.md` as the active operating rules.

## Architecture
   
```
app.py (Gradio Blocks)
  → shopstack.ui (views, components/cards — HTML rendering)
  → ToolRegistry (12 tools, validates args, calls DB)
    → Database (SQLite, WAL mode, 10 tables, 2 views)
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
| `shopstack/tools/registry.py` | 12 tool implementations |
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
    registry.py         (12 tools)
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
- **Multi-venv fallback (adopted June 2026):** Models whose C-extension dependencies lack Python 3.14 wheels (PaddlePaddle max cp313, matcha-tts needs distutils) can run via a `.venv-py312` secondary environment using a subprocess gateway pattern. The primary 3.14 process spawns a subprocess for inference, communicating via JSON over stdin/stdout. Do not build speculatively — only implement when a provider integration depends on it. Documented in `Docs/exploration/MODEL_EXPLORATION_2026.md` section "Multi-Venv Architecture".
- **Nothing gets silently removed:** Anyone who built and benchmarked a model — even one that failed — stays in the codebase with its provider, tests, benchmarks, and per-model docs. Failed claims are reclassified from `pending` to `failed` with measured evidence and an exploration doc reference for future re-evaluation. The exploration map documents every model's status, blocker, and path forward. If a claim is superseded, it's benchmarked on what worked, documented on what didn't, and referenced in the exploration map for later.

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

> To verify the current test count, run `uv run pytest tests/ --collect-only -q`. 

## Test Inventory

| File | Tests | Scope |
|------|-------|-------|
| `tests/test_config.py` | 6 | Settings defaults, env overrides, aliases |
| `tests/test_database.py` | 32 | All 10 tables: CRUD, edge cases, seeds, deprecated wrappers |
| `tests/test_schemas.py` | 22 | Model validation, defaults, edge cases |
| `tests/test_tools.py` | 22 | All 11 tools, arg validation, list tools, prefix resolution |
| `tests/test_traces.py` | 12 | PII redaction, trace creation, JSONL export |
| `tests/test_provider_registry.py` | 2 | Mock fallback for custom backends, local backend fallback |
| `tests/test_model_registry.py` | 4 | Parameter limit enforcement, budget validation |
| `tests/test_ui_support.py` | 24 | PriceMemoryView, FieldNotesView, escaping, sort, unit price, list_to_table |
| `tests/test_views.py` | 48 | All view functions: dashboard, shopping, add (inc. neg validation), inventory, cards, consume (inc. prefix), use-soon, map, traces, field notes |
| `tests/test_app.py` | 6 | App smoke tests (build_app, imports, dashboard shape, tabs) |
| `tests/test_portability.py` | 18 | JSON + CSV export/import, dedup, validation, summary HTML |
| `tests/test_screens.py` | 113 | Screen builders: dashboard, shopping, market lens, ask, inventory, traces |
| `tests/test_shopping_service.py` | 50 | Service-layer: shopping completion, mark purchased, edge cases |
| `tests/test_dashboard_service.py` | 3 | Dashboard state assembly service |
| `tests/test_market_lens_service.py` | 4 | Market Lens analysis service |
| `tests/test_local_provider.py` | 37 | Local provider init, graceful fallback, capability checks |
| `tests/test_local_whisper_provider.py` | 9 | Local whisper provider init, mlx guard, deferred import |
| `tests/test_planner.py` | 33 | JSON extraction, tool-call parsing, inventory formatting, planner engine |
| `tests/test_planner_eval.py` | 4 | Planner tool-call validation, structure checks, name validation |
| `tests/test_market.py` | 55 | Swiggy loader, size parser, unit prices, canonical matching, analytics, basket, produce metadata |
| `tests/test_decisions.py` | 20 | Decision engine: BUY/SKIP/USE_SOON classification, market basket, Swiggy integration |
| `tests/test_cadence_waste.py` | 16 | Purchase cadence detection, waste patterns, Swiggy availability checks |
| `tests/test_safe_render.py` | 4 | Error boundary decorator: pass-through, catch, args, name preservation |
| `tests/test_runtime.py` | 5 | Runtime diagnostics: provider status, model info |
| `tests/test_swiggy_data_source.py` | 4 | Swiggy data source validation |
| `tests/test_voice_add.py` | 14 | Voice add commands, price intelligence |
| `tests/test_import_audit.py` | 19 | C-extension import audit during provider init |
| `tests/test_huggingface_provider.py` | 34 | HF provider: init, complete, plan, retry, registry, env key, structured chat routing |
| `tests/test_openai_provider.py` | 24 | OpenAI provider: init, complete, analyze_image, embed, env key, registry |
| `tests/test_whisper_provider.py` | 18 | Whisper API provider: init, transcribe, file-not-found, env key, registry |
| `tests/test_new_providers.py` | 59 | MiniCPM-V, MiniCPM5, Qwen3-TTS, NuExtract3, RMBG, Parakeet, SenseVoice, Qwen3-ASR |
| `tests/test_flux_provider.py` | 19 | Flux image generation provider |
| `tests/test_module_registry.py` | 16 | Module registry: registration, lookup, tab labels |
| `tests/test_weather_trip.py` | 21 | Weather and trip context services |
| `tests/test_adapter_blinkit.py` | 20 | Blinkit market source adapter: loader, normalization, freshness, adapter class |
| `tests/test_adapter_zepto.py` | 20 | Zepto market source adapter: loader, normalization, freshness, adapter class |
| `tests/test_adapter_dmart.py` | 20 | DMart market source adapter: loader, normalization, freshness, adapter class |
| **Total** | *(run pytest to count)* | (growing) |

## Next Work

- Live deployment test, load testing, performance benchmarking
- Seed demo data for walkthroughs
- CI pipeline (GitHub Actions + test suite)
- Modal provider for cloud GPU inference
- ~~Wire HF Inference API provider into planner routing (currently backend-selected only)~~ (done)
- ~~Add Blinkit, Zepto, DMart data source adapters~~ (done)
- ~~Create test_openai_provider.py and test_whisper_provider.py~~ (done)
- ~~Create per-model config.yaml + claims.yaml for all model registry entries~~ (done)

## Addendum (2026-06-06) — Current Verified State

This file is a project guidance snapshot; current source of truth remains code/runtime/tests at the time of work.

- Primary app UI no longer exposes `Load Demo Data` on the Today tab; seed utilities remain developer/walkthrough tooling only.
- Header runtime badge is derived from provider runtime state instead of hardcoded `Mock`/version copy.
- Swiggy views, shopping-list enrichment, and Market Lens price cross-references now label Swiggy data as point-in-time and surface freshness.

## Addendum (2026-06-06) — Service Boundary Extraction

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

- Added `shopstack/services/shopping.py` for shopping-list normalization, decision classification, and Swiggy enrichment.
- Added `shopstack/services/market_lens.py` for Market Lens barcode/object/OCR/STT analysis and Swiggy enrichment.
- Added `shopstack/services/dashboard.py` for Today dashboard state assembly.
- `shopstack/ui/screens/shopping.py`, `shopstack/ui/screens/market_lens.py`, and `shopstack/ui/screens/dashboard.py` now act more like Gradio adapters: parse/render/trace/wire, while product logic lives in services.

## Addendum (2026-06-06) — Product Naming & Module Architecture

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

- **ShopStack** is the full product/platform. **ShopStock** is the inventory module inside ShopStack.
- Module architecture introduced in `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md`:
  - ShopStock — inventory/pantry/fridge/expiry/use-soon
  - ShopBasket — shopping list / cart / market basket
  - ShopCompare — retailer price comparison
  - ShopLens — scanning (barcode, photo, receipt)
  - ShopMemory — price history, preferences, field notes
  - ShopAgent — reasoning across all modules
  - Sources — retailer datasets (Swiggy + future)
- The Python package remains `shopstack` (no import path changes needed).
- The product subtitle in `app.py` updated to "Your home's shopping intelligence & memory."
- `shopstack/config.py` app_name remains "ShopStack"; added `app_description` field.
- `README.md` reframed around shopping intelligence platform language.

## Addendum (2026-06-07) — Test Suite Stabilization

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

- Fixed `MockPlannerProvider.available = True` (explicit availability flag) and `PlannerEngine.process()` to handle list returns from `plan()` per the interface contract.
- Fixed indentation error in `shopstack/providers/registry.py` (`_try_real_provider` was syntactically broken).
- Fixed tests to explicitly set `planner_backend="mock"` to prevent OS env var overrides.
- Fixed `test_views.py`, `test_voice_add.py`, `test_planner.py` to work with mock planner availability.
- Resolved test suite timeout issue (full suite now runs in ~70s deterministically).

## Addendum (2026-06-07) — HuggingFace Inference API Provider

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

- Added `shopstack/providers/huggingface_provider.py` — HuggingFaceProvider implementing `complete()`, `plan()`, retry logic, `last_latency_ms`/`last_token_count` tracking, and healthcheck.
- Uses `huggingface_hub.InferenceClient` for serverless HF Inference API calls. Default model: `microsoft/Phi-3-mini-4k-instruct` (3.8B params).
- Added `hf_api_key` to `shopstack/config.py` (reads `SHOPSTACK_HF_API_KEY` env var, falls back to `HF_API_KEY`).
- Wired into `shopstack/providers/registry.py` — backend `"huggingface"` activates via `planner_backend=huggingface`. Falls back to mock gracefully when deps/token missing.
- 26 tests in `tests/test_huggingface_provider.py` covering init, complete, plan, retry, registry wiring, env var precedence, and latency tracking.

## Addendum (2026-06-09) — Python 3.14 + mlx segfault fix

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

**Root cause:** `LocalWhisperProvider._init_mlx()` called `import mlx_whisper` which triggers `mlx.core` C extension loading. On Python 3.14.5 (darwin), this segfaults when multiple AI modules (transformers, torch, etc.) are initialised concurrently during pytest collection. A C-level segfault cannot be caught by `try/except ImportError`.

**Fix** (`shopstack/providers/local_whisper_provider.py`):
- Use `importlib.util.find_spec("mlx_whisper")` instead of direct import to check package availability — `find_spec` scans the filesystem without loading C extensions
- Added `sys.modules` guard before `find_spec` to respect test mocking (`patch.dict("sys.modules", {"mlx_whisper": None})`)
- Defer the actual `import mlx_whisper` to `transcribe()` via lazy import (`self._mlx_module`), avoiding the crash entirely during init-time and test collection
- Initialize `self._mlx_module: Any = None` in `__init__()` for defensive coding

**CI compatibility note:**
- mlx 0.31.2 on Python 3.14.5 is the confirmed crash combination. If CI uses a different Python version or mlx release, the `find_spec` + lazy-import pattern remains the safe approach since it avoids C-extension loading during availability checks.
- Other packages imported via `find_spec` + deferred load pattern (safe for any C-extension-backed package that may crash on import): `mlx`, `mlx-lm`, `llama-cpp-python`, `faster-whisper`
- The pattern: `find_spec("package")` → set `_available = True` → defer `import package` to the method that actually uses it

## Addendum (2026-06-09) — C-Extension Import Audit, Planner Eval, Multi-Source Decisions, Doc Updates

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

- Added `tests/test_import_audit.py` (19 tests) — verifies no C-extensions are loaded during provider import time. Uses `importlib.util.find_spec` pattern to prevent segfaults from C-extension loading during test collection.
- Added `tests/test_planner_eval.py` (4 tests) — planner tool-call validation: structure checks, tool name validation against registry, edge cases (empty/None context), backend independence.
- Fixed ABC contract in `shopstack/providers/interfaces.py`: `plan()` signature from `dict[str, Any]` to `dict[str, Any] | str` to match all implementations.
- Added `embeddings_backend=bge_m3` and `tool_call_parser_backend=minicpm5` to `shopstack/config.py`.
- Added multi-source market data integration via `SourceRegistry` in `shopstack/decisions/rules.py` and `shopstack/services/dashboard.py`.
- Benchmark: `test_tesseract_hindi_devanagari_receipt` added — Tesseract+hin extracted **0/15 Devanagari terms** (16% word overlap from English only). Claim reclassified `pending → failed` with evidence.
- Evaluation: PaddleOCR-VL-1.5 (0.9B, Apache 2.0, 109 languages) — blocked on Python 3.14 (PaddlePaddle wheels max cp313). Documented in exploration doc with multi-venv architecture proposal.
- Multi-venv architecture documented as an Active Decision: `.venv-py312` secondary env via subprocess gateway pattern for Python-3.14-blocked C-extension models.
- Exploration doc updated: PaddleOCR status, Tesseract+hin 0/15 result, multi-venv architecture section, updated practical path forward.

## Status Update (2026-06-10) — Stale Test Count

Note: The test inventory table at the top of this file is inherently stale. Do not rely on hardcoded counts. Run `uv run pytest tests/ --collect-only -q` to get the actual current count.

## Addendum (2026-06-11) — Compact Tool Descriptions, OCR Pipeline, Engine Bug Fix

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

- **Compact tool descriptions** (`shopstack/tools/spec.py`, `shopstack/planner/prompts.py`, `shopstack/tools/registry.py`, `shopstack/planner/engine.py`, `shopstack/config.py`):
  - `ToolSpec.format_compact()` renders type-shorthand descriptions (e.g. `canonical_name: string, quantity: number?`).
  - `format_tool_descriptions(compact=True)` threaded through prompt builder → engine → planner prompt.
  - New setting `SHOPSTACK_PLANNER_COMPACT_TOOLS` / `planner_compact_tools` (default `False`).
  - Benchmarked at ~90% planner accuracy vs ~50% for verbose prose (Qwen3.5-4B-4bit, chat template, 512 tok).
- **Receipt OCR pipeline** (`shopstack/services/ocr_pipeline.py`):
  - `ReceiptOCRPipeline` with 3-stage fallback: GLM-OCR → preprocessing + retry → Tesseract.
  - OpenCV image preprocessing: grayscale, deskew, adaptive binarization, denoising.
  - Failure detection for GLM-OCR special-token output (`<|image|>`).
  - 22 unit tests in `tests/test_ocr_pipeline.py` covering all pipeline stages.
- **Engine bug fix** (`shopstack/planner/engine.py`):
  - `getattr(provider, "model_id", provider.name)` eagerly evaluated `provider.name` as getattr's default, crashing any provider without a `name` attribute. Changed to `getattr(provider, "model_id", None) or getattr(provider, "name", "unknown")`.
  - This was the root cause of the pre-existing `test_process_escapes_provider_response_text` failure.
