#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
from typing import Iterable

from shopstack.model_lab.frontier import (
    FrontierModelResult,
    FrontierModelSpec,
    render_markdown_report,
    run_planner_frontier_benchmark,
    write_results_jsonl,
)


DEFAULT_MODELS = [
    FrontierModelSpec(
        stage="planner",
        model_id="qwen3.5-9b",
        hf_model="Qwen/Qwen3.5-9B",
        params_b=9.0,
        runtime="transformers-int4",
        notes="HF frontier planner candidate (live-checked on 13-Jun-2026).",
    ),
    FrontierModelSpec(
        stage="planner",
        model_id="qwen3.6-35b-a3b",
        hf_model="Qwen/Qwen3.6-35B-A3B",
        params_b=35.0,
        runtime="transformers",
        notes="HF frontier heavy planner candidate (live-checked on 13-Jun-2026).",
    ),
]


def _parse_models(raw: list[str]) -> list[FrontierModelSpec]:
    specs: list[FrontierModelSpec] = []
    known = {spec.model_id: spec for spec in DEFAULT_MODELS}
    for item in raw:
        if item in known:
            specs.append(known[item])
            continue
        if ":" not in item:
            raise SystemExit(f"Unknown model id '{item}'. Use one of: {', '.join(sorted(known))} or model_id:hf_repo:params")
        parts = item.split(":")
        if len(parts) < 3:
            raise SystemExit(f"Model override '{item}' must look like model_id:hf_repo:params")
        model_id, hf_repo, params = parts[0], parts[1], parts[2]
        specs.append(
            FrontierModelSpec(
                stage="planner",
                model_id=model_id,
                hf_model=hf_repo,
                params_b=float(params),
                runtime="transformers",
                notes="custom CLI override",
            )
        )
    return specs


def run(models: Iterable[FrontierModelSpec], output_dir: Path) -> list[FrontierModelResult]:
    results: list[FrontierModelResult] = []
    for model in models:
        result = run_planner_frontier_benchmark(model, api_key=os.getenv("SHOPSTACK_HF_API_KEY") or os.getenv("HF_API_KEY"))
        results.append(result)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = output_dir / f"frontier_planner_{stamp}.jsonl"
    md_path = output_dir / f"frontier_planner_{stamp}.md"
    write_results_jsonl(results, jsonl_path)
    md_path.write_text(render_markdown_report(results, "ShopStack Frontier Planner Sweep"), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ShopStack frontier planner sweep against Hugging Face models.")
    parser.add_argument(
        "--output-dir",
        default=os.getenv("SHOPSTACK_MODEL_LAB_OUTPUT_DIR", "benchmarks/model_lab/results"),
        help="Directory to write JSONL + markdown results.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Model id to benchmark. Use multiple times. Defaults to qwen3.5-9b and qwen3.6-35b-a3b.",
    )
    args = parser.parse_args()

    models = _parse_models(args.model) if args.model else DEFAULT_MODELS
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = run(models, output_dir)
    for result in results:
        print(
            f"{result.candidate_id}: {result.accuracy_pct}% | "
            f"{result.latency_mean_s}s mean | {result.hf_id}"
        )


if __name__ == "__main__":
    main()
