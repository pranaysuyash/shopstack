"""Cost tracking for LLM provider calls.

Maintains per-request cost records, per-tier routing decisions
(haiku / sonnet / local / mock), and a budget guard so a
session cannot accidentally exceed a configured USD cap.

Used by ``shopstack.providers.*`` to attach a ``cost`` dict to
every provider response, and by ``shopstack.planner.engine`` to
gate session-level spend via ``settings.cost_budget_limit``.

Tier routing rationale (see ``estimate_model_tier``):

- **haiku** (cheap, fast): short requests, few items
- **sonnet** (mid-tier, capable): long requests, many items
- **local** (free): any local GGUF/MLX/Llama model
- **mock** (free): the default mock provider used off-the-grid

For pricing, the table in ``MODEL_PRICING`` lists USD per million tokens
for known cloud models. Unknown models fall through to a conservative
``sonnet`` rate so the budget guard still trips rather than silently
recording $0 for a cloud-backed call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MODEL_PRICING: dict[str, dict[str, float | str]] = {
    "gpt-4o": {"input_per_mtok": 2.50, "output_per_mtok": 10.00},
    "gpt-4o-mini": {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
    "text-embedding-3-small": {"input_per_mtok": 0.02, "output_per_mtok": 0.02},
    "whisper-1": {"input_per_mtok": 0.0, "output_per_mtok": 0.0, "note": "priced per audio minute"},
    "microsoft/Phi-3-mini-4k-instruct": {"input_per_mtok": 0.0, "output_per_mtok": 0.0, "note": "HF inference may bill separately"},
    "mlx-community/Llama-3.2-3B-Instruct-4bit": {"input_per_mtok": 0.0, "output_per_mtok": 0.0, "note": "local - free"},
    "unsloth/Llama-3.2-3B-Instruct-GGUF": {"input_per_mtok": 0.0, "output_per_mtok": 0.0, "note": "local - free"},
    "mock": {"input_per_mtok": 0.0, "output_per_mtok": 0.0, "note": "mock - free"},
}

INPUT_TIER_THRESHOLDS: list[tuple[int, str]] = [
    (300, "haiku"),
    (1000, "sonnet"),
]

MODEL_TIER_MAP: dict[str, str] = {
    "gpt-4o-mini": "haiku",
    "gpt-4o": "sonnet",
    "microsoft/Phi-3-mini-4k-instruct": "haiku",
    "mlx-community/Llama-3.2-3B-Instruct-4bit": "local",
    "unsloth/Llama-3.2-3B-Instruct-GGUF": "local",
    "mock": "mock",
}

TIER_COST_MULTIPLIER: dict[str, float] = {
    "haiku": 1.0,
    "sonnet": 4.0,
    "local": 0.0,
    "mock": 0.0,
}


def estimate_model_tier(text_length: int, item_count: int = 0) -> str:
    """Route a request to a model tier based on its size.

    The first matching threshold wins:

    - ``text_length < 300`` and ``item_count < 30`` → ``"haiku"`` (cheapest)
    - ``text_length < 1000`` → ``"sonnet"`` (mid-tier)
    - everything else → ``"sonnet"`` (default)

    Args:
        text_length: Character count of the user request.
        item_count: Number of items being processed in the request.

    Returns:
        One of ``"haiku"``, ``"sonnet"``, ``"local"``, ``"mock"`` —
        the keys in ``TIER_COST_MULTIPLIER``.
    """
    for threshold, tier in INPUT_TIER_THRESHOLDS:
        if text_length < threshold and item_count < 30:
            return tier
    return "sonnet"


def estimate_cost_usd(
    model_key: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate the USD cost of an LLM call.

    Looks up ``model_key`` in ``MODEL_PRICING`` and applies the
    input/output per-million-token rates. Unknown model keys fall
    through to a conservative ``sonnet`` rate (or $0 for known
    local/mock models) so the budget guard still trips rather than
    silently recording $0 for a cloud-backed call.

    Args:
        model_key: The model identifier (e.g. ``"gpt-4o"``).
        input_tokens: Input token count for the call.
        output_tokens: Output token count for the call.

    Returns:
        Cost in USD, rounded to 6 decimal places.
    """
    pricing = MODEL_PRICING.get(model_key)
    if pricing:
        input_rate = pricing.get("input_per_mtok", 0)
        output_rate = pricing.get("output_per_mtok", 0)
        input_cost = (input_tokens / 1_000_000) * (input_rate if isinstance(input_rate, (int, float)) else 0.0)
        output_cost = (output_tokens / 1_000_000) * (output_rate if isinstance(output_rate, (int, float)) else 0.0)
        return round(input_cost + output_cost, 6)
    # MOD-1: unknown model — don't silently return $0, which would let a
    # cloud-backed model bypass the cost guard entirely. Local/mock models
    # are correctly free (their name contains "mlx", "gguf", "llama",
    # "local", or "mock"). Anything else is assumed cloud and priced at
    # a conservative mid-tier estimate (sonnet rate) so the budget
    # guard can still trip.
    LOCAL_TAGS = ("mlx", "gguf", "llama", "local", "mock")
    key_lower = (model_key or "").lower()
    is_local = any(tag in key_lower for tag in LOCAL_TAGS)
    if is_local:
        return 0.0
    fallback_rate = TIER_COST_MULTIPLIER["sonnet"] * 1.0  # conservative nonzero estimate
    return round(((input_tokens + output_tokens) / 1_000_000) * fallback_rate, 6)


@dataclass(frozen=True)
class CostRecord:
    """A single LLM call's cost telemetry.

    Frozen so records can be safely shared across threads and
    included in trace payloads without defensive copying.
    """
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tier: str
    latency_ms: float | None = None


@dataclass(frozen=True)
class CostTracker:
    """Immutable, append-only cost ledger with budget guard.

    ``add()`` returns a new tracker rather than mutating in place
    so that race conditions across concurrent provider calls
    cannot silently corrupt the ledger. The previous instance
    remains valid for the duration of any in-flight read.
    """
    budget_limit: float = 1.00
    records: tuple[CostRecord, ...] = ()

    def add(self, record: CostRecord) -> CostTracker:
        """Return a new tracker with ``record`` appended.

        The original tracker is not modified.
        """
        return CostTracker(
            budget_limit=self.budget_limit,
            records=(*self.records, record),
        )

    @property
    def total_cost(self) -> float:
        """Sum of all recorded costs in USD."""
        return sum(r.cost_usd for r in self.records)

    @property
    def total_input_tokens(self) -> int:
        """Total input tokens across all records."""
        return sum(r.input_tokens for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens across all records."""
        return sum(r.output_tokens for r in self.records)

    @property
    def over_budget(self) -> bool:
        """True if total spend has exceeded ``budget_limit``."""
        return self.total_cost > self.budget_limit

    def summary(self) -> dict[str, Any]:
        """Serialize the ledger to a JSON-safe dict for trace payloads."""
        return {
            "total_cost": self.total_cost,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "call_count": len(self.records),
            "budget_limit": self.budget_limit,
            "over_budget": self.over_budget,
            "records": [
                {
                    "model": r.model,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "cost_usd": r.cost_usd,
                    "tier": r.tier,
                    "latency_ms": r.latency_ms,
                }
                for r in self.records
            ],
        }
