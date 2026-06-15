"""Tests for ``last_updated`` rollout onto the home dashboard's
intelligence cards (Item #41, Pass 17).

motto_v3 §0.10 + §0.14: every user-visible data surface
should tell the user when it was last updated. The
``build_use_soon_card`` and ``build_restock_card`` builders
now accept ``last_updated`` and the renderer emits a
relative-time stamp.

The pattern matches the Pass 15 price-memory / market-teaser
rollout: an XSS-safe ``last_updated_stamp(...)`` call is
inserted at the top of the rendered card, and the regression
test locks the contract in by asserting the stamp is present
when ``last_updated`` is provided and absent when it isn't
(preserves the no-stamp shape for callers that don't pass it).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

# Set test env BEFORE any shopstack import.
os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")
os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")
os.environ.setdefault("SHOPSTACK_OFF_THE_GRID", "true")

import pytest

from shopstack.services.intelligence_cards import (
    build_buy_soon_card,
    build_restock_card,
    build_use_soon_card,
    render_intelligence_card,
)


# ── Per-builder contract ──────────────────────────────────────────


class TestUseSoonCardStamp:
    def test_renders_stamp_when_last_updated_set(self):
        card = build_use_soon_card(
            item="milk", days_until_expiry=2,
            last_updated=datetime.now(timezone.utc),
        )
        html = render_intelligence_card(card)
        assert "Last updated" in html
        assert "<time datetime=" in html

    def test_no_stamp_when_last_updated_omitted(self):
        card = build_use_soon_card(item="eggs", days_until_expiry=1)
        html = render_intelligence_card(card)
        # No stamp = no "Last updated" string, no <time> element.
        assert "Last updated" not in html
        assert "<time datetime" not in html

    def test_stamp_uses_relative_time(self):
        """A fresh stamp renders as "just now"; the user
        sees a clear signal that the data is current.
        """
        card = build_use_soon_card(
            item="milk", days_until_expiry=2,
            last_updated=datetime.now(timezone.utc),
        )
        html = render_intelligence_card(card)
        assert "just now" in html


class TestRestockCardStamp:
    def test_renders_stamp_when_last_updated_set(self):
        card = build_restock_card(
            item="bread", days_until=3,
            last_updated=datetime.now(timezone.utc),
        )
        html = render_intelligence_card(card)
        assert "Last updated" in html
        assert "<time datetime=" in html

    def test_no_stamp_when_last_updated_omitted(self):
        card = build_restock_card(item="salt", days_until=5)
        html = render_intelligence_card(card)
        assert "Last updated" not in html


# ── Card builder signature: no breaking changes for existing callers ──


class TestBackwardCompatibility:
    """Existing callers (e.g. home_flow_render.py before Pass
    17) might not pass ``last_updated``. The builders must
    still construct cards without raising TypeError. The
    rendered HTML must keep the pre-stamp shape (no "Last
    updated" string) so cards that don't opt in don't get a
    surprise stamp they didn't ask for.
    """

    @pytest.mark.parametrize(
        "builder",
        [
            lambda: build_buy_soon_card(item="milk", days_until=2),
            lambda: build_use_soon_card(item="eggs", days_until_expiry=1),
            lambda: build_restock_card(item="bread", days_until=3),
        ],
    )
    def test_builder_works_without_last_updated(self, builder):
        card = builder()
        html = render_intelligence_card(card)
        assert "Last updated" not in html

    @pytest.mark.parametrize(
        "builder",
        [
            lambda: build_buy_soon_card(item="milk", days_until=2,
                                        last_updated=datetime.now(timezone.utc)),
            lambda: build_use_soon_card(item="eggs", days_until_expiry=1,
                                       last_updated=datetime.now(timezone.utc)),
            lambda: build_restock_card(item="bread", days_until=3,
                                      last_updated=datetime.now(timezone.utc)),
        ],
    )
    def test_builder_works_with_last_updated(self, builder):
        card = builder()
        html = render_intelligence_card(card)
        assert "Last updated" in html
        assert "<time datetime=" in html
