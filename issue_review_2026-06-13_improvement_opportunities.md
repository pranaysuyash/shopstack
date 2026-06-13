# ShopStack Improvement Opportunities

> Date: 2026-06-13  
> Scope: app-wide opportunities across product, UI, UX, infra, reliability, data, docs, and operating model.  
> Method: `motto_v3` pass over instruction stack, generated context, current code, recent worklogs, live app health, and test collection.  
> Evidence tiers: T1 = static inspection, T2 = targeted command/test, T4 = browser/runtime observation.

## Baseline Evidence

- T2: `/Users/pranay/Projects/agent-start --skip-index` regenerated `Docs/context/agent-start/*` and confirmed `motto_v3.md` is canonical.
- T2: `uv run pytest tests/ --collect-only -q` collected 2490 tests in 35.84s with 2 import warnings.
- T4: `curl http://127.0.0.1:7860/` returned 200.
- T4: Playwright browser visit to `http://127.0.0.1:7860/` stayed on Gradio `Loading...` and logged `SyntaxError: Unexpected token ';'`.
- T1: Current tree already has unrelated modified files: `scripts/demo_walkthrough.py`, `scripts/seed_walkthrough.py`, `shopstack/ui/screens/inventory.py`, `shopstack/ui/state/household.py`; final status also shows changes in `shopstack/ui/screens/consumption.py` and `shopstack/ui/screens/household_map.py`.

## P0 / P1: Must Fix First

1. **Browser hydration can fail while HTTP returns 200.** Evidence: Playwright saw only `Loading...`; console logged `SyntaxError: Unexpected token ';'`. Candidate seam: `app.py` registers `app.load(None, js=autocomplete_injector_js())` and `app.load(None, js=url_state_sync_js())`, while `shopstack/ui/components/js_helpers.py` says app-load JS should return a no-arg function expression but both helpers return bare `setTimeout(...)` statements. Fix path: wrap these helpers as `() => { ... }`, add a browser smoke test that asserts no console errors and that the Today tab text appears, then retest with Playwright.
2. **The test suite lacks browser-hydration proof.** Evidence: 2490 tests collect, but the live browser still fails to hydrate. Existing tests assert JS strings contain fragments, not that Gradio can evaluate them. Fix path: add a Playwright smoke in CI/dev tooling that opens the app, fails on console errors, waits for `main-content`, and captures a screenshot.
3. **Consumer UI still leaks engineering labels in action buttons and API descriptions.** Evidence: `Save Trace`, `Save Market Lens trace output`, `Save home scan trace output`, `canonical` table column, `Lot ID`, `Scene Type`, and `redacted JSONL` still appear across Market, Today, Pantry, and Memory seams. Some are hidden/internal, but several are visible. Fix path: create a UI-copy lint/check over visible `gr.*(label=...)`, `gr.Button(...)`, and table headers; keep API descriptions technical if needed, but hide them from consumer docs/routes unless developer mode.
4. **Household permissioning is still architectural debt.** Evidence: Phase 9 handoff calls out that "any code can read/write any household"; current app has household switch state, SMS registry, community opt-in, and trace/user_id work, but no real auth or permission boundary. Fix path: define a `HouseholdContext`/membership service, thread it through DB write paths, and test cross-household denial cases before adding network sync or family sharing.
5. **Silent exception swallowing hides product failures.** Evidence: many UI/service handlers catch broad `Exception` and return empty lists or terse HTML; examples include Today restock table returning `[]` on dashboard failure and Today intelligence returning raw unavailable text. Fix path: replace broad silent fallbacks with typed results, visible user-safe errors, trace/log entries, and operator diagnostics.
6. **No undo model for mutation-heavy home workflows.** Evidence: confirmations exist for several destructive actions now, but consumption, batch use, receipt import, restore, move, and reconciliation still do not share a common undo/reversal event model. Fix path: add immutable inventory event ledger semantics plus "recent changes" reversal where safe; expose "Undo last change" for use/move/add flows.
7. **PWA/custom shell remains fragile and needs live route smoke tests.** Evidence: prior handoff says Gradio 6 path interception made the custom shell unreachable at points, and the current project already had a PWA test lag around `/manifest.json` vs `/static/manifest.json`. Fix path: route-level smoke tests for `/manifest.json`, `/sw.js`, icons, service worker registration, and install metadata in the browser.
8. **Docs are useful but internally contradictory and drift-prone.** Evidence: `Docs/issue_review_2026-06-13.md` banner says all P0/P1/P2 are closed while the body still contains old open findings; `Docs/FEATURES_STATUS.md` is dated 2026-06-07 and has later correction sections. Fix path: add a canonical current-state index with statuses generated from code/tests where possible; archive superseded status tables.

## Product And Feature Opportunities

9. **First-run onboarding UI should gate empty app state.** Service exists, but the product should show a household setup path when onboarding is incomplete.
10. **Unify "Today intelligence", restock predictions, trip advisor, cook tonight, and Ask into one action queue.** Today risks becoming a stack of widgets instead of one household command center.
11. **Make "Cook tonight" actionable from every use-soon item.** Each use-first row should offer "Cook with this", "Add missing ingredients", and "Mark used after cooking".
12. **Add a real "I am at the store" mode.** Large touch targets, camera-first scan, list checklist, price compare, substitute, and receipt capture should live in one low-friction trip flow.
13. **Turn receipt scan into a complete after-shopping flow.** Scan receipt, match to list, confirm substitutions, update pantry, save price observations, and show "what changed".
14. **Add household member roles and attribution.** Track who added/used/moved items, allow child/guest modes, and separate "can view" from "can mutate".
15. **Federated community price sync.** The local community pool is a foundation; opt-in anonymized sync is the network-value layer.
16. **Trace-tuned parser loop.** Convert confirmed user actions and corrected parser previews into training/eval examples before trace TTL deletes useful data.
17. **Improve SMS/WhatsApp quick-add UX.** Surface inbox setup, phone registration, last message, dispatch status, and retry in the app instead of leaving it mostly service-backed.
18. **Voice memo UI.** Service exists; add a visible "hands busy" recording surface with session transcript, parsed commands, corrections, and undo.
19. **Barcode nutrition enrichment.** Wire barcode/product identity to nutrition facts and household dietary goals.
20. **Allergy and dietary guardrails.** Recipes, shopping suggestions, substitutions, and receipt imports should warn against household constraints.
21. **Waste prevention by package-size recommendation.** Use historical waste to recommend smaller/larger pack sizes at buy time.
22. **Budget mode.** Weekly/monthly budget, basket cost forecast, price-drop wait suggestions, and savings history.
23. **Pantry freshness confidence.** Show whether a quantity is scanned, manually entered, inferred, stale, or low-confidence.
24. **Storage-aware recommendations.** Buying advice should consider freezer/fridge/pantry capacity and suitable storage.
25. **Recurring household routines.** Milk every 3 days, vegetables twice weekly, medicine reminders, cleaning supplies cadence.
26. **Expiry label capture.** Camera OCR for expiry/manufacture dates with manual correction.
27. **Photo-based shelf diff.** Before/after shelf scans should identify changes, not just produce a one-off scan result.
28. **Smart shopping poster/share view.** Make the generated poster/checklist useful on phone screens, not only as an export artifact.
29. **Global search/command palette.** Search items, recipes, stores, actions, and activity records from one box.
30. **Saved filters and pinned views.** Families should pin "Fridge", "This week", "Kids snacks", "Medicine drawer", "Dinner under 30 min".
31. **Offline-first conflict resolution.** Local file sync and future federation need clear "both devices changed this list" handling.
32. **Import from common grocery exports.** Support retailer receipts, CSVs, and screenshots from Swiggy/Blinkit/Zepto/DMart.
33. **Better demo/walkthrough data management.** Seed realistic household stories with reset, not generic demo blobs.
34. **Launch/demo recording pack.** The walkthrough script should produce deterministic screenshots/video for submission and social.

## UI / UX Opportunities

35. **Fix app-load JS contract and add browser console tests.** This is the current blocker for live UI confidence.
36. **Replace raw "Loading..." failure with a branded recovery shell.** If Gradio hydration fails, show a useful fallback with refresh, diagnostics, and local log hint.
37. **Consumer-copy pass over all buttons/labels.** Replace "Trace", "canonical", "Lot ID", "Scene Type", "registry", and "JSONL" where visible.
38. **Make Today less explanatory.** Phrases like "Trip advisor call below" and "rolled up into one ranked list" explain implementation, not user value.
39. **Hide canonical columns.** Today restock rows should not expose a `canonical` column; use hidden state or map selected display names safely.
40. **Improve empty states to suggest next action.** "No data yet" should become "Add your first 5 pantry staples" or "Scan a receipt".
41. **Show last-updated timestamps.** Market data, weather, community medians, inventory scans, and Today intelligence need freshness markers.
42. **Use consistent section naming.** "Use Soon", "Use First", "Quick use", "Mark used", "Consume" should collapse into one consumer vocabulary.
43. **Add inline help/tooltips for advanced fields.** Lot IDs, batch syntax, scene type, backup restore, community opt-in, and SMS setup need compact help.
44. **Make slow operations visibly cancellable/retriable.** Scans, OCR, planner, poster generation, imports, and model calls need retry and timeout UX.
45. **Disable action buttons until prerequisites exist.** Confirm/skip/save buttons after scans should be disabled or explain why nothing can happen yet.
46. **Preview destructive changes before confirm.** Show exactly what will be moved, consumed, restored, or added.
47. **Add undo toast where reversal is safe.** Confirm dialogs prevent some accidents; undo handles "oops" after an intentional click.
48. **Improve mobile layout with real viewport QA.** Test 390px/430px mobile, 768px tablet, 1024px tablet landscape, and 1440px desktop.
49. **Add one-handed store mode.** Sticky bottom action bar, checklist progress, scan button, and large list rows.
50. **Strengthen accessibility beyond static checks.** Keyboard-only walkthrough, screen-reader smoke, aria-live assertions in browser, and focus return after dialogs.
51. **Make language switching comprehensive.** Header locale exists; audit all user-visible strings for translation coverage.
52. **Avoid emoji-only meaning.** Many buttons and headings use emoji; keep them decorative and ensure text conveys the action.
53. **Add visual status for runtime/mock/provider.** Consumer-friendly phrasing should tell whether AI/scan results are real model output, mock, cached, or unavailable.
54. **Show confidence/provenance on AI suggestions.** Why this suggestion, what data it used, and what it did not know.

## Architecture / Infra / Reliability Opportunities

55. **Add browser smoke tests to CI.** Backend import/tests are insufficient for a Gradio app with client JS hooks.
56. **Add JS syntax validation.** Run app-load/click JS snippets through `new Function` or Playwright before shipping.
57. **Make app route health reflect hydration.** Add a `/health/ui` or smoke script that fails if browser console errors appear.
58. **Canonicalize JS helpers.** `busy_js` returns a function expression; app-load helpers should follow the same contract or have a wrapper.
59. **Move remaining UI-local business parsing into services.** Screens still parse batch strings, receipts, and scan states in several places.
60. **Typed result objects for every mutation.** Replace ad-hoc HTML string returns with service results plus UI renderers.
61. **Centralize error rendering.** Many modules return raw `<div style='color:var(--red)'>`; use `form_error`, `toast`, and typed error cards consistently.
62. **Audit broad `except Exception`.** Each broad catch should either log, trace, re-raise as typed error, or have a documented user-safe fallback.
63. **Provider fallback observability.** Every model fallback should record requested backend, actual backend, reason, latency, and user-visible impact.
64. **Runtime diagnostics for non-developer users.** Not "Model Stack", but a trust panel: "Camera scan unavailable because OCR model not loaded."
65. **Performance baselines.** Add benchmark automation for app import, first render, dashboard state, scan pipeline, receipt OCR, and full suite wall time.
66. **Load testing.** Exercise Gradio queue, concurrent scans, concurrent household switches, large inventory, and long trace histories.
67. **Data retention controls.** Trace TTL, community pool retention, SMS registry, locale preferences, and backups need one privacy/settings surface.
68. **Backup UI should use encrypted service.** Plain JSON/CSV export exists; encrypted backup service should be the default consumer backup.
69. **Schema migration discipline.** As DB grows, add explicit migrations/versioning rather than opportunistic table creation.
70. **Cross-household scoping tests for every DB write.** AGENTS says every mutation path needs tests; extend this to household isolation and permission denial.
71. **Route/API discoverability hardening.** SMS webhook, locale save, PWA static routes, and Gradio APIs should have docs and smoke tests.
72. **CI should fail on stale generated context?** At minimum, document when `agent-start` must be regenerated and avoid checking in stale context silently.
73. **Docs source-of-truth check.** Add a script that flags docs claiming old test counts or closed items with open sections.
74. **Untracked/authoritative docs policy.** `Docs/SHOPSTACK_PRODUCT_ARCHITECTURE.md` is locally present but repo guidance says untracked docs are not authoritative; resolve tracking or downgrade references.
75. **Clean up stale screenshots/artifacts.** Several audit screenshots live in the repo root; move them to a tracked/ignored artifact location with an index.
76. **Dependency/runtime matrix.** Python 3.14 plus C-extension providers need a living compatibility matrix and import-audit expansion.
77. **Model download progress.** First model load should show progress, disk use, cancel, and fallback choice.
78. **Offline/network mode clarity.** Make Off the Grid vs cloud-enabled behavior explicit for every provider and feature.

## Data / Model / Intelligence Opportunities

79. **Real model dogfooding beyond mock mode.** Use local/Modal/OpenAI/HF providers in actual flows and record model-specific failures.
80. **Evaluation harness for Today intelligence.** Golden household scenarios should assert action ranking quality, not just renderer shape.
81. **Planner eval from real traces.** Build a labeled trace dataset for "what should the assistant have done?"
82. **Receipt OCR quality benchmarks.** Test receipts with Hindi/English, blur, skew, low light, and retailer layouts.
83. **Shelf scan benchmark set.** Store sample images and expected detected inventory deltas.
84. **Price normalization confidence.** Surface when unit-size parsing is estimated, missing, combo, or incomparable.
85. **Community median robustness.** Add k-anonymity thresholds, outlier handling, city/locality bucketing, and stale-observation decay.
86. **Nutrition data provenance.** Show source and confidence; avoid health claims beyond data support.
87. **Seasonality by region.** Seasonal produce and weather advice should be city/region-aware.
88. **Hinglish/regional language expansion.** Extend canonical aliases and UI strings beyond Hindi-first.
89. **Model routing policy UI.** Show and let user choose local/cloud/fallback policy at a high level.
90. **Model pipeline data third-layer docs.** For every model-backed feature, document model, pipeline, data, validation, fallback, observability, and recovery.

## Documentation / Product Ops Opportunities

91. **Create a canonical current-state dashboard doc.** One file generated/maintained from tests, module registry, docs index, and live smoke results.
92. **Turn this inventory into a roadmap with owners.** Each item needs status, evidence, acceptance criteria, and verification plan.
93. **Update older feature-status docs or archive them.** Avoid forcing future agents to reconcile multiple contradictory tables.
94. **Document user journeys, not only modules.** Home setup, cooking, shopping trip, put away groceries, recover mistake, backup/restore.
95. **Document operator workflows.** How to debug a failed scan, failed SMS webhook, provider fallback, or import error.
96. **Add release-readiness checklist.** Browser smoke, mobile smoke, PWA routes, privacy settings, backup restore, model fallback, docs current.
97. **Add visual regression artifacts.** Desktop and mobile screenshots for Today, Shopping, While Shopping, At Home, Memory.
98. **Use Linear for accepted follow-ups.** Repo guidance says Linear should track substantial findings when asked; inspect/update existing issues before creating new ones.

## Suggested Execution Order

1. Fix live browser hydration and add browser smoke test.
2. Run consumer-copy and jargon cleanup over visible UI.
3. Add mutation undo/event-ledger pattern for inventory/list/receipt actions.
4. Build household permissioning and cross-household denial tests.
5. Consolidate docs into a canonical current-state + roadmap artifact.
6. Deepen the product loop: first-run onboarding UI, store mode, receipt-to-put-away, and cook/use-first loops.
7. Add performance, model, OCR, and shelf-scan evaluation harnesses.

## Multi-Pass Notes

- Pass 1: Immediate correctness found the live hydration failure, stale/contradictory docs, and remaining visible technical terms.
- Pass 2: Architecture review found missing permissioning, missing undo/event ledger, broad exception fallbacks, and insufficient provider/runtime observability.
- Pass 3: Rule compliance review checked `motto_v3` evidence tiers and documented verified vs inferred claims here instead of presenting chat-only recommendations as complete.

## Artifact Note

An ignored draft copy also exists at `Docs/issue_review_2026-06-13_improvement_opportunities.md`. This root-level file is the git-visible canonical review artifact unless the repo's docs ignore policy is changed.
