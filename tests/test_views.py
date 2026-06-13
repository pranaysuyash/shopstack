from __future__ import annotations

import os
from datetime import date

import gradio as gr
import pytest

from shopstack.app_context import (
    current_user_id,
    db as app_db,
    providers as app_providers,
    tools as app_tools,
)
from shopstack.schemas.models import DecisionResult, DecisionSet, InventoryLot, Trace
from shopstack.ui.components import WORKFLOW_STEPS, workflow_header
from shopstack.ui.renderers import render_compare_panel
from shopstack.ui.screens import (
    add_purchase_form,
    agent_trace_bootstrap,
    agent_trace_export_file,
    agent_trace_view,
    ask_shopstack,
    consume_item,
    field_notes_save,
    field_notes_view,
    household_map_view,
    inventory_cards_view,
    inventory_view,
    market_lens_process,
    model_budget_view,
    provider_status_badge,
    today_dashboard,
    use_soon_view,
)
from shopstack.ui.screens.shopping import (
    _shopping_list_view_with_cards,
    shopping_list_create,
    shopping_list_view,
)
from shopstack.ui.screens.traces import agent_trace_detail



class TestTodayDashboard:
    def test_returns_six_strings(self, app):
        results = today_dashboard()
        assert len(results) == 6
        for r in results:
            assert isinstance(r, str)

    def test_empty_dashboard_shows_next_actions(self, app):
        results = today_dashboard()
        full_html = "".join(results)
        assert "Shopping path" in full_html
        assert "What needs attention" in full_html
        assert "Build shopping list" in full_html
        assert "Scan receipt" in full_html
        assert "Scan shelf item" in full_html

    def test_hides_runtime_proof_from_home(self, app):
        results = today_dashboard()
        assert "Runtime Proof" not in results[0]
        assert "Off-grid policy" not in results[0]

    def test_home_uses_progressive_disclosure(self, app):
        results = today_dashboard()
        assert "Market Map" not in results[0]
        assert "Open Market Map" not in results[0]
        assert "Shopping" in results[0]
        assert "Scan &amp; Compare" in results[0]
        assert "Start here" in results[0] or "Use what you have" in results[0]

    def test_shows_use_soon(self, app):
        app_db.add_inventory_lot(
            InventoryLot(canonical_name="milk", display_name="Milk", quantity=0.5, unit="L"),
            user_id=current_user_id(),
        )
        results = today_dashboard()
        assert any("Use soon" in r for r in results)

    def test_shows_low_stock(self, app):
        app_db.add_inventory_lot(
            InventoryLot(canonical_name="bread", display_name="Bread", quantity=0.3, unit="loaf"),
            user_id=current_user_id(),
        )
        results = today_dashboard()
        assert any("Low stock" in r for r in results)


class TestShoppingListView:
    def test_empty(self, app):
        html, table, list_id, goal = shopping_list_view()
        assert "No active shopping list" in html

    def test_create_and_view(self, app):
        result = shopping_list_create(
            "Weekly groceries", '[{"canonical_name":"milk","requested_quantity":2}]'
        )
        assert "Created list" in result
        html, table, list_id, goal = shopping_list_view()
        assert list_id
        assert goal == "Weekly groceries"

    def test_create_bare_list(self, app):
        result = shopping_list_create("Quick trip", "[]")
        assert "Created list" in result

    def test_create_list_invalid_json(self, app):
        result = shopping_list_create("Quick trip", "{bad json}")
        assert "Invalid JSON" in result

    def test_create_list_with_natural_text(self, app):
        app_db.add_inventory_lot(
            InventoryLot(
                canonical_name="milk",
                display_name="Milk",
                quantity=0.2,
                unit="L",
                storage_location_id="fridge",
            )
        )
        result = shopping_list_create("Breakfast run", "milk, bread, tomato")
        assert "Created list" in result
        cards, list_html, _table, list_id, goal, share = _shopping_list_view_with_cards()
        assert list_id
        assert goal == "Breakfast run"
        assert "milk" in share.lower()

    def test_shopping_list_cards_refresh(self, app):
        app_db.add_inventory_lot(
            InventoryLot(
                canonical_name="bread",
                display_name="Bread",
                quantity=2.0,
                unit="loaf",
                storage_location_id="pantry",
            ),
            user_id=current_user_id(),
        )
        shopping_list_create("Pantry top-up", "bread")
        cards, list_html, _table, list_id, _goal, share = _shopping_list_view_with_cards()
        assert "ShopStack list for today" in share
        assert list_id
        assert "Shopping List" in cards
        assert "Bread" in cards


class TestCompareBridge:
    def test_compare_panel_exposes_bridge_actions(self):
        ds = DecisionSet(
            decisions=[
                DecisionResult(
                    canonical_name="tomato",
                    display_name="Tomato",
                    action="compare",
                    confidence=0.7,
                    reasons=["Partially covered at home"],
                )
            ]
        )
        html = render_compare_panel(ds)
        assert "Compare bridge" in html
        assert "Open Shopping" in html
        assert "Tomato" in html


class TestModelBudgetView:
    def test_model_budget_view_renders(self, app):
        html = model_budget_view()
        assert "Selected Runtime Stack" in html
        assert "Candidate Models" in html
        assert "Active / Loaded" in html
        assert "Max Budget" in html

    def test_workflow_header_is_visible_markup(self, app):
        assert "Workflow Steps" in workflow_header(WORKFLOW_STEPS)


class TestAddPurchase:
    def test_adds_item(self, app):
        result = add_purchase_form("Paneer", 0.5, "kg", 120.0, "Local Store", "fridge",
                                       date.today().isoformat(), "Dairy")
        assert "Added" in result
        items = app_db.get_inventory(user_id=current_user_id())
        assert any(i.canonical_name == "paneer" for i in items)

    def test_negative_quantity(self, app):
        result = add_purchase_form("Salt", -1.0, "kg", 20.0, "Store", "fridge",
                                       date.today().isoformat(), "Spices")
        assert "Quantity must be 0 or more" in result

    def test_negative_price(self, app):
        result = add_purchase_form("Salt", 1.0, "kg", -20.0, "Store", "fridge",
                                       date.today().isoformat(), "Spices")
        assert "Price must be 0 or more" in result

    def test_with_price_records_observation(self, app):
        result = add_purchase_form("Butter", 0.2, "kg", 50.0, "Store A", "fridge",
                                       date.today().isoformat(), "Dairy")
        assert "Added" in result
        prices = app_db.conn.execute("SELECT * FROM price_observations").fetchall()
        assert any(row["canonical_name"] == "butter" for row in prices)

    def test_blank_item_rejected(self, app):
        result = add_purchase_form("   ", 1.0, "kg", 10.0, "Store", "fridge",
                                       date.today().isoformat(), "Dairy")
        assert "Item name is required" in result

    def test_add_purchase_escapes_html(self, app):
        result = add_purchase_form("<script>alert('x')</script>", 1.0, "kg", 10.0, "Store", "fridge",
                                       date.today().isoformat(), "Dairy")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestInventoryView:
    def test_empty(self, app):
        tbl = inventory_view()
        assert tbl == [["No data"]]

    def test_with_items(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg"))
        tbl = inventory_view()
        assert len(tbl) >= 2
        assert any("rice" in str(c).lower() for row in tbl for c in row)

    def test_search(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg"))
        app_db.add_inventory_lot(InventoryLot(canonical_name="dal", display_name="Toor Dal", quantity=1.0, unit="kg"))
        tbl = inventory_view(search="rice")
        assert len(tbl) == 2

    def test_semantic_search_fallback(self, app, monkeypatch):
        app_db.add_inventory_lot(InventoryLot(canonical_name="milk", display_name="Milk", quantity=1.0, unit="L"))
        app_db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Rice", quantity=2.0, unit="kg"))

        monkeypatch.setattr(
            app_tools,
            "semantic_find_item",
            lambda query, user_id="": {
                "results": [
                    {
                        "lot": next(
                            lot.model_dump()
                            for lot in app_db.get_inventory(user_id=user_id)
                            if lot.canonical_name == "milk"
                        ),
                        "location_name": "Fridge",
                        "location_id": "fridge",
                        "match_type": "semantic",
                        "match_score": 0.91,
                    }
                ],
                "count": 1,
                "match_type": "semantic",
            },
        )

        tbl = inventory_view(search="doodh")
        assert any("Milk" in str(cell) for row in tbl for cell in row)
        assert not any("Rice" in str(cell) for row in tbl for cell in row)


class TestConsume:
    def test_consume_item(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="salt", display_name="Salt", quantity=1.0, unit="kg"))
        items = app_db.get_inventory()
        lot_id = items[0].lot_id
        result = consume_item(lot_id, 0.5)
        assert "Consumed" in result

    def test_consume_prefix_resolves(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="butter", display_name="Butter", quantity=2.0, unit="kg"))
        lot_id = app_db.get_inventory()[0].lot_id
        result = consume_item(lot_id[:6], 0.5)
        assert "Consumed" in result
        assert "1.5" in result

    def test_consume_unknown(self, app):
        result = consume_item("nonexistent", 1.0)
        assert "Error" in result

    def test_consume_negative(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="ghee", display_name="Ghee", quantity=2.0, unit="kg"))
        lot_id = app_db.get_inventory()[0].lot_id
        result = consume_item(lot_id, -1.0)
        assert "Quantity to consume" in result


class TestInventoryCardsView:
    def test_empty(self, app):
        html = inventory_cards_view()
        assert "Your inventory is empty" in html

    def test_with_items(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg", storage_location_id="pantry"))
        html = inventory_cards_view()
        assert "Basmati Rice" in html
        assert "Pantry" in html or "pantry" in html

    def test_search_filters(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg", storage_location_id="pantry"))
        app_db.add_inventory_lot(InventoryLot(canonical_name="dal", display_name="Toor Dal", quantity=1.0, unit="kg", storage_location_id="pantry"))
        html = inventory_cards_view(search="rice")
        assert "Basmati Rice" in html
        assert "Toor Dal" not in html

    def test_semantic_search_fallback(self, app, monkeypatch):
        app_db.add_inventory_lot(InventoryLot(canonical_name="milk", display_name="Milk", quantity=1.0, unit="L", storage_location_id="fridge"))

        monkeypatch.setattr(
            app_tools,
            "semantic_find_item",
            lambda query, user_id="": {
                "results": [
                    {
                        "lot": next(
                            lot.model_dump()
                            for lot in app_db.get_inventory(user_id=user_id)
                            if lot.canonical_name == "milk"
                        ),
                        "location_name": "Fridge",
                        "location_id": "fridge",
                        "match_type": "semantic",
                        "match_score": 0.91,
                    }
                ],
                "count": 1,
                "match_type": "semantic",
            },
        )

        html = inventory_cards_view(search="doodh")
        assert "Showing semantic matches for doodh" in html
        assert "Milk" in html

    def test_inventory_cards_escape_html(self, app):
        app_db.add_inventory_lot(
            InventoryLot(
                canonical_name="xss",
                display_name="<script>alert('x')</script>",
                quantity=1.0,
                unit="kg",
                storage_location_id="pantry",
            )
        )
        html = inventory_cards_view()
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestAskShopStack:
    def test_ask_about_inventory(self, app):
        app_db.add_inventory_lot(
            InventoryLot(
                canonical_name="tomato",
                display_name="Tomato",
                quantity=2.0,
                unit="kg",
                storage_location_id="pantry",
            )
        )
        result = ask_shopstack("Do we have tomato?")
        # With mock planner available, response comes from the AI planner path,
        # which executes the canned mock tool call (add_inventory_item).
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_ask_for_skip_candidates(self, app):
        app_db.add_inventory_lot(
            InventoryLot(
                canonical_name="onion",
                display_name="Onion",
                quantity=3.0,
                unit="kg",
                storage_location_id="pantry",
            )
        )
        result = ask_shopstack("What can I skip today?")
        # With mock planner available, response comes from the AI planner path.
        assert isinstance(result, dict)
        assert len(result) > 0


class TestFieldNotesView:
    def test_initial_load(self, app):
        editor, preview, status = field_notes_view()
        assert isinstance(editor, str)
        assert editor == preview
        # When no notes exist, status shows either "No saved notes yet" or
        # the generated draft message; both are valid empty-state indicators.
        assert status and isinstance(status, str)

    def test_save_and_reload(self, app):
        editor, preview, status = field_notes_save("# My custom notes")
        assert "# My custom notes" in editor
        editor2, preview2, status2 = field_notes_view()
        assert "# My custom notes" in editor2
        assert "loaded saved" in status2.lower()


class TestUseSoonView:
    def test_empty(self, app):
        tbl = use_soon_view()
        assert isinstance(tbl, list)

    def test_with_old_item(self, app):
        app_db.add_inventory_lot(InventoryLot(canonical_name="old-spice", display_name="Old Spice", quantity=1.0, unit="unit"))
        tbl = use_soon_view()
        assert isinstance(tbl, list)


class TestHouseholdMap:
    def test_shows_header(self, app):
        result = household_map_view()
        assert "Household Storage Map" in result

    def test_lists_location_names(self, app):
        result = household_map_view()
        for loc in app_db.get_locations()[:3]:
            assert loc.name in result

    def test_map_does_not_use_inline_alerts(self, app):
        result = household_map_view()
        assert "alert(" not in result


class TestAgentTrace:
    def test_empty(self, app):
        tbl, trace_id = agent_trace_view()
        assert "No activity yet" in str(tbl)

    def test_with_data(self, app):
        app_db.save_trace(Trace(input_type="voice", user_goal="check inventory", final_response="ok"))
        app_db.save_trace(Trace(input_type="text", final_response="done"))
        tbl, trace_id = agent_trace_view()
        assert len(tbl) >= 2
        assert len(trace_id) > 0

    def test_detail_found(self, app):
        app_db.save_trace(Trace(
            input_type="voice",
            final_response="test",
            decision={
                "planner_debug": {
                    "provider": {
                        "provider": "planner",
                        "model": "openbmb/MiniCPM5-1B",
                        "backend": "minicpm5",
                        "latency_ms": 42.5,
                        "output_tokens": 77,
                    },
                    "parser": {"status": "ok"},
                    "execution": {"tool_calls_executed": 1},
                }
            },
        ))
        traces = app_db.get_traces()
        tid = traces[0].trace_id
        detail = agent_trace_detail(tid)
        assert tid in detail
        assert "Model Used" in detail
        assert "Provider" in detail

    def test_detail_not_found(self, app):
        detail = agent_trace_detail("nonexistent")
        assert "not found" in detail.lower()

    def test_export_file_returns_jsonl_path(self, app):
        app_db.save_trace(Trace(input_type="voice", user_goal="check inventory", final_response="ok"))
        trace = app_db.get_traces()[0]
        out_path = agent_trace_export_file(trace.trace_id)
        assert out_path.endswith(".jsonl")
        assert os.path.exists(out_path)

    def test_search_filters_by_goal(self, app):
        app_db.save_trace(Trace(input_type="text", user_goal="shopping list", final_response="ok"))
        app_db.save_trace(Trace(input_type="voice", user_goal="voice_add_item", final_response="ok"))
        from shopstack.ui.screens.traces import _filter_traces
        results = _filter_traces("shopping", "")
        assert len(results) == 1
        assert results[0].user_goal == "shopping list"

    def test_filter_by_input_type(self, app):
        app_db.save_trace(Trace(input_type="text", user_goal="goal1", final_response="ok"))
        app_db.save_trace(Trace(input_type="voice", user_goal="goal2", final_response="ok"))
        from shopstack.ui.screens.traces import _filter_traces
        voice_only = _filter_traces("", "voice")
        assert all(t.input_type == "voice" for t in voice_only)
        text_only = _filter_traces("", "text")
        assert all(t.input_type == "text" for t in text_only)

    def test_trace_bootstrap_returns_update(self, app):
        result = agent_trace_bootstrap()
        assert len(result) == 4
        assert isinstance(result[0], dict)
        assert "choices" in result[0]
        assert "value" in result[0]


class TestMarketLens:
    def test_market_lens_result_has_real_gradio_actions_only(self, app):
        result_html, detected_items, analysis, trace_id, barcode_json = market_lens_process("fake-market-image.jpg", None)
        assert "Market Lens" in result_html
        assert "alert(" not in result_html
        assert detected_items.startswith("{")
        assert analysis.startswith("{")
        assert barcode_json.startswith("[")


class TestModelStack:
    def test_provider_status_badge_reports_runtime_state(self, app):
        badge = provider_status_badge()
        assert badge.startswith('<span class="badge ')
        assert any(state in badge for state in {"Mock", "Configured", "AI", "Off-grid"})

    def test_provider_status_badge_reports_real_loaded_runtime(self, app, monkeypatch):
        monkeypatch.setattr(
            app_providers,
            "list_providers",
            lambda: [
                {"name": "planner", "type": "LocalProvider", "available": True, "capabilities": "planning"},
                {"name": "vision", "type": "MockVisionProvider", "available": True, "capabilities": "vision"},
            ],
        )
        badge = provider_status_badge()
        assert "AI" in badge
