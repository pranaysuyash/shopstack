"""Backward-compatibility re-export of the onboarding wizard.

Per motto_v3 §7 (supersession rule) and the composition-seam discipline
(see ``test_app_py_does_not_import_screens``), the canonical home of the
onboarding wizard is ``shopstack.ui.tabs.onboarding``.

This module is preserved as a thin re-export for callers that have not
yet migrated. It carries no implementation and MUST NOT be edited —
the canonical source is ``shopstack.ui.tabs.onboarding``.

When all callers have migrated, this file will be deleted.
"""
from __future__ import annotations

from shopstack.ui.tabs.onboarding import build_onboarding_wizard

__all__ = ["build_onboarding_wizard"]
