# ShopStack System State

**Generated:** 2026-06-15T16:07:11+00:00 · **Source:** `shopstack.tools.generate_state`

> This dashboard is **machine-generated** from the project. To refresh,
> run `python -m shopstack.tools.generate_state` (or let the CI hook do it).
> Hand-edits will be overwritten — add a `## Addendum` section if you need
> to record a long-term note.

## Headline Numbers

| Metric | Value | Method |
|--------|-------|--------|
| Tests | 4006 | `pytest-collect` |
| Test files | 208 | `walk` |
| Services | 77 | `walk` |
| Screens | 43 | `walk` |
| Tabs | 39 | `walk` |
| Providers | 24 | `walk` |
| WCAG 2.1 AA | 100 / 100 | breakdown: 13 pass / 0 warn / 0 fail |

## Open Issues (cross-referenced)

| Priority | Count |
|----------|-------|
| P0 | 0 |
| P1 | 0 |
| P2 | 0 |
| P3 | 0 |

_Counts are heuristics parsed from `Docs/REMAINING_WORK.md` and `Docs/issue_review_2026-06-13_improvement_opportunities.md`._

## Stale Docs (>30 days, top-level only)

_None._ All `Docs/*.md` files at the top level are fresh.

## Subsystem Inventory

### Services

- `shopstack/services/__init__.py`
- `shopstack/services/_utils.py`
- `shopstack/services/activity_log.py`
- `shopstack/services/analytics.py`
- `shopstack/services/backup.py`
- `shopstack/services/basket_compare.py`
- `shopstack/services/command_surface.py`
- `shopstack/services/community_federation.py`
- `shopstack/services/community_price_map.py`
- `shopstack/services/condition.py`
- `shopstack/services/cookbook.py`
- `shopstack/services/dashboard.py`
- `shopstack/services/data_retention.py`
- `shopstack/services/decision_engine.py`
- `shopstack/services/empty_states.py`
- `shopstack/services/expiry_parser.py`
- `shopstack/services/find.py`
- `shopstack/services/fine_tuned_parser.py`
- `shopstack/services/freshness.py`
- `shopstack/services/global_search.py`
- `shopstack/services/global_search_mount.py`
- `shopstack/services/health_mount.py`
- `shopstack/services/home_flow.py`
- `shopstack/services/i18n.py`
- `shopstack/services/intelligence_cards.py`
- `shopstack/services/market_intelligence.py`
- `shopstack/services/market_lens.py`
- `shopstack/services/market_sources.py`
- `shopstack/services/memory_facts.py`
- `shopstack/services/nutrition.py`
- `shopstack/services/nutrition_coach.py`
- `shopstack/services/ocr_pipeline.py`
- `shopstack/services/onboarding.py`
- `shopstack/services/per_member_activity.py`
- `shopstack/services/permissions.py`
- `shopstack/services/photo_search.py`
- `shopstack/services/preference.py`
- `shopstack/services/price_alerts.py`
- `shopstack/services/price_memory.py`
- `shopstack/services/privacy_mount.py`
- `shopstack/services/receipt.py`
- `shopstack/services/recipe_text_parser.py`
- `shopstack/services/recipes.py`
- `shopstack/services/reconciliation.py`
- `shopstack/services/restock_action.py`
- `shopstack/services/restock_card.py`
- `shopstack/services/results.py`
- `shopstack/services/search.py`
- `shopstack/services/seasonal.py`
- `shopstack/services/shared_list_sync.py`
- `shopstack/services/shelf_intelligence.py`
- `shopstack/services/shopping.py`
- `shopstack/services/shopping_substitutions.py`
- `shopstack/services/shortcuts.py`
- `shopstack/services/smart_planner.py`
- `shopstack/services/sms_intent_handlers.py`
- `shopstack/services/sms_quick_add.py`
- `shopstack/services/sms_webhook.py`
- `shopstack/services/sparkline.py`
- `shopstack/services/speech_intent.py`
- `shopstack/services/storage_suggest.py`
- `shopstack/services/substitution.py`
- `shopstack/services/timeline.py`
- `shopstack/services/today_intelligence.py`
- `shopstack/services/today_intelligence_golden.py`
- `shopstack/services/tooltips.py`
- `shopstack/services/trace.py`
- `shopstack/services/training_capture.py`
- `shopstack/services/trip_advisor.py`
- `shopstack/services/trip_context.py`
- `shopstack/services/undo_ledger.py`
- `shopstack/services/undo_mount.py`
- `shopstack/services/unified_shopping.py`
- `shopstack/services/voice_memo.py`
- `shopstack/services/walkthrough.py`
- `shopstack/services/waste_coach.py`
- `shopstack/services/weather.py`

### Screens

- `shopstack/ui/screens/__init__.py`
- `shopstack/ui/screens/_utils.py`
- `shopstack/ui/screens/activity_log.py`
- `shopstack/ui/screens/analytics.py`
- `shopstack/ui/screens/ask.py`
- `shopstack/ui/screens/basket.py`
- `shopstack/ui/screens/community.py`
- `shopstack/ui/screens/consumption.py`
- `shopstack/ui/screens/cookbook.py`
- `shopstack/ui/screens/dashboard.py`
- `shopstack/ui/screens/field_notes.py`
- `shopstack/ui/screens/find_trail.py`
- `shopstack/ui/screens/home_flow_render.py`
- `shopstack/ui/screens/household_map.py`
- `shopstack/ui/screens/households.py`
- `shopstack/ui/screens/intelligence.py`
- `shopstack/ui/screens/inventory.py`
- `shopstack/ui/screens/market_intelligence.py`
- `shopstack/ui/screens/market_lens.py`
- `shopstack/ui/screens/model_stack.py`
- `shopstack/ui/screens/nutrition.py`
- `shopstack/ui/screens/nutrition_coach.py`
- `shopstack/ui/screens/onboarding.py`
- `shopstack/ui/screens/other.py`
- `shopstack/ui/screens/parser_preview.py`
- `shopstack/ui/screens/per_member.py`
- `shopstack/ui/screens/photo_map.py`
- `shopstack/ui/screens/portability.py`
- `shopstack/ui/screens/price_compare.py`
- `shopstack/ui/screens/price_memory.py`
- `shopstack/ui/screens/receipt.py`
- `shopstack/ui/screens/recipe_text.py`
- `shopstack/ui/screens/repair_inbox.py`
- `shopstack/ui/screens/shelf_scan.py`
- `shopstack/ui/screens/shopping.py`
- `shopstack/ui/screens/smart_basket.py`
- `shopstack/ui/screens/store_mode.py`
- `shopstack/ui/screens/swiggy_market.py`
- `shopstack/ui/screens/timeline.py`
- `shopstack/ui/screens/today_intelligence.py`
- `shopstack/ui/screens/traces.py`
- `shopstack/ui/screens/trip_advisor.py`
- `shopstack/ui/screens/unified_shopping.py`

### Tabs

- `shopstack/ui/tabs/__init__.py`
- `shopstack/ui/tabs/analytics.py`
- `shopstack/ui/tabs/ask_panel.py`
- `shopstack/ui/tabs/basket.py`
- `shopstack/ui/tabs/basket_add_items.py`
- `shopstack/ui/tabs/basket_compare.py`
- `shopstack/ui/tabs/basket_plan.py`
- `shopstack/ui/tabs/basket_shopping_list.py`
- `shopstack/ui/tabs/command_surface.py`
- `shopstack/ui/tabs/community.py`
- `shopstack/ui/tabs/consumption.py`
- `shopstack/ui/tabs/context.py`
- `shopstack/ui/tabs/cookbook.py`
- `shopstack/ui/tabs/cookbook_filter.py`
- `shopstack/ui/tabs/find_trail.py`
- `shopstack/ui/tabs/market.py`
- `shopstack/ui/tabs/market_intel.py`
- `shopstack/ui/tabs/memory.py`
- `shopstack/ui/tabs/memory_activity.py`
- `shopstack/ui/tabs/memory_data.py`
- `shopstack/ui/tabs/memory_history.py`
- `shopstack/ui/tabs/memory_intelligence.py`
- `shopstack/ui/tabs/memory_notes.py`
- `shopstack/ui/tabs/memory_nutrition.py`
- `shopstack/ui/tabs/nutrition_coach.py`
- `shopstack/ui/tabs/onboarding.py`
- `shopstack/ui/tabs/parser.py`
- `shopstack/ui/tabs/photo_map.py`
- `shopstack/ui/tabs/recipe.py`
- `shopstack/ui/tabs/reconcile.py`
- `shopstack/ui/tabs/registry.py`
- `shopstack/ui/tabs/repair_inbox.py`
- `shopstack/ui/tabs/scanner.py`
- `shopstack/ui/tabs/smart_basket.py`
- `shopstack/ui/tabs/store_mode.py`
- `shopstack/ui/tabs/timeline.py`
- `shopstack/ui/tabs/today.py`
- `shopstack/ui/tabs/trip_advisor.py`
- `shopstack/ui/tabs/voice_memo.py`

### Providers

- `shopstack/providers/__init__.py`
- `shopstack/providers/ai_provider.py`
- `shopstack/providers/cosyvoice_provider.py`
- `shopstack/providers/embeddings_provider.py`
- `shopstack/providers/grounding_provider.py`
- `shopstack/providers/huggingface_provider.py`
- `shopstack/providers/image_gen_provider.py`
- `shopstack/providers/interfaces.py`
- `shopstack/providers/local_provider.py`
- `shopstack/providers/local_whisper_provider.py`
- `shopstack/providers/mock_providers.py`
- `shopstack/providers/modal_provider.py`
- `shopstack/providers/ocr_provider.py`
- `shopstack/providers/openai_provider.py`
- `shopstack/providers/planner_provider.py`
- `shopstack/providers/promptable_segmentation_provider.py`
- `shopstack/providers/registry.py`
- `shopstack/providers/runtime.py`
- `shopstack/providers/segmentation_provider.py`
- `shopstack/providers/stt_provider.py`
- `shopstack/providers/tesseract_provider.py`
- `shopstack/providers/tts_provider.py`
- `shopstack/providers/vision_provider.py`
- `shopstack/providers/whisper_provider.py`

## How To Refresh

```bash
# from project root
python -m shopstack.tools.generate_state
```

The generator also writes `Docs/STATE_DASHBOARD.json` (machine-readable)
so other tools (CI hooks, agent kickoff, the docs linter) can ingest
the same numbers without re-parsing the markdown.

## Why This Is Canonical

Hand-maintained state docs drift. The previous `Docs/SYSTEM_STATE.md` and
`Docs/FEATURES_STATUS.md` had been edited independently for months and
contradicted each other on basic numbers (test counts, statuses). This
generator re-derives everything from the actual project:

1. `pytest --collect-only -q` is the source for test count (with a
   directory-walk fallback when pytest is not available).
2. The WCAG score comes from `Docs/WCAG_AUDIT_2026-06-13.md`, which is
   itself regenerated by `shopstack.tools.audit_wcag` and pinned by the
   CI hook in `.github/workflows/wcag.yml`.
3. The open-issue counts parse the canonical backlog docs and tally
   priorities by a heuristic; for a stricter count, use the Linear board.
4. Doc-drift detection compares `mtime` to today, so any doc that hasn't
   been touched in 30 days shows up here.

If you find a discrepancy between this dashboard and reality, fix the code
(or the doc) and re-run the generator — that's the whole loop.


## Addendum (2026-06-15, fourth update) — tier-5 live deployment verification

The user confirmed the app is **live at
`https://huggingface.co/spaces/pranaysuyash/shopstack`**, with the
public URL `https://pranaysuyash-shopstack.hf.space`. Per
motto_v3 §0.5 evidence tier 5 (production-like / real-data
verification), the domain-layer work now includes actual HTTP calls
against the deployed app.

**New regression test file**: `tests/test_live_deployment.py`
(8 tests, all pass). The tests are **auto-skipped** if the live URL
is unreachable (network blocked, app down) so they don't fail
local CI runs.

Verified live endpoints:
- `GET /` — root page responds 200 within 10s
- `GET /config` — returns the full Gradio config (240+ events,
  all API names)
- `POST /gradio_api/queue/join` — handler invocation works
- `GET /gradio_api/queue/data` — SSE stream returns process_completed

**Live end-to-end handler chain** (called via Gradio API):
- `parser_preview` with `"doodh milk order"` — the deployed parser
  resolves the Hindi `doodh` alias to `milk` and classifies the
  intent as `general_query` with 40% confidence
- `parser_preview` with `""` — empty input doesn't crash; handler
  returns process_completed (graceful handling, no 500)
- 3 concurrent calls — at least 2/3 succeed (basic load-shedding
  check; HF Spaces has 1-worker queue by default)

**Live security regression** (prevents secret leak):
- `test_live_health_does_not_leak_secrets` — scans `/` and `/config`
  for distinctive secret patterns: `sk-[A-Za-z0-9]{20,}`,
  `skproj-[A-Za-z0-9]{20,}`, `hf_eeloOoBM` (the local HF token),
  `AKIA[A-Z0-9]{16}` (AWS), `ghp_[A-Za-z0-9]{20,}` (GitHub),
  `xox[ab]-[A-Za-z0-9-]{10,}` (Slack)
- False-positive-resistant: uses word boundaries so component
  names like `ask-input` don't match `sk-`

**Tier 5 evidence summary** (per motto_v3 §0.5):

| Evidence | Result | Tier |
|---|---|---|
| `import shopstack` works | PASS | Tier 1 |
| 172 domain tests | 172/172 pass | Tier 2 |
| 22 regression tests | 22/22 pass | Tier 2 |
| `import app` succeeds | PASS | Tier 4 |
| `app.build_app()` succeeds | PASS | Tier 4 |
| Live app boot (HTTP 200) | PASS | Tier 5 |
| Live app config endpoint | PASS | Tier 5 |
| Live `parser_preview` Hindi alias | PASS | Tier 5 |
| Live concurrent calls | PASS | Tier 5 |
| Live secret leak check | PASS | Tier 5 |
| **Total: 202 tests pass** | **0 fail** | Tier 1-5 |

**Important caveat**: the live tests use the public Gradio API and
do not require authentication. They test the handler chain, not
authenticated flows. The HF token from `.env` is for model downloads,
not for the public app, so it is correctly not in the test surface.

