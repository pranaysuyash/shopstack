from __future__ import annotations

from shopstack.persistence.database import Database
from shopstack.planner.engine import PlannerEngine
from shopstack.planner.parser import extract_json, parse_tool_calls
from shopstack.planner.prompts import build_planner_prompt, format_inventory_context
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


class TestThinkTagStripping:
    """Test that think-tag wrappers (Qwen3.5-style) are stripped before JSON extraction."""

    def test_think_tag_wrapped_json(self):
        """Full think block before JSON array."""
        text = (
            '<think>The user wants to find red onions. I should use find_item.</think>\n\n'
            '[{"tool": "find_item", "args": {"query": "red onions"}}]'
        )
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["tool"] == "find_item"
        assert result[0]["args"]["query"] == "red onions"

    def test_think_tag_with_brackets_in_reasoning(self):
        """Think block containing brackets that would confuse the bracket search."""
        text = (
            '<think>I should use [find_item] to search for this. Also check [add_inventory_item].</think>\n\n'
            '[{"tool": "find_item", "args": {"query": "milk"}}]'
        )
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["tool"] == "find_item"

    def test_think_tag_multiline(self):
        """Multiline think block with newlines inside the tag."""
        text = (
            '<think>\n'
            'The user is asking about inventory.\n'
            'I should search for the item.\n'
            'Let me use find_item with the right query.\n'
            '</think>\n\n'
            '[{"tool": "find_item", "args": {"query": "sugar"}}]'
        )
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["args"]["query"] == "sugar"

    def test_think_tag_with_markdown_fence(self):
        """Think block followed by markdown-fenced JSON."""
        text = (
            '<think>I need to add this item.</think>\n\n'
            '```json\n'
            '[{"tool": "add_inventory_item", "args": {"canonical_name": "bread", "quantity": 2}}]\n'
            '```'
        )
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["tool"] == "add_inventory_item"

    def test_think_tag_only(self):
        """Think block with no JSON after it returns None."""
        text = '<think>I don\'t think I have enough information.</think>'
        result = extract_json(text)
        assert result is None

    def test_bare_think_end_tag(self):
        """A standalone </think> tag (from Qwen with no opening tag) is harmless."""
        text = (
            '</think>\n\n'
            '[{"tool": "find_item", "args": {"query": "rice"}}]'
        )
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["args"]["query"] == "rice"

    def test_nested_brackets_in_think_with_json_after(self):
        """Think block with JSON-like content inside it, real JSON after."""
        text = (
            '<think>So the output would be [{"tool": "find_item"}] but that is wrong. I need to think more.</think>\n\n'
            '[{"tool": "find_item", "args": {"query": "eggs"}}]'
        )
        result = extract_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert result[0]["args"]["query"] == "eggs"


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
    def test_process_escapes_provider_response_text(self):
        from shopstack.config import Settings
        from shopstack.persistence.database import Database
        from shopstack.planner.engine import PlannerEngine
        from shopstack.providers.registry import ProviderRegistry
        from shopstack.tools.registry import ToolRegistry

        class FakePlanner:
            available = True
            model_id = "fake"
            capabilities = {"planning"}

            def complete(self, prompt):
                return {"text": '[{"tool":"respond","args":{"message":"<script>alert(1)</script>"}}]'}

        settings = Settings(_env_file=None, off_the_grid=True)
        db = Database(":memory:")
        providers = ProviderRegistry(settings)
        providers.register("planner", FakePlanner())
        tools = ToolRegistry(db)
        engine = PlannerEngine(db, tools, providers)
        result = engine.process("hello")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_build_prompt_includes_tool_contract(self):
        db = Database(":memory:")
        try:
            prompt = build_planner_prompt("How do I plan shopping?", db)
        finally:
            db.close()

        assert "Tool contract (canonical):" in prompt
        assert "\"tool_schema_version\": \"1.1\"" in prompt
        assert "\"name\": \"compare_visible_item_to_inventory\"" in prompt
        assert "must_buy/optional/avoid_buying" in prompt
        assert "find_item(" in prompt
        assert "Inventory is empty." in prompt

    def test_inventory_context_exposes_lot_ids_for_mutation_planning(self):
        class FakeDB:
            def get_inventory(self, status=None):
                return [InventoryLot(lot_id="milk-lot-123", canonical_name="milk", display_name="Milk", quantity=2.0, unit="L", storage_location_id="fridge")]

        ctx = format_inventory_context(FakeDB())
        assert "lot_id=milk-lot-123" in ctx

    def test_build_prompt_includes_canonical_mutation_routing(self):
        db = Database(":memory:")
        try:
            prompt = build_planner_prompt("Use half the rice", db)
        finally:
            db.close()

        assert "exact `lot_id` from INVENTORY CONTEXT" in prompt
        assert "Tool results are not variables" in prompt

    def test_process_blocks_write_tool_calls_when_writes_disabled(self, db, tool_registry):
        from shopstack.config import Settings
        from shopstack.providers.registry import ProviderRegistry

        class FakeWritePlanner:
            available = True
            capabilities = {"planning"}
            model_id = "fake-writes"

            def plan(self, payload):
                return [{
                    "tool": "add_inventory_item",
                    "args": {"canonical_name": "milk", "quantity": 1.0, "unit": "L"},
                }]

        settings = Settings(_env_file=None, off_the_grid=True, local_auto_download=False)
        providers = ProviderRegistry(settings)
        providers.register("planner", FakeWritePlanner())
        engine = PlannerEngine(db, tool_registry, providers)

        result = engine.process("Add milk to inventory")
        assert "Planner write blocked by safety policy" in result
        assert "Review and confirm this action in the relevant screen." in result
        assert len(db.get_inventory()) == 0

    def test_planner_resolves_unique_item_name_to_lot_id_before_mutation(self, monkeypatch, tmp_path):
        from types import SimpleNamespace

        from shopstack.config import Settings
        from shopstack.persistence.database import Database
        from shopstack.planner.engine import PlannerEngine
        from shopstack.providers.registry import ProviderRegistry
        from shopstack.tools.registry import ToolRegistry

        settings = Settings(_env_file=None, off_the_grid=True, planner_allow_writes=True)
        db = Database(str(tmp_path / "planner-resolution.db"))
        tools = ToolRegistry(db)
        tools.execute(
            "add_inventory_item",
            canonical_name="sugar",
            display_name="Sugar",
            quantity=1.0,
            unit="kg",
            storage_location_id="pantry",
        )
        provider = SimpleNamespace(
            available=True,
            model_id="fake-resolution",
            plan=lambda _payload: [{"tool": "move_inventory_item", "args": {"lot_id": "sugar", "to_location_id": "kitchen counter"}}],
        )
        providers = ProviderRegistry(settings)
        providers.register("planner", provider)
        monkeypatch.setattr("shopstack.planner.engine.settings.planner_allow_writes", True)
        engine = PlannerEngine(db, tools, providers)

        result = engine.process_structured("Move sugar to the kitchen")

        assert result["outcomes"][0]["success"] is True
        assert db.get_inventory(status="active")[0].storage_location_id == "kitchen"
        assert result["debug"]["execution"]["tool_runs"][0]["lot_resolution"]["method"] == "unique_active_item_name"
        assert result["debug"]["execution"]["tool_runs"][0]["location_resolution"]["method"] == "location_name_subphrase"

    def test_tool_validation_allows_punctuation_in_descriptive_metadata(self, db, tool_registry):
        engine = PlannerEngine(db, tool_registry, object())

        assert engine._validate_args(
            "create_or_update_shopping_list",
            {
                "items": [{
                    "canonical_name": "tomato",
                    "reason": "Requested addition; onions are already on the active list.",
                }],
                "goal": "Add tomatoes without duplicating onions",
            },
        ) is None

    def test_tool_validation_keeps_operational_and_code_checks(self, db, tool_registry):
        engine = PlannerEngine(db, tool_registry, object())

        operational_error = engine._validate_args("find_item", {"query": "milk; rm -rf"})
        assert operational_error is not None
        assert "suspicious pattern ';'" in operational_error
        traversal_error = engine._validate_args(
            "create_or_update_shopping_list",
            {"items": [{"canonical_name": "../etc/passwd", "reason": "normal"}]},
        )
        assert traversal_error is not None
        assert "suspicious pattern '../'" in traversal_error
        code_error = engine._validate_args(
            "create_or_update_shopping_list",
            {"items": [{"canonical_name": "tomato", "reason": "__import__('os')"}]},
        )
        assert code_error is not None
        assert "suspicious pattern '__import__'" in code_error
