import pytest
from shopstack.planner.engine import PlannerEngine
from shopstack.tools.registry import ToolRegistry
from shopstack.providers.registry import ProviderRegistry
from shopstack.persistence.database import Database
from shopstack.config import settings

@pytest.fixture
def planner_engine():
    db = Database(":memory:")
    # Database.__init__ auto-seeds locations via _seed_locations()
    tools = ToolRegistry(db)
    settings.planner_backend = "mock"
    providers = ProviderRegistry(settings)
    
    return PlannerEngine(db, tools, providers)

def test_planner_vegetable_basket(planner_engine):
    # Setup mock behavior for the planner provider to return specific tool calls
    planner_engine._providers.planner.set_mock_response("""
    [
      {"tool": "create_or_update_shopping_list", "args": {"items": [{"canonical_name": "potato", "requested_quantity": 1.0, "unit": "kg", "priority": "must_buy", "reason": "basket"}], "goal": "vegetable basket"}}
    ]
    """)
    response = planner_engine.process_structured("Build a ₹300 vegetable basket")
    
    # Assert we get a structured response
    assert isinstance(response, dict)
    assert "tool_calls" in response
    assert "outcomes" in response
    assert response["type"] == "tool_calls"
    
    # Assert tool call execution was successful
    assert len(response["outcomes"]) == 1
    assert "success" in response["outcomes"][0]
    # Check that it generated the right object format in the outcome
    # The engine wraps the tool result in a 'result' key, inside which
    # create_or_update_shopping_list returns {'list': {...}, 'list_id': ...}
    outcome = response["outcomes"][0]
    assert "list" in outcome.get("result", {})

def test_planner_where_is_item(planner_engine):
    planner_engine._providers.planner.set_mock_response("""
    [
      {"tool": "find_item", "args": {"query": "tomato"}}
    ]
    """)
    response = planner_engine.process_structured("Where is the tomato?")
    assert response["type"] == "tool_calls"
    assert "outcomes" in response
    assert len(response["outcomes"]) == 1
    # find_item returns {'results': [...], 'count': ...} nested inside 'result'
    outcome = response["outcomes"][0]
    assert "results" in outcome.get("result", {})
