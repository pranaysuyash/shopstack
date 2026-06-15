"""Regression tests for intelligence cards (2026-06-15).

The intelligence cards are the explainable action surfaces for the
new Today flow. Each card kind (buy_soon, use_soon, skip,
price_drop, price_overpriced, restock, memory, trip) renders with:

* item title
* one-line reason
* optional secondary detail
* confidence label
* primary action button
* optional secondary action

These tests pin the renderer contract.
"""
from __future__ import annotations

from html.parser import HTMLParser

from shopstack.services.intelligence_cards import (
    ConfidenceLabel,
    IntelligenceCard,
    build_buy_soon_card,
    build_memory_card,
    build_price_drop_card,
    build_price_overpriced_card,
    build_restock_card,
    build_skip_card,
    build_trip_card,
    build_use_soon_card,
    render_intelligence_card,
)


class _TagListParser(HTMLParser):
    """Tiny HTML parser that captures every tag name seen."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def _html_tags(html: str) -> list[str]:
    p = _TagListParser()
    p.feed(html)
    return p.tags


class TestConfidenceLabelFromCount:
    def test_zero_is_unscored(self):
        label = ConfidenceLabel.from_count(0)
        assert label.level == "unscored"

    def test_two_is_low(self):
        label = ConfidenceLabel.from_count(2)
        assert label.level == "low"

    def test_five_is_medium(self):
        label = ConfidenceLabel.from_count(5)
        assert label.level == "medium"

    def test_twelve_is_high(self):
        label = ConfidenceLabel.from_count(12)
        assert label.level == "high"

    def test_uses_singular_when_count_is_one(self):
        # The user-facing phrase should respect singular/plural.
        label = ConfidenceLabel.from_count(1)
        assert "1 purchase logged" in label.text


class TestBuildBuySoonCard:
    def test_includes_item_name(self):
        card = build_buy_soon_card(item="Milk", days_until=2, purchase_count=8)
        assert "Milk" in card.subtitle
        assert card.kind == "buy_soon"

    def test_includes_rhythm_in_subtitle(self):
        card = build_buy_soon_card(item="Milk", days_until=2, purchase_count=8)
        # The reason should mention the buying rhythm.
        lower = card.subtitle.lower()
        assert "usually" in lower or "logged" in lower

    def test_overdue_uses_different_subtitle(self):
        card = build_buy_soon_card(item="Bread", days_until=0, purchase_count=5)
        lower = card.subtitle.lower()
        assert "already" in lower or "overdue" in lower

    def test_typical_qty_in_secondary(self):
        card = build_buy_soon_card(
            item="Milk", days_until=2, typical_qty=1.0, unit="L",
        )
        assert "1 L" in card.secondary


class TestBuildUseSoonCard:
    def test_includes_item_and_days(self):
        card = build_use_soon_card(item="Tomato", days_until_expiry=2)
        assert "Tomato" in card.subtitle
        assert "2 days" in card.subtitle
        assert card.kind == "use_soon"

    def test_singular_day(self):
        card = build_use_soon_card(item="Tomato", days_until_expiry=1)
        assert "1 day" in card.subtitle
        # No plural "1 days"
        assert "1 days" not in card.subtitle


class TestBuildSkipCard:
    def test_basic(self):
        card = build_skip_card(item="Rice", reason="You have 5kg at home.")
        assert card.title == "Rice"
        assert card.subtitle == "You have 5kg at home."
        assert card.kind == "skip"


class TestBuildPriceDropCard:
    def test_includes_drop_pct(self):
        card = build_price_drop_card(item="Onion", drop_pct=12.0)
        assert "Onion" in card.subtitle
        assert "-12%" in card.subtitle
        assert card.secondary == "-12%"

    def test_negative_drop_pct_normalised(self):
        # Even if a future caller passes a negative value, the
        # renderer should show the absolute value.
        card = build_price_drop_card(item="Onion", drop_pct=-12.0)
        assert "-12%" in card.subtitle


class TestBuildPriceOverpricedCard:
    def test_includes_observed_and_median(self):
        card = build_price_overpriced_card(
            item="Tomato", observed_price=80, community_median=60, unit="kg",
        )
        assert "Tomato" in card.subtitle
        assert "80" in card.subtitle
        assert "60" in card.subtitle
        assert "kg" in card.subtitle
        # Confidence should be "low" — community signal needs verification.
        assert card.confidence is not None
        assert card.confidence.level == "low"


class TestBuildRestockCard:
    def test_overdue_uses_overdue_copy(self):
        card = build_restock_card(item="Milk", days_until=0)
        assert "overdue" in card.subtitle.lower() or "today" in card.subtitle.lower()

    def test_includes_urgency_in_secondary(self):
        card = build_restock_card(item="Milk", days_until=2, urgency="due_soon")
        assert "due soon" in card.secondary.lower()


class TestBuildMemoryCard:
    def test_basic(self):
        card = build_memory_card(
            title="Milk",
            fact="You buy it every 3 days.",
            supporting_evidence="Logged 12 purchases.",
        )
        assert card.title == "Milk"
        assert "every 3 days" in card.subtitle
        assert "12 purchases" in card.subtitle


class TestBuildTripCard:
    def test_basic(self):
        card = build_trip_card(
            label="Good time to go",
            reason="Clear weather, no use-soon items.",
            secondary="Trip advisor",
        )
        assert card.title == "Good time to go"
        assert "Clear weather" in card.subtitle


class TestRenderIntelligenceCardEscape:
    def test_escapes_html_in_title(self):
        card = IntelligenceCard(
            kind="buy_soon",
            title="<script>alert(1)</script>",
            subtitle="<img src=x onerror=alert(1)>",
        )
        html = render_intelligence_card(card)
        assert "<script>alert(1)</script>" not in html
        assert "<img src=x onerror=alert(1)>" not in html
        # Escaped versions are fine
        assert "&lt;script&gt;" in html
        assert "&lt;img" in html

    def test_rendered_html_has_required_anchors(self):
        card = build_buy_soon_card(item="Milk", days_until=2)
        html = render_intelligence_card(card)
        # Required HTML structure
        assert "intelligence-card" in html
        assert "ic-title" in html
        assert "ic-subtitle" in html
        assert "ic-action" in html
        assert "Add to shopping list" in html

    def test_rendered_html_includes_data_intent(self):
        # The action button's data-intent attribute is how the JS
        # handler knows what to do on click.
        card = build_buy_soon_card(item="Milk", days_until=2)
        html = render_intelligence_card(card)
        # Attribute quoting style matches the renderer's single-quote
        # convention; we just check the substring is present.
        assert "data-intent='add'" in html
        assert "data-item='Milk'" in html
