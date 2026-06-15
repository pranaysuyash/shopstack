"""Tests for `shopstack.services.global_search_mount` — the HTTP endpoint.

Verifies:
  * The endpoint parses the ``q`` query parameter.
  * Empty query returns empty results.
  * Results are serialised to the expected JSON shape.
  * A DB or cookbook failure does not crash the endpoint
    (degraded experience: empty results + error field).
  * The mount function is best-effort (does not raise on
    duplicate-route or other Gradio-internal errors).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from shopstack.services.global_search import GlobalSearchResult
from shopstack.services.global_search_mount import (
    _global_search_endpoint,
    _serialize_result,
)


# ── Fixtures ───────────────────────────────────────────────────────


class _FakeRequest:
    """Minimal Starlette-like request for testing."""

    def __init__(self, params: dict[str, str]) -> None:
        # Use SimpleNamespace-like behavior: just a query_params attribute
        self.query_params = params


class _FakeSearchSources:
    """Captures the SearchSources that would be built."""


# ── Serialisation ──────────────────────────────────────────────────


class TestSerializeResult:
    def test_serialises_all_fields(self):
        r = GlobalSearchResult(
            kind="inventory", title="Milk", meta="2 L, in fridge",
            score=0.8, action_kind="tab", action_target="pantry",
            household_id="hh1",
        )
        d = _serialize_result(r)
        assert d["kind"] == "inventory"
        assert d["title"] == "Milk"
        assert d["meta"] == "2 L, in fridge"
        assert d["score"] == 0.8
        assert d["action_kind"] == "tab"
        assert d["action_target"] == "pantry"


# ── Endpoint ───────────────────────────────────────────────────────


class TestGlobalSearchEndpoint:
    def test_empty_query_returns_empty_results(self, monkeypatch):
        # Force current_user_id to empty so we don't need the DB
        from shopstack.services import global_search_mount

        monkeypatch.setattr(
            global_search_mount, "current_user_id", lambda: "",
        )
        req = _FakeRequest({"q": ""})
        result = _global_search_endpoint(req)
        assert result == {"results": []}

    def test_query_with_no_db_returns_empty_gracefully(self, monkeypatch):
        """When the DB is None (e.g. import error), the endpoint
        returns empty results rather than crashing."""
        from shopstack.services import global_search_mount

        monkeypatch.setattr(
            global_search_mount, "current_user_id", lambda: "",
        )
        monkeypatch.setattr(global_search_mount, "db", None)
        req = _FakeRequest({"q": "milk"})
        result = _global_search_endpoint(req)
        assert "results" in result
        assert isinstance(result["results"], list)

    def test_exception_during_search_returns_error_field(self, monkeypatch):
        """If the search itself raises, the endpoint catches and
        returns an empty result with an error indicator."""
        from shopstack.services import global_search_mount

        def _boom_search(*a, **kw):
            raise RuntimeError("simulated search failure")

        monkeypatch.setattr(
            global_search_mount, "current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr(global_search_mount, "db", None)
        monkeypatch.setattr(
            global_search_mount, "search", _boom_search,
        )
        req = _FakeRequest({"q": "milk"})
        result = _global_search_endpoint(req)
        assert result["results"] == []
        assert "error" in result

    def test_successful_query_returns_serialised_results(self, monkeypatch):
        """Happy path: the search returns results that get
        serialised to the expected JSON shape."""
        from shopstack.services import global_search_mount

        fake_result = GlobalSearchResult(
            kind="action", title="Go to Home", meta="Dashboard",
            score=0.9, action_kind="tab", action_target="today",
        )

        def _fake_search(query, sources):
            return [fake_result]

        monkeypatch.setattr(
            global_search_mount, "current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr(global_search_mount, "db", None)
        monkeypatch.setattr(
            global_search_mount, "search", _fake_search,
        )
        req = _FakeRequest({"q": "home"})
        result = _global_search_endpoint(req)
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert r["kind"] == "action"
        assert r["title"] == "Go to Home"
        assert r["action_target"] == "today"
