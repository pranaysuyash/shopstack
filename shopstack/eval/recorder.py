"""Model call recorder and per-call record schema (EVAL-OP-1).

The recorder is the central observability surface for every model
interaction in ShopStack. It captures:

* **route** — both domain (what user action) and code (where in the
  codebase), per the stacked-route design (Docs/architecture/MODEL_OUTPUT_EVAL.md §2.2).
* **prompt / output** — redacted, with full PII ruleset reused from
  :mod:`shopstack.traces.export`.
* **timing** — wall-clock latency, token counts, model id.
* **outcome** — success, empty, parse error, timeout, exception, blocked.
* **eval verdict** — per-check pass/fail at capture time (filled in
  by :mod:`shopstack.eval.checks`).

A typical call site uses the context manager:

    from shopstack.eval.recorder import record_model_call

    with record_model_call(
        domain_route="planner",
        capability="planner_tool_calling",
        capability_expected_shape="tool_calls",
    ) as rec:
        result = provider.plan({"prompt": prompt, "system": system_prompt, ...})
        rec.set_output(result)

The recorder auto-resolves the code route from ``inspect.stack()`` if
not provided, redacts the prompt before persistence, runs the online
checks, and writes to both the JSONL sink and the SQLite table.

The recorder never raises into the hot path: any error during capture
is logged and swallowed. The model call itself runs to completion
whether or not the recorder works.
"""
from __future__ import annotations

import inspect
import logging
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from shopstack.eval.redact import redact_field, redact_text

logger = logging.getLogger(__name__)


# Outcome taxonomy — closed set so aggregations are unambiguous.
OUTCOME_SUCCESS = "success"
OUTCOME_EMPTY = "empty"
OUTCOME_PARSE_ERROR = "parse_error"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_EXCEPTION = "exception"
OUTCOME_BLOCKED = "blocked"
OUTCOMES = {
    OUTCOME_SUCCESS,
    OUTCOME_EMPTY,
    OUTCOME_PARSE_ERROR,
    OUTCOME_TIMEOUT,
    OUTCOME_EXCEPTION,
    OUTCOME_BLOCKED,
}


# Stable capability vocabulary. Not a hard enum — new routes can add
# new capabilities — but the common values are listed here for
# discoverability and to make route_baseline.json self-documenting.
CAP_PLANNER_TOOL_CALLING = "planner_tool_calling"
CAP_VISION_PRODUCT_RECOGNITION = "vision_product_recognition"
CAP_STT = "stt"
CAP_TTS = "tts"
CAP_OCR_RECEIPT = "ocr_receipt"
CAP_EMBEDDINGS = "embeddings"
CAP_SEGMENTATION = "segmentation"
CAP_GROUNDING = "grounding"
CAP_IMAGE_GEN = "image_gen"

# Expected output shapes — used by the parse_success check.
SHAPE_TOOL_CALLS = "tool_calls"
SHAPE_TEXT = "text"
SHAPE_STRUCTURED = "structured"
SHAPE_BYTES = "bytes"  # for TTS / image outputs
SHAPE_RAW = "raw"  # don't try to parse

VALID_SHAPES = {SHAPE_TOOL_CALLS, SHAPE_TEXT, SHAPE_STRUCTURED, SHAPE_BYTES, SHAPE_RAW}


@dataclass
class CheckResult:
    """Result of a single online eval check.

    Attributes:
        check: The check name (e.g., "parse_success", "latency_budget").
        passed: Whether the check passed.
        score: A float in [0, 1] (1.0 = perfect, 0.0 = total fail).
        notes: Human-readable explanation.
    """

    check: str
    passed: bool
    score: float
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelCallRecord:
    """A single model call's full record (post-capture, post-eval).

    Designed to be serializable to both JSON (for the JSONL sink) and
    a flat SQLite row (for the eval table). All fields are simple
    types — no nested objects beyond dicts/lists/strings.
    """

    # Identity / correlation
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    user_id: str = ""
    household_id: str = ""
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Route — both fields per the stacked-route design
    domain_route: str = ""  # e.g., "planner", "market_lens"
    code_route: str = ""  # e.g., "planner.engine.process:81"

    # Capability / model
    capability: str = ""  # e.g., "planner_tool_calling"
    capability_expected_shape: str = SHAPE_RAW
    model: str = ""
    backend: str = ""  # e.g., "local", "openai", "mock"
    provider_name: str = ""

    # Prompt / output (both redacted at capture)
    prompt: str = ""
    output: str = ""
    prompt_length: int = 0
    output_length: int = 0

    # Timing / usage
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    # Outcome
    outcome: str = OUTCOME_SUCCESS
    error: str = ""

    # Eval verdict (filled by the recorder after capture)
    eval_passed: bool = True
    eval_score: float = 1.0
    eval_check_results: list[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["eval_check_results"] = [c.to_dict() for c in self.eval_check_results]
        return d

    def short_summary(self) -> dict[str, Any]:
        """Compact dict for log lines and the UI list view."""
        return {
            "record_id": self.record_id,
            "started_at": self.started_at,
            "domain_route": self.domain_route,
            "code_route": self.code_route,
            "capability": self.capability,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "outcome": self.outcome,
            "eval_passed": self.eval_passed,
            "eval_score": self.eval_score,
        }


class _ActiveCall:
    """The live state the context manager mutates during a call.

    The recorder is intentionally dumb: it holds the in-flight record,
    lets the caller attach prompt/output/error, and resolves the final
    record on exit. It does not touch the provider or run model logic.
    """

    def __init__(
        self,
        recorder: "ModelCallRecorder",
        record: ModelCallRecord,
    ) -> None:
        self._recorder = recorder
        self.record = record
        self._started = time.monotonic()
        self._set_started_at()

    def _set_started_at(self) -> None:
        # The dataclass default_factory ran at construction, but we
        # want the timestamp to be the *start* of the call, not the
        # creation of the dataclass. For most uses these are within
        # microseconds; we still expose this hook for future precision.
        self.record.started_at = datetime.now(timezone.utc).isoformat()

    def set_prompt(self, prompt: str) -> None:
        """Set the redacted prompt and its length."""
        if prompt is None:
            prompt = ""
        self.record.prompt = redact_text(prompt)
        self.record.prompt_length = len(prompt)

    def set_output(self, output: Any) -> None:
        """Set the redacted output and its length, capture shape hint.

        Accepts any type because provider results are heterogeneous
        (str, dict with text/tool_calls, list of tool calls, bytes).
        The actual shape check is the recorder's job, not ours.
        """
        if output is None:
            self.record.output = ""
            self.record.output_length = 0
            return

        if isinstance(output, (bytes, bytearray)):
            self.record.output = f"<bytes len={len(output)}>"
            self.record.output_length = len(output)
            return

        text = output if isinstance(output, str) else str(output)
        self.record.output = redact_text(text)
        self.record.output_length = len(text)

    def set_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        model: str = "",
        backend: str = "",
        provider_name: str = "",
    ) -> None:
        if input_tokens:
            self.record.input_tokens = int(input_tokens)
        if output_tokens:
            self.record.output_tokens = int(output_tokens)
        if cost_usd:
            self.record.cost_usd = float(cost_usd)
        if model:
            self.record.model = model
        if backend:
            self.record.backend = backend
        if provider_name:
            self.record.provider_name = provider_name

    def set_outcome(
        self,
        outcome: str,
        error: str = "",
    ) -> None:
        if outcome not in OUTCOMES:
            logger.warning("Unknown outcome %r, coercing to 'exception'", outcome)
            outcome = OUTCOME_EXCEPTION
        self.record.outcome = outcome
        if error:
            self.record.error = redact_text(str(error))

    def set_code_route(self, code_route: str) -> None:
        if code_route:
            self.record.code_route = code_route

    def set_trace_id(self, trace_id: str) -> None:
        if trace_id:
            self.record.trace_id = trace_id

    def set_household(self, user_id: str = "", household_id: str = "") -> None:
        if user_id:
            self.record.user_id = user_id
        if household_id:
            self.record.household_id = household_id

    # Context manager protocol — ``record_model_call()`` returns one of
    # these directly, so we implement __enter__/__exit__ to make it
    # usable as ``with record_model_call(...) as rec:``. The exit runs
    # :meth:`finish` (which is idempotent for the typical case; the
    # record is the same instance both inside and outside the block).

    def __enter__(self) -> "_ActiveCall":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # If the caller's block raised, record the exception outcome
        # and finish. We never re-raise — the recorder is best-effort.
        if exc_type is not None and self.record.outcome == OUTCOME_SUCCESS:
            self.set_outcome(OUTCOME_EXCEPTION, f"{exc_type.__name__}: {exc}")
        self.finish()

    def finish(self) -> ModelCallRecord:
        """Compute latency, run online checks, persist, return final record."""
        elapsed = (time.monotonic() - self._started) * 1000.0
        self.record.latency_ms = round(elapsed, 3)
        try:
            self._recorder._finalize(self.record)
        except Exception:  # pragma: no cover - the recorder must never raise
            logger.warning("recorder finalize failed", exc_info=True)
        return self.record


# Filesystem path regex — used by the auto code_route resolver to pick
# a clean caller frame (skip frames inside the eval package itself).
_THIS_DIR = __file__.rsplit("/", 1)[0] + "/"
_FRAME_SKIP_RE = re.compile(
    r"(shopstack/eval/|tests/|/lib/python[0-9.]+/)"
)
# Module names of the test runners / Python bootstrap we always skip.
_FRAME_SKIP_MODULES = frozenset({
    "runpy",
    "pytest",
    "_pytest",
    "pydev",
    "IPython",
    "traceback",
})


def _resolve_code_route(skip_frames: int = 1) -> str:
    """Walk the call stack and return ``module.func:line`` for the first
    non-eval, non-test, non-stdlib frame.

    Strategy: prefer frames whose ``__name__`` starts with
    ``shopstack.`` (the app). If none, fall back to the first frame
    that is not in :data:`_FRAME_SKIP_MODULES` and does not match the
    path skip regex.

    Args:
        skip_frames: how many frames to skip from the top (caller's caller).
    """
    try:
        frame = inspect.currentframe()
    except Exception:
        return ""
    # skip the recorder's own frame plus caller-provided skips
    for _ in range(skip_frames + 1):
        if frame is None:
            return ""
        frame = frame.f_back

    preferred: tuple[str, int, str] | None = None
    fallback: tuple[str, int, str] | None = None
    while frame is not None:
        module = frame.f_globals.get("__name__", "") or ""
        filename = frame.f_code.co_filename or ""
        func = frame.f_code.co_name
        lineno = frame.f_lineno

        if not module or module in _FRAME_SKIP_MODULES or _FRAME_SKIP_RE.search(filename):
            frame = frame.f_back
            continue

        candidate = (module, lineno, func)
        if module.startswith("shopstack."):
            # Keep the *first* shopstack frame (closest to the call
            # site). Return immediately — deeper frames belong to
            # internal helpers, not the route.
            return f"{module}.{func}:{lineno}"
        if fallback is None:
            fallback = candidate
        frame = frame.f_back

    if preferred:
        module, lineno, func = preferred
        return f"{module}.{func}:{lineno}"
    if fallback:
        module, lineno, func = fallback
        return f"{module}.{func}:{lineno}"
    return ""


class ModelCallRecorder:
    """Singleton recorder; resolves sinks on first use, persists records.

    The recorder is process-global. A test that wants isolation can
    instantiate its own recorder and pass it to the call sites.
    """

    _instance: "ModelCallRecorder | None" = None

    def __init__(
        self,
        jsonl_sink: Any | None = None,
        sqlite_sink: Any | None = None,
        check_registry: Any | None = None,
    ) -> None:
        # Imports are deferred to keep the recorder import-cheap.
        from shopstack.eval.storage import JsonlSink, SqliteSink
        from shopstack.eval.checks import EvalCheckRegistry, default_registry

        self._jsonl = jsonl_sink or JsonlSink()
        self._sqlite = sqlite_sink or SqliteSink()
        self._checks: Any = check_registry or default_registry()

    @classmethod
    def instance(cls) -> "ModelCallRecorder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Clear the singleton — for tests."""
        cls._instance = None

    def _finalize(self, record: ModelCallRecord) -> None:
        # 1. run online checks (deterministic, capture-time)
        try:
            check_results = self._checks.run(record)
            record.eval_check_results = check_results
            if check_results:
                all_passed = all(c.passed for c in check_results)
                avg_score = sum(c.score for c in check_results) / len(check_results)
                record.eval_passed = all_passed
                record.eval_score = round(avg_score, 4)
        except Exception:  # pragma: no cover
            logger.warning("online checks failed", exc_info=True)

        # 2. persist to both sinks
        try:
            self._jsonl.write(record)
        except Exception:  # pragma: no cover
            logger.warning("jsonl sink failed", exc_info=True)
        try:
            self._sqlite.write(record)
        except Exception:  # pragma: no cover
            logger.warning("sqlite sink failed", exc_info=True)


# Module-level convenience — the typical call site uses this.

def record_model_call(
    domain_route: str,
    capability: str = "",
    capability_expected_shape: str = SHAPE_RAW,
    code_route: str = "",
    trace_id: str = "",
    user_id: str = "",
    household_id: str = "",
    model: str = "",
    backend: str = "",
    provider_name: str = "",
    auto_code_route: bool = True,
) -> _ActiveCall:
    """Open a per-call record. Use as ``with record_model_call(...) as rec:``.

    On exit, latency is computed, online checks run, and the record
    is persisted. The context manager yields an ``_ActiveCall`` whose
    setters you call inside the block:

        with record_model_call(
            domain_route="planner",
            capability="planner_tool_calling",
            capability_expected_shape="tool_calls",
        ) as rec:
            rec.set_prompt(prompt_text)
            try:
                result = provider.plan(...)
                rec.set_output(result)
            except Exception as e:
                rec.set_outcome("exception", error=str(e))
                raise
    """
    code = code_route
    if auto_code_route and not code:
        # skip this function's frame
        code = _resolve_code_route(skip_frames=1)
    record = ModelCallRecord(
        domain_route=domain_route or "unknown",
        code_route=code,
        capability=capability,
        capability_expected_shape=capability_expected_shape,
        model=model,
        backend=backend,
        provider_name=provider_name,
        trace_id=trace_id,
        user_id=user_id,
        household_id=household_id,
    )
    return _ActiveCall(ModelCallRecorder.instance(), record)


__all__ = [
    "CAP_PLANNER_TOOL_CALLING",
    "CAP_VISION_PRODUCT_RECOGNITION",
    "CAP_STT",
    "CAP_TTS",
    "CAP_OCR_RECEIPT",
    "CAP_EMBEDDINGS",
    "CAP_SEGMENTATION",
    "CAP_GROUNDING",
    "CAP_IMAGE_GEN",
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
    "SHAPE_BYTES",
    "SHAPE_RAW",
    "SHAPE_STRUCTURED",
    "SHAPE_TEXT",
    "SHAPE_TOOL_CALLS",
    "VALID_SHAPES",
    "record_model_call",
]
