"""Regression tests for the sub-builder extraction pattern.

Per `docs/audits/audit_03_gradio_app_architecture.md` finding 3.4:
    "A sub-builder is a function that:
     1. Accepts `blocks, app, ctx` (uniform signature)
     2. Registers components inside the parent `gr.Blocks` context
     3. Returns either `None` (self-contained) or `*Handles` (cross-tab references)"

Per `docs/audits/audit_03_gradio_app_architecture.md` finding 3.6:
    "Cross-tab references should be typed via `*Handles` dataclasses."

This test verifies the sub-builder pattern is followed. If someone
removes a sub-builder (and re-inlines its code into `app.py`),
the test fails.
"""
from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path


# Add tests/ to sys.path so we can import
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pwa_mount_is_a_sub_builder():
    """`mount_pwa_static(app)` is a sub-builder — no inlining into app.py."""
    from shopstack.ui.pwa_mount import mount_pwa_static
    sig = inspect.signature(mount_pwa_static)
    params = list(sig.parameters.keys())
    # Should accept `app: gr.Blocks`
    assert params == ["app"], (
        f"mount_pwa_static should accept a single `app` parameter. "
        f"Got: {params}. If you change the signature, also update "
        f"app.py and this test."
    )


def test_locale_save_is_a_sub_builder():
    """`build_locale_save()` is a sub-builder with a *Handles dataclass."""
    from shopstack.ui.locale_save import build_locale_save, LocaleSaveHandles

    # Returns a typed Handles dataclass
    result_type = inspect.signature(build_locale_save).return_annotation
    # With `from __future__ import annotations`, return_annotation is a string
    assert result_type in (LocaleSaveHandles, "LocaleSaveHandles"), (
        f"build_locale_save should return LocaleSaveHandles. "
        f"Got: {result_type}. If you change the return type, update "
        f"this test."
    )


def test_household_settings_is_a_sub_builder():
    """`build_household_settings(app)` returns HouseholdSettingsHandles."""
    from shopstack.ui.household_settings import (
        build_household_settings,
        HouseholdSettingsHandles,
    )
    sig = inspect.signature(build_household_settings)
    params = list(sig.parameters.keys())
    assert params == ["app"], (
        f"build_household_settings should accept a single `app` parameter. "
        f"Got: {params}."
    )
    result_type = sig.return_annotation
    assert result_type in (HouseholdSettingsHandles, "HouseholdSettingsHandles"), (
        f"build_household_settings should return HouseholdSettingsHandles. "
        f"Got: {result_type}."
    )


def test_sms_webhook_is_a_sub_builder():
    """`mount_sms_webhook(app)` is a sub-builder."""
    from shopstack.services.sms_webhook import mount_sms_webhook
    sig = inspect.signature(mount_sms_webhook)
    params = list(sig.parameters.keys())
    assert params == ["app"], (
        f"mount_sms_webhook should accept a single `app` parameter. "
        f"Got: {params}."
    )


def test_app_py_calls_all_5_sub_builders():
    """`app.py` should call all 5 sub-builders (architecture invariant).

    If any of these is missing from app.py, the sub-builder
    was either removed or inlined. Either way, this is a
    regression.
    """
    app_source = (PROJECT_ROOT / "app.py").read_text()

    required_sub_builder_calls = [
        "mount_pwa_static(app)",
        "mount_sms_webhook(app)",
        "build_locale_save()",
        "build_household_settings(app)",
    ]

    missing = [
        call for call in required_sub_builder_calls
        if call not in app_source
    ]

    assert not missing, (
        f"app.py does not call these sub-builders: {missing}. "
        f"Either re-add the call, or update this test if the "
        f"sub-builder was intentionally removed."
    )


def test_tab_builders_use_uniform_signature():
    """Tab builders should accept (blocks, app, ctx) — uniform signature.

    This is the contract that makes tab builders composable.
    A deviation breaks the composition pattern.
    """
    tab_modules = [
        "shopstack.ui.tabs.today",
        "shopstack.ui.tabs.basket",
        "shopstack.ui.tabs.cookbook",
        "shopstack.ui.tabs.market",
        "shopstack.ui.tabs.reconcile",
        "shopstack.ui.tabs.memory",
    ]

    for module_name in tab_modules:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue

        # Find the build_*_tab function in the module
        builder = None
        for attr in dir(mod):
            if attr.startswith("build_") and attr.endswith("_tab"):
                builder = getattr(mod, attr)
                break

        if builder is None:
            continue

        sig = inspect.signature(builder)
        params = list(sig.parameters.keys())
        # Should accept (blocks, app, ctx) — the uniform signature
        assert params[:3] == ["blocks", "app", "ctx"], (
            f"{module_name}.{builder.__name__} has wrong signature. "
            f"Expected first 3 params ['blocks', 'app', 'ctx'], got {params[:3]}. "
            f"Tab builders should follow the uniform signature."
        )
