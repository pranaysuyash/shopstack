"""Tests for shopstack.services.restock_card (Phase 10)."""
from __future__ import annotations

from datetime import datetime

import pytest

from shopstack.services.restock_card import (
    add_restock_to_list,
    render_restock_card_html,
)


# ── HTML rendering ──────────────────────────────────────────────


def test_render_empty_returns_empty_state():
    html = render_restock_card_html([])
    assert "No restock predictions" in html
    assert "restock-empty" in html


def test_render_basic_prediction():
    predictions = [{
        "canonical_name": "milk",
        "urgency": "due_soon",
        "typical_qty": 1.0,
        "typical_unit": "L",
        "days_until_restock": 2,
    }]
    html = render_restock_card_html(predictions)
    assert "restock-card" in html
    assert "Milk" in html
    assert "2d" in html
    assert "1 L" in html


def test_render_sorts_by_days_ascending():
    predictions = [
        {"canonical_name": "a", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 5},
        {"canonical_name": "b", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 1},
        {"canonical_name": "c", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 3},
    ]
    html = render_restock_card_html(predictions)
    # Find the order in which the names appear
    pos_a = html.find(">A<")
    pos_b = html.find(">B<")
    pos_c = html.find(">C<")
    assert 0 < pos_b < pos_c < pos_a


def test_render_color_coding_urgency():
    predictions = [
        {"canonical_name": "critical", "urgency": "critical", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 1},
        {"canonical_name": "soon", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 3},
        {"canonical_name": "later", "urgency": "later", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 7},
    ]
    html = render_restock_card_html(predictions)
    # Red for ≤1d
    assert "A63F31" in html  # red (--red)
    # Amber for 2-3d
    assert "A76012" in html  # amber (--amber)


def test_render_caps_at_8_with_more_summary():
    predictions = [
        {"canonical_name": f"item{i}", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": i + 1}
        for i in range(10)
    ]
    html = render_restock_card_html(predictions)
    # Only 8 should be shown
    assert html.count("restock-row") == 8
    # The "+2 more" footer
    assert "+2 more" in html


def test_render_handles_missing_days():
    predictions = [
        {"canonical_name": "x", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u"},  # no days_until_restock
    ]
    html = render_restock_card_html(predictions)
    assert "—" in html  # dash placeholder
    assert "X" in html


def test_render_handles_none_days():
    predictions = [
        {"canonical_name": "x", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": None},
    ]
    html = render_restock_card_html(predictions)
    assert "—" in html


def test_render_escapes_xss():
    predictions = [{
        "canonical_name": "<script>alert(1)</script>",
        "urgency": "due_soon", "typical_qty": 1.0, "typical_unit": "u",
        "days_until_restock": 1,
    }]
    html = render_restock_card_html(predictions)
    # The name is title-cased; check case-insensitively
    assert "<script>alert" not in html.lower()
    assert "&lt;script&gt;" in html.lower()


def test_render_card_title_and_count():
    predictions = [
        {"canonical_name": "a", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 2},
        {"canonical_name": "b", "urgency": "due_soon", "typical_qty": 1.0,
         "typical_unit": "u", "days_until_restock": 3},
    ]
    html = render_restock_card_html(predictions)
    assert "Restock next 7 days" in html
    assert "2 item(s)" in html
