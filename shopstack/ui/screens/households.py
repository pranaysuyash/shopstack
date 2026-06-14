"""Households screen module — ARCHIVED SHIM.

**STATUS (2026-06-13 supersession):** The canonical implementation has
been moved to `shopstack.ui.screens._legacy.households`. This file is
a backward-compatibility shim that re-exports the public functions
so any existing `from shopstack.ui.screens.households import X`
call site continues to work without modification.

Per `motto_v3` §7 (Supersession Rule) and §15 (Documentation Rules):
- §7: "do not delete old non-trivial logic without inventory and
  approval" — and inventory shows Phase 10 #1 future intent.
- §15: "If logic is preserved but not used, inventory it before
  deleting or archiving." Done — see `Docs/audits/audit_03_*` and
  `Docs/DECISION_RECORDS_CODE_REMOVALS_2026-06-13.md`.

The functions in `_legacy/households.py` are not dead code; they
are Phase 10 #1 wiring awaiting UI binding. See
`Docs/HANDOFF_PHASE10_PERMISSIONS_RESTOCK_CARD_2026-06-13.md`.

If a future caller wants to use any of these functions, prefer
importing them from `shopstack.ui.screens` (the public re-export
in `screens/__init__.py`) so the re-export surface stays consistent.
"""
from shopstack.ui.screens._legacy.households import (
    add_member_screen,
    change_role_screen,
    households_panel_screen,
    list_user_households_screen,
    remove_member_screen,
)

__all__ = [
    "add_member_screen",
    "change_role_screen",
    "households_panel_screen",
    "list_user_households_screen",
    "remove_member_screen",
]
