"""Evaluation infrastructure for ShopStack.

Provides benchmark result recording, baseline comparison, and regression
detection so accuracy claims are CI-assertable, not just prose.

See ``bench_results.py`` for the core API and ``bench_baseline.json``
for the committed known-good values.
"""
from shopstack.eval.bench_results import (
    BASELINE_PATH,
    BenchmarkResult,
    RegressionReport,
    check_regression,
    load_baseline,
    save_result,
)

__all__ = [
    "BASELINE_PATH",
    "BenchmarkResult",
    "RegressionReport",
    "check_regression",
    "load_baseline",
    "save_result",
]
