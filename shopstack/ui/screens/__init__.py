from shopstack.ui.screens.dashboard import today_dashboard
from shopstack.ui.screens.shopping import (
    shopping_list_view,
    shopping_list_create,
    shopping_list_view_with_cards,
    _shopping_list_view_with_cards,  # noqa: F401 — test backward compat
    build_shopping_list_and_refresh,
    _build_shopping_list_and_refresh,  # noqa: F401 — test backward compat
    complete_shopping_list,
    shopping_list_item_choices,
    shopping_list_share,
    mark_items_purchased,
    get_reconciliation_draft,
    confirm_reconciliation,
    generate_shopping_poster,
    shopping_list_substitutions_view,
)
from shopstack.ui.screens.market_lens import (
    market_lens_process,
    market_lens_confirm_buy,
    market_lens_skip,
    market_lens_save_trace,
    market_lens_barcode_add,
)
from shopstack.ui.screens.shelf_scan import (
    shelf_scan_process,
    shelf_scan_confirm,
    shelf_scan_skip,
    shelf_scan_save_trace,
)
from shopstack.ui.screens.ask import ask_shopstack
from shopstack.ui.screens.inventory import (
    add_purchase_form,
    add_purchase_batch,
    inventory_view,
    inventory_cards_view,
    consume_item,
    consume_items_batch,
    seed_demo_inventory,
    suggest_location_for_item,
    use_first_view,
    use_soon_view,  # noqa: F401 — deprecated alias (kept for one release cycle; see HANDOFF_USESOONVIEW_SUPERSESSION_2026-06-13.md)
)
# Backward-compat re-export for households.py — module was archived to
# _legacy/ on 2026-06-13 per motto_v3 §7 (supersession). The functions
# remain importable from `shopstack.ui.screens` (this module) for any
# external consumer. The original `from shopstack.ui.screens import households`
# import path is preserved by the shim at the end of this file.
from shopstack.ui.screens._legacy.households import (
    add_member_screen,
    change_role_screen,
    households_panel_screen,
    list_user_households_screen,
    remove_member_screen,
)  # noqa: F401 — public API re-export (archived 2026-06-13)
from shopstack.ui.screens.traces import (
    agent_trace_choices,
    agent_trace_bootstrap,
    agent_trace_view,
    agent_trace_detail,
    agent_trace_export_file,
    agent_trace_refresh,
    agent_trace_search_filter,
    record_workflow_trace,
    trace_bundle,
)
from shopstack.ui.screens.model_stack import model_budget_view, provider_status_badge, runtime_proof_view
from shopstack.ui.screens.price_memory import (
    price_memory_view,
    price_intelligence_view,
    seed_swiggy_prices,
)
from shopstack.ui.screens.household_map import (
    household_map_view,
    move_inventory_to_location,
)
from shopstack.ui.screens.field_notes import (
    field_notes_view,
    field_notes_save,
)
from shopstack.ui.screens.swiggy_market import (
    swiggy_market_view,
    swiggy_basket_estimate,
)
from shopstack.ui.screens.portability import export_data_json, export_data_csv, import_data_file
from shopstack.ui.screens.price_compare import (
    multi_source_price_view,
    single_item_compare,
    refresh_source_registry,
    basket_compare_view,
)
from shopstack.ui.screens.market_intelligence import market_intelligence_view
from shopstack.ui.screens.receipt import (
    receipt_scan_ocr,
    receipt_parse_text,
    receipt_confirm,
)
from shopstack.ui.screens.intelligence import (
    get_intelligence_dashboard,
    add_preference,
    delete_preference,
    refresh_preferences,
)
from shopstack.ui.screens.nutrition import nutrition_lookup_view, nutrition_kitchen_view  # noqa: F401 — public API re-export
from shopstack.ui.screens.unified_shopping import run_unified_plan, unified_plan_summary
from shopstack.ui.screens.recipe_text import (
    recipe_text_to_shopping_list,
    recipe_text_add_missing_to_list,
    recipe_image_to_text,
)
from shopstack.ui.screens.consumption import (
    consumption_dashboard,
    quick_consume,
    batch_consume_with_context,
    consumption_history,
    consumption_rates,
)
from shopstack.ui.screens.find_trail import (
    add_object_note,
    find_trail_view,
    add_negative_memory,
    add_person_association,
    create_find_object,
    record_find_feedback,
    record_object_sighting,
)
from shopstack.ui.screens.timeline import (
    timeline_view,
    timeline_for_canonical,
    timeline_for_lot,
    set_timeline_window,
)
from shopstack.ui.screens.photo_map import (
    photo_map_view,
    attach_photo_to_location,
    clear_location_photo,
    find_location_by_photo,
)
from shopstack.ui.screens.repair_inbox import (
    repair_inbox_view,
    report_damage,
    confirm_condition_event,
    close_condition_event,
    delete_condition_event,
)

__all__ = [
    "today_dashboard",
    # "shopping_list_view",  # REMOVED 2026-06-13: superseded by shopping_list_view_with_cards. See HANDOFF_SUPERSESSION_AUDIT_2026-06-13.md.
    "shopping_list_create",
    "shopping_list_view_with_cards",
    "build_shopping_list_and_refresh",
    "complete_shopping_list",
    "shopping_list_item_choices",
    "shopping_list_share",
    "mark_items_purchased",
    "get_reconciliation_draft",
    "confirm_reconciliation",
    "generate_shopping_poster",
    "shopping_list_substitutions_view",
    "market_lens_process",
    "market_lens_confirm_buy",
    "market_lens_skip",
    "market_lens_save_trace",
    "market_lens_barcode_add",
    "shelf_scan_process",
    "shelf_scan_confirm",
    "shelf_scan_skip",
    "shelf_scan_save_trace",
    "ask_shopstack",
    "add_purchase_form",
    "add_purchase_batch",
    "suggest_location_for_item",
    "recipe_text_to_shopping_list",
    "recipe_text_add_missing_to_list",
    "recipe_image_to_text",
    "inventory_view",
    "inventory_cards_view",
    "consume_item",
    "consume_items_batch",
    "seed_demo_inventory",
    "use_first_view",
    "use_soon_view",  # deprecated alias; see HANDOFF_USESOONVIEW_SUPERSESSION_2026-06-13.md
    "agent_trace_choices",
    "agent_trace_bootstrap",
    "agent_trace_view",
    "agent_trace_detail",
    "agent_trace_export_file",
    "agent_trace_refresh",
    "agent_trace_search_filter",
    "record_workflow_trace",
    "trace_bundle",
    "model_budget_view",
    "provider_status_badge",
    "runtime_proof_view",
    "price_memory_view",
    "price_intelligence_view",
    "seed_swiggy_prices",
    "household_map_view",
    "move_inventory_to_location",
    "field_notes_view",
    "field_notes_save",
    "swiggy_market_view",
    "swiggy_basket_estimate",
    "multi_source_price_view",
    "single_item_compare",
    "refresh_source_registry",
    "basket_compare_view",
    "market_intelligence_view",
    "export_data_json",
    "export_data_csv",
    "import_data_file",
    "receipt_scan_ocr",
    "receipt_parse_text",
    "receipt_confirm",
    "get_intelligence_dashboard",
    "add_preference",
    "delete_preference",
    "refresh_preferences",
    "run_unified_plan",
    "unified_plan_summary",
    "consumption_dashboard",
    "quick_consume",
    "batch_consume_with_context",
    "consumption_history",
    "consumption_rates",
    "find_trail_view",
    "add_negative_memory",
    "add_person_association",
    "create_find_object",
    "record_object_sighting",
    "add_object_note",
    "record_find_feedback",
    "timeline_view",
    "timeline_for_canonical",
    "timeline_for_lot",
    "set_timeline_window",
    "photo_map_view",
    "attach_photo_to_location",
    "clear_location_photo",
    "find_location_by_photo",
    "repair_inbox_view",
    "report_damage",
    "confirm_condition_event",
    "close_condition_event",
    "delete_condition_event",
    # Archived 2026-06-13 to _legacy/ per motto_v3 §7 (supersession).
    # Kept in __all__ for backward compatibility — see DR-SS1.
    "add_member_screen",
    "change_role_screen",
    "households_panel_screen",
    "list_user_households_screen",
    "remove_member_screen",
]
