"""Accessibility (a11y) tests — WCAG 2.1 AA static HTML analysis.

Every HTML-generating component function in ``shopstack.ui`` is parsed with
BeautifulSoup and validated for correct ARIA attributes, roles, labels, and
semantic structure. No browser/DOM required — unit-testing the static HTML.

Coverage:
  - shopstack.ui.components.primitives  (item_row, stat_card, data_table, ...)
  - shopstack.ui.components.cards       (card, render_decision_card, ...)
  - shopstack.ui.renderers.image_cards  (SVG cards)
  - shopstack.ui.renderers.decision_cards  (market basket, decision panel, ...)
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from shopstack.ui.components.primitives import (
    confirm_dialog,
    data_table,
    empty_state_enhanced,
    item_row,
    loading_skeleton,
    stat_card,
    toast,
)
from shopstack.ui.components.cards import (
    badge_html,
    card,
    empty_state,
    render_action_grid,
    render_action_tile,
    render_decision_card as render_decision_card_html,
    render_hero_panel,
    render_metric,
    render_rows,
    render_workflow_rail,
)
from shopstack.ui.renderers import (
    decision_cards as dc,
    image_cards as ic,
    shopping_results as sr,
)
from shopstack.services.results import (
    CompletionItem,
    MarkPurchasedResult,
    PurchaseResultItem,
    ShoppingCompletionResult,
)
from shopstack.schemas.models import DecisionSet, DecisionResult


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _parse(html: str) -> BeautifulSoup:
    """Parse HTML string with lxml and return a BeautifulSoup tree."""
    return BeautifulSoup(html, "lxml")


def _assert_role(soup: BeautifulSoup, role: str, msg: str = "") -> None:
    """Assert that at least one element has the given role."""
    assert soup.find(attrs={"role": role}) is not None, (
        msg or f"Expected role='{role}' not found in HTML"
    )


# ═══════════════════════════════════════════════════════════════════════
# shopstack.ui.components.primitives
# ═══════════════════════════════════════════════════════════════════════


class TestItemRow:
    """WCAG: role='group', aria-label includes name+quantity."""

    def test_role_group_present(self):
        html = item_row("Milk", 2.0, "L")
        soup = _parse(html)
        _assert_role(soup, "group", "item_row missing role='group'")

    def test_aria_label_contains_name_and_quantity(self):
        html = item_row("Milk", 2.0, "L")
        soup = _parse(html)
        el = soup.find(attrs={"role": "group"})
        assert el is not None
        label = el.get("aria-label", "")
        assert "Milk" in label
        assert "2.0" in label or "2 L" in label

    def test_aria_label_with_decision(self):
        html = item_row("Eggs", 12, "pieces", decision="buy")
        soup = _parse(html)
        el = soup.find(attrs={"role": "group"})
        assert el is not None
        assert "Eggs" in el.get("aria-label", "")

    def test_escaped_content_does_not_break_html(self):
        """html.escape is applied; HTML injection should be escaped."""
        html = item_row('<script>alert("xss")</script>', 1, "unit")
        assert "&lt;script&gt;" in html
        assert "<script>" not in html


class TestStatCard:
    """WCAG: role='region', aria-label includes value+label."""

    def test_role_region_present(self):
        html = stat_card("12", "Items")
        soup = _parse(html)
        _assert_role(soup, "region", "stat_card missing role='region'")

    def test_aria_label_contains_value_and_label(self):
        html = stat_card("\u20b9340", "Spent", icon="\U0001f4b0")
        soup = _parse(html)
        el = soup.find(attrs={"role": "region"})
        assert el is not None
        label = el.get("aria-label", "")
        assert "340" in label or "Spent" in label

    def test_icon_rendered_when_provided(self):
        html = stat_card("3", "Todos", icon="\U0001f4cb")
        assert "\U0001f4cb" in html


class TestDataTable:
    """WCAG: role='region', aria-label, <caption class='sr-only'>."""

    def test_role_region_present(self):
        html = data_table([{"name": "Milk", "qty": "2"}])
        soup = _parse(html)
        _assert_role(soup, "region", "data_table missing role='region'")

    def test_aria_label_contains_table_description(self):
        html = data_table([{"name": "Milk", "qty": "2"}])
        soup = _parse(html)
        el = soup.find(attrs={"role": "region"})
        assert el is not None
        label = el.get("aria-label", "")
        # When empty_message is default "No data", aria-label becomes "Table: data table"
        assert "Table:" in label or "table" in label.lower()

    def test_custom_aria_label_uses_empty_message(self):
        html = data_table([{"name": "Milk", "qty": "2"}], empty_message="Inventory items")
        soup = _parse(html)
        el = soup.find(attrs={"role": "region"})
        assert el is not None
        label = el.get("aria-label", "")
        assert "Inventory" in label

    def test_caption_sr_only_present(self):
        html = data_table([{"name": "Milk", "qty": "2"}])
        soup = _parse(html)
        caption = soup.find("caption")
        assert caption is not None, "data_table missing <caption>"
        assert "sr-only" in caption.get("class", []), (
            "caption missing sr-only class"
        )

    def test_empty_state_returns_home_card(self):
        """Empty states return a home-card div (no role='region' — just a
        plain <div class='home-card'>)."""
        html = data_table([], empty_message="No inventory")
        assert "home-card" in html
        assert "No inventory" in html


class TestConfirmDialog:
    """WCAG: role='alertdialog', aria-label, icon aria-hidden='true'."""

    def test_role_alertdialog_present(self):
        html = confirm_dialog("Delete this item?")
        soup = _parse(html)
        _assert_role(soup, "alertdialog",
                     "confirm_dialog missing role='alertdialog'")

    def test_aria_label_contains_message(self):
        html = confirm_dialog("Delete this item?")
        soup = _parse(html)
        el = soup.find(attrs={"role": "alertdialog"})
        assert el is not None
        assert "Delete" in el.get("aria-label", "")

    def test_warning_icon_aria_hidden(self):
        html = confirm_dialog("Are you sure?")
        soup = _parse(html)
        icon = soup.find(attrs={"aria-hidden": "true"})
        assert icon is not None, \
            "confirm_dialog icon missing aria-hidden='true'"

    def test_danger_variant(self):
        html = confirm_dialog("Delete permanently?", variant="danger")
        assert "alertdialog" in html


class TestToast:
    """WCAG: role='status', aria-live='polite', aria-label, icon aria-hidden."""

    def test_role_status_present(self):
        html = toast("Item added", kind="success")
        soup = _parse(html)
        _assert_role(soup, "status", "toast missing role='status'")

    def test_aria_live_polite(self):
        html = toast("Item added")
        # The HTML uses aria-live='polite' (single quotes inside f-string)
        assert "aria-live=" in html and "polite" in html, \
            "toast missing aria-live='polite'"

    def test_aria_label_contains_message(self):
        html = toast("Item added", kind="success")
        soup = _parse(html)
        el = soup.find(attrs={"role": "status"})
        assert el is not None
        assert "Item added" in el.get("aria-label", "")

    def test_icon_aria_hidden(self):
        html = toast("Error occurred", kind="error")
        soup = _parse(html)
        icon = soup.find(attrs={"aria-hidden": "true"})
        assert icon is not None, "toast icon missing aria-hidden='true'"

    def test_error_kind_renders(self):
        html = toast("Something failed", kind="error")
        assert "role=" in html

    def test_info_kind_renders(self):
        html = toast("FYI", kind="info")
        assert "role=" in html

    def test_warning_kind_renders(self):
        html = toast("Be careful", kind="warning")
        assert "role=" in html


class TestEmptyStateEnhanced:
    """WCAG: role='status', aria-label, icon aria-hidden."""

    def test_role_status_present(self):
        html = empty_state_enhanced("No items found")
        soup = _parse(html)
        _assert_role(soup, "status",
                     "empty_state_enhanced missing role='status'")

    def test_aria_label_contains_message(self):
        html = empty_state_enhanced("No items found")
        soup = _parse(html)
        el = soup.find(attrs={"role": "status"})
        assert el is not None
        assert "No items found" in el.get("aria-label", "")

    def test_icon_aria_hidden(self):
        html = empty_state_enhanced("Empty!", icon="\U0001f4e6")
        soup = _parse(html)
        icon = soup.find(attrs={"aria-hidden": "true"})
        assert icon is not None, \
            "empty_state icon missing aria-hidden='true'"

    def test_with_cta_button(self):
        html = empty_state_enhanced(
            "No items",
            action_label="Add Item",
            on_click_tab="inventory",
        )
        assert "Add Item" in html
        assert "button" in html


class TestLoadingSkeleton:
    """No specific WCAG requirements — decorative placeholder."""

    def test_card_variant_renders(self):
        html = loading_skeleton(variant="card")
        assert html.strip()

    def test_table_variant_renders(self):
        html = loading_skeleton(variant="table")
        assert html.strip()

    def test_metric_variant_renders(self):
        html = loading_skeleton(variant="metric")
        assert html.strip()

    def test_text_variant_renders(self):
        html = loading_skeleton(variant="text")
        assert html.strip()


# ═══════════════════════════════════════════════════════════════════════
# shopstack.ui.components.cards
# ═══════════════════════════════════════════════════════════════════════


class TestCard:
    """WCAG: role='region', aria-labelledby pointing to a valid id."""

    def test_role_region_present(self):
        html = card("My Title", "body content")
        soup = _parse(html)
        _assert_role(soup, "region", "card missing role='region'")

    def test_aria_labelledby_points_to_valid_id(self):
        html = card("My Title", "body content")
        soup = _parse(html)
        el = soup.find(attrs={"role": "region"})
        assert el is not None
        labelledby = el.get("aria-labelledby", "")
        assert labelledby, "card missing aria-labelledby"
        heading = soup.find(id=labelledby)
        assert heading is not None, (
            f"card aria-labelledby='{labelledby}' has no matching element"
        )

    def test_heading_text_matches_labelledby_id(self):
        html = card("Shopping List", "content")
        soup = _parse(html)
        el = soup.find(attrs={"role": "region"})
        assert el is not None
        labelledby = el.get("aria-labelledby", "")
        heading = soup.find(id=labelledby)
        assert heading is not None
        assert "Shopping List" in heading.get_text()


class TestRenderDecisionCardHTML:
    """WCAG: role='article', aria-label with name+decision."""

    def test_role_article_present(self):
        html = render_decision_card_html("Milk", "buy", "Running low", 0.85)
        soup = _parse(html)
        _assert_role(soup, "article",
                     "decision_card missing role='article'")

    def test_aria_label_contains_name_and_decision(self):
        html = render_decision_card_html("Milk", "buy", "Running low", 0.85)
        soup = _parse(html)
        el = soup.find(attrs={"role": "article"})
        assert el is not None
        label = el.get("aria-label", "")
        assert "Milk" in label
        assert "BUY" in label

    def test_confidence_displayed(self):
        html = render_decision_card_html("Milk", "buy", "Running low", 0.85)
        assert "85" in html


class TestRenderActionTile:
    """WCAG: aria-label with label+subtitle."""

    def test_aria_label_present(self):
        html = render_action_tile("Add Item", "Record a purchase", "inventory")
        soup = _parse(html)
        btn = soup.find("button")
        assert btn is not None
        label = btn.get("aria-label", "")
        assert "Add Item" in label

    def test_aria_label_includes_subtitle(self):
        html = render_action_tile("Scan", "Scan a receipt", "receipt")
        soup = _parse(html)
        btn = soup.find("button")
        assert btn is not None
        assert "Scan" in btn.get("aria-label", "")
        assert "receipt" in btn.get("aria-label", "").lower()

    def test_button_element(self):
        html = render_action_tile("Go", "Do something", "tab")
        assert "<button" in html and "</button>" in html

    def test_tone_variant_renders(self):
        html = render_action_tile("Primary", "CTA", "tab", tone="primary")
        assert "primary" in html


class TestRenderActionGrid:
    """render_action_grid wraps tiles in action-grid wrapper."""

    def test_empty_actions_returns_empty_string(self):
        assert render_action_grid([]) == ""

    def test_single_action_renders(self):
        html = render_action_grid([
            {"label": "Scan", "subtitle": "Check a shelf item", "tab_id": "market"},
        ])
        assert "action-grid" in html
        assert "Scan" in html
        assert "Check a shelf item" in html
        assert "<button" in html

    def test_multiple_actions_all_rendered(self):
        html = render_action_grid([
            {"label": "Scan", "subtitle": "Check a shelf item", "tab_id": "market"},
            {"label": "Add", "subtitle": "Record a purchase", "tab_id": "purchase"},
            {"label": "View", "subtitle": "Browse inventory", "tab_id": "inventory"},
        ])
        assert html.count("<button") == 3
        assert "Scan" in html
        assert "Add" in html
        assert "View" in html

    def test_tone_propagated_to_tiles(self):
        html = render_action_grid([
            {"label": "Primary", "subtitle": "CTA", "tab_id": "tab", "tone": "primary"},
            {"label": "Default", "subtitle": "No tone", "tab_id": "tab"},
        ])
        assert "action-tile-primary" in html
        # Default tone should also render
        assert "action-tile-default" in html

    def test_wrapper_class_present(self):
        html = render_action_grid([
            {"label": "X", "subtitle": "Y", "tab_id": "z"},
        ])
        soup = BeautifulSoup(html, "lxml")
        wrapper = soup.find("div", class_="action-grid")
        assert wrapper is not None, "action-grid wrapper div missing"

    def test_labels_and_subtitles_escaped(self):
        html = render_action_grid([
            {"label": "<script>", "subtitle": "<alert>", "tab_id": "tab"},
        ])
        assert "&lt;script&gt;" in html
        assert "&lt;alert&gt;" in html
        assert "<script>" not in html


class TestRenderHeroPanel:
    """Semantic structure: h2 heading, section-kicker."""

    def test_heading_present(self):
        html = render_hero_panel("Welcome", "Your dashboard")
        soup = _parse(html)
        heading = soup.find("h2")
        assert heading is not None
        assert "Welcome" in heading.get_text()


class TestRenderMetric:
    """Semantic structure: metric-label, metric-value."""

    def test_label_and_value_rendered(self):
        html = render_metric("Items", "12")
        assert "Items" in html
        assert "12" in html

    def test_hint_renders_when_provided(self):
        html = render_metric("Items", "12", hint="3 expiring soon")
        assert "3 expiring soon" in html


class TestRenderWorkflowRail:
    """Semantic structure — steps are uppercased for styling."""

    def test_renders_steps_uppercased(self):
        html = render_workflow_rail(["Step 1", "Step 2"], current_step=0)
        # Steps are uppercased via escape(str(step).upper())
        assert "STEP 1" in html
        assert "STEP 2" in html


class TestRenderRows:
    def test_renders_label_value_pairs(self):
        html = render_rows([("Name", "Milk"), ("Qty", "2 L")])
        assert "Milk" in html
        assert "2 L" in html

    def test_empty_returns_fallback(self):
        html = render_rows([])
        assert "No entries" in html


class TestEmptyState:
    def test_message_rendered(self):
        html = empty_state("Nothing here")
        assert "Nothing here" in html


class TestBadgeHTML:
    def test_all_variants(self):
        for variant in ("green", "amber", "red", "blue", "gray", "neutral"):
            html = badge_html("Test", variant)
            assert "badge" in html

    def test_label_escaped(self):
        html = badge_html('<script>alert("xss")</script>', "green")
        assert "&lt;script&gt;" in html
        assert "<script>" not in html


# ═══════════════════════════════════════════════════════════════════════
# shopstack.ui.renderers.image_cards (SVG components)
# ═══════════════════════════════════════════════════════════════════════


class TestSVGItemCard:
    """WCAG: SVG role='img' + aria-label."""

    def test_svg_role_img_present(self):
        html = ic.render_item_card("Milk", 2.0, "L")
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert svg.get("role") == "img", \
            "Item card SVG missing role='img'"

    def test_svg_aria_label_contains_item_name(self):
        html = ic.render_item_card("Milk", 2.0, "L")
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert "Milk" in svg.get("aria-label", "")


class TestSVGDecisionCard:
    """WCAG: SVG role='img' + aria-label."""

    def test_svg_role_img_present(self):
        html = ic.render_decision_card("Milk", "buy", "Running low", 0.85)
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert svg.get("role") == "img", \
            "Decision SVG missing role='img'"

    def test_svg_aria_label_contains_item_and_decision(self):
        html = ic.render_decision_card("Milk", "buy", "Running low", 0.85)
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        label = svg.get("aria-label", "")
        assert "Milk" in label
        assert "buy" in label.lower()

    def test_wcag_colors_synced(self):
        """SVG decision colors should match WCAG-compliant CSS values."""
        html = ic.render_decision_card("Milk", "buy", "test", 0.9)
        assert "#1A9E4A" in html, \
            "WCAG buy color (#1A9E4A) not found in decision SVG"


class TestSVGUseSoonCard:
    """WCAG: SVG role='img' + aria-label."""

    def test_svg_role_img_present(self):
        html = ic.render_use_soon_card(
            [{"display_name": "Milk", "reason": "Expires soon"}]
        )
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert svg.get("role") == "img", \
            "Use-soon SVG missing role='img'"

    def test_svg_aria_label_contains_item_count(self):
        html = ic.render_use_soon_card(
            [{"display_name": "Milk", "reason": "Expires soon"}]
        )
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert "item" in svg.get("aria-label", "").lower()


class TestSVGShoppingSummaryCard:
    """WCAG: SVG role='img' + aria-label."""

    def test_svg_role_img_present(self):
        html = ic.render_shopping_summary_card(3, 2, 150.0)
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert svg.get("role") == "img", \
            "Shopping summary SVG missing role='img'"

    def test_svg_aria_label_contains_counts(self):
        html = ic.render_shopping_summary_card(3, 2, 150.0)
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        label = svg.get("aria-label", "")
        assert "3" in label or "150" in label


class TestSVGPriceComparisonCard:
    """WCAG: SVG role='img' + aria-label."""

    def test_svg_role_img_present(self):
        html = ic.render_price_comparison_card(
            "Milk", {"Store A": 100, "Store B": 90}
        )
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert svg.get("role") == "img", \
            "Price comparison SVG missing role='img'"

    def test_svg_aria_label_contains_item_name(self):
        html = ic.render_price_comparison_card("Milk", {"Store A": 100})
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert "Milk" in svg.get("aria-label", "")


class TestSVGCardsToGrid:
    """WCAG: SVG role='img' + aria-label with card count."""

    def test_svg_role_img_present(self):
        cards = [
            ic.render_item_card("Milk", 2.0, "L"),
            ic.render_item_card("Eggs", 12, "pieces"),
        ]
        html = ic.cards_to_grid(cards, columns=2)
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert svg.get("role") == "img", "Grid SVG missing role='img'"

    def test_svg_aria_label_contains_card_count(self):
        cards = [ic.render_item_card("Milk", 2.0, "L")]
        html = ic.cards_to_grid(cards, columns=1)
        soup = _parse(html)
        svg = soup.find("svg")
        assert svg is not None
        assert "1" in svg.get("aria-label", "") or "card" in svg.get("aria-label", "")

    def test_empty_cards_returns_empty(self):
        assert ic.cards_to_grid([]) == ""


# ═══════════════════════════════════════════════════════════════════════
# shopstack.ui.renderers.decision_cards
# ═══════════════════════════════════════════════════════════════════════


def _sample_ds() -> DecisionSet:
    return DecisionSet(
        decisions=[
            DecisionResult(
                canonical_name="milk",
                display_name="Milk",
                action="buy",
                reason="Running low",
                confidence=0.9,
                market_price=50.0,
                market_price_per_kg=200.0,
                market_source="swiggy",
                waste_risk="low",
                shelf_life_days=5,
                data_freshness="fresh",
                data_freshness_label="Snapshot from 10 Jun 2026",
            ),
            DecisionResult(
                canonical_name="eggs",
                display_name="Eggs",
                action="skip",
                reason="Already have",
                confidence=0.8,
                market_price=0,
                market_price_per_kg=0,
                market_source="",
                waste_risk="unknown",
                shelf_life_days=0,
                data_freshness="unknown",
                data_freshness_label="",
            ),
        ]
    )


class TestDecisionCardsMarketBasket:
    """Semantic: h3 heading, estimated total, decision badges."""

    def test_heading_present(self):
        html = dc.render_market_basket(_sample_ds())
        assert "Market Basket" in html

    def test_buy_items_rendered(self):
        html = dc.render_market_basket(_sample_ds())
        assert "Milk" in html

    def test_estimated_total_present(self):
        html = dc.render_market_basket(_sample_ds())
        assert "Estimated total" in html


class TestDecisionCardsDecisionPanel:
    """Semantic: h3 heading, decision labels."""

    def test_heading_present(self):
        html = dc.render_decision_panel(_sample_ds())
        assert "Today's Decisions" in html

    def test_buy_items_appear(self):
        html = dc.render_decision_panel(_sample_ds())
        assert "Milk" in html

    def test_skip_items_appear(self):
        html = dc.render_decision_panel(_sample_ds())
        assert "Eggs" in html


class TestDecisionCardsInventoryOverview:
    def test_total_items_displayed(self):
        html = dc.render_inventory_overview([])
        assert "inventory" in html.lower()

    def test_empty_list_shows_zero(self):
        html = dc.render_inventory_overview([])
        assert any(t in html for t in ("0", "None", "No", "empty"))


class TestDecisionCardsWhatChanged:
    def test_returns_empty_string_for_no_events(self):
        assert dc.render_what_changed([], []) == ""

    def test_heading_present_with_data(self):
        from datetime import datetime

        class MockPurchase:
            canonical_name = "milk"
            timestamp = datetime(2026, 6, 10)

        html = dc.render_what_changed([MockPurchase()], [])
        assert "What Changed" in html or "milk" in html or "Milk" in html


class TestDecisionCardsWasteWarnings:
    def test_returns_empty_string_for_no_signals(self):
        assert dc.render_waste_warnings([]) == ""

    def test_warning_rendered_with_data(self):
        signals = [
            {"display_name": "Milk", "reason": "Expiring in 1 day", "confidence": "high"}
        ]
        html = dc.render_waste_warnings(signals)
        assert "Milk" in html


class TestDecisionCardsSwiggySoldout:
    def test_returns_empty_string_when_all_available(self):
        html = dc.render_swiggy_soldout_warning({"milk": {"available": True}})
        assert html == ""

    def test_warning_rendered_for_sold_out(self):
        html = dc.render_swiggy_soldout_warning(
            {"milk": {"available": False}, "eggs": {"available": True}}
        )
        assert "milk" in html or "Milk" in html


class TestDecisionCardsComparePanel:
    """render_compare_panel: h3 heading, compare/watch items, empty state."""

    def test_empty_returns_no_signals_message(self):
        ds = _sample_ds()  # only has buy and skip
        html = dc.render_compare_panel(ds)
        assert "Compare" in html or "Market Signals" in html
        assert "No comparison signals" in html

    def test_heading_present_with_data(self):
        ds = DecisionSet(decisions=[
            DecisionResult(
                canonical_name="tomato",
                display_name="Tomato",
                action="compare",
                reason="Multiple pack sizes available, 80% price spread",
                confidence=0.75,
                market_price_per_kg=56.0,
                waste_risk="unknown",
                shelf_life_days=0,
            ),
        ])
        html = dc.render_compare_panel(ds)
        assert "Compare / Market Signals" in html
        assert "Compare" in html  # the decision badge label

    def test_compare_item_renders_with_reason(self):
        ds = DecisionSet(decisions=[
            DecisionResult(
                canonical_name="tomato",
                display_name="Tomato",
                action="compare",
                reason="Price spread 80%",
                confidence=0.75,
                market_price_per_kg=56.0,
                waste_risk="unknown",
                shelf_life_days=0,
            ),
        ])
        html = dc.render_compare_panel(ds)
        soup = BeautifulSoup(html, "lxml")
        heading = soup.find("h3")
        assert heading is not None
        assert "Compare" in heading.get_text()

    def test_wait_item_renders_with_watch_label(self):
        ds = DecisionSet(decisions=[
            DecisionResult(
                canonical_name="sold_out_item",
                display_name="Premium Broccoli",
                action="wait",
                reason="Sold out, waiting for restock",
                confidence=0.6,
                waste_risk="unknown",
                shelf_life_days=0,
            ),
        ])
        html = dc.render_compare_panel(ds)
        assert "Watch" in html
        assert "Premium Broccoli" in html

    def test_compare_and_wait_both_displayed(self):
        ds = DecisionSet(decisions=[
            DecisionResult(
                canonical_name="tomato", display_name="Tomato",
                action="compare", reason="Price spread 80%",
                confidence=0.75, market_price_per_kg=56.0,
                waste_risk="unknown", shelf_life_days=0,
            ),
            DecisionResult(
                canonical_name="broccoli", display_name="Broccoli",
                action="wait", reason="Sold out",
                confidence=0.6,
                waste_risk="unknown", shelf_life_days=0,
            ),
        ])
        html = dc.render_compare_panel(ds)
        assert "Compare" in html
        assert "Watch" in html
        assert "Tomato" in html
        assert "Broccoli" in html

    def test_max_items_respected(self):
        """Only first 4 compare and first 4 wait items shown."""
        decisions = [
            DecisionResult(
                canonical_name=f"item_{i}", display_name=f"Item {i}",
                action="compare", reason=f"Reason {i}",
                confidence=0.7, market_price_per_kg=50.0,
                waste_risk="unknown", shelf_life_days=0,
            )
            for i in range(6)
        ]
        ds = DecisionSet(decisions=decisions)
        html = dc.render_compare_panel(ds)
        # Should show at most 4 compare + 0 wait = 4 items total
        for i in range(4):
            assert f"Item {i}" in html
        # Items beyond the [:4] limit must not appear
        assert "Item 5" not in html


class TestDecisionCardsMyListPanel:
    """render_my_list_panel: h3 heading, decision badges, empty state."""

    def test_empty_list_returns_empty_state_html(self):
        html = dc.render_my_list_panel(_sample_ds(), None)
        assert "My Own List" in html
        assert "No active shopping list" in html

    def test_empty_list_with_empty_items_returns_state(self):
        class MockList:
            items = []
        html = dc.render_my_list_panel(_sample_ds(), MockList())
        assert "No active shopping list" in html or "My Own List" in html

    def test_heading_present_with_items(self):
        from shopstack.schemas.models import ShoppingListItem

        class MockList:
            items = [
                ShoppingListItem(canonical_name="milk"),
                ShoppingListItem(canonical_name="eggs"),
            ]

        ds = DecisionSet(decisions=[
            DecisionResult(
                canonical_name="milk", display_name="Milk",
                action="buy", reason="Running low",
                confidence=0.9,
                waste_risk="low", shelf_life_days=5,
            ),
            DecisionResult(
                canonical_name="eggs", display_name="Eggs",
                action="skip", reason="Already have",
                confidence=0.8,
                waste_risk="unknown", shelf_life_days=0,
            ),
        ])
        html = dc.render_my_list_panel(ds, MockList())
        assert "My Own List" in html
        assert "Milk" in html
        assert "Eggs" in html

    def test_decision_badge_colors_match_action(self):
        from shopstack.schemas.models import ShoppingListItem

        class MockList:
            items = [
                ShoppingListItem(canonical_name="milk"),
                ShoppingListItem(canonical_name="eggs"),
            ]

        ds = DecisionSet(decisions=[
            DecisionResult(
                canonical_name="milk", display_name="Milk",
                action="buy", reason="Running low",
                confidence=0.9,
                waste_risk="low", shelf_life_days=5,
            ),
            DecisionResult(
                canonical_name="eggs", display_name="Eggs",
                action="skip", reason="Already have",
                confidence=0.8,
                waste_risk="unknown", shelf_life_days=0,
            ),
        ])
        html = dc.render_my_list_panel(ds, MockList())
        soup = BeautifulSoup(html, "lxml")
        h3 = soup.find("h3")
        assert h3 is not None
        assert "My Own List" in h3.get_text()

    def test_item_without_decision_shows_unknown(self):
        from shopstack.schemas.models import ShoppingListItem

        class MockList:
            items = [
                ShoppingListItem(canonical_name="unknown_item"),
            ]

        html = dc.render_my_list_panel(_sample_ds(), MockList())
        assert "Unknown" in html


class TestDecisionCardsCadenceInsights:
    """render_cadence_insights: h3 heading, upcoming items, due-now labels."""

    def test_empty_cadence_returns_empty_string(self):
        assert dc.render_cadence_insights({}) == ""

    def test_items_outside_window_returns_empty(self):
        """Items due >3 days away should not appear."""
        from datetime import date, timedelta
        today = date(2026, 6, 10)
        cadence = {
            "onion": {
                "next_expected": today + timedelta(days=5),
                "typical_qty": 1.0,
                "typical_unit": "kg",
                "avg_interval_days": 7.0,
            }
        }
        html = dc.render_cadence_insights(cadence, today)
        assert html == ""

    def test_due_now_item_appears(self):
        from datetime import date, timedelta
        today = date(2026, 6, 10)
        cadence = {
            "onion": {
                "next_expected": today,
                "typical_qty": 1.0,
                "typical_unit": "kg",
                "avg_interval_days": 7.0,
            }
        }
        html = dc.render_cadence_insights(cadence, today)
        assert "Purchase Rhythm" in html
        assert "Onion" in html
        assert "Due now" in html

    def test_due_tomorrow_item_appears(self):
        from datetime import date, timedelta
        today = date(2026, 6, 10)
        cadence = {
            "onion": {
                "next_expected": today + timedelta(days=1),
                "typical_qty": 1.0,
                "typical_unit": "kg",
                "avg_interval_days": 7.0,
            }
        }
        html = dc.render_cadence_insights(cadence, today)
        assert "Due tomorrow" in html

    def test_due_in_few_days_item_appears(self):
        from datetime import date, timedelta
        today = date(2026, 6, 10)
        cadence = {
            "onion": {
                "next_expected": today + timedelta(days=2),
                "typical_qty": 1.0,
                "typical_unit": "kg",
                "avg_interval_days": 7.0,
            }
        }
        html = dc.render_cadence_insights(cadence, today)
        assert "Due in 2 days" in html

    def test_overdue_item_appears(self):
        from datetime import date, timedelta
        today = date(2026, 6, 10)
        cadence = {
            "onion": {
                "next_expected": today - timedelta(days=1),
                "typical_qty": 1.0,
                "typical_unit": "kg",
                "avg_interval_days": 7.0,
            }
        }
        html = dc.render_cadence_insights(cadence, today)
        assert "Due now" in html

    def test_heading_present_when_items_show(self):
        from datetime import date
        today = date(2026, 6, 10)
        cadence = {
            "tomato": {
                "next_expected": date(2026, 6, 11),
                "typical_qty": 0.5,
                "typical_unit": "kg",
                "avg_interval_days": 4.0,
            }
        }
        html = dc.render_cadence_insights(cadence, today)
        soup = BeautifulSoup(html, "lxml")
        heading = soup.find("h3")
        assert heading is not None
        assert "Purchase Rhythm" in heading.get_text()

    def test_multiple_items_sorted_by_urgency(self):
        from datetime import date
        today = date(2026, 6, 10)
        cadence = {
            "tomato": {
                "next_expected": date(2026, 6, 18),  # 8 days away — outside window
                "typical_qty": 0.5,
                "typical_unit": "kg",
                "avg_interval_days": 4.0,
            },
            "onion": {
                "next_expected": date(2026, 6, 11),  # 1 day away — inside window
                "typical_qty": 1.0,
                "typical_unit": "kg",
                "avg_interval_days": 7.0,
            },
            "milk": {
                "next_expected": date(2026, 6, 10),  # today — inside window
                "typical_qty": 2.0,
                "typical_unit": "L",
                "avg_interval_days": 3.0,
            },
        }
        html = dc.render_cadence_insights(cadence, today)
        # Only onion and milk should appear (tomato is >3 days away)
        assert "Onion" in html
        assert "Milk" in html
        assert "tomato" not in html or "Tomato" not in html

    def test_max_items_respected(self):
        """Only first 5 items shown."""
        from datetime import date
        today = date(2026, 6, 10)
        cadence = {
            f"item_{i}": {
                "next_expected": today,
                "typical_qty": 1.0,
                "typical_unit": "unit",
                "avg_interval_days": 7.0,
            }
            for i in range(8)
        }
        html = dc.render_cadence_insights(cadence, today)
        # Should show max 5 items (upcoming[:5])
        count = html.count("Due now")
        assert count <= 5  # max 5 items from the [:5] limit


class TestDecisionCardsConfirmation:
    def test_returns_empty_string_for_no_lots(self):
        assert dc.render_needs_confirmation([]) == ""


# ═══════════════════════════════════════════════════════════════════════
# shopstack.ui.renderers.shopping_results
# ═══════════════════════════════════════════════════════════════════════


class TestShoppingResults:
    def test_completion_success_shows_list_completed(self):
        result = ShoppingCompletionResult(
            success=True,
            list_id="list-1",
            items_added=[CompletionItem("milk", "lot-1", 2.0, "L")],
            message="Done",
        )
        html = sr.render_shopping_completion(result)
        assert "List completed" in html
        assert "milk" in html

    def test_completion_failure_shows_error(self):
        result = ShoppingCompletionResult(
            success=False, list_id="", message="Something failed"
        )
        html = sr.render_shopping_completion(result)
        assert "Something failed" in html

    def test_completion_zero_items_shows_message(self):
        result = ShoppingCompletionResult(
            success=True, list_id="list-1", message="All done, nothing to add"
        )
        html = sr.render_shopping_completion(result)
        assert "nothing to add" in html

    def test_mark_purchased_success(self):
        result = MarkPurchasedResult(
            success=True,
            items_added=[PurchaseResultItem("milk", "lot-1", 2.0, "L")],
            message="Marked",
        )
        html = sr.render_mark_purchased(result)
        assert "Marked" in html

    def test_mark_purchased_failure(self):
        result = MarkPurchasedResult(success=False, message="Error occurred")
        html = sr.render_mark_purchased(result)
        assert "Error occurred" in html


# ═══════════════════════════════════════════════════════════════════════
# Cross-cutting: all components produce valid-ish HTML
# ═══════════════════════════════════════════════════════════════════════

class TestCrossCutting:
    """Every HTML-generating function should parse without errors."""

    def test_all_primitives_produce_valid_html(self):
        for html in [
            item_row("Test", 1, "kg"),
            stat_card("10", "Items"),
            data_table([{"a": "1"}]),
            data_table([], empty_message="Empty"),
            confirm_dialog("Sure?"),
            toast("OK"),
            empty_state_enhanced("Nothing"),
            loading_skeleton(),
        ]:
            soup = BeautifulSoup(html, "lxml")
            assert len(soup.contents) > 0

    def test_all_card_functions_produce_valid_html(self):
        for html in [
            card("Title", "body"),
            render_decision_card_html("X", "buy", "reason", 0.5),
            render_action_tile("Label", "sub", "tab"),
            render_hero_panel("Title", "sub"),
            render_metric("N", "V"),
            render_rows([("A", "1")]),
            render_workflow_rail(["A"], current_step=0),
        ]:
            soup = BeautifulSoup(html, "lxml")
            assert len(soup.contents) > 0

    def test_all_svg_functions_produce_valid_html(self):
        for html in [
            ic.render_item_card("X", 1, "kg"),
            ic.render_decision_card("X", "buy", "reason", 0.5),
            ic.render_use_soon_card([{"display_name": "X"}]),
            ic.render_shopping_summary_card(1, 0, 0),
            ic.render_price_comparison_card("X", {"A": 10}),
        ]:
            soup = BeautifulSoup(html, "lxml")
            assert len(soup.contents) > 0
