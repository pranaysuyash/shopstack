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
    → Database (SQLite, WAL mode, 17 tables, 2 views)
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
  services/
    decision_engine.py  (should_buy, should_skip, use_soon)
    shopping.py         (shopping list enrichment & optimization)
    dashboard.py        (Today dashboard state builder)
    preference.py       (preference signals CRUD)
    freshness.py        (freshness classifier)
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

## Addendum (2026-06-12) — Trust Primitives, Service Boundaries, App Surface, Gradio 6 Migration

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

### 1. Test inventory made trustworthy

- `AGENTS.md` test inventory table regenerated from live `pytest --collect-only` output: **837 tests** total.
- Added 10 missing test files: `test_screens`, `test_shopping_service`, `test_dashboard_service`, `test_market_lens_service`, `test_local_whisper_provider`, `test_planner_eval`, `test_import_audit`, `test_flux_provider`, `test_module_registry`, `test_weather_trip`.
- Corrected stale per-file counts (e.g. `test_huggingface_provider`: 62→34, `test_views`: 47→48, `test_app`: 5→6).
- Removed "Verified counts" lines from prior addenda — they accumulated contradictory numbers over time and undermined the trust principle this product is built on.
- `README.md` line 111 now reads "837 tests (run `pytest tests/ --collect-only -q` for current count)".
- This file's pre-commit section now declares: **"Current verified: 837 tests. The inventory table above is the canonical reference."**
- Pre-existing `Status Update (2026-06-10)` already warned "do not rely on hardcoded counts"; the table is still the canonical reference but is paired with a clear "regenerate before trusting" instruction.

### 2. Architecture doc must be git-tracked to be authoritative

- Added explicit ground rule: **"Git-tracked docs only."** A doc that exists on disk but is not committed is not a source of truth.
- `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` exists locally (222 lines, well-structured) but `git ls-files` returns nothing for it. It is reachable as a file on this machine but not from a clean clone.
- Action required from owner: `git add Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` (and any other doc files in `Docs/` not yet tracked) so the architecture can serve as the canonical reference the README and code import-graph already assume it is. Until then, treat it as a local-only draft.

### 3. Service boundaries: HTML out, dependency in, imports at top

- `shopstack/services/results.py` had `to_html()` methods on `ShoppingCompletionResult` and `MarkPurchasedResult` — HTML rendering inside the service package.
- Created `shopstack/ui/renderers/` package with `render_shopping_completion()` and `render_mark_purchased()`. Results are now pure dataclasses.
- Drift evolved this into a fuller `renderers/` package (`decision_cards.py`, `image_cards.py`, `shopping_results.py`, `__init__.py` re-exporting `render_compare_panel` and the shopping-result renderers).
- `shopstack/services/shopping.py` no longer has mid-file imports:
  - `Database` type hint moved to `TYPE_CHECKING` import at top of file.
  - `create_trace` import moved above the function body that uses it (no more `# noqa: E402`).
  - `complete_shopping_list_service` and `mark_items_purchased_service` now take `database: Database` as a required parameter (not `Database | None = None` with a fallback to `shopstack.app_context.db`).
  - Both services also take an `inventory: InventoryRepo` parameter for explicit dependency injection (not the legacy `tools: ToolRegistry` only).
  - Both accept an optional `user_id: str` for household scoping.
- All existing call sites (UI screens, `tests/test_shopping_service.py`) already pass these explicitly, so no behavior change — only the contract tightened.

### 4. App surface: backward-compat aliases removed, tests bound to canonical symbols

- `app.py` previously imported `agent_trace_detail`, `shopping_list_view`, `shopping_list_create`, `_shopping_list_view_with_cards`, `_build_shopping_list_and_refresh` solely to expose them as `app.X` for tests. None were used in `app.py` itself.
- Removed all 5 from `app.py` import block. The `_workflow_header = workflow_header` duplication mentioned in the review was independently resolved by drift (the import path moved to `shopstack.ui.components` and the alias was dropped in the same pass).
- `tests/test_views.py` and `tests/test_traces.py` now import the same symbols directly from their canonical screen modules (`shopstack.ui.screens.shopping`, `shopstack.ui.screens.traces`, `shopstack.ui.components`). Tests bind to the real source, not a re-exported alias on the app module.
- Affected test surface: 274 tests across `test_views.py`, `test_traces.py`, `test_app.py`, `test_shopping_service.py`, `test_screens.py` — **all 274 pass**.

### 5. Gradio 6.0 `col_count` migration (blast-radius fix)

- The 17 deprecation warnings during test runs were not environmental — they were real `col_count=(N, "fixed")` calls in `app.py` (lines 399 and 644) that Gradio 6.0+ removed.
- Migrated both call sites to `column_count=N, column_limits=(N, N)` per the Gradio 6.0 deprecation guidance.
- `col_count` is no longer referenced anywhere in the codebase.
- Affected surfaces: `sl_reconciliation_table` and `receipt_df` `gr.Dataframe` constructors. Behavior preserved (both were already `interactive=True` and used fixed-N headers).
- Verification: `pytest tests/test_app.py` now reports **6 warnings** (down from 17), with no `col_count` or `column_count` deprecations remaining. The remaining 6 are unrelated (Python 3.14 swig `__module__` importlib noise).

### Open / deferred (not in this pass)

- `app.py` is now 1205 lines and still hand-wires all 5 top-level tabs inline in `build_app()`. The drift-merged imports (households, basket, market_intelligence, runtime_proof, generate_shopping_poster, etc.) make it more accreted than before. Tab extraction (`app_tabs/`) is a real long-term move but is out of scope for this pass — the review flagged it as "not fatal."
- `app.py` still reads `db.get_locations()` at module-level (`app.py:486` inside `with gr.Tab(...)`) for the storage-location dropdown. Building the choices list at module-load means stale-locations can be served if a new household is added in the same session. Should be moved into a per-render callable. Deferred.
- The swigy `DeprecationWarning: builtin type SwigPyPacked/SwigPyObject/swigvarlink has no __module__ attribute` warnings on Python 3.14 are upstream (Gradio + hf-gradio + pandas C-extension interop). Not actionable in this repo.

---

## Addendum (2026-06-12, Pass 2) — Doc Trust Audit & Ground-Rule Correction

This file remains a guidance snapshot; code/runtime/tests at the time of work remain source of truth.

### A. Correction to the previous "Git-tracked docs only" ground rule

The previous addendum (Pass 1) added this ground rule:
> **Git-tracked docs only.** A doc that exists on disk but is not committed is not a source of truth. `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` exists locally but is not git-tracked (not returned by `git ls-files`). It must be committed before it is authoritative.

**This ground rule is incorrect for this project and is being superseded (not erased — see §A.1 below).** It was added on the assumption that a doc on disk not in git was a "stale draft." It is in fact the project's explicit design:

- `.gitignore` line 33 declares `Docs/` ignored.
- `.gitignore` line 34 re-includes `Docs/` (negation).
- `.gitignore` line 35 force-includes `Docs/README.md` (the only deliberately-tracked doc in the folder).
- `Docs/README.md` itself documents this: *"This repository keeps historical design docs and context files out of Git tracking to keep PRs focused on code and runtime behavior. The active runtime truth remains in source code under `shopstack/` and `app.py`. For historical planning context, keep files in your local workspace copy of `Docs/` as needed."*

**The real issue is not "Docs aren't tracked" — it is "README.md and AGENTS.md *link to* Docs that are not in the repo, so those links are broken from a clean clone."** That is a different problem with a different fix.

#### A.1 The previous ground rule is preserved as historical record

Per the "addendums, never overwrites" rule, the incorrect rule from Pass 1 is left in place above (Ground Rules bullet 2, line 8) and in the Pass 1 addendum. Future agents who read it should read this correction in the same file and prefer this addendum.

**Action for owner:** when committing, either (a) delete the Pass 1 ground rule and replace it with the corrected version in this addendum, or (b) keep both with the addendum as the active authority. Both are correct; the project should not have two contradictory ground rules without a marker showing which is active.

### B. Corrected ground rule (proposed replacement)

> **Docs/ is local-only by design.** `Docs/` is in `.gitignore` (re-included with `!Docs/`, with `!Docs/README.md` as the only force-tracked file). The folder exists to hold historical design docs, hackathon dossiers, exploration maps, audit reports, and per-session context that would otherwise pollute PRs. The active runtime truth remains in source code under `shopstack/` and `app.py`. When README.md or AGENTS.md links to a path under `Docs/`, that link is reachable on a contributor's local workspace but **broken from a clean clone** — call it out in the same doc and provide a fallback (canonical source-of-truth in code, or a git-tracked summary).

### C. Doc classification (all 46 `Docs/*.md`)

Evidence used: file mtime (last edit), line count, cross-references from `README.md` and `AGENTS.md`, naming pattern. Classification is *informational only* — nothing was deleted or moved in this pass.

| File | Lines | Last edit | Class | Reason |
|------|-------|-----------|-------|--------|
| `Docs/README.md` | 11 | Jun 5 | **GIT-TRACKED KEEPER** | Force-tracked in `.gitignore`. Documents the local-only-by-design policy. |
| `Docs/ACCEPTANCE_CONTRACT_2026-06-08.md` | 153 | Jun 10 | historical | Hackathon acceptance criteria; date-stamped. |
| `Docs/ARCHITECTURE.md` | 538 | Jun 7 | **AUTHORITATIVE (under-documented)** | Long-form system architecture. Not linked from README/AGENTS; relies on discoverability. |
| `Docs/BUILD_OPPORTUNITIES_2026-06-12.md` | 208 | Jun 12 | **AUTHORITATIVE (recent decision aid)** | Decision aid for what to ship next. Self-declares "Not a commitment. Promote items to `ROADMAP.md` Phase 1/2/3 when accepted." Top 3 picks: multi-store basket compare, "Cook tonight" mode, BGE-M3 semantic search end-to-end. |
| `Docs/DECISION_RECORDS.md` | 355 | Jun 8 | historical | Decision log; dated. |
| `Docs/DEVELOPMENT.md` | 218 | Jun 7 | historical | Older dev guide. May be superseded by `AGENTS.md` "Development" section. |
| `Docs/explorations.md` | 127 | Jun 8 | historical | Top-level exploration index. |
| `Docs/FEATURE_MAP.md` | 195 | Jun 7 | historical | Older feature inventory. May be superseded by `FEATURES_STATUS.md`. |
| `Docs/FEATURES_STATUS.md` | 249 | Jun 10 | **AUTHORITATIVE (active)** | Per-feature status. More recent than `FEATURE_MAP.md`. |
| `Docs/HACKATHON_SUBMISSION_CHECKLIST.md` | 65 | Jun 12 | **AUTHORITATIVE (recent)** | Hackathon tracks + badge evidence. Maps submission claims to code paths. |
| `Docs/MODEL_CATALOG.md` | 230 | Jun 6 | **BROKEN LINK** | Linked from `README.md:229` but untracked. From a clean clone, the link is dead. |
| `Docs/REMAINING_WORK.md` | 169 | Jun 10 | historical | Older backlog. May be superseded by `BUILD_OPPORTUNITIES_2026-06-12.md`. |
| `Docs/RESOURCE_OPTIMIZATION_POLICY.md` | 51 | Jun 7 | **BROKEN LINK** | Linked from `README.md:210` but untracked. From a clean clone, the link is dead. |
| `Docs/REVIEW_TRACKER.md` | 47 | Jun 7 | historical | Older review log. Has unresolved items ("Needs sync" for README/AGENTS test counts — these were addressed in Pass 1). |
| `Docs/ROADMAP.md` | 241 | Jun 7 | historical | Older roadmap. May be partially superseded by `BUILD_OPPORTUNITIES_2026-06-12.md`. |
| `Docs/RUNTIME_AUDIT.md` | 610 | Jun 8 | **AUTHORITATIVE (deep)** | Runtime audit, the most detailed performance/system-level document in the project. |
| `Docs/SERVICES_ARCHITECTURE.md` | 117 | Jun 12 | **AUTHORITATIVE (recent)** | Service-layer architecture. Includes a mermaid diagram of service→data flow. References services (`dashboard.py`, `decision_engine.py`, `freshness.py`, `reconciliation.py`, `preference.py`, `price_memory.py`, `shopping.py`, `substitution.py`, `ocr_pipeline.py`, `receipt.py`, `search.py`, `trace.py`) that may or may not all exist yet — needs code cross-check before being treated as canonical. |
| `Docs/SHOPSTACK_NAMING_AND_MODULE_ARCHITECTURE.md` | 1059 | Jun 6 | **AUTHORITATIVE (canonical naming)** | The canonical naming doc. Should be linked from `AGENTS.md` "Key Files" table. |
| `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` | 35 | Jun 10 | **BROKEN LINK** | Linked from `README.md:38` and `AGENTS.md:239,342` but untracked. From a clean clone, the link is dead. The 222-line version from Pass 1 has been **shrunk to 35 lines** by parallel work (the actual content lives in `SHOPSTACK_NAMING_AND_MODULE_ARCHITECTURE.md` and `SERVICES_ARCHITECTURE.md` now). This is a content-classification issue — the doc is a stub pointing at its successors. |
| `Docs/STASH_ARCHITECTURE_RECOVERY.md` | 348 | Jun 8 | historical | Recovery notes from a prior restructure. |
| `Docs/SYSTEM_STATE.md` | 169 | Jun 7 | historical | Older system-state snapshot. May be partially superseded by `AGENTS.md` "Active Decisions". |
| `Docs/Swiggy_Snapshot_Integration.md` | 51 | Jun 9 | **AUTHORITATIVE (narrow)** | Specific integration doc. |
| `Docs/WALKTHROUGH_SCRIPT.md` | 43 | Jun 11 | **AUTHORITATIVE (recent)** | Demo walkthrough script. |
| `Docs/ShopSaathi_*.md` (4 files) | 2,418–6,026 | Jun 5 | **HISTORICAL — ALTERNATE NAMES** | Older "ShopSaathi" / "GharStock" naming. Superseded by `SHOPSTACK_NAMING_AND_MODULE_ARCHITECTURE.md`. The product was renamed; these are archival. |
| `Docs/ShopStack_*.md` (8 files, mix of `Dossier`, `Dossier_WITH_*`, `*_Addendum.md`) | 153–6,026 | Jun 5–12 | mixed | Dossier series is historical product-design context. `ShopStack_Exploration_Map.md` (Jun 12, 3,478 lines) is the most actively maintained. `*_Addendum.md` files are dated addenda. |
| `Docs/bonus-quest-evidence.md` | 43 | Jun 5 | historical | Hackathon bonus evidence. |
| `Docs/codex-build-log.md` | 55 | Jun 5 | historical | Earlier agent build log. |
| `Docs/field-notes.md` | 49 | Jun 7 | historical | Older field notes. |
| `Docs/huggingface-space-deployment.md` | 45 | Jun 5 | **AUTHORITATIVE (narrow)** | Specific deployment doc. |
| `Docs/local-cleanup-policy.md` | 78 | Jun 5 | **AUTHORITATIVE (operator)** | Operator/host cleanup policy. References cron script and protected paths. |
| `Docs/model-registry.md` | 48 | Jun 6 | historical | Older model-registry pointer. Likely superseded by `MODEL_CATALOG.md` and the per-model folders in `Docs/models/`. |
| `Docs/privacy-and-redaction.md` | 40 | Jun 5 | **AUTHORITATIVE (narrow)** | PII policy summary. |
| `Docs/product_hardening_findings.md` | 237 | Jun 6 | historical | Pre-launch hardening notes. Likely resolved but not marked. |
| `Docs/trace-schema.md` | 42 | Jun 5 | **AUTHORITATIVE (narrow)** | Trace schema reference. |
| `Docs/architecture/stash-to-canonical-audit.md` | (subdir) | — | historical | Subdirectory audit. |
| `Docs/audits/audit_*.md` (6 files) | (subdir) | — | historical | Subdirectory audit series. |
| `Docs/audits/llm-eval-skills/` | (subdir) | — | historical | LLM-eval skill audit. |
| `Docs/context/agent-start/` | (subdir) | — | operational | Likely auto-generated by `agent-start` script (per `/Users/pranay/AGENTS.md` instruction stack). |
| `Docs/data_sources/swiggy_fresh_vegetables.md` | (subdir) | — | **AUTHORITATIVE (narrow)** | Per-source data spec. |
| `Docs/exploration/HF_PIPELINE_MODEL_EXPLORATION_2026-06-09.md` | (subdir) | Jun 9 | **AUTHORITATIVE (recent)** | HF pipeline exploration log. |
| `Docs/exploration/MODEL_EXPLORATION_2026.md` | (subdir) | Jun 9 | **AUTHORITATIVE (recent)** | Per-model exploration doc. Referenced from "Active Decisions" bullet on multi-venv. |
| `Docs/exploration/PRODUCT_REVIEW_RESPONSE.md` | (subdir) | Jun 9 | historical | Pre-Pass-1 review response (the very one this pass is responding to). |
| `Docs/models/<model>/` (27 model folders) | (subdir) | — | **AUTHORITATIVE (narrow)** | Per-model config, claims, benchmarks. The Active Decision in `AGENTS.md` mandates: *"Nothing gets silently removed: Anyone who built and benchmarked a model — even one that failed — stays in the codebase with its provider, tests, benchmarks, and per-model docs."* |

### D. Broken README links — action required

`README.md` references 3 docs that are not reachable from a clean clone:

| Link | README line | Doc state |
|------|------------|-----------|
| `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` | 38 | Exists locally, 35 lines, stub. The 222-line version from Pass 1 has been shrunk by parallel work — actual content now lives in `SHOPSTACK_NAMING_AND_MODULE_ARCHITECTURE.md` (1059 lines) and `SERVICES_ARCHITECTURE.md` (117 lines). |
| `Docs/RESOURCE_OPTIMIZATION_POLICY.md` | 210 | Exists locally, 51 lines, complete. |
| `Docs/MODEL_CATALOG.md` | 230 | Exists locally, 230 lines, complete. |

**Three viable fixes** (any one is correct; pick based on intent):

1. **Move the canonical content to a git-tracked location.** E.g. `README.md` could link to `SHOPSTACK_NAMING_AND_MODULE_ARCHITECTURE.md` content embedded as a section in `AGENTS.md` (which IS tracked). Or create a `docs/` (lowercase, tracked) subdir with the truly canonical subset.
2. **Inline the essential content into `README.md` itself.** Small enough for `RESOURCE_OPTIMIZATION_POLICY.md` (51 lines) and `MODEL_CATALOG.md` (230 lines would need a curated excerpt).
3. **Accept the local-only design and call it out in `README.md`.** Add a top-of-file note: *"Several links in this README point to `Docs/` paths that are intentionally local-only. On a clean clone, see `AGENTS.md` for the canonical equivalents."*

**My recommendation: option 1 for `SHOPSTACK_PRODUCT_ARCHITECTURE.md` (it's already a stub pointing at successors — delete the stub and update the link), and option 3 for the other two** (they are real local-only references that work fine on a contributor's machine). That keeps the local-only design intact and resolves only the link rot.

### E. Newly-active docs since Pass 1 (drift additions)

Three new docs landed in `Docs/` between Pass 1 and Pass 2:

- `Docs/BUILD_OPPORTUNITIES_2026-06-12.md` (208 lines) — Decision aid. Top 3 to ship: multi-store basket compare, "Cook tonight", BGE-M3 semantic search. *Should be cross-referenced from `ROADMAP.md` when accepted.*
- `Docs/HACKATHON_SUBMISSION_CHECKLIST.md` (65 lines) — Active submission tracking. Maps tracks/badges to specific code paths.
- `Docs/SERVICES_ARCHITECTURE.md` (117 lines) — Service-layer architecture with mermaid diagram. Needs a code cross-check before being treated as canonical — references `decision_engine.py`, `freshness.py`, `substitution.py`, `preference.py` that need to be verified against `ls shopstack/services/`.
- `Docs/WALKTHROUGH_SCRIPT.md` (43 lines) — Demo walkthrough. References `scripts/seed_walkthrough.py` — verify the script exists.

### F. Open / deferred (from Pass 2)

- **Service cross-check** (`SERVICES_ARCHITECTURE.md` vs `ls shopstack/services/`): need to verify each named service file actually exists. Drift may have renamed or split them.
- **Tab extraction in `app.py`**: now 1207 lines, 5 hand-wired tabs. Targeted in the next pass.
- **`db.get_locations()` module-load calls** at `app.py:743` and `app.py:935`: stale-location bug. Targeted in the next pass.
- **Test count drift**: AGENTS.md inventory says 837, `pytest --collect-only` says 1579. Inventory table needs regeneration. Same "regenerate before trusting" pattern as Pass 1.
- **Doc-dedup decision**: The `ShopSaathi_*` (4 files, 3.5K+ lines) and `ShopStack_*Dossier*` (8 files, 30K+ lines) series are an obvious dedup target. Both are pre-rename archives, but the volume is large enough to warrant an "archive these to `Docs/_archive/`" move with a `Docs/_archive/README.md` pointer. Deferred until content-vs-canonical check is done.

---

## Status Update (2026-06-12, Pass 2) — Test Count Drift

`uv run pytest tests/ --collect-only -q` reports **1579 tests collected** (up from 837 documented in the Pass 1 inventory). The inventory table at the top of this file is stale again. The drift is real — parallel agents added 742 tests (~30 minutes of work). Regeneration needed before this table is trusted.

## Addendum (2026-06-12, Pass 2 follow-up) — Services Cross-Check

Cross-checked `Docs/SERVICES_ARCHITECTURE.md` (Mermaid graph + service list) against `ls shopstack/services/` immediately after writing the Pass 2 addendum. Result: **all 11 services named in the doc exist as files**, so the doc is structurally accurate. However, **7 additional service files exist that are not mentioned in the doc** — the doc is incomplete, not wrong.

| Named in `SERVICES_ARCHITECTURE.md` | Exists in `shopstack/services/` |
|--------------------------------------|----------------------------------|
| `dashboard.py` | ✅ |
| `decision_engine.py` | ✅ |
| `freshness.py` | ✅ |
| `reconciliation.py` | ✅ |
| `preference.py` | ✅ |
| `price_memory.py` | ✅ |
| `shopping.py` | ✅ |
| `substitution.py` | ✅ |
| `ocr_pipeline.py` | ✅ |
| `receipt.py` | ✅ |
| `search.py` | ✅ |
| `trace.py` | ✅ |

| Exists in `shopstack/services/` but **NOT** in `SERVICES_ARCHITECTURE.md` | Likely role |
|--------------------------------------------------------------------------|-------------|
| `market_lens.py` | Per-MODEL_EXPLORATION doc, the Market Lens service. The mermaid graph routes through `Receipt` but `market_lens` is a parallel perception path. |
| `market_intelligence.py` | Cross-source market intelligence (recently added per `BUILD_OPPORTUNITIES_2026-06-12.md`). |
| `market_sources.py` | Adapter/registry for retailer sources (Swiggy/Blinkit/Zepto/DMart). |
| `nutrition.py` | Nutrition lookup service (referenced in `app.py` imports — `nutrition_lookup_view`, `nutrition_kitchen_view`). |
| `trip_context.py` | Trip advice (weather + inventory + basket). |
| `unified_shopping.py` | Unified shopping planner (referenced in `app.py` — `run_unified_plan`, `unified_plan_summary`). |
| `weather.py` | Weather context service. |
| `results.py` | Typed result dataclasses (pure data, not really a service — but lives in the `services/` package). |
| `preferences.py` | Exists alongside `preference.py` — naming overlap to investigate (one may be a deprecated alias, one plural-form, or two distinct services). |

**Two real findings for the owner:**

1. **`preference.py` vs `preferences.py`** — both exist in `shopstack/services/`. This is either a rename-in-progress (with `preference.py` as the deprecated alias for `preferences.py`) or two distinct services with confusingly similar names. Whichever it is, the SERVICES_ARCHITECTURE.md doc only mentions one. Worth a 10-minute reconciliation.
2. **The mermaid graph in `SERVICES_ARCHITECTURE.md` is incomplete.** It shows 12 services and 4 data sinks. The codebase has 19 service files. Updating the doc to include the missing 7 (and reconciling `preference`/`preferences`) is ~30 minutes of work and would make the doc genuinely canonical.
