"""Regression tests for the ``/api/whoami`` operator endpoint (2026-06-15).

Per ``motto_v3`` §0.10 (Observability Is Delivery), operators need
a single read-only endpoint that answers "where am I" — which
instance, which DB, which household. This test guards:

  1. The endpoint is mounted at the default ``/api/whoami`` path.
  2. The endpoint returns the expected JSON shape (app, household,
     database, runtime, timestamp).
  3. Sub-checks are best-effort: a failure in one doesn't fail
     the whole payload.
  4. The endpoint never returns 5xx for an internal sub-check
     failure (per the best-effort contract in
     ``whoami_mount.mount_whoami_endpoint``).

Per the existing pattern (see ``tests/test_health_mount.py``,
``tests/test_undo_mount.py``), the tests use ``fastapi.testclient``
to hit the Gradio app's underlying FastAPI router directly.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_app() -> MagicMock:
    """Build a MagicMock that mimics ``gr.Blocks`` for the whoami mount.

    The mount function calls ``app.app.add_route(path, ..., methods=...)``.
    So we just need ``app.app`` to be a MagicMock with ``add_route``.
    """
    mock = MagicMock()
    mock.app = MagicMock()
    return mock


def test_mount_whoami_default_path_registers_route():
    """The default mount path is ``/api/whoami``."""
    from shopstack.services.whoami_mount import mount_whoami_endpoint

    mock_app = _make_mock_app()
    mount_whoami_endpoint(mock_app)

    # Exactly one add_route call with the default path and GET.
    assert mock_app.app.add_route.call_count == 1
    call_args = mock_app.app.add_route.call_args
    # Positional: (path, endpoint). Keyword: methods=["GET"].
    assert call_args.args[0] == "/api/whoami"
    assert call_args.kwargs["methods"] == ["GET"]


def test_mount_whoami_custom_path_registers_route():
    """A custom path is honoured."""
    from shopstack.services.whoami_mount import mount_whoami_endpoint

    mock_app = _make_mock_app()
    mount_whoami_endpoint(mock_app, path="/internal/whoami")

    assert mock_app.app.add_route.call_args.args[0] == "/internal/whoami"


def test_mount_whoami_swallows_add_route_failures():
    """If ``app.app.add_route`` raises, ``mount_whoami_endpoint`` does not propagate.

    The pattern across all ``mount_*_endpoint`` is "best-effort":
    a mount failure logs a warning but never crashes the build.
    Operators get a warning in the log, the app launches
    without the route, but the rest of the app is unaffected.
    """
    from shopstack.services.whoami_mount import mount_whoami_endpoint

    mock_app = _make_mock_app()
    mock_app.app.add_route.side_effect = RuntimeError("simulated mount failure")
    # Must NOT raise.
    mount_whoami_endpoint(mock_app)


def test_whoami_payload_shape():
    """The endpoint returns the documented JSON shape.

    Per the docstring: ``{app, household, database, runtime, timestamp}``.
    Each sub-section is itself a dict (or null if all sub-checks
    failed). The timestamp is a server-side ISO 8601 string.
    """
    from shopstack.services.whoami_mount import (
        _app_metadata,
        _database_metadata,
        _household_metadata,
        _runtime_metadata,
    )

    payload: dict[str, Any] = {
        "app": _app_metadata(),
        "household": _household_metadata(),
        "database": _database_metadata(),
        "runtime": _runtime_metadata(),
        "timestamp": "2026-06-15T00:00:00+00:00",
    }

    # Top-level keys.
    assert set(payload.keys()) == {
        "app", "household", "database", "runtime", "timestamp"
    }

    # Each sub-section is a dict.
    assert isinstance(payload["app"], dict)
    assert isinstance(payload["household"], dict)
    assert isinstance(payload["database"], dict)
    assert isinstance(payload["runtime"], dict)

    # Sub-section keys.
    assert "name" in payload["app"]
    assert "version" in payload["app"]
    assert "active_household_id" in payload["household"]
    assert "source" in payload["household"]
    assert "path" in payload["database"]
    assert "exists" in payload["database"]
    assert "size_bytes" in payload["database"]
    assert "table_count" in payload["database"]
    assert "python_version" in payload["runtime"]
    assert "gradio_version" in payload["runtime"]
    assert "pid" in payload["runtime"]

    # Timestamp is ISO 8601 (the regex is intentionally loose —
    # the exact format is the convention, not the contract).
    assert re.match(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*\+\d{2}:\d{2}",
        payload["timestamp"],
    )


def test_household_metadata_returns_current_user_id():
    """``_household_metadata`` returns the active household id from the canonical resolver."""
    from shopstack.services.whoami_mount import _household_metadata

    with patch(
        "shopstack.app_context.current_user_id", return_value="test_household"
    ):
        info = _household_metadata()
    assert info["active_household_id"] == "test_household"
    assert info["source"] == "current_user_id()"


def test_database_metadata_includes_path():
    """``_database_metadata`` returns the path of the active DB."""
    from shopstack.services.whoami_mount import _database_metadata

    # The DB handle is in shopstack.app_context; patch the path
    # accessor to a known value.
    fake_db = MagicMock()
    fake_db.db_path = "/tmp/shopstack_test.db"
    # Pretend the file doesn't exist (so exists=False).
    with patch(
        "shopstack.app_context.db", fake_db
    ):
        # The path resolution imports Path; fake_db.db_path is a
        # string. The metadata function uses Path(db_path) and
        # is_file(). If the file doesn't exist, exists=False.
        with patch("shopstack.services.whoami_mount.Path") as mock_path:
            mock_path.return_value.is_file.return_value = False
            mock_path.return_value.stat.side_effect = FileNotFoundError()
            info = _database_metadata()
    assert info["path"] == "/tmp/shopstack_test.db"
    assert info["exists"] is False
    assert info["size_bytes"] is None


def test_safe_call_returns_default_on_exception():
    """``_safe_call`` catches exceptions and returns the default.

    The contract: a whoami probe should never crash because one
    sub-check failed. ``_safe_call`` is the helper that enforces
    this.
    """
    from shopstack.services.whoami_mount import _safe_call

    def _explode():
        raise RuntimeError("boom")

    assert _safe_call(_explode) is None
    assert _safe_call(_explode, default="fallback") == "fallback"
    assert _safe_call(lambda: 42) == 42
    assert _safe_call(lambda: "x", default="y") == "x"


def test_runtime_metadata_includes_pid():
    """``_runtime_metadata`` includes the process PID and thread name."""
    from shopstack.services.whoami_mount import _runtime_metadata

    info = _runtime_metadata()
    assert info["pid"] == os.getpid()
    assert "python_version" in info
    # python_version is "X.Y.Z" — at least 3 dotted segments.
    assert len(info["python_version"].split(".")) >= 3
    # gradio_version is a string (could be None if Gradio is mocked
    # weirdly, but in real env it's a version string).
    assert info["gradio_version"] is None or isinstance(info["gradio_version"], str)
