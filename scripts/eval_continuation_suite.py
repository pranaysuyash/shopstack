"""Run the bounded planner continuation evaluation corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shopstack.eval.agent.continuation_corpus import build_continuation_scenarios
from shopstack.eval.agent.continuation_eval import ContinuationEvalRunner, continuation_summary
from shopstack.eval.agent.schema import EvalModelConfig
from shopstack.eval.agent.storage import AgentEvalStorage


def _model(value: str) -> EvalModelConfig:
    backend = "openai" if value.startswith("gpt-") else "mock"
    generation: dict[str, Any] = {
        "max_tokens": 768 if backend == "openai" else 256,
        "temperature": 0.0,
    }
    if backend == "openai" and value.startswith("gpt-5"):
        generation["reasoning_effort"] = "high"
    return EvalModelConfig(
        key=value.replace("/", "_"),
        requested_model=value,
        backend=backend,
        provider=backend,
        generation=generation,
    )


def _markdown(
    summary: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    model_names: list[str],
    scenario_ids: list[str],
) -> str:
    lines = [
        "# ShopStack Planner Continuation Evaluation",
        "",
        "This report evaluates the bounded multi-turn continuation protocol. It is advisory and does not mutate planner routing.",
        "",
        f"Models: `{', '.join(model_names)}`",
        f"Scenarios: `{', '.join(scenario_ids)}`",
        "",
        "## Model summary",
        "",
        "| Model | Cases | Passed | Success rate | Composite | Mean latency ms | Cost USD |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model, row in summary.get("models", {}).items():
        lines.append(
            f"| {model} | {row['cases']} | {row['passed']} | "
            f"{row['success_rate']:.1%} | {row['mean_composite']:.3f} | "
            f"{row['mean_latency_ms']:.2f} | {row['total_cost_usd']:.6f} |"
        )
    lines.extend(["", "## Scenario results", "", "| Scenario | Model | Status | Score | Failures |", "|---|---|---|---:|---|"])
    for result in results:
        failures = ", ".join(result.get("failure_codes", [])) or "none"
        lines.append(
            f"| {result['scenario_id']} | {result['model_key']} | "
            f"{result['status']} | {result['composite_score']:.3f} | {failures} |"
        )
    lines.extend(["", "## Failure clusters", ""])
    failures = summary.get("failure_clusters", {})
    if failures:
        lines.extend(f"- `{code}`: {count}" for code, count in failures.items())
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Evidence boundary",
        "",
        "- The mock corpus proves evaluator determinism, fault containment, binding rejection, duplicate suppression, confirmation boundaries, and call-count truncation.",
        "- Real-model cases prove provider behavior only for the scenarios explicitly selected in the run.",
        "- A passing continuation suite is not production-readiness proof until browser, persistence, operator recovery, and provider failure evidence are also current.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/eval_continuation_suite.py")
    parser.add_argument("--model", action="append")
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--db", required=True, help="SQLite path for evaluation results")
    parser.add_argument("--output", required=True, help="JSON report path; Markdown is written beside it")
    parser.add_argument("--resume-run-id", help="Resume completed cases from an interrupted run in --db")
    parser.add_argument("--max-cases", type=int, help="Bound newly executed cases for interruption/resume drills")
    args = parser.parse_args(argv)

    scenarios = build_continuation_scenarios()
    selected = [scenario for scenario in scenarios if not args.scenario or scenario.id in args.scenario]
    requested_ids = args.scenario or [scenario.id for scenario in scenarios]
    unknown = sorted(set(requested_ids) - {scenario.id for scenario in scenarios})
    if unknown:
        parser.error(f"unknown continuation scenario(s): {', '.join(unknown)}")
    if not selected:
        parser.error("no continuation scenarios selected")

    model_names = args.model or ["mock-planner-v1"]
    model_configs = [_model(value) for value in model_names]
    runner = ContinuationEvalRunner(model_configs, result_db=args.db)
    metadata, results = runner.run(
        selected,
        resume_run_id=args.resume_run_id,
        max_cases=args.max_cases,
    )
    storage = AgentEvalStorage(args.db)
    try:
        storage.save(metadata, results)
    finally:
        storage.close()

    summary = continuation_summary(results)
    result_dicts = [result.model_dump(mode="json") for result in results]
    report = {
        "suite": "planner_continuation",
        "suite_version": metadata.suite_version,
        "run": metadata.model_dump(mode="json"),
        "summary": summary,
        "cases": result_dicts,
        "routing_mutated": False,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    output_path.with_suffix(".md").write_text(
        _markdown(summary, result_dicts, model_names=model_names, scenario_ids=[scenario.id for scenario in selected]),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output_path), "markdown": str(output_path.with_suffix('.md')), "summary": summary}, indent=2, sort_keys=True))
    if metadata.interrupted:
        return 2
    return 0 if all(result.task_success for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
