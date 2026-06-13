from __future__ import annotations

from datetime import date

from shopstack.persistence.database import Database
from shopstack.schemas.models import InventoryLot, PriceObservation, Trace
from shopstack.ui import (
    FieldNotesView,
    build_price_memory_view,
    empty_state,
    list_to_table,
    load_field_notes,
    render_action_grid,
    render_action_tile,
    render_decision_card,
    render_hero_panel,
    render_metric,
    render_workflow_rail,
    save_field_notes,
)
from shopstack.ui.components.primitives import (
    confirm_dialog,
    confirm_hide_updates,
    confirm_toggle_updates,
    empty_state_enhanced,
    loading_skeleton,
    toast,
)
from shopstack.ui.theme import CSS


def test_build_price_memory_view_returns_summary_plot_and_table(db: Database):
    db.record_price(
        PriceObservation(canonical_name="milk", price=50.0, quantity=1.0, unit="L", store_name="Store A")
    )
    db.record_price(
        PriceObservation(canonical_name="milk", price=55.0, quantity=1.0, unit="L", store_name="Store B")
    )

    view = build_price_memory_view(db, "milk")

    assert view.item_name == "milk"
    assert view.observation_count == 2
    assert view.store_count == 2
    assert view.latest_price == 55.0
    assert view.first_price == 50.0
    assert view.min_price == 50.0
    assert view.max_price == 55.0
    assert view.direction == "higher"
    assert "Price Memory for milk" in view.summary_html
    assert "observations" in view.summary_html
    assert list(view.df["price"]) == [50.0, 55.0]
    assert view.table[0] == ["Date", "Store", "Price", "Per Unit", "Qty", "Unit", "Source", "Notes"]
    assert len(view.table) == 3


def test_build_price_memory_view_handles_missing_item(db: Database):
    view = build_price_memory_view(db, "")
    assert "Enter an item name" in view.summary_html
    assert view.df.empty
    assert view.table[0][0] == "Enter an item name to see price history"


def test_build_price_memory_view_handles_none_item(db: Database):
    view = build_price_memory_view(db, None)
    assert "Enter an item name" in view.summary_html
    assert view.df.empty
    assert view.table[0][0] == "Enter an item name to see price history"


def test_build_price_memory_view_handles_no_history(db: Database):
    view = build_price_memory_view(db, "nonexistent")
    assert "No price observations found" in view.summary_html
    assert view.df.empty
    assert view.item_name == "nonexistent"


def test_build_price_memory_view_computes_unit_price(db: Database):
    db.record_price(
        PriceObservation(
            canonical_name="rice",
            price=90.0,
            quantity=0.5,
            unit="kg",
            store_name="Store A",
            observation_date=date(2026, 1, 1),
        )
    )
    db.record_price(
        PriceObservation(
            canonical_name="rice",
            price=160.0,
            quantity=1.0,
            unit="kg",
            store_name="Store B",
            observation_date=date(2026, 2, 1),
        )
    )

    view = build_price_memory_view(db, "rice")

    assert view.unit_price_latest == 160.0
    assert view.unit_price_best == 160.0
    assert "unit_price" in view.df.columns
    unit_prices = view.df["unit_price"].dropna().tolist()
    assert unit_prices == [180.0, 160.0]


def test_build_price_memory_view_escapes_html_in_item_name(db: Database):
    db.record_price(
        PriceObservation(
            canonical_name="<script>alert('xss')</script>",
            price=10.0,
            quantity=1.0,
            unit="unit",
        )
    )
    view = build_price_memory_view(db, "<script>alert('xss')</script>")
    assert "<script>" not in view.summary_html
    assert "&lt;script&gt;" in view.summary_html


def test_build_price_memory_view_sorts_by_date(db: Database):
    db.record_price(
        PriceObservation(
            canonical_name="eggs",
            price=60.0,
            quantity=12.0,
            unit="unit",
            store_name="Later Store",
            observation_date=date(2026, 3, 1),
        )
    )
    db.record_price(
        PriceObservation(
            canonical_name="eggs",
            price=50.0,
            quantity=12.0,
            unit="unit",
            store_name="Early Store",
            observation_date=date(2026, 1, 1),
        )
    )

    view = build_price_memory_view(db, "eggs")

    assert view.latest_price == 60.0
    assert view.first_price == 50.0
    assert view.direction == "higher"
    assert list(view.df["price"]) == [50.0, 60.0]


def test_field_notes_round_trip(db: Database):
    db.add_inventory_lot(
        InventoryLot(canonical_name="bread", display_name="Bread", quantity=0.5, unit="loaf")
    )
    db.save_trace(Trace(input_type="voice", final_response="buy bread"))

    view = load_field_notes(db)

    assert isinstance(view, FieldNotesView)
    assert "# Field Notes" in view.editor_value or "# Household Snapshot" in view.editor_value
    assert view.editor_value == view.preview_value
    assert "No saved notes yet" in view.status_html

    saved = save_field_notes(db, "# Saved notes")

    assert saved.editor_value == "# Saved notes"
    assert saved.preview_value == "# Saved notes"
    assert "saved locally" in saved.status_html.lower()

    reloaded = load_field_notes(db)

    assert reloaded.editor_value == "# Saved notes"
    assert reloaded.preview_value == "# Saved notes"
    assert "loaded saved field notes" in reloaded.status_html.lower()


def test_field_notes_uses_provided_today(db: Database):
    view = load_field_notes(db, today=date(2026, 6, 1))
    assert "2026-06-01" in view.editor_value


def test_save_blank_field_notes_preserves_blank(db: Database):
    saved = save_field_notes(db, "  ")
    assert saved.editor_value == ""


def test_load_field_notes_after_blank_save_strands_blank(db: Database):
    save_field_notes(db, "")
    reloaded = load_field_notes(db)
    assert "No saved notes yet" in reloaded.status_html


def test_build_price_memory_view_single_observation(db: Database):
    db.record_price(
        PriceObservation(canonical_name="salt", price=20.0, quantity=1.0, unit="kg", store_name="Store A")
    )
    view = build_price_memory_view(db, "salt")
    assert view.direction == "unchanged"
    assert view.latest_price == 20.0
    assert view.first_price == 20.0


class TestListToTable:
    def test_empty(self):
        result = list_to_table([])
        assert result == [["No data"]]

    def test_basic(self):
        items = [{"name": "milk", "qty": 2}, {"name": "bread", "qty": 1}]
        result = list_to_table(items)
        assert result[0] == ["Name", "Qty"]
        assert len(result) == 3

    def test_custom_columns(self):
        items = [{"name": "milk", "qty": 2, "extra": "x"}]
        result = list_to_table(items, cols=["name"])
        assert result[0] == ["Name"]
        assert result[1] == ["milk"]

    def test_header_title_case(self):
        items = [{"canonical_name": "milk"}]
        result = list_to_table(items)
        assert result[0] == ["Canonical Name"]


def test_build_price_memory_view_with_unknown_store(db: Database):
    db.record_price(
        PriceObservation(canonical_name="spice", price=15.0, quantity=100.0, unit="g", store_name=None)
    )
    view = build_price_memory_view(db, "spice")
    assert view.table[1][1] == "Unknown"
    assert view.unit_price_latest is not None


def test_shared_cards_escape_user_visible_text():
    html = render_decision_card(
        "<script>alert('x')</script>",
        "buy",
        "<img src=x onerror=alert(1)>",
        0.9,
        1,
        "<unit>",
    )

    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;unit&gt;" in html


def test_empty_state_and_metric_escape_text():
    assert "<script>" not in empty_state("<script>alert('x')</script>")
    metric = render_metric("<b>Name</b>", "<img>", "<tag>")
    assert "<b>Name</b>" not in metric
    assert "&lt;b&gt;Name&lt;/b&gt;" in metric
    assert "&lt;img&gt;" in metric


def test_metric_uses_canonical_readable_classes():
    metric = render_metric("Active items", "5", "tap to inspect", tab_id="inventory")

    assert "metric-label" in metric
    assert "metric-value" in metric
    assert "metric-hint" in metric
    assert "font-size:34px" not in metric
    assert "color:var(--text-dim)" not in metric


def test_workflow_rail_uses_accessible_state_classes():
    html = render_workflow_rail(["Input", "Decision", "Saved Trace"], current_step=1)

    assert "workflow-rail" in html
    assert "workflow-step is-complete" in html
    assert "workflow-step is-pending" in html
    assert "Workflow Steps" in html


def test_theme_defines_high_contrast_design_tokens():
    assert "--text: #1F1812" in CSS
    assert "--text-muted: #5F5144" in CSS
    assert "--accent: #176B49" in CSS
    assert "--font-display" in CSS
    assert "metric-value" in CSS
    assert "opacity: 1 !important" in CSS


def test_custom_action_components_escape_and_use_canonical_classes():
    tile = render_action_tile("<b>Market</b>", "<img>", "market", "primary")
    grid = render_action_grid([
        {"label": "Add Purchase", "subtitle": "Record what changed", "tab_id": "purchase"}
    ])

    assert "<b>Market</b>" not in tile
    assert "<img>" not in tile
    assert "&lt;b&gt;Market&lt;/b&gt;" in tile
    assert "action-tile action-tile-primary" in tile
    assert "button[role=tab]" in tile
    assert "While Shopping" in tile
    assert "action-grid" in grid


def test_hero_panel_escapes_and_uses_design_classes():
    html = render_hero_panel("<script>x</script>", "Use what you have", "Today")

    assert "<script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert "hero-panel" in html
    assert "hero-copy" in html


def test_confirm_dialog_escapes_and_supports_danger_variant():
    html = confirm_dialog("<script>alert(1)</script>", confirm_label="<b>Yes</b>")
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;Yes&lt;/b&gt;" in html
    assert "role=\"alertdialog\"" in html
    assert "var(--red)" in html  # default = danger

    safe = confirm_dialog("Proceed?", variant="default")
    assert "var(--amber)" in safe


def test_confirm_toggle_and_hide_return_pair_of_gr_updates():
    import gradio as gr
    primary_update, confirm_update = confirm_toggle_updates()
    assert isinstance(primary_update, gr.update.__class__ if hasattr(gr.update, "__class__") else object)
    assert primary_update.visible is False
    assert confirm_update.visible is True

    restore_primary, hide_confirm = confirm_hide_updates()
    assert restore_primary.visible is True
    assert hide_confirm.visible is False


def test_empty_state_enhanced_renders_icon_message_and_optional_cta():
    html = empty_state_enhanced(
        "No items yet",
        icon="📦",
        action_label="Add first item",
        secondary_text="You can add more later",
    )
    assert "📦" in html
    assert "No items yet" in html
    assert "Add first item" in html
    assert "You can add more later" in html
    assert "role=\"status\"" in html
    # escaping works
    escaped = empty_state_enhanced("<script>", icon="x")
    assert "<script>" not in escaped


def test_loading_skeleton_variants_render_correct_class():
    card = loading_skeleton(variant="card", lines=3)
    assert "home-card" in card
    assert "loading-pulse" in card  # backwards-compat class

    metric = loading_skeleton(variant="metric")
    assert "metric-card" in metric

    text = loading_skeleton(variant="text", lines=2)
    assert "loading-pulse" in text

    table = loading_skeleton(variant="table", lines=3)
    assert "home-card" in table


def test_toast_uses_role_status_and_aria_live():
    html = toast("Saved!", kind="success")
    assert "role=\"status\"" in html
    assert "aria-live=\"polite\"" in html
    assert "Saved!" in html
    # escaping
    escaped = toast("<b>ok</b>")
    assert "&lt;b&gt;ok&lt;/b&gt;" in escaped
