from __future__ import annotations

from shopstack.services.results import (
    CompletionItem,
    MarkPurchasedResult,
    PurchaseResultItem,
    ShoppingCompletionResult,
)


def test_completion_item_fields():
    item = CompletionItem(canonical_name="milk", lot_id="lot_1", quantity=2.0, unit="L")
    assert item.canonical_name == "milk"
    assert item.lot_id == "lot_1"
    assert item.quantity == 2.0
    assert item.unit == "L"


def test_shopping_completion_result_defaults():
    result = ShoppingCompletionResult(success=True, list_id="abc")
    assert result.items_added == []
    assert result.items_skipped == 0
    assert result.goal == ""
    assert result.message == ""
    assert result.count == 0


def test_shopping_completion_result_count():
    items = [
        CompletionItem(canonical_name="milk", lot_id="1", quantity=1.0, unit="L"),
        CompletionItem(canonical_name="bread", lot_id="2", quantity=1.0, unit="unit"),
    ]
    result = ShoppingCompletionResult(success=True, list_id="abc", items_added=items)
    assert result.count == 2


def test_purchase_result_item_fields():
    item = PurchaseResultItem(canonical_name="rice", lot_id="lot_3", quantity=5.0, unit="kg")
    assert item.canonical_name == "rice"


def test_mark_purchased_result_defaults():
    result = MarkPurchasedResult(success=False, message="No items.")
    assert result.items_added == []
    assert result.count == 0


def test_mark_purchased_result_with_items():
    items = [PurchaseResultItem(canonical_name="onion", lot_id="1", quantity=1.0, unit="kg")]
    result = MarkPurchasedResult(success=True, items_added=items)
    assert result.count == 1
