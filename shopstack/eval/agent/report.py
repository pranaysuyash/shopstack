"""Stable JSON, Markdown, and CSV report formats."""
from __future__ import annotations

import csv
import io
import json
from typing import Any


def to_json(summary: dict[str, Any], decision: dict[str, Any] | None = None) -> str:
    return json.dumps({"decision": decision or {}, "summary": summary}, indent=2, sort_keys=True, default=str)


def to_markdown(summary: dict[str, Any], decision: dict[str, Any] | None = None) -> str:
    decision = decision or {}
    lines = ["# ShopStack Agent Evaluation Report", "", f"Decision: **{decision.get('decision', 'UNKNOWN')}**", f"Winner: **{decision.get('winner') or 'none'}**", "", "## Model comparison", "", "| Model | Cases | Core success | Composite | Mean latency ms | Cost USD |", "|---|---:|---:|---:|---:|---:|"]
    for key, row in summary.get("models", {}).items():
        lines.append(f"| {key} | {row.get('cases', 0)} | {row.get('core_success_rate', 0):.1%} | {row.get('mean_composite', 0):.3f} | {row.get('mean_latency_ms') if row.get('mean_latency_ms') is not None else 'Unknown'} | {row.get('total_cost_usd') if row.get('total_cost_usd') is not None else 'Unknown'} |")
    lines.extend(["", "## Failure clusters", ""])
    for code, count in summary.get("failure_clusters", {}).items():
        lines.append(f"- `{code}`: {count}")
    lines.extend(["", "This report is advisory. It does not mutate planner routing."])
    return "\n".join(lines) + "\n"


def to_csv(summary: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["model", "cases", "core_success_rate", "mean_composite", "mean_latency_ms", "total_cost_usd"])
    writer.writeheader()
    for key, row in summary.get("models", {}).items():
        writer.writerow({"model": key, **{field: row.get(field) for field in writer.fieldnames[1:]}})
    return output.getvalue()
