"""Scenario-level agent evaluation for ShopStack."""

from shopstack.eval.agent.aggregate import summarize
from shopstack.eval.agent.loader import assert_valid_suite, load_scenarios, validate_suite
from shopstack.eval.agent.recommend import recommend
from shopstack.eval.agent.runner import AgentEvalRunner
from shopstack.eval.agent.schema import EvalCaseResult, EvalModelConfig, Scenario
from shopstack.eval.agent.storage import AgentEvalStorage

__all__ = [
    "AgentEvalRunner", "AgentEvalStorage", "EvalCaseResult", "EvalModelConfig",
    "Scenario", "assert_valid_suite", "load_scenarios", "recommend", "summarize",
    "validate_suite",
]
