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
    for threshold, tier in INPUT_TIER_THRESHOLDS:
        if text_length < threshold and item_count < 30:
            return tier
    return "sonnet"


def estimate_cost_usd(
    model_key: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    pricing = MODEL_PRICING.get(model_key)
    if not pricing:
        return 0.0
    input_rate = pricing.get("input_per_mtok", 0)
    output_rate = pricing.get("output_per_mtok", 0)
    input_cost = (input_tokens / 1_000_000) * (input_rate if isinstance(input_rate, (int, float)) else 0.0)
    output_cost = (output_tokens / 1_000_000) * (output_rate if isinstance(output_rate, (int, float)) else 0.0)
    return round(input_cost + output_cost, 6)


@dataclass(frozen=True)
class CostRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tier: str
    latency_ms: float | None = None


@dataclass(frozen=True)
class CostTracker:
    budget_limit: float = 1.00
    records: tuple[CostRecord, ...] = ()

    def add(self, record: CostRecord) -> CostTracker:
        return CostTracker(
            budget_limit=self.budget_limit,
            records=(*self.records, record),
        )

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.records)

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.records)

    @property
    def over_budget(self) -> bool:
        return self.total_cost > self.budget_limit

    def summary(self) -> dict[str, Any]:
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
