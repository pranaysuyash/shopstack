# `_legacy/` — Archived Screens

**Date:** 2026-06-13
**Status:** Active
**Per:** `motto_v3` §7 (Supersession Rule) + §15 (Documentation Rules) + `Docs/DECISION_RECORDS_CODE_REMOVALS_2026-06-13.md`

## Purpose

This directory contains screen modules that are **not currently called
by production code** but are **preserved per supersession rules**.

The companion test `tests/test_screens_dead_code.py` reports all
modules in this directory as "dead" (zero Python callers). The
**correct response is archive, not delete** — see the decision
rationale for each module below.

## Inventory

### `households.py` — Phase 10 wiring, KEEP per §11

| Field | Value |
|-------|-------|
| **Status** | Archived 2026-06-13 (not deleted) |
| **Functions** | `add_member_screen`, `change_role_screen`, `households_panel_screen`, `list_user_households_screen`, `remove_member_screen` |
| **Future intent** | Yes — Phase 10 #1 wiring |
| **Doc reference** | `Docs/HANDOFF_PHASE10_PERMISSIONS_RESTOCK_CARD_2026-06-13.md` |
| **Decision** | DR-SS1 (this PR) — preserve per §11 |

**Rationale:** These functions wrap the service layer
(`shopstack.services.permissions: add_member, remove_member,
change_role, list_members, list_households_for_user`) and are
documented in the Phase 10 handoff as the canonical UI wiring. The
5 functions were flagged as dead because the household settings UI
panel (`shopstack/ui/household_settings.py`) was extracted from the
main tabs — the household members panel has not yet been wired up.
This is **future intent, not dead code**.

Per `motto_v3` §11: *"Do not delete overbuilt, enterprise, or
speculative features just to simplify the current view, as that
creates rework later. If they distract from the core product, hide
them from the UI instead of deleting the code."*

**Compatibility shim:** `shopstack/ui/screens/households.py` (a
3-line re-export) preserves the original import path:
```python
from shopstack.ui.screens.households import add_member_screen  # still works
```

## How to Add a New Archived Module

1. Move the file: `mv shopstack/ui/screens/foo.py shopstack/ui/screens/_legacy/foo.py`
2. Add a top-of-file docstring noting supersession + future intent
3. Create a shim at `shopstack/ui/screens/foo.py`:
   ```python
   from shopstack.ui.screens._legacy.foo import *  # noqa: F401,F403
   from shopstack.ui.screens._legacy.foo import __all__ as __all__
   ```
4. Add a re-export in `shopstack/ui/screens/__init__.py`
5. Add a section to this `_LEGACY.md` with the rationale
6. Run the dead-code test — it will continue to flag the module, but
   that's the **correct behavior** (informational, not a failure)

## What NOT to Do

Per `motto_v3` §7 and §11, do NOT:

- **Delete** the file outright — even if no caller is found today,
  the function may be Phase 10+ wiring.
- **Move to a trash/ folder** without documenting why.
- **Rename** the file without a shim — `from shopstack.ui.screens import households`
  must still work for tests and external consumers.
- **Mark `__all__` as empty** without archiving — the public API
  contract is broken if functions vanish from `__all__` but
  external consumers still import them.

## Related Documents

- `Docs/DECISION_RECORDS_CODE_REMOVALS_2026-06-13.md` — prior dead-code cleanup that violated §7/§11/§15 and was reversed.
- `motto_v3.md` §7 (Supersession Rule), §11 (Engineering Standards), §15 (Documentation Rules)
- `docs/audits/audit_03_gradio_app_architecture.md` — Finding 3.24 (dead code discovery)
- `docs/audits/ACTION_ITEMS.md` — AI-19, DR-SS1
