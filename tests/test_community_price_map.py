"""Tests for shopstack.services.community_price_map (Phase 6 #15)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from shopstack.services.community_price_map import (
    CommunityObservation,
    _normalize_store_name,
    clear_pool,
    community_delta,
    community_median,
    is_opted_in,
    make_anon_id,
    pool_stats,
    render_community_indicator_html,
    render_opt_in_toggle_html,
    rotate_salt,
    set_opt_in,
    submit_observation,
)


# ── Opt-in / opt-out ─────────────────────────────────────────────


def test_is_opted_in_default_false(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    assert is_opted_in("hh-1") is False


def test_set_opt_in_and_check(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    set_opt_in("hh-1", True)
    assert is_opted_in("hh-1") is True
    set_opt_in("hh-1", False)
    assert is_opted_in("hh-1") is False


def test_set_opt_in_empty_user_noop(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    set_opt_in("", True)  # should not raise
    assert not (fake_dir / "opted_in.json").exists()


# ── Anonymization ─────────────────────────────────────────────────


def test_make_anon_id_is_stable_within_same_day():
    today = date(2026, 6, 13)
    a1 = make_anon_id("hh-1", when=today)
    a2 = make_anon_id("hh-1", when=today)
    assert a1 == a2


def test_make_anon_id_differs_across_days():
    today = date(2026, 6, 13)
    yesterday = today - timedelta(days=1)
    a1 = make_anon_id("hh-1", when=today)
    a2 = make_anon_id("hh-1", when=yesterday)
    assert a1 != a2


def test_make_anon_id_differs_across_users():
    today = date(2026, 6, 13)
    a1 = make_anon_id("hh-1", when=today)
    a2 = make_anon_id("hh-2", when=today)
    assert a1 != a2


def test_make_anon_id_length_16():
    a = make_anon_id("hh-1", when=date(2026, 6, 13))
    assert len(a) == 16
    # Should be hex
    int(a, 16)


def test_make_anon_id_changes_after_salt_rotation(tmp_path, monkeypatch):
    # First generate a salt, capture the anon_id
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    today = date(2026, 6, 13)
    a1 = make_anon_id("hh-1", when=today)
    rotate_salt()
    a2 = make_anon_id("hh-1", when=today)
    assert a1 != a2


def test_make_anon_id_no_user_id_safe():
    # Should not raise
    a = make_anon_id("", when=date(2026, 6, 13))
    assert isinstance(a, str) and len(a) == 16


# ── Store-name normalization ──────────────────────────────────────


def test_normalize_store_name_drops_city_token():
    assert _normalize_store_name("DMart Mumbai", "mumbai") == "DMart"
    assert _normalize_store_name("Reliance Fresh Delhi", "delhi") == "Reliance Fresh"


def test_normalize_store_name_drops_branch_suffix():
    assert _normalize_store_name("Big Bazaar, Bandra", "mumbai") == "Big Bazaar"
    assert _normalize_store_name("DMart - Andheri", "mumbai") == "DMart"


def test_normalize_store_name_handles_empty():
    assert _normalize_store_name("", "mumbai") == "unknown"


def test_normalize_store_name_handles_garbage():
    assert _normalize_store_name(",,,", "mumbai") == "unknown"


# ── Submit observations ──────────────────────────────────────────


def test_submit_observation_refuses_when_not_opted_in(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", fake_dir / "pool.jsonl"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    result = submit_observation("hh-1", "tomato", 80, city="mumbai", store="DMart Mumbai")
    assert result["written"] is False
    assert "Not opted in" in result["reason"]


def test_submit_observation_refuses_zero_price(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", fake_dir / "pool.jsonl"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    set_opt_in("hh-1", True)
    result = submit_observation("hh-1", "tomato", 0)
    assert result["written"] is False


def test_submit_observation_refuses_empty_name(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", fake_dir / "pool.jsonl"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    set_opt_in("hh-1", True)
    result = submit_observation("hh-1", "", 80)
    assert result["written"] is False


def test_submit_observation_writes_when_opted_in(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", fake_dir / "pool.jsonl"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    set_opt_in("hh-1", True)
    result = submit_observation(
        "hh-1", "tomato", 80, city="mumbai", store="DMart Mumbai", unit="kg"
    )
    assert result["written"] is True
    assert result["anon_id"]  # non-empty
    assert (fake_dir / "pool.jsonl").exists()
    content = (fake_dir / "pool.jsonl").read_text(encoding="utf-8")
    assert "tomato" in content
    assert "80" in content
    # Anon_id should be in the line
    assert result["anon_id"] in content
    # No PII: the original user_id should NOT be in the line
    assert "hh-1" not in content


def test_submit_observation_normalizes_store_name(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", fake_dir / "pool.jsonl"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    set_opt_in("hh-1", True)
    submit_observation(
        "hh-1", "tomato", 80, city="mumbai", store="DMart Mumbai, Andheri"
    )
    content = (fake_dir / "pool.jsonl").read_text(encoding="utf-8")
    # City token and branch name should be dropped
    assert "Mumbai" not in content
    assert "Andheri" not in content
    assert "DMart" in content


# ── Read API ──────────────────────────────────────────────────────


def _seed_pool(rows: list[dict], tmp_path, monkeypatch) -> None:
    """Write a JSONL pool file directly for read-side tests."""
    fake_dir = tmp_path / "community"
    pool = fake_dir / "pool.jsonl"
    pool.parent.mkdir(parents=True, exist_ok=True)
    with open(pool, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(__import__("json").dumps(row) + "\n")
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", pool
    )


def test_community_median_no_data_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", tmp_path / "nope.jsonl"
    )
    assert community_median("tomato", city="mumbai") is None


def test_community_median_empty_name_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", tmp_path / "nope.jsonl"
    )
    assert community_median("", city="mumbai") is None


def test_community_median_computes_median(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 80, "city": "mumbai", "store": "DMart",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
        {"canonical_name": "tomato", "price": 100, "city": "mumbai", "store": "Reliance",
         "anon_id": "a2", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
        {"canonical_name": "tomato", "price": 90, "city": "mumbai", "store": "Local",
         "anon_id": "a3", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    summary = community_median("tomato", city="mumbai", when=today)
    assert summary["median_price"] == 90.0
    assert summary["sample_size"] == 3
    assert summary["store_count"] == 3


def test_community_median_filters_by_city(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 80, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
        {"canonical_name": "tomato", "price": 200, "city": "delhi", "store": "Y",
         "anon_id": "a2", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    summary_mumbai = community_median("tomato", city="mumbai", when=today)
    summary_delhi = community_median("tomato", city="delhi", when=today)
    assert summary_mumbai["median_price"] == 80
    assert summary_delhi["median_price"] == 200


def test_community_median_filters_by_window(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    old_day = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    rows = [
        {"canonical_name": "tomato", "price": 80, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
        {"canonical_name": "tomato", "price": 10, "city": "mumbai", "store": "Y",
         "anon_id": "a2", "day": old_day, "unit": "kg"},  # outside window
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    summary = community_median("tomato", city="mumbai", days=30, when=today)
    assert summary["sample_size"] == 1
    assert summary["median_price"] == 80


def test_community_delta_cheaper_verdict(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 100, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    delta = community_delta("tomato", own_price=80, city="mumbai", when=today)
    assert delta["verdict"] == "cheaper"
    assert delta["delta_pct"] < 0


def test_community_delta_pricier_verdict(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 80, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    delta = community_delta("tomato", own_price=120, city="mumbai", when=today)
    assert delta["verdict"] == "pricier"
    assert delta["delta_pct"] > 0


def test_community_delta_fair_verdict(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 100, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    delta = community_delta("tomato", own_price=102, city="mumbai", when=today)
    assert delta["verdict"] == "fair"


def test_community_delta_no_data_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", tmp_path / "nope.jsonl"
    )
    delta = community_delta("tomato", own_price=80, city="mumbai")
    assert delta is None


# ── HTML rendering ───────────────────────────────────────────────


def test_render_community_indicator_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", tmp_path / "nope.jsonl"
    )
    html = render_community_indicator_html("tomato", city="mumbai")
    assert "no community data" in html


def test_render_community_indicator_with_data(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 90, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    html = render_community_indicator_html("tomato", city="mumbai", when=today)
    assert "₹90" in html
    assert "👥" in html


def test_render_community_indicator_with_own_price(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 100, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    html = render_community_indicator_html("tomato", own_price=80, city="mumbai", when=today)
    assert "₹100" in html
    assert "you" in html


def test_render_opt_in_toggle_opted_in(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    set_opt_in("hh-1", True)
    html = render_opt_in_toggle_html("hh-1")
    assert "✅" in html
    assert "anon_id" in html


def test_render_opt_in_toggle_not_opted_in(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._OPTED_IN_FILE", fake_dir / "opted_in.json"
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", fake_dir / "salt"
    )
    html = render_opt_in_toggle_html("hh-1")
    assert "🔒" in html
    assert "not sharing" in html


# ── Pool maintenance ─────────────────────────────────────────────


def test_clear_pool_wipes_file_and_rotates_salt(tmp_path, monkeypatch):
    fake_dir = tmp_path / "community"
    pool = fake_dir / "pool.jsonl"
    salt = fake_dir / "salt"
    pool.parent.mkdir(parents=True, exist_ok=True)
    pool.write_text('{"canonical_name": "x", "price": 1}\n', encoding="utf-8")
    salt.write_text("oldsalt", encoding="utf-8")
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", pool
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._SALT_FILE", salt
    )
    monkeypatch.setattr(
        "shopstack.services.community_price_map._COMMUNITY_DIR", fake_dir
    )
    result = clear_pool()
    assert result["cleared"] is True
    assert not pool.exists()
    assert not salt.exists()


def test_pool_stats_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.community_price_map._POOL_FILE", tmp_path / "nope.jsonl"
    )
    stats = pool_stats()
    assert stats["size"] == 0


def test_pool_stats_with_data(tmp_path, monkeypatch):
    today = date(2026, 6, 13)
    rows = [
        {"canonical_name": "tomato", "price": 80, "city": "mumbai", "store": "X",
         "anon_id": "a1", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
        {"canonical_name": "onion", "price": 50, "city": "mumbai", "store": "Y",
         "anon_id": "a2", "day": today.strftime("%Y-%m-%d"), "unit": "kg"},
    ]
    _seed_pool(rows, tmp_path, monkeypatch)
    stats = pool_stats()
    assert stats["size"] == 2
    assert stats["distinct_items"] == 2
    assert stats["distinct_anon"] == 2
