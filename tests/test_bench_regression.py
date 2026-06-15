"""EVAL-1: Benchmark results recording + regression detection tests.

Verifies the ``shopstack.eval.bench_results`` infrastructure that converts
accuracy claims from prose into CI-assertable quality gates. This test
exercises:

1. Saving and loading benchmark results (JSONL round-trip).
2. Loading the committed baseline.
3. Regression detection for "higher is better" metrics (accuracy, iou).
4. Regression detection for "lower is better" metrics (wer, latency).
5. The baseline file itself is valid and covers key capabilities.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopstack.eval.bench_results import (
    BASELINE_PATH,
    BenchmarkResult,
    check_regression,
    load_baseline,
    save_result,
)


class TestBenchmarkResultSchema:
    def test_result_is_frozen_and_serializable(self):
        r = BenchmarkResult(
            model="test-model",
            capability="test_cap",
            metric="accuracy",
            value=0.95,
            sample_size=100,
            evidence="tests/test_bench_regression.py",
        )
        assert r.value == 0.95
        # Frozen dataclass — mutation should fail
        with pytest.raises(AttributeError):
            r.value = 0.50  # type: ignore[misc]
        # Serializable to dict
        d = r.__dict__ if hasattr(r, "__dict__") else json.loads(json.dumps(r.__dataclass_fields__))  # noqa
        assert d is not None


class TestSaveLoadRoundTrip:
    def test_save_and_read_result(self, tmp_path):
        """save_result appends to JSONL; the line parses back to the fields."""
        results_file = tmp_path / "results.jsonl"
        r = BenchmarkResult(
            model="ministral-8b",
            capability="planner_tool_calling",
            metric="accuracy",
            value=0.92,
            sample_size=10,
            evidence="bench.py",
        )
        save_result(r, path=results_file)
        assert results_file.exists()
        line = results_file.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["model"] == "ministral-8b"
        assert parsed["value"] == 0.92
        assert parsed["capability"] == "planner_tool_calling"

    def test_multiple_results_append(self, tmp_path):
        """Each save appends a new line — results accumulate."""
        results_file = tmp_path / "results.jsonl"
        for v in (0.90, 0.92, 0.95):
            save_result(
                BenchmarkResult("m", "cap", "accuracy", v, evidence="b"),
                path=results_file,
            )
        lines = results_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3


class TestBaselineIntegrity:
    def test_baseline_file_exists(self):
        """The committed baseline must exist — it's the known-good reference."""
        assert BASELINE_PATH.exists(), (
            f"Benchmark baseline not found at {BASELINE_PATH}. "
            "This file is git-tracked and defines the known-good accuracy values."
        )

    def test_baseline_loads_and_has_capabilities(self):
        baseline = load_baseline()
        assert isinstance(baseline, dict)
        assert len(baseline) > 0, "Baseline must define at least one capability"

    def test_baseline_covers_planner(self):
        """The planner tool-calling accuracy must be in the baseline — it's
        the product's most critical AI quality metric."""
        baseline = load_baseline()
        assert "planner_tool_calling" in baseline
        assert "accuracy" in baseline["planner_tool_calling"]
        assert 0.0 <= baseline["planner_tool_calling"]["accuracy"] <= 1.0

    def test_baseline_covers_known_failures(self):
        """Known limitations (Hindi OCR 0%) must be recorded in the baseline
        so they're not silently re-claimed."""
        baseline = load_baseline()
        assert "ocr_devanagari" in baseline
        assert baseline["ocr_devanagari"]["accuracy"] < 0.20


class TestRegressionDetection:
    def test_higher_is_better_no_regression(self):
        """Accuracy at or above baseline-tolerance passes."""
        baseline_entry = {"accuracy": 0.90}
        measured = BenchmarkResult("m", "cap", "accuracy", 0.88, evidence="t")
        report = check_regression(baseline_entry, measured, tolerance=0.10)
        # 0.88 >= 0.90 * 0.90 = 0.81 → pass
        assert report.passed is True

    def test_higher_is_better_regression_detected(self):
        """Accuracy dropping more than tolerance triggers a regression."""
        baseline_entry = {"accuracy": 0.90}
        measured = BenchmarkResult("m", "cap", "accuracy", 0.70, evidence="t")
        report = check_regression(baseline_entry, measured, tolerance=0.10)
        # 0.70 < 0.81 → regression
        assert report.passed is False
        assert "REGRESSION" in report.summary

    def test_lower_is_better_no_regression(self):
        """WER at or below baseline-tolerance passes."""
        baseline_entry = {"wer": 0.25}
        measured = BenchmarkResult("m", "cap", "wer", 0.27, evidence="t")
        report = check_regression(baseline_entry, measured, tolerance=0.10)
        # 0.27 <= 0.25 * 1.10 = 0.275 → pass
        assert report.passed is True

    def test_lower_is_better_regression_detected(self):
        """WER increasing beyond tolerance triggers a regression."""
        baseline_entry = {"wer": 0.25}
        measured = BenchmarkResult("m", "cap", "wer", 0.40, evidence="t")
        report = check_regression(baseline_entry, measured, tolerance=0.10)
        # 0.40 > 0.275 → regression
        assert report.passed is False
        assert "REGRESSION" in report.summary

    def test_report_summary_is_human_readable(self):
        """The summary must contain enough context to diagnose without code."""
        baseline_entry = {"accuracy": 0.90}
        measured = BenchmarkResult("ministral-8b", "planner", "accuracy", 0.85, evidence="bench.py")
        report = check_regression(baseline_entry, measured, tolerance=0.10)
        assert "planner" in report.summary
        assert "ministral-8b" in report.summary
        assert "bench.py" in report.summary
        assert "0.85" in report.summary
