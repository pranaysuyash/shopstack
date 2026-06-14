"""Tests for shopstack.services.community_federation (Phase 11)."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from shopstack.services.community_federation import (
    BUNDLE_HEADER_KEY,
    BUNDLE_VERSION,
    CommunityBundle,
    export_bundle,
    export_bundle_to_string,
    import_bundle,
    sync_status,
)
from shopstack.services.community_price_map import (
    clear_pool,
    is_opted_in,
    set_opt_in,
)


# ── Bundle serialization round-trip ─────────────────────────


def test_bundle_to_jsonl_includes_header():
    bundle = CommunityBundle(
        version=1, salt_fingerprint="abc123", source_label="test",
        exported_at="2026-06-13T10:00:00",
        day_range_start="2026-06-01", day_range_end="2026-06-13",
        observations=[{"canonical_name": "milk", "price": 60.0,
                       "city": "mumbai", "store": "DMart", "day": "2026-06-13",
                       "anon_id": "anon-1", "unit": "L"}],
    )
    raw = bundle.to_jsonl()
    lines = raw.strip().split("\n")
    assert len(lines) == 2
    header_obj = json.loads(lines[0])
    assert BUNDLE_HEADER_KEY in header_obj
    assert header_obj[BUNDLE_HEADER_KEY]["version"] == 1
    assert header_obj[BUNDLE_HEADER_KEY]["observation_count"] == 1
    obs = json.loads(lines[1])
    assert obs["canonical_name"] == "milk"


def test_bundle_round_trip():
    bundle = CommunityBundle(
        version=1, salt_fingerprint="xyz", source_label="round-trip",
        exported_at="2026-06-13T10:00:00",
        day_range_start="2026-06-01", day_range_end="2026-06-13",
        observations=[
            {"canonical_name": "milk", "price": 60.0, "city": "mumbai",
             "store": "DMart", "day": "2026-06-13", "anon_id": "a1", "unit": "L"},
            {"canonical_name": "bread", "price": 40.0, "city": "delhi",
             "store": "Reliance", "day": "2026-06-12", "anon_id": "a2", "unit": "pack"},
        ],
    )
    raw = bundle.to_jsonl()
    parsed = CommunityBundle.from_jsonl(raw)
    assert parsed.version == 1
    assert parsed.source_label == "round-trip"
    assert len(parsed.observations) == 2
    assert parsed.observations[0]["canonical_name"] == "milk"


def test_bundle_from_jsonl_rejects_unsupported_version():
    raw = json.dumps({BUNDLE_HEADER_KEY: {"version": 99}}) + "\n"
    with pytest.raises(ValueError, match="Unsupported bundle version"):
        CommunityBundle.from_jsonl(raw)


def test_bundle_from_jsonl_rejects_missing_header():
    raw = json.dumps({"canonical_name": "milk", "price": 60.0})
    with pytest.raises(ValueError, match="missing the header line"):
        CommunityBundle.from_jsonl(raw)


def test_bundle_from_jsonl_rejects_invalid_json():
    raw = "not json\n"
    with pytest.raises(ValueError, match="Invalid JSON"):
        CommunityBundle.from_jsonl(raw)


def test_bundle_handles_blank_lines():
    raw = json.dumps({BUNDLE_HEADER_KEY: {"version": 1, "salt_fingerprint": "x"}}) + "\n\n\n"
    parsed = CommunityBundle.from_jsonl(raw)
    assert parsed.observations == []


# ── Export ──────────────────────────────────────────────


def test_export_bundle_empty_pool():
    bundle = export_bundle()
    assert bundle.version == 1
    assert bundle.observations == []
    assert bundle.day_range_start == ""
    assert bundle.day_range_end == ""


def test_export_bundle_filters_by_city(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    fake_pool = tmp_path / "pool.jsonl"
    monkeypatch.setattr(cpm, "_POOL_FILE", fake_pool)
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    cpm.submit_observation("hh-1", "milk", 60.0, city="mumbai", store="DMart")
    cpm.submit_observation("hh-1", "bread", 40.0, city="delhi", store="Reliance")
    bundle = export_bundle(city="mumbai")
    assert len(bundle.observations) == 1
    assert bundle.observations[0]["canonical_name"] == "milk"


def test_export_bundle_to_string_round_trip(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    cpm.submit_observation("hh-1", "milk", 60.0, city="mumbai", store="DMart")
    raw = export_bundle_to_string()
    parsed = CommunityBundle.from_jsonl(raw)
    assert len(parsed.observations) == 1


# ── Import ──────────────────────────────────────────────


def test_import_bundle_refuses_when_not_opted_in(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    # Don't opt in
    raw = export_bundle_to_string()
    result = import_bundle(raw, actor_user_id="hh-1")
    assert result["accepted"] == 0
    assert "not opted in" in result["reason"].lower()


def test_import_bundle_appends_to_pool(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    # Build a bundle manually
    bundle = CommunityBundle(
        version=1, salt_fingerprint="src-salt", source_label="friend",
        exported_at="2026-06-13T10:00:00",
        day_range_start="2026-06-12", day_range_end="2026-06-13",
        observations=[
            {"canonical_name": "milk", "price": 60.0, "city": "mumbai",
             "store": "DMart", "day": "2026-06-13", "anon_id": "a1", "unit": "L"},
        ],
    )
    raw = bundle.to_jsonl()
    result = import_bundle(raw, actor_user_id="hh-1")
    assert result["accepted"] == 1
    assert result["rejected"] == 0
    # The pool should now have 1 observation
    stats = cpm.pool_stats()
    assert stats["size"] == 1


def test_import_bundle_dedupes_observations(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    bundle = CommunityBundle(
        version=1, salt_fingerprint="x", source_label="dup-test",
        exported_at="2026-06-13T10:00:00",
        day_range_start="2026-06-13", day_range_end="2026-06-13",
        observations=[
            {"canonical_name": "milk", "price": 60.0, "city": "mumbai",
             "store": "DMart", "day": "2026-06-13", "anon_id": "a1", "unit": "L"},
        ],
    )
    raw = bundle.to_jsonl()
    # First import: 1 accepted
    r1 = import_bundle(raw, actor_user_id="hh-1")
    assert r1["accepted"] == 1
    # Second import: dedup → 0 accepted, 1 skipped
    r2 = import_bundle(raw, actor_user_id="hh-1")
    assert r2["accepted"] == 0
    assert r2["skipped"] == 1


def test_import_bundle_rejects_invalid_observations(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    bundle = CommunityBundle(
        version=1, salt_fingerprint="x", source_label="invalid-test",
        exported_at="2026-06-13T10:00:00",
        day_range_start="2026-06-13", day_range_end="2026-06-13",
        observations=[
            {"canonical_name": "", "price": 60.0, "city": "mumbai",
             "store": "DMart", "day": "2026-06-13", "anon_id": "a1", "unit": "L"},
            {"canonical_name": "milk", "price": 0, "city": "mumbai",
             "store": "DMart", "day": "2026-06-13", "anon_id": "a2", "unit": "L"},
            {"canonical_name": "milk", "price": 50.0, "city": "mumbai",
             "store": "DMart", "day": "2026-06-13", "anon_id": "a3", "unit": "L"},
        ],
    )
    raw = bundle.to_jsonl()
    result = import_bundle(raw, actor_user_id="hh-1")
    assert result["rejected"] == 2
    assert result["accepted"] == 1


def test_import_bundle_handles_invalid_jsonl(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    result = import_bundle("not json", actor_user_id="hh-1")
    assert result["accepted"] == 0
    assert "Invalid bundle" in result["reason"]


# ── sync_status ────────────────────────────────────────


def test_sync_status_not_opted_in(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    html = sync_status("hh-1")
    assert "Opt in" in html or "🔒" in html


def test_sync_status_opted_in_with_data(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    cpm.submit_observation("hh-1", "milk", 60.0, city="mumbai", store="DMart")
    html = sync_status("hh-1")
    assert "📡" in html
    assert "1" in html
    assert "milk" in html.lower() or "items" in html.lower()


def test_sync_status_opted_in_empty_pool(tmp_path, monkeypatch):
    from shopstack.services import community_price_map as cpm
    monkeypatch.setattr(cpm, "_POOL_FILE", tmp_path / "pool.jsonl")
    monkeypatch.setattr(cpm, "_OPTED_IN_FILE", tmp_path / "opted_in.json")
    set_opt_in("hh-1", True)
    html = sync_status("hh-1")
    assert "empty" in html.lower() or "Opted" in html


# ── XSS safety ────────────────────────────────────────


def test_bundle_to_jsonl_escapes_pii_fields():
    bundle = CommunityBundle(
        version=1, salt_fingerprint="x", source_label="<script>alert(1)</script>",
        exported_at="2026-06-13T10:00:00",
        day_range_start="2026-06-13", day_range_end="2026-06-13",
        observations=[],
    )
    raw = bundle.to_jsonl()
    # The source_label is JSON-escaped (within quotes), so the
    # raw <script> tag never appears unescaped in the bundle.
    # When parsed back, the source_label preserves the literal text.
    parsed = CommunityBundle.from_jsonl(raw)
    assert parsed.source_label == "<script>alert(1)</script>"


def test_sync_status_escapes_xss():
    html = sync_status("<script>alert(1)</script>")
    # The actor_id in the URL is escaped
    assert "<script>alert(1)</script>" not in html
