"""Advisory model recommendations. This module never edits routing config."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_policy() -> dict[str, Any]:
    return json.loads((Path(__file__).parent / "policy.json").read_text(encoding="utf-8"))


def recommend(summary: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    eligible: list[dict[str, Any]] = []
    for key, row in summary.get("models", {}).items():
        failures = row.get("failures", {})
        critical = failures.get("CONSTRAINT_VIOLATION", 0) + failures.get("FAILED_TO_ABSTAIN", 0) + failures.get("FAILED_TO_CLARIFY", 0)
        invalid_rate = failures.get("INVALID_TOOL", 0) / row["cases"] if row.get("cases") else 1.0
        forbidden_rate = failures.get("FORBIDDEN_TOOL", 0) / row["cases"] if row.get("cases") else 1.0
        core_rate = row.get("core_success_rate", row.get("success_rate", 0.0))
        eligible.append({**row, "model_key": key, "eligible": core_rate >= policy["minimum_core_success_rate"] and invalid_rate <= policy["maximum_invalid_tool_rate"] and forbidden_rate <= policy["maximum_forbidden_tool_rate"] and critical <= policy["maximum_critical_failures"]})
    valid = [row for row in eligible if row["eligible"]]
    if not valid:
        decision = "NO_WINNER"
        winner = None
    else:
        valid.sort(key=lambda row: (-row.get("mean_composite", 0), row.get("mean_latency_ms") or float("inf"), row.get("total_cost_usd") if row.get("total_cost_usd") is not None else float("inf")))
        winner = valid[0]["model_key"]
        decision = "ADVISORY_WINNER"
    return {"decision": decision, "winner": winner, "eligible": eligible, "policy": policy, "routing_mutated": False}
