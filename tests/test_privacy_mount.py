"""Tests for `shopstack.services.privacy_mount` — the privacy HTTP endpoints.

Verifies:
  * The purge endpoint requires confirm=true (returns success=False
    when missing — a safety net beyond the JS confirm() dialog).
  * The purge endpoint requires a user_id (returns success=False
    when missing).
  * The retention summary endpoint returns the canonical policy.
  * A purge failure (e.g. DB error) does not crash the endpoint;
    it returns success=False with an error message.
  * The mount function is best-effort (does not raise).
"""
from __future__ import annotations

import pytest

from shopstack.services.privacy_mount import (
    _purge_endpoint,
    _retention_endpoint,
    mount_privacy_endpoints,
)


class _FakeRequest:
    def __init__(self, params: dict[str, str]) -> None:
        self.query_params = params


# ── Purge endpoint ────────────────────────────────────────────────


class TestPurgeEndpoint:
    def test_missing_confirm_returns_failure(self, monkeypatch):
        from shopstack.services import privacy_mount

        monkeypatch.setattr(
            privacy_mount, "current_user_id", lambda: "hh1",
        )
        req = _FakeRequest({})
        result = _purge_endpoint(req)
        assert result["success"] is False
        assert "confirm" in result["error"].lower()

    def test_missing_user_id_returns_failure(self, monkeypatch):
        from shopstack.services import privacy_mount

        monkeypatch.setattr(
            privacy_mount, "current_user_id", lambda: "",
        )
        req = _FakeRequest({"confirm": "true"})
        result = _purge_endpoint(req)
        assert result["success"] is False
        assert "household" in result["error"].lower()

    def test_successful_purge_returns_result(self, monkeypatch):
        from shopstack.services import privacy_mount
        from shopstack.services.data_retention import PurgeResult

        monkeypatch.setattr(
            privacy_mount, "current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr(
            privacy_mount, "purge_user_data",
            lambda db, user_id, confirm: PurgeResult(
                traces_purged=5, success=True,
            ),
        )
        req = _FakeRequest({"confirm": "true"})
        result = _purge_endpoint(req)
        assert result["success"] is True
        assert result["result"]["traces_purged"] == 5

    def test_confirm_via_1_or_yes_works(self, monkeypatch):
        from shopstack.services import privacy_mount
        from shopstack.services.data_retention import PurgeResult

        monkeypatch.setattr(
            privacy_mount, "current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr(
            privacy_mount, "purge_user_data",
            lambda db, user_id, confirm: PurgeResult(success=True),
        )
        for variant in ("1", "yes", "TRUE", "True"):
            req = _FakeRequest({"confirm": variant})
            result = _purge_endpoint(req)
            assert result["success"] is True, f"failed for confirm={variant!r}"

    def test_db_exception_returns_failure(self, monkeypatch):
        from shopstack.services import privacy_mount

        monkeypatch.setattr(
            privacy_mount, "current_user_id", lambda: "hh1",
        )

        def _boom_purge(*a, **kw):
            raise RuntimeError("simulated db failure")

        monkeypatch.setattr(
            privacy_mount, "purge_user_data", _boom_purge,
        )
        req = _FakeRequest({"confirm": "true"})
        result = _purge_endpoint(req)
        assert result["success"] is False
        assert "error" in result


# ── Retention summary endpoint ───────────────────────────────────


class TestRetentionEndpoint:
    def test_returns_policy(self, monkeypatch):
        from shopstack.services import privacy_mount
        from shopstack.services.data_retention import RetentionPolicy

        monkeypatch.setattr(
            privacy_mount, "current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr(
            privacy_mount, "retention_summary",
            lambda db, user_id: RetentionPolicy(trace_ttl_days=7),
        )
        req = _FakeRequest({})
        result = _retention_endpoint(req)
        assert result["summary"]["trace_ttl_days"] == 7

    def test_exception_returns_empty_summary(self, monkeypatch):
        from shopstack.services import privacy_mount

        monkeypatch.setattr(
            privacy_mount, "current_user_id", lambda: "hh1",
        )

        def _boom_summary(*a, **kw):
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(
            privacy_mount, "retention_summary", _boom_summary,
        )
        req = _FakeRequest({})
        result = _retention_endpoint(req)
        assert result["summary"] == {}
        assert "error" in result


# ── Mount is best-effort ─────────────────────────────────────────


class TestMountPrivacyEndpoints:
    def test_mount_handles_no_app(self):
        """mount_privacy_endpoints does not raise when the app
        has no `app.app` attribute (Gradio not yet started)."""
        class _BadApp:
            pass
        # Should not raise
        mount_privacy_endpoints(_BadApp())  # type: ignore
