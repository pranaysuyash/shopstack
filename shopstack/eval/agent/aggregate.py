"""Aggregations for model comparison and failure clusters."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from shopstack.eval.agent.schema import EvalCaseResult, Scenario


def _rate(values: list[bool]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def summarize(results: list[EvalCaseResult], scenarios: list[Scenario] | None = None) -> dict[str, Any]:
    scenario_map = {scenario.id: scenario for scenario in (scenarios or [])}
    by_model: dict[str, list[EvalCaseResult]] = defaultdict(list)
    groups: dict[str, dict[str, list[EvalCaseResult]]] = {key: defaultdict(list) for key in ("category", "difficulty", "language", "tier")}
    for result in results:
        by_model[result.model_key].append(result)
        scenario = scenario_map.get(result.scenario_id)
        if scenario:
            groups["category"][result.scenario_id.split("-")[0]].append(result)
            groups["difficulty"][scenario.difficulty.value].append(result)
            groups["language"][scenario.language.value].append(result)
            groups["tier"][scenario.tier.value].append(result)
    models = {}
    for key, rows in by_model.items():
        costs = [row.cost_usd for row in rows if row.cost_usd is not None]
        models[key] = {
            "cases": len(rows),
            "success_rate": _rate([row.task_success for row in rows]),
            "core_success_rate": _rate([row.task_success for row in rows if not scenario_map or scenario_map.get(row.scenario_id, None) and scenario_map[row.scenario_id].tier.value == "core"]),
            "mean_composite": round(sum(row.composite_score for row in rows) / len(rows), 4) if rows else 0.0,
            "mean_latency_ms": round(sum(row.latency_ms for row in rows if row.latency_ms is not None) / len([row for row in rows if row.latency_ms is not None]), 2) if any(row.latency_ms is not None for row in rows) else None,
            "total_cost_usd": round(sum(costs), 6) if costs else None,
            "failures": dict(Counter(code for row in rows for code in row.failure_codes)),
        }
    grouped = {}
    for group_name, buckets in groups.items():
        grouped[group_name] = {
            label: {"cases": len(rows), "success_rate": _rate([row.task_success for row in rows]), "mean_composite": round(sum(row.composite_score for row in rows) / len(rows), 4)}
            for label, rows in buckets.items()
        }
    return {"models": models, "groups": grouped, "failure_clusters": {key: count for key, count in Counter(code for row in results for code in row.failure_codes).most_common()}, "cases": len(results)}
