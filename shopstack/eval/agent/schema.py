"""Typed contracts for scenario-level agent evaluation.

This layer intentionally does not replace ``shopstack.eval.recorder``. The
recorder measures one model call, while these contracts describe whether the
whole planner interaction was correct in a controlled world.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvalTier(StrEnum):
    CORE = "core"
    CHALLENGE = "challenge"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Language(StrEnum):
    EN = "en"
    HI_LATIN = "hi-latin"
    MIXED = "mixed"


class Criticality(StrEnum):
    NORMAL = "normal"
    IMPORTANT = "important"
    CRITICAL = "critical"


class ExpectedBehavior(StrEnum):
    TOOL_CALLS = "tool_calls"
    NO_ACTION = "no_action"
    CLARIFY = "clarify"


class EvalStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class ArgumentAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class StateAssertion(BaseModel):
    """A deterministic assertion evaluated against the isolated Database."""

    model_config = ConfigDict(extra="allow")
    kind: str
    canonical_name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    location: str | None = None
    contains: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    count: int | None = None
    price: float | None = None
    store_name: str | None = None


class FaultSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    kind: Literal["tool_error", "empty", "timeout", "stale"]
    message: str = "Injected evaluation fault"


class EvalBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_tool_calls: int = 8
    max_latency_ms: float | None = None
    max_cost_usd: float | None = None


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = Field(ge=1)
    title: str
    request: str
    tier: EvalTier
    difficulty: Difficulty
    language: Language = Language.EN
    criticality: Criticality = Criticality.NORMAL
    expected_behavior: ExpectedBehavior = ExpectedBehavior.TOOL_CALLS
    initial_state: dict[str, Any] = Field(default_factory=dict)
    required_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    required_order: list[str] = Field(default_factory=list)
    argument_assertions: list[ArgumentAssertion] = Field(default_factory=list)
    state_assertions: list[StateAssertion] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    allowed_entities: list[str] = Field(default_factory=list)
    faults: list[FaultSpec] = Field(default_factory=list)
    budgets: EvalBudgets = Field(default_factory=EvalBudgets)
    tags: list[str] = Field(default_factory=list)


class EvalModelConfig(BaseModel):
    """A comparison configuration, with requested and observed identity kept apart."""

    model_config = ConfigDict(extra="forbid")
    key: str
    requested_model: str
    backend: str = "mock"
    provider: str = "mock"
    compact_tools: bool = False
    generation: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class MetricScores(BaseModel):
    task_correctness: float = 0.0
    tool_selection: float = 0.0
    argument_accuracy: float = 0.0
    final_state: float = 0.0
    constraints: float = 0.0
    tool_precision: float = 0.0
    tool_recall: float = 0.0
    invalid_tool_rate: float = 0.0
    excess_tool_calls: float = 0.0


class ToolCallEvidence(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)


class EvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    run_id: str
    scenario_id: str
    model_key: str
    requested_model: str
    actual_model: str | None = None
    backend: str = ""
    provider: str = ""
    trace_id: str
    status: EvalStatus = EvalStatus.ERROR
    tool_calls: list[ToolCallEvidence] = Field(default_factory=list)
    task_success: bool = False
    composite_score: float = 0.0
    metrics: MetricScores = Field(default_factory=MetricScores)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    failure_codes: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    planner_outcome: str = ""
    error: str = ""


class EvalRunMetadata(BaseModel):
    run_id: str
    suite_version: int
    scenario_count: int
    policy_version: int
    started_at: str
    ended_at: str | None = None
    shopstack_version: str = "unknown"
    git_sha: str = "unknown"
    python_version: str = ""
    os: str = ""
    scenario_hashes: dict[str, str] = Field(default_factory=dict)
    model_configs: list[EvalModelConfig] = Field(default_factory=list)
    interrupted: bool = False
