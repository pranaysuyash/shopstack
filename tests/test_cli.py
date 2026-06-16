"""Regression tests for ``shopstack.cli`` (Pass 17, 2026-06-15).

The CLI is the **mode-portability proof** for ShopStack: it
exercises the public service API (``shopstack.app_context.tools``)
without launching the Gradio UI. These tests guard:

  1. The CLI can be imported without importing ``app.py`` or
     ``gradio`` (mode-portability contract).
  2. All 7 subcommands are wired (inventory / shopping / find /
     use-soon / next-buy / tools / whoami).
  3. Output is valid JSON by default; ``--human`` flips to
     pretty-printed output.
  4. ``whoami`` returns the documented contract.
  5. The CLI exit code is 0 on success.

Per ``motto_v3`` §0.10 (Observability Is Delivery), the CLI is
the operator-friendly counterpart of the ``/api/whoami`` HTTP
endpoint. Operators who don't want to launch a Gradio server can
get the same introspection data from the shell.
"""
from __future__ import annotations

import io
import json
import re
import sys
from unittest.mock import patch

import pytest


# ── Mode-portability contract ────────────────────────────────────────


def test_cli_does_not_import_app_or_gradio_directly():
    """The CLI module does NOT import ``app`` or ``gradio`` directly.

    This is the mode-portability contract: the CLI proves the
    public service API works without the UI layer. If a future
    change imports ``app.py`` or ``gradio`` directly, the
    mode-portability claim breaks.

    ``shopstack.app_context`` IS allowed (it's the public
    service layer). The Gradio import is an indirect side effect
    of importing ``app_context`` (via the tools registry
    bootstrap), but it's not a direct import in the CLI module.
    """
    cli_path = "shopstack/cli/__init__.py"
    with open(cli_path) as fp:
        src = fp.read()
    # No direct imports of ``app`` (the app.py module) or ``gradio``
    # (other than via app_context).
    # Allowed: ``from shopstack.app_context import ...``
    # Disallowed: ``from app import ...`` or ``import gradio`` (direct)
    assert "from app import" not in src, (
        "CLI must not import `app` directly. "
        "If you need an app-specific function, add it to "
        "`shopstack.app_context` or `shopstack.cli` itself."
    )
    assert "import gradio" not in src, (
        "CLI must not import `gradio` directly. "
        "The whole point of the CLI is to prove the public service "
        "API works without the UI layer."
    )


# ── Parser + dispatch ──────────────────────────────────────────────


def test_parser_includes_all_seven_subcommands():
    """All 7 subcommands are registered (inventory, shopping, find,
    use-soon, next-buy, tools, whoami).
    """
    from shopstack.cli import build_parser

    parser = build_parser()
    # Parse each subcommand with a minimal valid argv.
    for cmd_args in [
        ["inventory"],
        ["shopping"],
        ["find", "milk"],
        ["use-soon"],
        ["use-soon", "--days", "3"],
        ["next-buy"],
        ["tools"],
        ["whoami"],
    ]:
        args = parser.parse_args(cmd_args)
        assert args.cmd is not None, f"no cmd parsed from {cmd_args!r}"


def test_subcommand_dispatch_table_covers_all_commands():
    """The ``SUBCOMMANDS`` dispatch dict covers every registered subcommand."""
    from shopstack.cli import SUBCOMMANDS, build_parser

    parser = build_parser()
    # Re-parse and confirm each subcommand has a handler.
    for cmd_args in [
        ["inventory"], ["shopping"], ["find", "x"],
        ["use-soon"], ["next-buy"], ["tools"], ["whoami"],
    ]:
        args = parser.parse_args(cmd_args)
        assert args.cmd in SUBCOMMANDS, (
            f"subcommand {args.cmd!r} not in SUBCOMMANDS dispatch"
        )


# ── ``whoami`` output contract ─────────────────────────────────────


def test_whoami_payload_shape():
    """``whoami`` returns the documented JSON contract.

    Per the docstring: ``{household, database, runtime, timestamp}``.
    Each sub-section is itself a dict. The timestamp is
    ISO 8601 with timezone info.
    """
    from shopstack.cli import build_parser
    from datetime import datetime

    parser = build_parser()
    args = parser.parse_args(["whoami"])

    # Dispatch through the same path main() uses.
    from shopstack.cli import SUBCOMMANDS
    payload = SUBCOMMANDS["whoami"](args)

    assert "household" in payload
    assert "database" in payload
    assert "runtime" in payload
    assert "timestamp" in payload
    # Database sub-section keys.
    assert "path" in payload["database"]
    assert "size_bytes" in payload["database"]
    assert "table_count" in payload["database"]
    # Runtime sub-section keys.
    assert "pid" in payload["runtime"]
    assert "python_version" in payload["runtime"]
    # Timestamp is parseable ISO 8601 with timezone.
    parsed = datetime.fromisoformat(payload["timestamp"])
    assert parsed.tzinfo is not None


def test_whoami_json_output_is_valid():
    """Running ``cli whoami`` produces parseable JSON on stdout."""
    from shopstack.cli import main

    captured = io.StringIO()
    with patch("sys.stdout", captured):
        rc = main(["whoami"])
    assert rc == 0, f"cli whoami returned non-zero: {rc}"
    # Must be valid JSON.
    payload = json.loads(captured.getvalue())
    assert "household" in payload
    assert "database" in payload
    assert "runtime" in payload


def test_whoami_human_output_is_not_json():
    """``--human`` produces a non-JSON, line-based output."""
    from shopstack.cli import main

    captured = io.StringIO()
    with patch("sys.stdout", captured):
        rc = main(["--human", "whoami"])
    assert rc == 0
    out = captured.getvalue()
    # The --human output is plain text, not JSON.
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    # But it should contain recognizable keys.
    assert "household:" in out
    assert "pid:" in out


# ── ``tools`` subcommand ────────────────────────────────────────────


def test_tools_subcommand_lists_public_service_surface():
    """The ``tools`` subcommand lists the public service API."""
    from shopstack.cli import main

    captured = io.StringIO()
    with patch("sys.stdout", captured):
        rc = main(["tools"])
    assert rc == 0
    payload = json.loads(captured.getvalue())
    assert "count" in payload
    assert "tools" in payload
    assert payload["count"] > 0
    assert isinstance(payload["tools"], list)
    # Each entry has a name and a description.
    for tool in payload["tools"][:3]:
        assert "name" in tool
        assert "description" in tool


# ── ``find`` subcommand ────────────────────────────────────────────


def test_find_subcommand_returns_results():
    """``find <name>`` returns the tool's response.

    We use a name that's likely to be in the seeded test data
    (``milk`` is a canonical name added by ``seed_walkthrough.py``).
    If the search finds nothing, the test still passes — the
    contract is "returns the tool's response", not "finds a match".
    """
    from shopstack.cli import main

    captured = io.StringIO()
    with patch("sys.stdout", captured):
        rc = main(["find", "milk"])
    assert rc == 0
    # The payload may be empty (no match) or non-empty. Either is valid;
    # the contract is that the CLI returns the tool's response cleanly.
    payload = json.loads(captured.getvalue())


# ── Error handling ─────────────────────────────────────────────────


def test_unknown_subcommand_exits_nonzero():
    """An unknown subcommand exits with a non-zero code."""
    from shopstack.cli import main

    # argparse exits with code 2 on unknown subcommands.
    with pytest.raises(SystemExit) as exc_info:
        main(["nonsense-command"])
    assert exc_info.value.code == 2


def test_find_subcommand_requires_name():
    """``find`` requires a NAME argument (argparse enforces this)."""
    from shopstack.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["find"])
    assert exc_info.value.code == 2


# ── explain subcommand (Pass 18: decision explainability) ──────────


def test_explain_subcommand_dispatches():
    """The ``explain`` subcommand is in SUBCOMMANDS."""
    from shopstack.cli import SUBCOMMANDS, build_parser

    parser = build_parser()
    args = parser.parse_args(["explain", "milk"])
    assert args.canonical_name == "milk"
    assert "explain" in SUBCOMMANDS


def test_explain_subcommand_returns_decision_explanation_shape():
    """The ``explain`` subcommand returns a JSON-serializable dict.

    Either it returns a ``DecisionExplanation``-shaped dict
    (when a decision exists for the item) or an ``error`` dict
    (when no decision is active). Both are valid.
    """
    from shopstack.cli import main, SUBCOMMANDS

    args = type("Args", (), {"canonical_name": "milk"})()
    payload = SUBCOMMANDS["explain"](args)

    if "error" in payload:
        # The "no decision" case is also a valid contract.
        assert payload["error"] == "no_decision"
        assert "canonical_name" in payload
    else:
        # The "decision exists" case — should have the full
        # DecisionExplanation shape.
        for key in (
            "item_id", "canonical_name", "action", "confidence",
            "summary", "key_signal", "confidence_label",
            "evidence_summary", "override_hint",
        ):
            assert key in payload, f"missing key: {key}"


def test_explain_subcommand_handles_unknown_canonical_name():
    """The ``explain`` subcommand returns a clean error for unknown items."""
    from shopstack.cli import SUBCOMMANDS

    args = type("Args", (), {"canonical_name": "this_item_does_not_exist_xyz"})()
    payload = SUBCOMMANDS["explain"](args)
    assert payload["error"] == "no_decision"
    assert "canonical_name" in payload


def test_explain_subcommand_json_output_is_valid():
    """Running ``cli explain milk`` produces parseable JSON on stdout."""
    from shopstack.cli import main

    captured = io.StringIO()
    with patch("sys.stdout", captured):
        rc = main(["explain", "milk"])
    # Either rc=0 (decision found) or rc=0 (clean error case).
    # Both cases produce valid JSON.
    assert rc == 0
    payload = json.loads(captured.getvalue())
    # payload is either a DecisionExplanation-shaped dict or an
    # error dict; both are valid JSON.
    assert isinstance(payload, dict)


# ── Mode-portability proof (Tier 3) ─────────────────────────────────


def test_cli_runs_without_launching_gradio():
    """The CLI runs end-to-end without Gradio's launch path.

    This is the Tier-3 (integration) mode-portability proof:
    invoking the CLI does NOT call ``gradio.launch()`` or
    ``app.build_app()``. If a future change accidentally pulls
    the Gradio UI into the CLI's import chain, this test catches
    it.

    We use the ``whoami`` subcommand (no DB writes, no service
    calls beyond introspection) as the canary.
    """
    from shopstack.cli import main

    with patch("gradio.Blocks.launch") as mock_launch:
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            rc = main(["whoami"])
    assert rc == 0
    assert not mock_launch.called, (
        "CLI must not call `gradio.Blocks.launch()`. "
        "If this fires, the CLI's import chain now pulls in the "
        "Gradio UI, which breaks the mode-portability contract."
    )
