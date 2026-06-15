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

import os

# Set the canonical test env BEFORE any shopstack import.
os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")
os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")
os.environ.setdefault("SHOPSTACK_OFF_THE_GRID", "true")

import pytest

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
    """

    def test_build_app_succeeds(self):
        from app import build_app
        app = build_app()
        # The app should have at least one tab (a sanity check
        # that build_all_tabs actually ran).
        assert app is not None
        children = getattr(app, "children", [])
        assert len(children) > 0, (
            "build_app() returned an app with no children — "
            "build_all_tabs() didn't render any tabs."
        )
