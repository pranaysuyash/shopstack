from __future__ import annotations




class TestAddInventoryItem:
    def test_add_basic(self, tool_registry):
        result = tool_registry.execute("add_inventory_item", canonical_name="milk", quantity=2.0, unit="L")
        assert result["success"] is True
        assert result["result"]["lot"]["canonical_name"] == "milk"
        assert "lot_id" in result["result"]

    def test_add_with_all_fields(self, tool_registry):
        result = tool_registry.execute(
            "add_inventory_item",
            canonical_name="basmati rice",
            display_name="Basmati Rice",
            quantity=5.0,
            unit="kg",
            storage_location_id="pantry",
            category="grains",
            price_paid=600.0,
        )
        assert result["success"] is True

    def test_unknown_tool(self, tool_registry):
        result = tool_registry.execute("nonexistent")
        assert result["success"] is False
        assert "Unknown" in result["error"]

    def test_list_tools(self, tool_registry):
        tools = tool_registry.list_tools()
        names = [t["name"] for t in tools]
        assert "add_inventory_item" in names
        assert "consume_inventory_item" in names
        assert "find_item" in names
        assert len(names) >= 10


class TestConsumeItem:
    def test_consume_partial(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="rice", quantity=5.0, unit="kg")
        items = tool_registry.db.get_inventory()
        lot_id = items[0].lot_id
        result = tool_registry.execute("consume_inventory_item", lot_id=lot_id, quantity=2.0)
        assert result["success"] is True
        assert result["result"]["remaining"] == 3.0

    def test_consume_unknown_lot(self, tool_registry):
        result = tool_registry.execute("consume_inventory_item", lot_id="nonexistent", quantity=1.0)
        assert result["success"] is True
        assert "error" in result["result"]

    def test_consume_exact(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="eggs", quantity=1.0, unit="dozen")
        lot_id = tool_registry.db.get_inventory()[0].lot_id
        result = tool_registry.execute("consume_inventory_item", lot_id=lot_id, quantity=1.0)
        assert result["result"]["status"] == "used"

    def test_consume_negative_quantity_error(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="milk", quantity=2.0, unit="L")
        lot_id = tool_registry.db.get_inventory()[0].lot_id
        result = tool_registry.execute("consume_inventory_item", lot_id=lot_id, quantity=-0.5)
        assert result["success"] is True
        assert "positive" in result["result"].get("error", "")

    def test_consume_prefix_resolves(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="butter", quantity=1.0, unit="pack")
        tool_registry.execute("add_inventory_item", canonical_name="bread", quantity=1.0, unit="loaf")
        lot_id = tool_registry.db.get_inventory()[0].lot_id
        prefix = lot_id[:6]
        result = tool_registry.execute("consume_inventory_item", lot_id=prefix, quantity=0.2)
        assert result["success"] is True
        assert result["result"].get("remaining") == 0.8


class TestFindItem:
    def test_find_existing(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="milk", quantity=2.0, unit="L")
        result = tool_registry.execute("find_item", query="milk")
        assert result["success"] is True
        assert result["result"]["count"] >= 1

    def test_find_missing(self, tool_registry):
        result = tool_registry.execute("find_item", query="unicorn")
        assert result["result"]["count"] == 0


class TestMoveItem:
    def test_move_item(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="butter", quantity=1.0, unit="box", storage_location_id="fridge")
        lot_id = tool_registry.db.get_inventory()[0].lot_id
        result = tool_registry.execute("move_inventory_item", lot_id=lot_id, to_location_id="pantry")
        assert result["success"] is True
        assert result["result"]["to"] == "pantry"

    def test_move_to_unknown(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="x", quantity=1.0, unit="unit")
        lot_id = tool_registry.db.get_inventory()[0].lot_id
        result = tool_registry.execute("move_inventory_item", lot_id=lot_id, to_location_id="nonexistent")
        assert result["success"] is True
        assert "error" in result["result"]


class TestCompareVisibleItem:
    def test_compare_empty_inventory(self, tool_registry):
        result = tool_registry.execute("compare_visible_item_to_inventory", canonical_name="milk", quantity=1.0, unit="L")
        assert result["result"]["decision"] == "buy"
        assert result["result"]["in_home_inventory"] is False

    def test_compare_sufficient(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="rice", quantity=10.0, unit="kg")
        result = tool_registry.execute("compare_visible_item_to_inventory", canonical_name="rice", quantity=1.0, unit="kg")
        assert result["result"]["in_home_inventory"] is True
        assert result["result"]["decision"] == "skip"


class TestUseSoon:
    def test_use_soon_empty(self, tool_registry):
        result = tool_registry.execute("get_use_soon_items", days=3)
        assert result["result"]["count"] >= 0

    def test_use_soon_with_old_item(self, tool_registry):
        tool_registry.execute(
            "add_inventory_item",
            canonical_name="old bread",
            quantity=1.0,
            unit="loaf",
            purchase_date="2020-01-01",
        )
        result = tool_registry.execute("get_use_soon_items", days=7)
        assert result["result"]["count"] >= 1


class TestPriceObservation:
    def test_record_price(self, tool_registry):
        result = tool_registry.execute(
            "record_price_observation",
            canonical_name="milk",
            price=50.0,
            quantity=1.0,
            unit="L",
            store_name="Big Bazaar",
        )
        assert result["success"] is True
        assert result["result"]["observation"]["canonical_name"] == "milk"


class TestShoppingList:
    def test_create_list(self, tool_registry):
        result = tool_registry.execute("create_or_update_shopping_list", goal="Weekend groceries")
        assert result["success"] is True

    def test_create_list_with_items(self, tool_registry):
        items = [
            {"canonical_name": "milk", "requested_quantity": 2},
            {"canonical_name": "bread", "requested_quantity": 1},
        ]
        result = tool_registry.execute("create_or_update_shopping_list", goal="test", items=items)
        assert result["success"] is True


class TestGetNextBuySuggestions:
    def test_suggestions_empty(self, tool_registry):
        result = tool_registry.execute("get_next_buy_suggestions")
        assert result["result"]["count"] == 0

    def test_suggestions_with_depleted(self, tool_registry):
        tool_registry.execute("add_inventory_item", canonical_name="milk", quantity=0, unit="L")
        result = tool_registry.execute("get_next_buy_suggestions")
        assert result["result"]["count"] >= 1
        assert result["result"]["suggestions"][0]["priority"] == "must_buy"
