# ShopStack Recovery and Semantic Salvage Plan

Status: inventory complete, recovery in progress, five controlled batches integrated

Date: 2026-08-26

This document is the recovery ledger for old stashes, the detached worktree,
and concurrent uncommitted work around the current ShopStack `main`. It is a
working control document, not evidence that any candidate has been accepted.

## 1. Recovery objective

Recover valuable behavior into the current canonical `main` without applying
an old snapshot wholesale, erasing concurrent work, or confusing historical
evidence with production source. Every accepted hunk must be understandable
in today's architecture, have a current owner path, and be validated at the
appropriate evidence tier.

The recovery unit is a semantic hunk or a tightly coupled file set, not a
stash. A stash is only provenance.

## 2. Non-negotiable invariants

1. Current `main` is preserved as the comparison baseline. No direct stash
   apply, checkout, reset, merge, stash deletion, branch deletion, worktree
   pruning, or force operation is allowed during inventory.
2. Current uncommitted files are concurrent work. They are not silently
   staged, rewritten, or mixed with recovered material.
3. Provenance is retained for every candidate: source ref, parent ref, path,
   hunk or symbol, reason for acceptance, tests run, and rejection or deferral
   reason when applicable.
4. Canonical routes and registries win. A recovered implementation must
   extend the current route, service, schema, tool registry, or test harness.
   Parallel replacements and compatibility shims require an explicit reason.
5. Secrets, `.env` content, generated screenshots, binary scratch artifacts,
   runtime databases, and copied provider credentials are never recovered as
   source. Data fixtures require provenance, privacy review, and a test use.
6. Domain and database changes require focused tests before they can be
   integrated. UI changes require contract tests and, where the claim is
   visual or interactive, runtime evidence rather than static inspection
   alone.
7. Test, browser, native/mobile, provider/API, and release evidence remain
   separate. A passing static test is not presented as end-to-end proof.
8. Each integration batch is independently revertible and leaves a clean
   evidence record before the next batch begins.

## 3. Current baseline and residual drift

| Item | Evidence |
| --- | --- |
| Repository | `/Users/pranay/Projects/shopstack` |
| Branch | `main` |
| Historical pushed baseline | `3319373dd14a8cfaa10335de85b7ee3e594f0c3c` |
| Current local main | `340de80` (`feat: restore recipe rich empty state`) |
| Baseline subject | `feat: deliver ShopStack mobile and platform tranche` |
| Upstream | `origin/main` |
| Remote alignment at inventory start | `HEAD` and `origin/main` matched at `3319373`; recovery commits are local and not pushed |
| Current local drift | `shopstack/eval/storage.py`, `shopstack/planner/engine.py`, `shopstack/providers/openai_provider.py`, `shopstack/ui/screens/model_stack.py`, new `shopstack/eval/agent/` package, new agent-evaluation screen and tests |
| Untracked runtime artifact | `:memory:.jsonl`, classified as generated trace output, not source |
| Last pushed full gate | Build, type/import, security, diff, normal hooks and push passed; full verifier still reported pre-existing lint and four known test issues, so release readiness was not green |

The residual evaluation tranche is not part of the historical stash set. It
must be reviewed as live concurrent work first and either left untouched,
explicitly integrated as its own batch, or superseded by a better canonical
implementation.

## 4. Source inventory

### 4.1 Stashes

All six stashes remain intact and were inspected without applying them.

| ID | Commit | Parent | Shape | Initial disposition |
| --- | --- | --- | --- | --- |
| `stash@{0}` | `a73a38896bf8f7c916b34b47ceeca11fe5b955b4` | `362f58ca6fa9ebb9f4be6bc190743771b6535381` | 17 files, 497 additions, 114 deletions | overlapping UI and data WIP; inspect symbols, reject generated images |
| `stash@{1}` | `ce694df2210c1316d8d9ca007751603d143cda49` | `362f58ca6fa9ebb9f4be6bc190743771b6535381` | 10 files, 377 additions, 78 deletions | narrowest repeated UI snapshot; mostly superseded by broader snapshots |
| `stash@{2}` | `1feea8ae9e0ee7d48983bdfc35bd2f123bc2a2ca` | `362f58ca6fa9ebb9f4be6bc190743771b6535381` | 10 files, 374 additions, 74 deletions | repeated UI snapshot plus one data line; compare to 0 and 1 |
| `stash@{3}` | `5ef2dfe387266a00462464a511e134e9cdffc3fc` | `362f58ca6fa9ebb9f4be6bc190743771b6535381` | 26 files, 894 additions, 149 deletions | broad home-flow, correction, memory and test WIP; high overlap |
| `stash@{4}` | `76d4ac8d4634dfaf7bd6f95708027ad7e654d8ea` | `362f58ca6fa9ebb9f4be6bc190743771b6535381` | 49 files, 1,427 additions, 352 deletions | broadest snapshot; primary historical candidate source, never bulk-applied |
| `stash@{5}` | `3a7bec77ac9e9a28283819daa6853d841e18be38` | `8073e3e4a85e5efb31dcb184a3ee077bec0a1e86` | 7 files, 127 additions, 108 deletions | separate older E2E and fixture WIP; inspect independently |

Stashes 0 through 4 share the same parent and repeat the same correction,
theme, permission, walkthrough, and unified-shopping paths. They are not five
independent feature sets. Stash 4 contains the widest set of additional
paths, but wider does not mean more correct.

### 4.2 Detached worktree

The worktree metadata reports:

```text
worktree /private/tmp/shopstack-stash
HEAD 3b3a2b0a1d41877483e9539224e6e9765d57d86b
detached
prunable: gitdir file points to a non-existent location
```

The directory is already absent. The commit tree is still inspectable, so the
metadata and commit are preserved. The commit is a June 8 WIP merge based on
`2fc697a` and `86fea99`, while current `main` has 806 tree paths and the old
tree has 134. The two trees differ at 786 paths. The old tree also contains an
`.env`, old doctrine and deployment files, legacy modules, and broad deletions
of current API, mobile, market, evaluation, and test surfaces.

Disposition: stale alternate snapshot, not an integration base. Only a named
symbol absent from current `main` may be mined from it after proving that it
is still architecturally relevant. `.env`, old doctrine copies, deleted
current surfaces, generated artifacts, and legacy compatibility code are
rejected by default. Do not prune the missing worktree metadata as part of
this recovery pass.

## 5. File-level recovery ledger

The table below is exhaustive for paths changed by the six stashes. Repeated
paths are listed once with all provenance refs. A `nitpick` disposition means
the actual diff still needs symbol-level comparison before any edit. It does
not mean that the entire file will be copied.

| Path | Source refs | Classification and next action |
| --- | --- | --- |
| `.tmp-workspace-click.png` | 4 | generated binary evidence; exclude unless a dated visual claim needs it |
| `Docs/REMAINING_WORK.md` | 3 | stale snapshot documentation; mine unresolved factual items only, reconcile with current docs |
| `Docs/SYSTEM_STATE.md` | 4 | state snapshot; do not restore wholesale, extract only current-verifiable facts |
| `app.py` | 4 | legacy launcher and shared-context changes; compare current entrypoint and routes, likely superseded |
| `data/fresh_mart.png` | 4 | captured binary input; privacy and provenance review required, exclude from source by default |
| `data/maa_laxmi.png` | 4 | captured binary input; privacy and provenance review required, exclude from source by default |
| `data/parser_training_real.jsonl` | 0, 2, 3, 4, 5 | fixture/training data; inspect records for privacy, duplication, schema and test usage before any retention |
| `data/sai_pharma.png` | 4 | captured binary input; privacy and provenance review required, exclude from source by default |
| `scripts/e2e_full_run.py` | 5 | tool candidate; compare against current verifier and canonical test commands, recover only missing useful checks |
| `shopstack-audit-2.png` | 4 | generated audit image; exclude from source, retain only as separately documented evidence if needed |
| `shopstack-audit-final.png` | 4 | generated audit image; exclude from source, retain only as separately documented evidence if needed |
| `shopstack-audit-updated.png` | 4 | generated audit image; exclude from source, retain only as separately documented evidence if needed |
| `shopstack-audit.png` | 4 | generated audit image; exclude from source, retain only as separately documented evidence if needed |
| `shopstack-first-principles-final.png` | 0, 1, 2, 3, 4 | repeated generated visual artifact; current blob is already unchanged across snapshots, no recovery |
| `shopstack-flow-audit.png` | 0, 1, 2, 3, 4 | repeated generated visual artifact; current blob is already unchanged across snapshots, no recovery |
| `shopstack-home-flow-final.png` | 0, 1, 2, 3, 4 | repeated generated visual artifact; current blob is already unchanged across snapshots, no recovery |
| `shopstack/app_context.py` | 4 | source candidate; deprecated runtime-label alias and warning need current import-graph and API review |
| `shopstack/config.py` | 4 | high-risk configuration candidate; `load_dotenv()` behavior needs security and precedence review, never recover credentials |
| `shopstack/domain/inventory_alerts.py` | 4 | narrow domain candidate; expiry-today semantics are plausible, recover only with focused boundary tests |
| `shopstack/domain/unit_price.py` | 4 | narrow parser candidate; decimal size-class support is plausible, recover only with locale and unit tests |
| `shopstack/persistence/database.py` | 0, 3, 4 | high-risk data-layer overlap; compare trace scoping and correction-row mapping to current schema, test every changed path |
| `shopstack/schemas/models.py` | 3, 4 | schema candidate; correction fields may be required, reconcile with current DB and API contracts before acceptance |
| `shopstack/services/empty_states.py` | 0, 4, 5 | service candidate with repeated additions; consolidate presets against current canonical i18n and call sites |
| `shopstack/services/i18n.py` | 0, 4 | translation candidate; recover only keys used by accepted canonical empty states |
| `shopstack/services/permissions.py` | 0, 1, 2, 3 | repeated presentation change; inspect role-badge semantics and security wording, do not apply four copies |
| `shopstack/services/walkthrough.py` | 0, 1, 2, 3 | repeated walkthrough change; compare state transitions and test discoverability before salvage |
| `shopstack/ui/components/cards.py` | 0, 1, 2, 3 | repeated card markup change; inspect escaping, accessibility and decision semantics, likely hunk-level salvage |
| `shopstack/ui/header.py` | 3, 4 | header wiring candidate; verify canonical script ownership and route mounting before acceptance |
| `shopstack/ui/renderers/decision_cards.py` | 4 | renderer candidate; freshness stamp needs source timestamp contract and visual/runtime evidence |
| `shopstack/ui/screens/corrections.py` | 0, 1, 2, 3, 4 | repeated large correction workflow; likely valuable but must reconcile current persistence, confirmation, escaping and event wiring |
| `shopstack/ui/screens/dashboard.py` | 3, 4 | dashboard behavior candidate; conditional trip section needs current home-flow contract and runtime test |
| `shopstack/ui/screens/shopping.py` | 0, 4 | screen candidate; inspect share rendering and cache invalidation against current shopping flow |
| `shopstack/ui/screens/unified_shopping.py` | 0, 1, 2, 3 | repeated style/content change; compare current decision language and preserve only canonical semantics |
| `shopstack/ui/tabs/basket_add_items.py` | 4, 5 | tab candidate; compare basket write path and confirmation behavior, test mutation path |
| `shopstack/ui/tabs/basket_shopping_list.py` | 4 | tab candidate; compare current basket route and empty states, recover only if still canonical |
| `shopstack/ui/tabs/context.py` | 3, 4 | shared context candidate; inspect state ownership and avoid duplicate detection paths |
| `shopstack/ui/tabs/memory.py` | 3, 4 | memory navigation candidate; compare current sub-tab registration and canonical data sources |
| `shopstack/ui/tabs/memory_data.py` | 3, 4 | memory data wiring candidate; preserve canonical memory facts and test refresh behavior |
| `shopstack/ui/tabs/recipe.py` | 4 | empty-state candidate; reconcile with current service and i18n contracts |
| `shopstack/ui/tabs/today.py` | 3, 4 | home-flow candidate; inspect visual merge and interaction reachability, require runtime proof for user-facing claims |
| `shopstack/ui/theme.py` | 0, 1, 2, 3 | large repeated CSS rewrite; no bulk recovery, extract individual accessible or canonical token fixes and run browser checks |
| `tests/conftest.py` | 4 | test infrastructure candidate; compare fixtures and isolation guarantees before acceptance |
| `tests/domain/test_inventory_alerts.py` | 4 | focused test candidate; likely paired with expiry semantics, run after source comparison |
| `tests/domain/test_unit_price.py` | 4 | focused test candidate; likely paired with parser semantics, run after source comparison |
| `tests/test_app.py` | 3, 4 | contract-test candidate; reconcile expected section count with current home-flow state |
| `tests/test_app_composition.py` | 0, 3, 4 | repeated composition tests; retain only assertions that match current canonical entrypoint |
| `tests/test_browser_hydration.py` | 4 | browser/runtime candidate; inspect fixture identity and run in isolated server if retained |
| `tests/test_build_app_smoke.py` | 0, 3, 4 | repeated smoke-test edits; consolidate against current build contract and avoid stale line-count assertions |
| `tests/test_cadence_waste.py` | 3, 4 | domain test candidate; compare changed expected behavior to current service semantics |
| `tests/test_decisions.py` | 3, 4 | decision test candidate; preserve only changed business rules verified from current implementation |
| `tests/test_e2e_reconciliation.py` | 5 | E2E candidate; inspect whether it tests current API and persistence route, run only after fixture isolation |
| `tests/test_env_and_handoff_lock.py` | 4 | security/config test candidate; do not adopt assertions that require secrets or import-time credential loading without doctrine review |
| `tests/test_household_wiring.py` | 1 | wiring test candidate; compare current household route and avoid stale line-budget expectations |
| `tests/test_pass_14_16_venv_smoke.py` | 5 | environment smoke candidate; compare current supported runtimes and optional dependency policy |
| `tests/test_recent_corrections.py` | 3, 4 | correction UI test candidate; likely useful, but reconcile markup and row-count contracts |
| `tests/test_regression_e2e_harness.py` | 0 | harness candidate; inspect artifact assumptions and current release gate ownership |
| `tests/test_regression_guards.py` | 4 | broad regression candidate; mine focused guards, reject stale path or line-count assertions |
| `tests/test_repo_truth.py` | 5 | repository truth candidate; compare current generated context and avoid historical assertions |
| `tests/test_test_count_audit.py` | 4 | audit candidate; inspect whether tolerance masks drift, prefer exact collection or manifest evidence |
| `tests/test_views.py` | 3, 4 | view contract candidate; reconcile dashboard cardinality and current fixture state |
| `tests/test_whoami_mount.py` | 4 | HTTP route candidate; verify current mount and best-effort semantics with isolated TestClient |

### 5.1 Repeated snapshot conclusion

The repeated files in stashes 0 through 3 are one historical change stream:

- `corrections.py` adds the largest behavioral surface and is the first UI
  area worth symbol-level review.
- `theme.py` is a large visual rewrite and must be decomposed into tokens,
  accessibility rules, and component selectors before any salvage.
- `permissions.py`, `walkthrough.py`, `cards.py`, `unified_shopping.py`,
  and the repeated smoke tests contain overlapping refinements, not separate
  implementations.
- `database.py`, `models.py`, `memory_data.py`, and the correction tests form
  a data-to-UI coupling cluster. They must be reviewed together, not file by
  file in isolation, while provenance remains file-specific.

### 5.2 Completed file-level dispositions

The following is the completed disposition for every unique path changed by
the six stashes. Paths are grouped only where the decision is identical; no
group implies that a whole stash or directory was applied.

| Decision | Paths and concrete finding |
| --- | --- |
| `ACCEPT-HUNK` / `ADAPT-HUNK` | `shopstack/domain/unit_price.py`, `tests/domain/test_unit_price.py`: decimal quantities such as `1.5 medium` and `1,5 large` filled a current parser gap; integrated as `abbb23b`. `shopstack/services/empty_states.py`, `shopstack/services/i18n.py`, `tests/test_empty_state_coverage.py`, `tests/test_regression_guards.py`: current `recipe.py` already called `render("recipe.no_input")`, but the registry and English/Hindi keys were absent; adapted and integrated as `340de80`. |
| `TEST-ONLY` | `tests/test_repo_truth.py`: added the existing `correction_events` table to repository truth assertions; integrated as `3a1e2ec`. `tests/test_recent_corrections.py`: narrowed row counting to the exact row class so nested action classes do not inflate the count; integrated as `b00681e`. `tests/test_browser_hydration.py`: modernized the recovered palette flow to the current route and isolated browser timing contract; integrated with the route hardening as `c8b2d50`. |
| `AUDIT-DERIVED` | `shopstack/api/v1/mount.py`, `shopstack/api/v1/routers/search.py`, `tests/test_api_v1_legacy_aliases.py`: not copied from a stash. The audit found that Starlette route cloning stripped FastAPI dependency and response metadata, and the browser palette called a protected search alias without auth. The APIRoute-safe clone and explicit local legacy adapter preserve the canonical v1 route while keeping protected routes protected; integrated as `c8b2d50`. |
| `DEFER` | `shopstack/domain/inventory_alerts.py`, `tests/domain/test_inventory_alerts.py`: the stash changes day zero from `EXPIRED` to `EXPIRING_SOON` with critical severity and “expires today.” Current `check_expiry()` has no production callers, and active expiry policies are elsewhere. This is a product-contract decision, not a safe parser correction; no code was integrated. |
| `DOC-MINE` | `Docs/REMAINING_WORK.md`, `Docs/SYSTEM_STATE.md`: historical and generated snapshots with stale test counts, deployment claims, and legacy paths. No source was restored. Their still-current factual leads were compared against code and the present ledger; the ignored local docs remain outside the recovery commits. |
| `REJECT: generated or sensitive artifact` | `.tmp-workspace-click.png`; `data/fresh_mart.png`; `data/maa_laxmi.png`; `data/sai_pharma.png`; `shopstack-audit-2.png`; `shopstack-audit-final.png`; `shopstack-audit-updated.png`; `shopstack-audit.png`; `shopstack-first-principles-final.png`; `shopstack-flow-audit.png`; `shopstack-home-flow-final.png`. These are binary evidence or captured inputs, not source. `data/parser_training_real.jsonl` was also rejected: all inspected rows duplicate existing data and have no justified current test contract. |
| `REJECT: stale or harmful source snapshot` | `app.py`: old monolithic composition conflicts with canonical `shopstack/app_builder.py`. `shopstack/app_context.py`: removes request-scoped household context and replaces the canonical runtime path with a deprecated alias. `shopstack/config.py`: import-time `load_dotenv()` exposes unprefixed credentials through process-wide `os.environ` and also removes current Modal settings. `shopstack/persistence/database.py`: removes connection tracking, safe cleanup, nutrition migration, and current schema behavior. `shopstack/schemas/models.py`: removes nutrition and `ShoppingListItem.item_id` compatibility while weakening current schema comments. `shopstack/ui/screens/corrections.py`: old snapshot removes current escaping, inline action wiring, and persistence behavior. `shopstack/ui/screens/dashboard.py`, `shopstack/ui/screens/shopping.py`, `shopstack/ui/tabs/today.py`, and `shopstack/ui/theme.py`: each removes newer canonical behavior or accessibility safeguards. `shopstack/ui/header.py`: moves a lazy import to module scope and risks the existing import cycle. |
| `REDUNDANT` or `SUPERSEDED` | `shopstack/services/permissions.py`, `shopstack/services/walkthrough.py`, `shopstack/ui/components/cards.py`, `shopstack/ui/renderers/decision_cards.py`, `shopstack/ui/tabs/basket_add_items.py`, `shopstack/ui/tabs/basket_shopping_list.py`, `shopstack/ui/tabs/context.py`, `shopstack/ui/tabs/memory.py`, `shopstack/ui/tabs/memory_data.py`, `shopstack/ui/tabs/recipe.py`, `tests/test_build_app_smoke.py`, `tests/test_cadence_waste.py`, `tests/test_decisions.py`, `tests/test_household_wiring.py`, `tests/test_views.py`: current main already contains the behavior or a newer canonical form. The recipe source call site is already canonical; only its missing service contract was recovered. |
| `REJECT: weakens test safety or evidence` | `tests/conftest.py`: stash removes connection cleanup, request-context reset, undo-ledger reset, standalone-test isolation, and post-test community-file cleanup; current main is safer. `tests/test_app.py`, `tests/test_app_composition.py`: stash accepts stale section counts and old `app.py` composition. `tests/test_e2e_reconciliation.py`: old household and route assumptions. `tests/test_env_and_handoff_lock.py`: requires process-wide `HF_TOKEN` loading from `.env`, which conflicts with secret-safe configuration. `tests/test_pass_14_16_venv_smoke.py`: removes subprocess isolation, temporary DB, and environment pinning. `tests/test_regression_e2e_harness.py`: permits failed image uploads and would mask a broken flow. `tests/test_test_count_audit.py`: raises drift tolerance from 10 percent to 25 percent, weakening the audit after improving the counter. `tests/test_whoami_mount.py`: targets the deleted `shopstack.services.whoami_mount` instead of canonical `shopstack.api.v1.routers.meta`. |

### 5.3 Detached worktree file-level conclusion

The detached commit `3b3a2b0a1d41877483e9539224e6e9765d57d86b` has 134 paths
against 808 in current local main. The trees share 126 paths, have 8 old-only
paths, and 682 current-only paths. The old-only set is:

```text
.env
AGENTS.md
motto_v2.md
shopstack/_legacy_decisions.py
shopstack/data_sources/__init__.py
shopstack/data_sources/swiggy.py
tests/test_safe_render.py
tests/test_swiggy_data_source.py
```

The old-only source modules are deleted or superseded by the current API,
domain, and market-source paths. The two old tests target those deleted paths.
The policy files are not current canonical instruction sources, and `.env` is
never recovered. No detached-worktree file is currently a recovery candidate.
The prunable metadata remains untouched so this audit does not destroy
historical provenance.

## 6. Concurrent evaluation tranche ledger

The following files arrived after the pushed baseline and are currently dirty:

| Path set | Initial assessment |
| --- | --- |
| `shopstack/eval/storage.py`, `shopstack/planner/engine.py` | trace ID and generation metadata plumbing; plausible observability improvement, but requires API compatibility and recorder tests |
| `shopstack/providers/openai_provider.py` | provider generation/reasoning forwarding; provider/API boundary, requires mocked request-shape tests and no secret output |
| `shopstack/eval/agent/*.py`, `shopstack/eval/agent/*.json`, `tests/eval/agent/test_agent_eval.py` | substantial new scenario-evaluation package; inspect schema, canonical ToolSpec parity, isolated DB, deterministic scoring, cost/latency policy and test coverage before integration |
| `shopstack/ui/screens/agent_eval.py`, `shopstack/ui/screens/model_stack.py` | read-only UI wiring; verify import safety, empty state, escaping and no run-on-render side effects |
| `:memory:.jsonl` | generated trace output from an in-memory recorder; exclude from source and do not stage |

This tranche is not claimed as accepted or rejected yet. It is kept apart
from historical salvage so ownership and timing remain clear.

## 7. Integration protocol

### Phase A: freeze and prove the baseline

1. Re-read the current instruction stack and doctrine before each mutation
   batch.
2. Record `git status`, `git diff --stat`, `git diff --check`, current HEAD,
   upstream alignment, branch list, worktree list, stash list, and the exact
   candidate refs.
3. Keep a copy of this ledger current. Do not create a recovery branch or
   worktree until the user authorizes integration mutation for that phase.

### Phase B: symbol-level comparison

For every candidate file, compare `stash-parent -> stash` with `HEAD` using
the path and relevant function or class. Record one of:

- `ACCEPT-HUNK`: current architecture has a gap and the hunk is compatible.
- `ADAPT-HUNK`: behavior is valuable but names, route, schema, or contracts
  changed; manually port the smallest correct form.
- `TEST-ONLY`: the assertion exposes a current requirement but source is
  already correct or the test needs modernizing.
- `DOC-MINE`: the material is a historical lead, not a canonical document.
- `REDUNDANT`: current `HEAD` already contains the same behavior or blob.
- `REJECT`: generated, secret-bearing, stale, unsafe, or contradicted by
  current doctrine.
- `DEFER`: valuable but blocked by a missing decision, fixture, dependency,
  or runtime evidence.

### Phase C: isolated batch integration

1. Work from a fresh recovery branch or worktree based on current `main`, not
   from a stash-applied main checkout.
2. Integrate one coherent cluster at a time: domain and tests, data model and
   tests, UI wiring and tests, tools and tests, then documentation.
3. Use `apply_patch` or an equivalent explicit hunk edit. Preserve current
   changes and never overwrite dirty files without a resolved ownership
   decision.
4. Run targeted tests immediately. For DB writes, include mutation,
   rollback/idempotency, household scope, and failure-path tests.
5. Run lint, type/import checks, source tests, browser/runtime tests, and
   release gates appropriate to the cluster. Label evidence by tier.
6. Commit each accepted batch with provenance in the commit body or trailer.
   Do not push until the batch is reviewed and the user authorizes the push.

### Phase D: final reconciliation

At the end, report separately:

- recovered and tested;
- adapted and tested;
- test-only additions;
- rejected with reason;
- deferred with blocker;
- current dirty drift not owned by recovery;
- branch, worktree, stash and remote status;
- gate results and any known failures.

## 8. Rollback and safety points

- The pushed `3319373dd14a8cfaa10335de85b7ee3e594f0c3c` remains the known
  remote checkpoint.
- Historical stashes remain untouched.
- The detached worktree metadata remains untouched.
- Every recovery batch must be independently revertible by its commit. No
  recovery batch may require rewriting the known remote checkpoint.
- If a batch changes a schema or migration contract, stop and review before
  accepting dependent UI or fixture changes.

## 9. Immediate next action

The stash and detached-worktree recovery inventory is now complete. The next
work is not another bulk salvage pass. It is a separate review of the live
concurrent evaluation tranche, followed by an explicit product decision on
the deferred expiry boundary. Any further source recovery must be justified
by a newly demonstrated current gap and must use a new isolated batch.

The integrated recovery commits on `main` are:

1. `abbb23b` `fix: support decimal market size classes`
2. `3a1e2ec` `test: assert correction table in repo truth`
3. `c8b2d50` `fix: restore safe legacy API aliases`
4. `b00681e` `test: count correction rows precisely`
5. `340de80` `feat: restore recipe rich empty state`

The expiry-alert hunk remains deferred because `check_expiry()` has no
production callers and the repository has other active expiry policies.

## 10. First cluster findings

Focused current-main verification ran:

```text
uv run pytest tests/domain/test_inventory_alerts.py tests/domain/test_unit_price.py -q
80 passed in 1.93s
```

Additional read-only probes against current `main` found:

- `parse_size("1,5 small")` returns `unrecognized_size`.
- `parse_size("1.5 medium")` returns `unrecognized_size`.
- `parse_size("1,5 kg")` already works.
- `check_expiry(..., 0)` currently returns `EXPIRED`, `CRITICAL`, and
  `"has expired"`.

The stash 4 domain tests add coverage for decimal size classes and split
negative days from day zero. The unit-price hunk is an `ACCEPT-HUNK` and has
now been integrated. The
expiry hunk is an `ADAPT-HUNK` candidate: the code is small, but the user-facing
boundary between “expires today” and “already expired” must be confirmed in
the active domain contract before integration. This distinction is precisely
why recovery is semantic salvage instead of a mechanical stash apply.

Batch result: the unit-price hunk was accepted and cherry-picked into `main`
as `abbb23b` after 155 relevant tests and Ruff passed. The recovery worktree
commit was `4ef733f`. The recovery worktree remains available for subsequent
batches.

### 10.1 Subsequent batch evidence

The repository-truth candidate added the existing `correction_events` table
to `tests/test_repo_truth.py`. This was test-only and passed with the current
schema. It was cherry-picked as `3a1e2ec`.

The legacy route review found a real current defect: cloning a FastAPI route
as a plain Starlette `Route` strips dependency injection and response-model
metadata. The browser global-search palette also called the legacy path
without authentication, while the canonical versioned route is protected.
The adapted APIRoute clone, explicit local legacy search adapter, protected
route assertions, and isolated browser hydration test passed 16 focused API
tests plus one standalone browser test. This was cherry-picked as `c8b2d50`.

The correction-row test was modernized to count `class='correction-row'`
exactly. Ten focused correction tests passed, and the change was cherry-
picked as `b00681e`.

The recipe review found a current contract gap rather than a stale feature:
`shopstack/ui/tabs/recipe.py` already rendered `recipe.no_input`, but
`shopstack/services/empty_states.py` did not register that preset and
`shopstack/services/i18n.py` lacked its English and Hindi keys. The smallest
adapted recovery added those keys and focused guards. Fifty-two focused
empty-state and recipe regression tests passed, plus compilation and diff
checks. This was cherry-picked as `340de80`.

The full regression-guard file was not treated as green solely from that
focused result. One unrelated guard still requires the ignored local file
`Docs/SERVICES_ARCHITECTURE.md`, which is absent from the isolated recovery
worktree. That environment/documentation dependency remains a separate
known condition.
