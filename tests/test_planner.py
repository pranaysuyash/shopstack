from __future__ import annotations

from shopstack.planner.parser import extract_json, parse_tool_calls
from shopstack.planner.prompts import format_inventory_context
from shopstack.schemas.models import InventoryLot


# ─── Parser tolerance tests ───────────────────────────────────────

class TestExtractJSON:
    def test_valid_json_array(self):
        text = '[{"tool": "find_item", "args": {"query": "milk"}}]'
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["tool"] == "find_item"

    def test_markdown_fenced_json(self):
        text = "```json\n[{\"tool\": \"find_item\", \"args\": {\"query\": \"eggs\"}}]\n```"
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["args"]["query"] == "eggs"

    def test_prose_surrounded_json(self):
        text = "Here is what I found:\n[{\"tool\": \"find_item\", \"args\": {\"query\": \"bread\"}}]\nLet me know if you need more."
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["args"]["query"] == "bread"

    def test_single_object(self):
        text = '{"tool": "find_item", "args": {"query": "rice"}}'
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, dict)

    def test_trailing_comma(self):
        text = '[{"tool": "find_item", "args": {"query": "milk",},}]'
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["args"]["query"] == "milk"

    def test_single_quotes(self):
        text = "[{'tool': 'find_item', 'args': {'query': 'pasta'}}]"
        result = extract_json(text)
        assert result is not None
        assert result[0]["args"]["query"] == "pasta"

    def test_unquoted_keys(self):
        text = "[{tool: 'find_item', args: {query: 'oil'}}]"
        result = extract_json(text)
        assert result is not None
        assert result[0]["args"]["query"] == "oil"

    def test_no_json(self):
        text = "I don't know what you're asking about."
        result = extract_json(text)
        assert result is None

    def test_empty_string(self):
        assert extract_json("") is None

    def test_only_brackets(self):
        assert extract_json("[") is None

    def test_multiple_tool_calls(self):
        text = (
            '['
            '{"tool": "find_item", "args": {"query": "milk"}},'
            '{"tool": "add_inventory_item", "args": {"canonical_name": "bread", "quantity": 2}}'
            ']'
        )
        result = extract_json(text)
        assert result is not None
        assert len(result) == 2
        assert result[0]["tool"] == "find_item"
        assert result[1]["tool"] == "add_inventory_item"


class TestParseToolCalls:
    def test_valid_parsed(self):
        result = parse_tool_calls('[{"tool": "find_item", "args": {"query": "milk"}}]')
        assert len(result) == 1
        assert result[0]["tool"] == "find_item"
        assert result[0]["args"]["query"] == "milk"

    def test_missing_tool_field(self):
        result = parse_tool_calls('[{"args": {"query": "milk"}}]')
        assert len(result) == 1
        assert result[0]["tool"] == "respond"

    def test_missing_args_field(self):
        result = parse_tool_calls('[{"tool": "find_item"}]')
        assert len(result) == 1
        assert result[0]["tool"] == "find_item"
        assert result[0]["args"] == {}

    def test_not_a_dict(self):
        result = parse_tool_calls('["string_item"]')
        assert len(result) == 1
        assert result[0]["tool"] == "respond"

    def test_no_json_returns_respond(self):
        result = parse_tool_calls("It's all good, nothing to do.")
        assert len(result) == 1
        assert result[0]["tool"] == "respond"

    def test_respond_tool_preserved(self):
        result = parse_tool_calls('[{"tool": "respond", "args": {"message": "Hello"}}]')
        assert len(result) == 1
        assert result[0]["tool"] == "respond"
        assert result[0]["args"]["message"] == "Hello"

    def test_surrounded_by_prose(self):
        result = parse_tool_calls(
            "Based on your inventory, I can see that:\n\n"
            '[{"tool": "find_item", "args": {"query": "milk"}}]\n\n'
            "Would you like me to do anything else?"
        )
        assert len(result) == 1
        assert result[0]["tool"] == "find_item"

    def test_markdown_fence(self):
        result = parse_tool_calls(
            "```json\n"
            '[{"tool": "add_inventory_item", "args": {"canonical_name": "eggs", "quantity": 12}}]\n'
            "```"
        )
        assert len(result) == 1
        assert result[0]["tool"] == "add_inventory_item"
        assert result[0]["args"]["canonical_name"] == "eggs"

    def test_single_object_parsed(self):
        result = parse_tool_calls('{"tool": "find_item", "args": {"query": "rice"}}')
        assert len(result) == 1
        assert result[0]["tool"] == "find_item"


# ─── Prompt tests ────────────────────────────────────────────────

class TestFormatInventoryContext:
    def test_empty_inventory(self):
        class FakeDB:
            def get_inventory(self, status=None):
                return []
        ctx = format_inventory_context(FakeDB())
        assert ctx == "Inventory is empty."

    def test_with_items(self):
        class FakeDB:
            def get_inventory(self, status=None):
                return [
                    InventoryLot(canonical_name="milk", display_name="Milk", quantity=2.0, unit="L", storage_location_id="fridge"),
                    InventoryLot(canonical_name="eggs", display_name="Eggs", quantity=12.0, unit="pieces", storage_location_id="fridge"),
                ]
        ctx = format_inventory_context(FakeDB())
        assert "milk" in ctx
        assert "2.0" in ctx
        assert "eggs" in ctx
        assert "fridge" in ctx

    def test_truncates_at_20(self):
        lots = [
            InventoryLot(canonical_name=f"item-{i}", display_name=f"Item {i}", quantity=1.0)
            for i in range(25)
        ]
        class FakeDB:
            def get_inventory(self, status=None):
                return lots
        ctx = format_inventory_context(FakeDB())
        assert "... and 5 more items" in ctx


# ─── Planner engine tests ────────────────────────────────────────

class TestPlannerEngine:
    def test_not_available_with_mock_backend(self):
        from shopstack.config import Settings
        from shopstack.persistence.database import Database
        from shopstack.providers.registry import ProviderRegistry
        from shopstack.tools.registry import ToolRegistry
        from shopstack.planner.engine import PlannerEngine

        settings = Settings(off_the_grid=True)
        db = Database(":memory:")
        providers = ProviderRegistry(settings)
        tools = ToolRegistry(db)
        engine = PlannerEngine(db, tools, providers)
        assert not engine.available

    def test_process_returns_setup_message_when_not_available(self):
        from shopstack.config import Settings
        from shopstack.persistence.database import Database
        from shopstack.providers.registry import ProviderRegistry
        from shopstack.tools.registry import ToolRegistry
        from shopstack.planner.engine import PlannerEngine

        settings = Settings(off_the_grid=True)
        db = Database(":memory:")
        providers = ProviderRegistry(settings)
        tools = ToolRegistry(db)
        engine = PlannerEngine(db, tools, providers)
        result = engine.process("Do we have milk?")
        assert "Planner not available" in result
