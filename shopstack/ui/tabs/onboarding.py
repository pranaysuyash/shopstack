"""Composition-layer wrapper for the onboarding wizard.

Per the composition-seam discipline (see ``test_app_py_does_not_import_screens``),
app.py must not import directly from ``shopstack.ui.screens.*``. This
sub-builder re-exports ``build_onboarding_wizard`` so app.py can compose
the wizard via the canonical sub-builder layer.

The canonical implementation lives in ``shopstack.ui.screens.onboarding``
for now (it predates the composition-seam discipline). When that module
is migrated to its own sub-builder layer, this re-export can be deleted
in favor of a direct import.
"""

from __future__ import annotations

from shopstack.ui.screens.onboarding import build_onboarding_wizard

__all__ = ["build_onboarding_wizard"]
