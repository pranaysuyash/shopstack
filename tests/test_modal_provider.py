"""Tests for shopstack.providers.modal_provider (Phase 6 #18)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from shopstack.providers.modal_provider import (
    ModalEmbeddingsProvider,
    ModalPlannerProvider,
    ModalVisionProvider,
    call_modal,
    get_modal_url,
)

# ── get_modal_url ─────────────────────────────────────────────────


def test_get_modal_url_default_empty():
    assert get_modal_url("NONEXISTENT_VAR_XYZ") == ""


def test_get_modal_url_reads_env(monkeypatch):
    monkeypatch.setenv("TEST_MODAL_URL", "https://test.modal.run")
    assert get_modal_url("TEST_MODAL_URL") == "https://test.modal.run"


def test_get_modal_url_strips_whitespace(monkeypatch):
    monkeypatch.setenv("TEST_MODAL_URL", "  https://test.modal.run  ")
    assert get_modal_url("TEST_MODAL_URL") == "https://test.modal.run"


# ── call_modal with empty URL → stub ─────────────────────────────


def test_call_modal_empty_url_returns_stub():
    out = call_modal("", {"prompt": "plan a trip"}, stub_kind="planner")
    assert "[stub modal planner]" in out["text"]
    assert "tool_calls" in out


def test_call_modal_stub_planner_shape():
    out = call_modal("", {"prompt": "test"}, stub_kind="planner")
    assert "text" in out
    assert "tool_calls" in out
    assert "usage" in out
    assert "total_tokens" in out["usage"]


def test_call_modal_stub_vision_shape():
    out = call_modal("", {"image_path": "/x.png", "prompt": "what is this"}, stub_kind="vision")
    assert "caption" in out
    assert "objects" in out


def test_call_modal_stub_embeddings_shape():
    out = call_modal("", {"text": "hello world"}, stub_kind="embeddings")
    assert "embedding" in out
    assert isinstance(out["embedding"], list)
    assert len(out["embedding"]) == 8


def test_call_modal_stub_embeddings_deterministic():
    a = call_modal("", {"text": "hello world"}, stub_kind="embeddings")
    b = call_modal("", {"text": "hello world"}, stub_kind="embeddings")
    assert a == b  # same input → same output


def test_call_modal_stub_embeddings_differs_by_text():
    a = call_modal("", {"text": "hello world"}, stub_kind="embeddings")
    b = call_modal("", {"text": "goodbye world"}, stub_kind="embeddings")
    assert a != b


# ── call_modal with URL → HTTP POST ─────────────────────────────


def test_call_modal_calls_url_when_set(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout=30.0):
        captured["url"] = url
        captured["payload"] = payload
        return {"text": "from modal", "tool_calls": []}

    monkeypatch.setattr("shopstack.providers.modal_provider._post_json", fake_post_json)
    out = call_modal("https://test.modal.run", {"prompt": "hi"}, stub_kind="planner")
    assert out == {"text": "from modal", "tool_calls": []}
    assert captured["url"] == "https://test.modal.run"
    assert captured["payload"] == {"prompt": "hi"}


def test_call_modal_propagates_http_errors():
    from shopstack.providers.modal_provider import _post_json
    with patch.object(
        _post_json, "__call__",
        side_effect=RuntimeError("Modal HTTP call failed"),
    ), pytest.raises(RuntimeError, match="Modal HTTP call failed"):
        call_modal("https://test.modal.run", {"prompt": "x"}, stub_kind="planner")


# ── ModalPlannerProvider ──────────────────────────────────────────


def test_modal_planner_provider_attributes():
    p = ModalPlannerProvider()
    assert p.name == "modal_planner"
    assert "planner" in p.capabilities
    assert "remote" in p.capabilities
    assert "gpu" in p.capabilities
    assert p.supports_off_grid is False


def test_modal_planner_provider_load_is_noop():
    p = ModalPlannerProvider()
    p.load()  # should not raise
    assert p.healthcheck() is True


def test_modal_planner_empty_url_uses_stub():
    p = ModalPlannerProvider(url="")
    out = p.plan("plan a trip")
    assert "[stub modal planner]" in out["text"]


def test_modal_planner_with_url_calls_remote(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout=30.0):
        captured["url"] = url
        return {"text": "remote response", "tool_calls": [], "usage": {}}

    monkeypatch.setattr("shopstack.providers.modal_provider._post_json", fake_post_json)
    p = ModalPlannerProvider(url="https://test.modal.run")
    out = p.plan("plan a trip", system="be helpful")
    assert out["text"] == "remote response"
    assert captured["url"] == "https://test.modal.run"


def test_modal_planner_passes_kwargs(monkeypatch):
    captured = {}

    def fake_post_json(url, payload, timeout=30.0):
        captured["payload"] = payload
        return {"text": "ok", "tool_calls": []}

    monkeypatch.setattr("shopstack.providers.modal_provider._post_json", fake_post_json)
    p = ModalPlannerProvider(url="https://test.modal.run", model="my-model")
    p.plan("hi", temperature=0.5, max_tokens=200)
    assert captured["payload"]["model"] == "my-model"
    assert captured["payload"]["kwargs"]["temperature"] == 0.5
    assert captured["payload"]["kwargs"]["max_tokens"] == 200


# ── ModalVisionProvider ───────────────────────────────────────────


def test_modal_vision_provider_attributes():
    p = ModalVisionProvider()
    assert p.name == "modal_vision"
    assert "vision" in p.capabilities
    assert p.supports_off_grid is False


def test_modal_vision_caption_stub():
    p = ModalVisionProvider(url="")
    out = p.caption("/tmp/photo.jpg", "what is this?")
    assert "[stub modal vision]" in out["caption"]


def test_modal_vision_caption_with_url(monkeypatch):
    captured = {}
    def fake_post_json(url, payload, timeout=30.0):
        captured["payload"] = payload
        return {"caption": "remote", "objects": [{"label": "x", "score": 0.9}]}

    monkeypatch.setattr("shopstack.providers.modal_provider._post_json", fake_post_json)
    p = ModalVisionProvider(url="https://test.modal.run")
    out = p.caption("/tmp/photo.jpg", "what is this?")
    assert out["caption"] == "remote"
    assert captured["payload"]["image_path"] == "/tmp/photo.jpg"
    assert captured["payload"]["prompt"] == "what is this?"


# ── ModalEmbeddingsProvider ──────────────────────────────────────


def test_modal_embeddings_provider_attributes():
    p = ModalEmbeddingsProvider()
    assert p.name == "modal_embeddings"
    assert "embeddings" in p.capabilities


def test_modal_embeddings_stub():
    p = ModalEmbeddingsProvider(url="")
    out = p.embed(["hello", "world"])
    assert len(out) == 2
    assert all(len(emb) == 8 for emb in out)


def test_modal_embeddings_stub_deterministic():
    p = ModalEmbeddingsProvider(url="")
    a = p.embed(["hello"])
    b = p.embed(["hello"])
    assert a == b


def test_modal_embeddings_with_url(monkeypatch):
    captured = []
    def fake_post_json(url, payload, timeout=30.0):
        captured.append(payload)
        return {"embeddings": [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]], "count": 2}

    monkeypatch.setattr("shopstack.providers.modal_provider._post_json", fake_post_json)
    p = ModalEmbeddingsProvider(url="https://test.modal.run")
    out = p.embed(["hello", "world"])
    assert len(out) == 2
    assert out[0] == [0.1, 0.2, 0.3, 0.4]
    assert len(captured) == 1  # single batch POST


def test_modal_embeddings_handles_missing_embeddings_field(monkeypatch):
    def fake_post_json(url, payload, timeout=30.0):
        return {"unexpected_field": "x"}  # no "embeddings"

    monkeypatch.setattr("shopstack.providers.modal_provider._post_json", fake_post_json)
    p = ModalEmbeddingsProvider(url="https://test.modal.run")
    out = p.embed(["hello"])
    assert out == []  # empty, no crash


# ─- Registry integration ────────────────────────────────────────


def test_modal_provider_loadable_via_registry():
    """The Modal provider should be importable via the registry's lazy loader."""
    from shopstack.providers.registry import _load_modal
    cls = _load_modal()
    assert cls is not None
    assert cls is ModalPlannerProvider
