# ShopStack Hackathon Submission Smoke Plan

Date: 2026-06-12

This doc tracks the pre-submission checks for the Gradio + Hugging Face Small Hackathon trail.

## Objective
Ship a household-scoped, traceable, multi-surface app with clean submission evidence and explicit app-polish fixes.

## Mandatory Smoke Checklist (Do Before Submission)

- [ ] Start app
  - `uv run python app.py`
  - Confirm Gradio renders all tabs from the home screen
  - Confirm household switcher and active household are visible

- [ ] Verify Market Lens metadata signaling
  - Confirm image/audio mode appears in output
  - Confirm freshness warning is visible for Swiggy / market snapshots
  - Confirm warnings render safely when inputs are incomplete

- [ ] Dashboard integrity
  - Open Today dashboard
  - Confirm `DecisionSet`, use-soon panel, low-stock tiles, and weather block render
  - Confirm basket optimization panel appears when active list exists
  - Confirm missing/partial snapshots still show deterministic decision-only basket candidates

- [ ] Household scoping integrity
  - Seed two households with overlapping activity in a test scenario
  - Confirm `classify_all(..., user_id=...)` returns only the selected household
  - Confirm dashboard and list views do not bleed across households

- [ ] Planning and tool safety
  - Open Ask/Planner flow
  - Attempt an inventory mutation with planner writes disabled
  - Confirm write tools require explicit confirmation path

- [ ] Shopping list workflow
  - Create list from free text
  - Confirm classifications appear
  - Confirm share text area and copy + WhatsApp open action work (no placeholder/invalid URL)

- [ ] Reconciliation workflow
  - Mark partial purchases, skipped items, and substitutions
  - Confirm trace/log entries persist per household

- [ ] Trace + backup workflow
  - Create a trace in app UI
  - Export trace JSONL
  - Backup DB + import back into a fresh run

- [ ] Market Lens sanity
  - Verify Swiggy snapshot freshness and market hints render
  - Confirm compare suggestions are bounded to scoped inventory

## Priority Regression Commands

- `uv run pytest tests/test_decisions.py::TestDecisionClassification::test_classify_all_respects_user_id_scope`
- `uv run pytest tests/test_cadence_waste.py::TestPurchaseCadence::test_empty_returns_empty`
- `uv run pytest tests/test_dashboard_service.py::test_build_dashboard_state_counts_inventory`
- `uv run pytest tests/test_reconciliation_service.py::test_reconciliation_inventory_scopes_to_user_id`
- `uv run pytest tests/test_portability.py`
- `uv run pytest tests/test_basket_service.py`
- `uv run pytest tests/test_market_lens_service.py tests/test_views.py::TestTodayDashboard::test_empty_dashboard_shows_next_actions`

## Hackathon Scoring Alignment (Preliminary)

- ✅ Small-model fit: `SHOPSTACK` remains within existing model-budget contract
- ✅ Built on Gradio: existing Gradio app surface kept
- ✅ Local-first guardrails: write gating + household scoping fixes
- ✅ Submission polish: broken shopping-share link removed
- ✅ Documentation: explicit smoke checklist added in repo root

## Optional Bonus Quest Targets

- Off-grid / Local-first: avoid cloud-only dependency in critical paths
- Llama.cpp: route heavy inference through llama-compatible runtime where feasible
- Open trace: keep trace export path documented and working
- Field notes/blog: add a concise postmortem report for what improved this sprint

## Open Items Before Filing Submission

- Record final demo video + social post URL in this checklist
- Verify Space metadata and README align with active features
- Attach screenshot sequence for Today + Shopping + Reconcile flows
