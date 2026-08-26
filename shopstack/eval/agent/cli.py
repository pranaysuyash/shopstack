"""Command line interface for ShopStack agent evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shopstack.eval.agent.aggregate import summarize
from shopstack.eval.agent.loader import assert_valid_suite, load_scenarios, validate_suite
from shopstack.eval.agent.recommend import recommend
from shopstack.eval.agent.report import to_csv, to_json, to_markdown
from shopstack.eval.agent.runner import AgentEvalRunner
from shopstack.eval.agent.schema import EvalModelConfig
from shopstack.eval.agent.storage import AgentEvalStorage


def _db_path(value: str | None) -> str:
    if value:
        return value
    from shopstack.config import settings
    return settings.db_path


def _model(value: str) -> EvalModelConfig:
    backend = "openai" if value.startswith("gpt-") else "mock" if value.startswith("mock") else "local"
    # The evaluator deliberately gives GPT-5 reasoning calls more room than
    # the compact production-shaped default, so truncation is not mis-scored
    # as planner quality. Cost remains recorded per call.
    generation = {"max_tokens": 768 if backend == "openai" else 256, "temperature": 0.0}
    if backend == "openai" and value.startswith("gpt-5"):
        generation["reasoning_effort"] = "high"
    return EvalModelConfig(key=value.replace("/", "_"), requested_model=value, backend=backend, provider=backend, generation=generation)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shopstack.eval.agent.cli")
    parser.add_argument("--db", help="SQLite path for agent-eval results")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("list-scenarios")
    checks = sub.add_parser("check-models")
    checks.add_argument("--model", action="append", default=[])
    run = sub.add_parser("run")
    run.add_argument("--model", action="append", default=[])
    run.add_argument("--scenario", action="append")
    run.add_argument("--tier", choices=["core", "challenge"])
    run.add_argument("--dry-run", action="store_true")
    sub.add_parser("summarize")
    export = sub.add_parser("export")
    export.add_argument("--format", choices=["markdown", "json", "csv"], default="markdown")
    export.add_argument("--output")
    args = parser.parse_args(argv)
    scenarios = load_scenarios()
    if args.command == "validate":
        errors = validate_suite(scenarios)
        if errors:
            print("\n".join(errors))
            return 1
        print(f"valid: {len(scenarios)} scenarios, {len({s.id.split('-')[0] for s in scenarios})} groups")
        return 0
    if args.command == "list-scenarios":
        for scenario in scenarios:
            print(f"{scenario.id}\t{scenario.tier.value}\t{scenario.language.value}\t{scenario.title}")
        return 0
    if args.command == "check-models":
        import os
        for value in args.model or ["mock-planner-v1"]:
            config = _model(value)
            available = config.backend == "mock"
            status = "available" if available else "unavailable"
            if config.backend == "openai":
                try:
                    from shopstack.providers.openai_provider import OpenAIProvider
                    provider = OpenAIProvider(
                        api_key=os.environ.get("SHOPSTACK_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
                        model=config.requested_model,
                    )
                    available = bool(provider.available)
                    status = "available" if available else "provider_unavailable"
                except Exception:
                    status = "provider_unavailable"
            print(json.dumps({"key": config.key, "requested_model": config.requested_model, "backend": config.backend, "status": status, "available": available}, sort_keys=True))
        return 0
    storage = AgentEvalStorage(_db_path(args.db))
    try:
        if args.command == "run":
            selected = [s for s in scenarios if (not args.scenario or s.id in args.scenario) and (not args.tier or s.tier.value == args.tier)]
            assert_valid_suite(scenarios)  # validate the committed corpus before filtering
            model_names = args.model or ["mock-planner-v1"]
            if args.dry_run:
                print(json.dumps({"models": model_names, "scenarios": [s.id for s in selected], "count": len(selected)}, indent=2))
                return 0
            runner = AgentEvalRunner([_model(value) for value in model_names], result_db=_db_path(args.db))
            metadata, results = runner.run(selected, on_result=lambda result: print(f"{result.model_key} {result.scenario_id}: {result.status.value}"))
            storage.save(metadata, results)
            summary = summarize(results, selected)
            decision = recommend(summary)
            print(to_markdown(summary, decision))
            return 0
        rows = storage.results()
        summary = summarize(rows, scenarios)
        decision = recommend(summary)
        if args.command == "summarize":
            print(to_markdown(summary, decision))
            return 0
        content = {"markdown": to_markdown(summary, decision), "json": to_json(summary, decision), "csv": to_csv(summary)}[args.format]
        if args.output:
            Path(args.output).write_text(content, encoding="utf-8")
        else:
            print(content)
        return 0
    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
