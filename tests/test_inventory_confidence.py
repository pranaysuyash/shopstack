"""Tests for inventory confidence drift model.

The review (§4.1) identifies confidence as essential:
  - Manual user entry → high confidence
  - Receipt extraction → high/medium
  - Image/fridge scan → medium/low
  - Old inferred inventory → low
  - Planned but unconfirmed cart → not inventory

Tests cover:
  - inventory_confidence() with shelf life (decay curve)
  - inventory_confidence() without shelf life (generic decay)
  - needs_confirmation() threshold
  - confirmation_prompt() generation
  - Edge cases: future dates, no dates, very old items
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest


# ── inventory_confidence tests ──────────────────────────────────────────────


class TestInventoryConfidence:
    def test_just_purchased(self):
        """Item purchased today should have near-max confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        assert inventory_confidence(
            purchase_date=today, shelf_life_days=7, today=today,
        ) > 0.9

    def test_within_shelf_life(self):
        """Item at 20% of shelf life should have high confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        # 1 day out of 7-day shelf life = ~14%
        assert inventory_confidence(
            purchase_date=date(2026, 6, 8), shelf_life_days=7, today=today,
        ) > 0.9

    def test_near_half_shelf_life(self):
        """Item at ~43% of shelf life should have 0.85 confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        # 3 days out of 7-day shelf life = 43%, within 0.5 fraction
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 6), shelf_life_days=7, today=today,
        )
        assert conf == 0.85

    def test_past_half_shelf_life(self):
        """Item at 57% of shelf life should have 0.65 confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        # 4 days out of 7-day shelf life = 57%, within 0.8 fraction
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 5), shelf_life_days=7, today=today,
        )
        assert conf == 0.65

    def test_near_expiry(self):
        """Item at 80% of shelf life should have reduced confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        # 6 days out of 7-day shelf life = 86%
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 3), shelf_life_days=7, today=today,
        )
        assert conf < 0.8

    def test_past_shelf_life_recent(self):
        """Item just past shelf life should have low confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 20)
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 7), shelf_life_days=7, today=today,
        )
        assert conf < 0.4
        assert conf >= 0.2

    def test_very_old_no_shelf_life(self):
        """Item purchased 60 days ago with no shelf life info should have very low confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        conf = inventory_confidence(
            purchase_date=date(2026, 4, 1), today=today,
        )
        assert conf < 0.2

    def test_no_dates(self):
        """No purchase or confirmation date should return low confidence."""
        from shopstack.services.freshness import inventory_confidence
        assert inventory_confidence(purchase_date=None, last_confirmed=None) < 0.4

    def test_last_confirmed_updates_confidence(self):
        """Last confirmed date should be used if more recent than purchase."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        # Purchased long ago but confirmed yesterday
        conf = inventory_confidence(
            purchase_date=date(2026, 5, 1),
            last_confirmed=date(2026, 6, 8),
            shelf_life_days=7,
            today=today,
        )
        # Should use last_confirmed (1 day ago) not purchase_date (39 days ago)
        assert conf > 0.5

    def test_future_date_returns_max(self):
        """Future purchase dates should return 1.0 confidence (trust)."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 20), today=today,
        )
        assert conf == 1.0

    def test_recent_no_shelf_life(self):
        """Item purchased yesterday without shelf life should have high confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 8), today=today,
        )
        assert conf > 0.9

    def test_week_old_no_shelf_life(self):
        """Item purchased 7 days ago without shelf life should have medium confidence."""
        from shopstack.services.freshness import inventory_confidence
        today = date(2026, 6, 9)
        conf = inventory_confidence(
            purchase_date=date(2026, 6, 2), today=today,
        )
        assert 0.5 < conf < 0.85


# ── needs_confirmation tests ────────────────────────────────────────────────


class TestNeedsConfirmation:
    def test_below_threshold(self):
        from shopstack.services.freshness import needs_confirmation
        assert needs_confirmation(0.3, threshold=0.4) is True

    def test_above_threshold(self):
        from shopstack.services.freshness import needs_confirmation
        assert needs_confirmation(0.85, threshold=0.4) is False

    def test_default_threshold(self):
        from shopstack.services.freshness import needs_confirmation
        assert needs_confirmation(0.3) is True
        assert needs_confirmation(0.5) is False

    def test_edge_case_at_threshold(self):
        from shopstack.services.freshness import needs_confirmation
        assert needs_confirmation(0.4, threshold=0.4) is False  # not strictly below


# ── confirmation_prompt tests ──────────────────────────────────────────────


class TestConfirmationPrompt:
    def test_high_confidence_returns_empty(self):
        from shopstack.services.freshness import confirmation_prompt
        prompt = confirmation_prompt(
            canonical_name="onion",
            display_name="Onion",
            confidence=0.85,
            purchase_date=date(2026, 6, 8),
            quantity=2.0,
            unit="kg",
        )
        assert prompt == ""

    def test_no_purchase_date(self):
        from shopstack.services.freshness import confirmation_prompt
        prompt = confirmation_prompt(
            canonical_name="coriander",
            display_name="Coriander",
            confidence=0.2,
            quantity=1.0,
            unit="bunch",
        )
        assert "Do you still have" in prompt
        assert "Coriander" in prompt
        assert "purchase date" in prompt.lower()

    def test_very_low_confidence(self):
        from shopstack.services.freshness import confirmation_prompt
        prompt = confirmation_prompt(
            canonical_name="broccoli",
            display_name="Broccoli",
            confidence=0.15,
            purchase_date=date(2026, 5, 1),
            quantity=1.0,
            unit="piece",
        )
        assert "used or discarded" in prompt.lower() or "still have" in prompt.lower()
        assert "Broccoli" in prompt

    def test_purchased_today_no_prompt(self):
        """Item purchased today should not need confirmation."""
        from shopstack.services.freshness import confirmation_prompt
        prompt = confirmation_prompt(
            canonical_name="onion",
            display_name="Onion",
            confidence=0.3,
            purchase_date=date.today(),
            quantity=2.0,
            unit="kg",
        )
        assert prompt == ""

    def test_confidence_just_below_threshold(self):
        """Items at 0.35 confidence with moderate age should get a confirmation prompt."""
        from shopstack.services.freshness import confirmation_prompt
        purchase_date = date.today() - timedelta(days=10)
        prompt = confirmation_prompt(
            canonical_name="potato",
            display_name="Potato",
            confidence=0.3,
            purchase_date=purchase_date,
            quantity=5.0,
            unit="kg",
        )
        assert "Do you still have" in prompt or "Has" in prompt
