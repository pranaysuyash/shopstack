from __future__ import annotations

from shopstack.model_lab.frontier import (
    FrontierModelResult,
    FrontierModelSpec,
    FrontierPromptResult,
    render_markdown_report,
)


def test_render_markdown_report_includes_models() -> None:
    result = FrontierModelResult(
        stage="planner",
        candidate_id="qwen3.5-9b",
        hf_id="Qwen/Qwen3.5-9B",
        params_b=9.0,
        runtime="transformers-int4",
        notes="frontier candidate",
        platform="hf-inference",
        load_time_s=None,
        accuracy_pct=40.0,
        latency_mean_s=3.349,
        latency_p50_s=3.361,
        prompt_count=20,
        details=[
            FrontierPromptResult(
                prompt_name="add_milk",
                latency_s=3.325,
                output_tokens=154,
                tokens_per_s=46.3,
                correct=True,
                parsed_tools=["add_inventory_item"],
                expected_tools=["add_inventory_item"],
                raw_output_preview="[]",
            )
        ],
        source="shopstack.model_lab.frontier",
        benchmarked_at="2026-06-13T00:00:00+00:00",
        model_usage={"prompt_tokens": 10},
    )
    md = render_markdown_report([result], "Frontier")
    assert "# Frontier" in md
    assert "`qwen3.5-9b`" in md
    assert "40.0%" in md


def test_frontier_model_spec_is_serializable() -> None:
    spec = FrontierModelSpec(
        stage="planner",
        model_id="qwen3.6-35b-a3b",
        hf_model="Qwen/Qwen3.6-35B-A3B",
        params_b=35.0,
        runtime="transformers",
    )
    assert spec.model_id == "qwen3.6-35b-a3b"
    assert spec.hf_model.endswith("35B-A3B")
