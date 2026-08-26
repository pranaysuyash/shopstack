"""Evaluation infrastructure for ShopStack.

Two complementary layers:

* **Batch benchmarks** (offline, CI) — :mod:`bench_results` records
  aggregate results from benchmark scripts and detects regression
  against ``bench_baseline.json``. Used in CI gates.
* **Per-call o/p eval** (live, app) — :mod:`recorder`, :mod:`checks`,
  :mod:`storage`, :mod:`aggregator` capture every model call as it
  happens, run deterministic online checks, persist to JSONL +
  SQLite, and surface per-route regressions in the UI. Driven by
  ``record_model_call(...)`` at the call site.

See ``Docs/architecture/MODEL_OUTPUT_EVAL.md`` for the design.
"""
from shopstack.eval.aggregator import (
    DEFAULT_ROUTE_BASELINE_PATH,
    DEFAULT_TOLERANCE,
    FAILURE_OUTCOMES,
    RouteRegression,
    RouteStats,
    aggregate_by_route,
    aggregate_records,
    load_route_baseline,
    route_regression_for_all,
    route_regression_report,
    save_route_baseline,
)
from shopstack.eval.bench_results import (
    BASELINE_PATH,
    BenchmarkResult,
    RegressionReport,
    check_regression,
    load_baseline,
    save_result,
)
from shopstack.eval.checks import (
    DEFAULT_COST_BUDGET_USD,
    DEFAULT_DUPLICATE_THRESHOLD,
    DEFAULT_DUPLICATE_TIME_WINDOW_S,
    DEFAULT_DUPLICATE_WINDOW,
    DEFAULT_LATENCY_BUDGET_MS,
    DEFAULT_MAX_OUTPUT_LENGTH,
    DEFAULT_MODEL_CONTEXT_TOKENS,
    EvalCheckRegistry,
    check_cost_budget,
    check_execution_success,
    check_latency_budget,
    check_length_sanity,
    check_non_duplicate,
    check_parse_success,
    check_tokens_within_context,
    default_registry,
)
from shopstack.eval.recorder import (
    CAP_EMBEDDINGS,
    CAP_GROUNDING,
    CAP_IMAGE_GEN,
    CAP_OCR_RECEIPT,
    CAP_PLANNER_TOOL_CALLING,
    CAP_SEGMENTATION,
    CAP_STT,
    CAP_TTS,
    CAP_VISION_PRODUCT_RECOGNITION,
    OUTCOME_BLOCKED,
    OUTCOME_EMPTY,
    OUTCOME_EXCEPTION,
    OUTCOME_PARSE_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
    OUTCOME_TOOL_FAILURE,
    OUTCOMES,
    SHAPE_BYTES,
    SHAPE_RAW,
    SHAPE_STRUCTURED,
    SHAPE_TEXT,
    SHAPE_TOOL_CALLS,
    VALID_SHAPES,
    CheckResult,
    ModelCallRecord,
    ModelCallRecorder,
    record_model_call,
)
from shopstack.eval.redact import redact_field, redact_text
from shopstack.eval.storage import (
    DEFAULT_JSONL_PATH,
    EVAL_RECORDS_DDL,
    EVAL_RECORDS_SCHEMA_VERSION,
    JsonlSink,
    SqliteSink,
)

__all__ = [
    # batch benchmarks
    "BASELINE_PATH",
    "BenchmarkResult",
    "RegressionReport",
    "check_regression",
    "load_baseline",
    "save_result",
    # per-call recorder
    "CAP_EMBEDDINGS",
    "CAP_GROUNDING",
    "CAP_IMAGE_GEN",
    "CAP_OCR_RECEIPT",
    "CAP_PLANNER_TOOL_CALLING",
    "CAP_SEGMENTATION",
    "CAP_STT",
    "CAP_TTS",
    "CAP_VISION_PRODUCT_RECOGNITION",
    "CheckResult",
    "ModelCallRecord",
    "ModelCallRecorder",
    "OUTCOMES",
    "OUTCOME_BLOCKED",
    "OUTCOME_EMPTY",
    "OUTCOME_EXCEPTION",
    "OUTCOME_PARSE_ERROR",
    "OUTCOME_SUCCESS",
    "OUTCOME_TIMEOUT",
    "OUTCOME_TOOL_FAILURE",
    "SHAPE_BYTES",
    "SHAPE_RAW",
    "SHAPE_STRUCTURED",
    "SHAPE_TEXT",
    "SHAPE_TOOL_CALLS",
    "VALID_SHAPES",
    "record_model_call",
    # checks
    "DEFAULT_COST_BUDGET_USD",
    "DEFAULT_DUPLICATE_THRESHOLD",
    "DEFAULT_DUPLICATE_TIME_WINDOW_S",
    "DEFAULT_DUPLICATE_WINDOW",
    "DEFAULT_LATENCY_BUDGET_MS",
    "DEFAULT_MAX_OUTPUT_LENGTH",
    "DEFAULT_MODEL_CONTEXT_TOKENS",
    "EvalCheckRegistry",
    "check_cost_budget",
    "check_execution_success",
    "check_latency_budget",
    "check_length_sanity",
    "check_non_duplicate",
    "check_parse_success",
    "check_tokens_within_context",
    "default_registry",
    # aggregator / regression
    "DEFAULT_ROUTE_BASELINE_PATH",
    "DEFAULT_TOLERANCE",
    "FAILURE_OUTCOMES",
    "RouteRegression",
    "RouteStats",
    "aggregate_by_route",
    "aggregate_records",
    "load_route_baseline",
    "route_regression_for_all",
    "route_regression_report",
    "save_route_baseline",
    # storage
    "DEFAULT_JSONL_PATH",
    "EVAL_RECORDS_DDL",
    "EVAL_RECORDS_SCHEMA_VERSION",
    "JsonlSink",
    "SqliteSink",
    # redact
    "redact_field",
    "redact_text",
]
