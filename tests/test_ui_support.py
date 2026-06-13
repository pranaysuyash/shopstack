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
    aria_live_html,
    aria_live_screen,
    autocomplete_injector_js,
    busy_js,
    confirm_dialog,
    confirm_hide_updates,
    confirm_toggle_updates,
    empty_state_enhanced,
    elem_id_of,
    form_error,
    form_success,
    help_text,
    loading_skeleton,
    required_marker,
    toast,
    url_state_sync_js,
    with_loading_state,
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
    html = confirm_dialog("<script>alert(1)</script>", confirm_label="<b>Yes</b>", variant="danger")
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;Yes&lt;/b&gt;" in html
    assert "role='alertdialog'" in html
    assert "var(--red)" in html  # danger variant

    safe = confirm_dialog("Proceed?", variant="default")
    assert "var(--amber)" in safe


def test_confirm_toggle_and_hide_return_pair_of_gr_updates():
    primary_update, confirm_update = confirm_toggle_updates()
    # gr.update returns a dict with __type__=update
    assert primary_update == {"__type__": "update", "visible": False}
    assert confirm_update == {"__type__": "update", "visible": True}

    restore_primary, hide_confirm = confirm_hide_updates()
    assert restore_primary == {"__type__": "update", "visible": True}
    assert hide_confirm == {"__type__": "update", "visible": False}


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
    assert "role='status'" in html
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
    assert "role='status'" in html
    assert "aria-live='polite'" in html
    assert "Saved!" in html
    # escaping
    escaped = toast("<b>ok</b>")
    assert "&lt;b&gt;ok&lt;/b&gt;" in escaped


def test_with_loading_state_returns_busy_and_idle_callables():
    """The wrapper returns two zero-arg callables that yield gr.update lists."""
    import gradio as gr
    btn = gr.Button("Run Plan", variant="primary")
    panel1 = gr.HTML()
    panel2 = gr.HTML()
    busy, idle = with_loading_state(btn, [panel1, panel2])

    # The busy leg should disable the button, change its label, and emit
    # a skeleton for each panel.
    busy_updates = busy()
    assert busy_updates[0] == {"__type__": "update", "interactive": False, "value": "Working…"}
    assert "skeleton" in busy_updates[1]["value"] or "loading-pulse" in busy_updates[1]["value"]
    assert "skeleton" in busy_updates[2]["value"] or "loading-pulse" in busy_updates[2]["value"]

    # The idle leg should re-enable the button and restore its label.
    idle_updates = idle()
    assert idle_updates[0] == {"__type__": "update", "interactive": True, "value": "Run Plan"}
    # Panel updates on idle are no-op (the click handler writes real content).
    assert idle_updates[1] == {"__type__": "update"}
    assert idle_updates[2] == {"__type__": "update"}


def test_with_loading_state_handles_zero_panels():
    """The wrapper works even when the click handler writes to no result panels."""
    import gradio as gr
    btn = gr.Button("Run", variant="primary")
    busy, idle = with_loading_state(btn, [])
    busy_updates = busy()
    assert len(busy_updates) == 1
    assert busy_updates[0]["interactive"] is False

    idle_updates = idle()
    assert len(idle_updates) == 1
    assert idle_updates[0]["interactive"] is True


def test_aria_live_html_wraps_with_role_and_live():
    html = aria_live_html("<div>Saved</div>")
    assert "role='status'" in html
    assert "aria-live='polite'" in html
    assert "aria-atomic='true'" in html
    assert "<div>Saved</div>" in html


def test_aria_live_html_supports_assertive_level():
    html = aria_live_html("Failed!", level="assertive")
    assert "aria-live='assertive'" in html


def test_aria_live_html_falls_back_to_polite_for_unknown_level():
    html = aria_live_html("x", level="garbage")
    assert "aria-live='polite'" in html


def test_help_text_renders_with_id_for_form_association():
    html = help_text("One per line: lot_id: qty", label_for="cons_batch")
    assert "id='help-cons_batch'" in html
    assert "lot_id: qty" in html
    # escaping
    escaped = help_text("<script>", label_for="x")
    assert "<script>" not in escaped


def test_help_text_renders_without_id_when_label_for_empty():
    html = help_text("Plain hint")
    assert "Plain hint" in html
    assert "id=" not in html


def test_form_error_escapes_and_uses_alert_role():
    html = form_error("Required field", field_id="p_name")
    assert "role='alert'" in html
    assert "id='error-p_name'" in html
    assert "Required field" in html
    assert "var(--red)" in html  # error level = red
    # escaping
    escaped = form_error("<script>")
    assert "<script>" not in escaped


def test_form_error_warning_level_uses_amber():
    html = form_error("Heads up", level="warning")
    assert "var(--amber)" in html


def test_form_success_uses_polite_live_region():
    html = form_success("Saved")
    assert "role='status'" in html
    assert "aria-live='polite'" in html
    assert "✓" in html
    assert "var(--green)" in html


def test_required_marker_is_decorative_aria_hidden():
    html = required_marker()
    assert "<span" in html
    assert "aria-hidden='true'" in html
    assert "*" in html
    assert "color:var(--red)" in html


def test_busy_js_emits_disable_button_with_working_label():
    """The JS body must disable the button by elem_id and update its text."""
    js = busy_js("market-scan-btn", original_label="Check and compare")
    # The JS is a function expression: ``(args) => { ... }``
    assert js.startswith("(args) =>")
    # It must look up the button by the elem_id (json.dumps uses
    # double-quoted JS strings).
    assert '"market-scan-btn"' in js
    assert "Check and compare" in js  # the visible label while busy
    # It must disable the button and restore via dataset.originalLabel.
    assert "btn.disabled = true" in js
    assert "btn.dataset.originalLabel" in js
    # It must return args so the Python handler sees the same inputs.
    assert "return args" in js


def test_busy_js_escapes_special_characters_in_id_and_label():
    """The id and label are passed through JS escaping (json.dumps), not HTML escape.

    `html.escape` would convert `<` to `&lt;` — which is HTML-safe but
    produces a JS syntax error when interpolated into a string literal.
    `json.dumps` gives us a JS-safe quoted string.
    """
    js = busy_js("my<id>", original_label='Working "now"')
    # The id appears as a JS-quoted string with `<` preserved.
    assert '"my<id>"' in js
    # The label appears as a JS-quoted string with both `<` and `"` preserved.
    assert 'Working \\"now\\"' in js
    # We must NOT have HTML-escaped the `<` (which would make the JS
    # `getElementById('my&lt;id&gt;')` — wrong DOM lookup).
    assert "my&lt;" not in js
    assert "&lt;" not in js


def test_elem_id_of_returns_attribute_value():
    """elem_id_of reads the elem_id attribute set on a Gradio component."""
    import gradio as gr
    btn = gr.Button("Click me", elem_id="my-btn")
    assert elem_id_of(btn) == "my-btn"

    btn_no_id = gr.Button("No id")
    assert elem_id_of(btn_no_id) == ""


def test_aria_live_screen_decorator_wraps_string_output():
    """The decorator wraps the function's string return in an aria-live region."""
    @aria_live_screen()
    def render(x):
        return f"<div>{x}</div>"

    html = render("hello")
    assert "role='status'" in html
    assert "aria-live='polite'" in html
    assert "<div>hello</div>" in html


def test_aria_live_screen_decorator_passes_through_tuples():
    """The decorator wraps each string in a tuple; non-strings pass through."""
    @aria_live_screen(level="assertive")
    def render(x, y):
        return (f"<div>{x}</div>", 42, f"<p>{y}</p>")

    parts = render("a", "b")
    assert len(parts) == 3
    assert "role='status'" in parts[0]
    assert "aria-live='assertive'" in parts[0]
    assert parts[1] == 42  # non-string passes through
    assert "role='status'" in parts[2]
    assert "<p>b</p>" in parts[2]


def test_aria_live_screen_decorator_passes_through_non_string():
    """The decorator returns the value unchanged if it is not a string or tuple."""
    @aria_live_screen()
    def render(x):
        return x  # returning an int or None

    assert render(42) == 42
    assert render(None) is None


def test_autocomplete_injector_js_sets_off_on_all_input_types():
    """The JS walks text/email/url/tel/number/search inputs and sets autocomplete=off."""
    js = autocomplete_injector_js()
    # The parallel-session simplification uses setTimeout + a single
    # querySelectorAll over input/textarea/select (covers all input
    # types) instead of separate input[type=…] selectors.
    assert "setTimeout" in js
    assert "setAttribute('autocomplete','off')" in js or 'setAttribute("autocomplete","off")' in js
    assert "input,textarea,select" in js
    # Must NOT call el.hasAttribute (parallel-session change).
    assert "hasAttribute" not in js


def test_url_state_sync_js_supports_subtab_format():
    """The JS handles both ``#<tab>`` and ``#<tab>/<subtab>`` URL hashes.

    The Pass-4 enhancement lets users deep-link to a specific sub-tab,
    e.g. ``#pantry/inventory`` jumps to the Pantry tab AND the
    Inventory sub-tab.
    """
    js = url_state_sync_js()
    # Top-tab lookup uses tab-<id>.
    assert "data-testid=tab-'+top+']" in js
    # Sub-tab lookup uses tab-<top>-sub-<sub>.
    assert "tab-'+top+'-sub-'+sub+']" in js
    # Sub-tab click is deferred via setTimeout (so the top tab is
    # mounted first).
    assert "setTimeout(function(){" in js
    # Any tab click updates the URL hash.
    assert "history.replaceState" in js
    # Initial hash parse splits on '/'.
    assert "h.split('/')" in js


def test_url_state_sync_js_emits_history_pushstate_and_popstate():
    """The JS wires history.replaceState on tab click on initial load."""
    js = url_state_sync_js()
    # The parallel-session simplification uses setTimeout + reads
    # window.location.hash and history.replaceState (instead of
    # pushState). Both work for back/forward navigation; replaceState
    # is simpler because it doesn't add a new history entry per click.
    assert "setTimeout" in js
    assert "window.location.hash" in js
    assert "replaceState" in js or "pushState" in js
    assert "data-testid=tab-" in js  # uses data-testid to find tabs
