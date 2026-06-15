"""Benchmark results recording and regression detection (EVAL-1).

This module provides the infrastructure to convert accuracy claims from
prose into CI-assertable quality gates. It defines:

1. ``BenchmarkResult`` — a typed record of a single benchmark run
   (model, capability, metric, value, timestamp, evidence).
2. ``save_result`` — appends a result to a gitignored JSONL file.
3. ``load_baseline`` — reads the committed baseline (known-good values).
4. ``check_regression`` — compares a result against the baseline and
   returns whether accuracy dropped beyond a tolerance.

Design principles (motto §0.5 evidence tiers, §0.9 model/routing):
- The baseline is git-tracked (``bench_baseline.json``) so it's the
  shared, reviewed, known-good state.
- Run results are gitignored (``.bench_results.jsonl``) — they're
  ephemeral per-run artifacts.
- The regression check is non-blocking by default (returns a report)
  so CI can surface drift without failing on a first run. The caller
  (a test) decides whether to assert hard.
- Every result carries an ``evidence`` field (test path or bench script)
  so claims trace to their source (Tier 2+ traceability).

Usage in a benchmark script::

    from shopstack.eval.bench_results import BenchmarkResult, save_result

    result = BenchmarkResult(
        model="ministral-8b-instruct",
        capability="planner_tool_calling",
        metric="accuracy",
        value=0.95,
        sample_size=10,
        evidence="benchmarks/bench_planner_tool_calling.py",
    )
    save_result(result)

Usage in a regression test::

    from shopstack.eval.bench_results import load_baseline, check_regression

    def test_planner_accuracy_no_regression():
        baseline = load_baseline()["planner_tool_calling"]
        latest = ...  # run or load the latest result
        report = check_regression(baseline, latest, tolerance=0.10)
        assert report.passed, report.summary
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# The baseline is git-tracked — it's the reviewed known-good state.
BASELINE_PATH = Path(__file__).parent / "bench_baseline.json"
# Run results are ephemeral — gitignored, per-run.
RESULTS_PATH = Path(__file__).parent.parent.parent / ".bench_results.jsonl"


@dataclass(frozen=True)
class BenchmarkResult:
    """A single benchmark measurement.

    Attributes:
        model: The model_id (must match a model_registry entry).
        capability: The capability area (planner_tool_calling, ocr_hindi, etc.).
        metric: What was measured (accuracy, latency_ms, wer, iou, etc.).
        value: The measured value.
        sample_size: Number of test cases evaluated.
        evidence: File path of the benchmark script or test that produced this.
        timestamp: ISO-8601 UTC of when the measurement was taken.
        notes: Optional context (run environment, precision, etc.).
    """

    model: str
    capability: str
    metric: str
    value: float
    sample_size: int = 0
    evidence: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""


@dataclass
class RegressionReport:
    """The result of comparing a measurement against a baseline."""

    capability: str
    metric: str
    baseline_value: float
    measured_value: float
    tolerance: float
    passed: bool
    summary: str

    def __bool__(self) -> bool:
        """A report is truthy when the regression check passed."""
        return self.passed


def save_result(result: BenchmarkResult, path: Path | None = None) -> None:
    """Append a benchmark result to the JSONL results file.

    Args:
        result: The measurement to record.
        path: Override the default results path (for testing).
    """
    target = path or RESULTS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result)) + "\n")


def load_baseline(path: Path | None = None) -> dict[str, dict[str, float]]:
    """Load the committed baseline of known-good benchmark values.

    Returns a dict keyed by capability, each containing metric → value.
    Example::

        {
            "planner_tool_calling": {"accuracy": 0.90, "sample_size": 10},
            "ocr_devanagari": {"accuracy": 0.0, "sample_size": 15},
        }
    """
    target = path or BASELINE_PATH
    if not target.exists():
        return {}
    with open(target, encoding="utf-8") as f:
        return json.load(f)


def check_regression(
    baseline_entry: dict[str, float],
    measured: BenchmarkResult,
    tolerance: float = 0.10,
) -> RegressionReport:
    """Check whether a measurement regressed beyond tolerance.

    For "higher is better" metrics (accuracy, iou), regression is when
    measured < baseline × (1 - tolerance). For "lower is better" metrics
    (wer, latency_ms), regression is when measured > baseline × (1 + tolerance).

    Args:
        baseline_entry: The baseline dict for this capability (metric → value).
        measured: The latest BenchmarkResult.
        tolerance: Allowed fractional degradation (0.10 = 10% drop OK).

    Returns:
        A RegressionReport with ``passed`` and a human-readable summary.
    """
    lower_is_better = measured.metric in ("wer", "latency_ms", "cost_usd")
    baseline_value = baseline_entry.get(measured.metric, 0.0)

    if lower_is_better:
        threshold = baseline_value * (1 + tolerance)
        passed = measured.value <= threshold
        direction = f"≤ {threshold:.4f} (baseline {baseline_value:.4f} × 1+{tolerance})"
    else:
        threshold = baseline_value * (1 - tolerance)
        passed = measured.value >= threshold
        direction = f"≥ {threshold:.4f} (baseline {baseline_value:.4f} × 1-{tolerance})"

    status = "PASS" if passed else "REGRESSION"
    summary = (
        f"[{status}] {measured.capability}/{measured.metric}: "
        f"measured {measured.value:.4f}, expected {direction}. "
        f"Model: {measured.model}, evidence: {measured.evidence}"
    )
    return RegressionReport(
        capability=measured.capability,
        metric=measured.metric,
        baseline_value=baseline_value,
        measured_value=measured.value,
        tolerance=tolerance,
        passed=passed,
        summary=summary,
    )
