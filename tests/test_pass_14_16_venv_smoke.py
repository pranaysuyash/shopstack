"""Operator-facing smoke test for Pass 14-16 modules.

motto_v3 §0.5 evidence tiers: the project's CLI / public
APIs are how an operator or CI step actually drives the
features. If a new module's public surface is broken at
import or at the public entry point, every individual unit
test can still pass while the operator-facing experience is
broken.

This file is the single test that proves "the operator can
use this feature right now". It exercises each new module
the way a real caller would:

* ``shopstack.tools.js_validate.main()`` — runs the full
  scan and asserts exit 0 (no JS SyntaxErrors in the project).
* ``shopstack.services.training_capture.extract_training_examples``
  with a synthetic Pydantic ``Trace`` (the shape produced
  by the SMS webhook) — proves the capture pipeline works
  end-to-end through the public API.
* ``shopstack.ui.components.primitives`` — exercises the
  three new HTML primitives end-to-end.
* ``app.build_app()`` — proves the full Gradio app composes
  without any import-time errors from the new modules.

This test is intentionally NOT a unit test. It is a
post-deployment health probe disguised as a test. When
parallel agents are landing changes in this repo, this
test catches the "I shipped a new module that breaks
app.build_app()" class of regression.
"""
from __future__ import annotations

# Per the 2026-06-14 test isolation hardening pattern, the
# full-app build test in this file launches a Gradio
# ``gr.Blocks`` instance that mutates the ``app`` module's
# global state. It must run in its own pytest process
# (or with -m standalone in a separate invocation) so it
# does not pollute the in-process ``app`` module state for
# other tests (e.g. test_browser_hydration.py, which is
# also marked standalone). The subprocess implementation
# in TestAppBuildsInVenv mitigates in-process pollution,
# but the canonical pattern across the project is to mark
# any test that touches the live Gradio stack as
# ``standalone`` so a bulk test runner can filter it.
# NOTE: do NOT override os.environ here. conftest.py
# (tests/conftest.py) already sets SHOPSTACK_DB_PATH to a
# session-scoped temp FILE path, which is the safe default
# for tests that build the full Gradio app (the prior
# :memory: choice broke under Gradio worker threads — see
# the conftest comment block). The env-smoke test reuses
# that same DB; we do not re-set it.

import pytest

# Per the 2026-06-14 test isolation hardening pattern, the
# full-app build test in this file launches a Gradio
# ``gr.Blocks`` instance that mutates the ``app`` module's
# global state. It must run in its own pytest process
# (or with -m standalone in a separate invocation) so it
# does not pollute the in-process ``app`` module state for
# other tests (e.g. test_browser_hydration.py, which is
# also marked standalone). The subprocess implementation
# in TestAppBuildsInVenv mitigates in-process pollution,
# but the canonical pattern across the project is to mark
# any test that touches the live Gradio stack as
# ``standalone`` so a bulk test runner can filter it.
pytestmark = pytest.mark.standalone

from shopstack.schemas.models import ToolCall, Trace
from shopstack.services.training_capture import (
    CONFIRMATION_RANK,
    MIN_RANK_DEFAULT,
    extract_training_examples,
)
from shopstack.ui.components.primitives import (
    branded_error_shell,
    last_updated_stamp,
    prereq_interactive,
)


# ── Public-API smoke: primitives ──────────────────────────────────


class TestPrimitivesPublicAPI:
    """The three new HTML primitives must be importable and
    callable from the project venv. The unit tests cover
    the contract; this covers the wiring."""

    def test_last_updated_stamp_importable_and_callable(self):
        from datetime import datetime, timezone

        html = last_updated_stamp(datetime.now(timezone.utc))
        assert "Last updated" in html
        assert "<time datetime=" in html

    def test_prereq_interactive_returns_callable(self):
        h = prereq_interactive(prereq=lambda *v: bool(v and v[0]))
        # Returns a handler; calling it returns a Gradio update
        # (dict-shaped on the Gradio version we test against).
        update = h("x")
        assert update is not None

    def test_branded_error_shell_importable_and_callable(self):
        html = branded_error_shell("Test failure", detail="NullPointerException")
        assert "Test failure" in html
        assert "NullPointerException" in html


# ── Public-API smoke: training_capture ──────────────────────────


class TestTrainingCapturePublicAPI:
    """The training_capture pipeline must accept a real Pydantic
    Trace (the shape produced by the SMS webhook / Ask panel)
    and produce a real training example."""

    def test_real_pydantic_trace_round_trip(self):
        trace = Trace(
            input_type="sms",
            user_goal="add milk",
            redacted_user_request="add 2 L milk",
            proposed_tool_calls=[
                ToolCall(
                    tool_name="add_inventory_lot",
                    args={"canonical_name": "milk", "quantity": 2.0, "unit": "L"},
                )
            ],
            human_confirmation="confirmed-by-user",
            final_response="Added 2 L milk",
            actor_id="hh-1",
        )
        report = extract_training_examples([trace])
        assert report.total == 1
        example = report.captured[0]
        assert example.intent == "add_inventory_item"
        assert example.args["canonical_name"] == "milk"
        assert example.confirmation == "confirmed-by-user"
        assert example.source == "real-confirmed"

    def test_min_rank_default_is_a_reasonable_floor(self):
        """The default floor must include the two highest-signal
        confirmations. A floor too low (e.g. 0) leaks
        uncommitted traces; a floor too high (e.g. 100)
        drops auto-confirmed training data.
        """
        assert MIN_RANK_DEFAULT <= CONFIRMATION_RANK["confirmed-by-user"]
        assert MIN_RANK_DEFAULT <= CONFIRMATION_RANK["auto-confirmed"]
        assert MIN_RANK_DEFAULT > CONFIRMATION_RANK["uncommitted"]


# ── Public-API smoke: js_validate CLI ────────────────────────────


class TestJSValidatorCLI:
    """The CLI must be invokable from the project venv and
    must return 0 (no JS SyntaxErrors in the current codebase).
    A non-zero exit would mean the pre-commit hook (Item #56)
    is broken or the codebase has regressed.
    """

    def test_js_validate_main_exits_zero(self):
        """Invoke main([]) and assert exit 0.

        main([]) writes ``Docs/JS_VALIDATION.json`` as a side
        effect. We run it against the real project (not a
        temp directory) so the operator-visible behavior is
        what's tested.
        """
        from shopstack.tools import js_validate

        rc = js_validate.main([])
        assert rc == 0, (
            f"js_validate.main() exited {rc} — JS SyntaxErrors in "
            f"the codebase would block pre-commit (Item #56)."
        )


# ── Public-API smoke: full app build ────────────────────────────


class TestAppBuildsInVenv:
    """The full Gradio app must build without import-time
    errors. A failure here means a new module is breaking
    app composition — the kind of regression that unit
    tests on individual modules can't catch.

    Implementation note (motto_v3 §0.6 reliability +
    §6 blast-radius): we run the build in a *subprocess*
    so the smoke check never pollutes the in-process
    ``app`` module state. Without the subprocess, calling
    ``build_app()`` here creates a second ``gr.Blocks``
    instance that can interfere with browser-hydration
    tests (which also call ``build_app()``) — the
    Playwright test would then see "toggleTheme is not
    defined" because the global Gradio JS shim registry
    was reset between the two builds.

    The subprocess is a one-off cost: the second
    ``build_app()`` invocation in a fresh Python process
    is fast (~10s) and we only run it once per test
    session.
    """

    def test_build_app_succeeds(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        # Use a private temp DB so the subprocess's Settings()
        # picks up its own DB rather than the test session's
        # file DB. This is the same defense-in-depth as the
        # SHOPSTACK_LOCAL_AUTO_DOWNLOAD=false env in conftest.
        with tempfile.NamedTemporaryFile(
            suffix=".db", prefix="shopstack_env_smoke_", delete=False
        ) as f:
            smoke_db_path = f.name
        try:
            env_overrides = {
                "SHOPSTACK_DB_PATH": smoke_db_path,
                "SHOPSTACK_LOCAL_AUTO_DOWNLOAD": "false",
                "SHOPSTACK_OFF_THE_GRID": "true",
                # Pin all backends to mock so the subprocess doesn't
                # try to load real providers (which would slow the
                # test and possibly fail in CI without HF tokens).
                "SHOPSTACK_PLANNER_BACKEND": "mock",
                "SHOPSTACK_STT_BACKEND": "mock",
                "SHOPSTACK_TTS_BACKEND": "mock",
                "SHOPSTACK_VISION_BACKEND": "mock",
                "SHOPSTACK_OBJECT_DETECTION_BACKEND": "mock",
                "SHOPSTACK_GROUNDING_BACKEND": "mock",
                "SHOPSTACK_SEGMENTATION_BACKEND": "mock",
                "SHOPSTACK_OCR_BACKEND": "mock",
                "SHOPSTACK_TOOL_CALL_PARSER_BACKEND": "mock",
                "SHOPSTACK_EMBEDDINGS_BACKEND": "mock",
                "SHOPSTACK_IMAGE_EDIT_BACKEND": "mock",
                "SHOPSTACK_IMAGE_GEN_BACKEND": "mock",
            }
            result = subprocess.run(
                [sys.executable, "-c", _BUILD_APP_SCRIPT],
                capture_output=True,
                text=True,
                timeout=180,
                env={**__import__("os").environ, **env_overrides},
            )
            assert result.returncode == 0, (
                f"build_app() in subprocess exited {result.returncode}. "
                f"stderr:\n{result.stderr[-2000:]}\n"
                f"stdout:\n{result.stdout[-1000:]}"
            )
            # The script prints "OK:<n_children>" on success.
            assert result.stdout.strip().startswith("OK:"), (
                f"Unexpected subprocess output: {result.stdout[:200]!r}"
            )
        finally:
            # Clean up the smoke test's private DB.
            base = Path(smoke_db_path)
            for suffix in ("", "-wal", "-shm"):
                base.with_suffix(base.suffix + suffix).unlink(missing_ok=True)


# Script run in the subprocess. Kept as a module-level
# constant (not a function) so the subprocess can exec it
# without needing the test module's imports.
_BUILD_APP_SCRIPT = (
    "import sys; "
    "sys.path.insert(0, '.'); "
    "from app import build_app; "
    "app = build_app(); "
    "n = len(getattr(app, 'children', [])); "
    "assert n > 0, f'build_app() returned app with no children: {n}'; "
    "print(f'OK:{n}')"
)
