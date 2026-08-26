from __future__ import annotations

import base64
import logging
import mimetypes
import time
from collections.abc import Mapping
from typing import Any, Callable

from shopstack.cost_tracker import estimate_cost_usd, estimate_model_tier
from shopstack.prompts.ocr import OPENAI_RECEIPT_TEXT_EXTRACTION_PROMPT
from shopstack.prompts.vision import OPENAI_DESCRIBE_PROMPT

logger = logging.getLogger(__name__)


def _plain_data(value: Any) -> Any:
    """Convert SDK response values into JSON-safe provider metadata."""
    model_dump = getattr(type(value), "model_dump", None)
    if callable(model_dump):
        try:
            return _plain_data(value.model_dump())
        except Exception:
            pass
    if isinstance(value, Mapping):
        return {str(key): _plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_data(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _usage_data(value: Any) -> dict[str, Any]:
    """Return usage metadata as a plain mapping for real and mocked SDKs."""
    if not value:
        return {}
    plain = _plain_data(value)
    if isinstance(plain, Mapping):
        return dict(plain)
    # Test doubles and older SDK versions may expose attributes without a
    # mapping/model_dump interface. Keep only numeric usage fields.
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {
        field: getattr(value, field)
        for field in fields
        if isinstance(getattr(value, field, None), (int, float))
    }


def _check_deps() -> tuple[bool, str]:
    try:
        import openai  # noqa: F401
        return True, ""
    except ImportError:
        return False, "openai package not installed. Run: uv pip install openai"


def _is_retryable_error(error: Exception) -> bool:
    """Identify transient provider failures without retrying bad requests."""
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(error, "status", None)
    try:
        status_code = int(status) if status is not None else None
    except (TypeError, ValueError):
        status_code = None
    if status_code in {408, 409, 425, 429} or (status_code is not None and status_code >= 500):
        return True

    error_name = type(error).__name__.lower()
    error_text = str(error).lower()
    transient_markers = (
        "timeout",
        "connection",
        "ratelimit",
        "rate limit",
        "internalserver",
        "serviceunavailable",
        "temporarily unavailable",
    )
    return any(marker in error_name or marker in error_text for marker in transient_markers)


class _OpenAIRequestFailure(RuntimeError):
    """Internal wrapper retaining the number of attempts made."""

    def __init__(self, cause: Exception, attempts: int):
        super().__init__(str(cause))
        self.cause = cause
        self.attempts = attempts


class OpenAIProvider:
    name = "openai"
    capabilities: set[str] = {"text", "vision", "ocr", "embeddings", "planning"}
    supports_off_grid = False


    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-small",
        max_retries: int = 2,
        retry_base_delay: float = 0.25,
    ):
        self._api_key = api_key
        self._model = model
        self._embedding_model = embedding_model
        self._max_retries = max(0, int(max_retries))
        self._retry_base_delay = max(0.0, float(retry_base_delay))
        self._available = False
        self._error: str | None = None
        self.last_plan_diagnostics: dict[str, Any] = {}
        self.last_completion_meta: dict[str, Any] = {}
        self.last_embedding_meta: dict[str, Any] = {}
        self._init_client()

    def _request_with_retries(
        self,
        operation: str,
        request: Callable[[], Any],
    ) -> tuple[Any, int]:
        """Run one provider request with bounded retry and attempt reporting."""
        for attempt in range(1, self._max_retries + 2):
            try:
                return request(), attempt
            except Exception as error:
                if attempt > self._max_retries or not _is_retryable_error(error):
                    raise _OpenAIRequestFailure(error, attempt) from error
                delay = self._retry_base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Retrying OpenAI %s after transient failure (attempt %d/%d, delay %.2fs)",
                    operation,
                    attempt,
                    self._max_retries + 1,
                    delay,
                )
                if delay:
                    time.sleep(delay)

    def _init_client(self) -> None:
        deps_ok, deps_error = _check_deps()
        if not deps_ok:
            self._error = deps_error
            self._available = False
            return
        key = self._api_key or self._env_key()
        if not key:
            self._error = "OpenAI API key not found. Set OPENAI_API_KEY env var or SHOPSTACK_OPENAI_API_KEY."
            self._available = False
            return
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=key)
            self._available = True
        except Exception as e:
            self._error = f"Failed to init OpenAI client: {e}"
            self._available = False

    @staticmethod
    def _env_key() -> str:
        import os
        return os.getenv("SHOPSTACK_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")

    @property
    def model_id(self) -> str:
        """Public model identity used by registries and evaluation reports."""
        return self._model

    @property
    def embedding_model(self) -> str:
        """Public embedding model identity used by evaluation reports."""
        return self._embedding_model

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        from shopstack.tracing import trace_call

        if not self._available:
            self.last_completion_meta = {
                "error": self._error or "OpenAI not available",
                "model": self.name,
                "attempts": 0,
            }
            return self.last_completion_meta
        model = kwargs.get("model", self._model)
        max_tokens = kwargs.get("max_tokens", 512)
        tier = estimate_model_tier(len(prompt))
        with trace_call("llm.complete", attributes={
            "model": model,
            "tier": tier,
            "provider": self.name,
            "prompt_length": len(prompt),
        }) as span:
            try:
                t0 = time.monotonic()
                request_kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if str(model).lower().startswith("gpt-5"):
                    request_kwargs["max_completion_tokens"] = max_tokens
                    reasoning_effort = kwargs.get("reasoning_effort")
                    if reasoning_effort:
                        request_kwargs["reasoning_effort"] = reasoning_effort
                else:
                    request_kwargs["max_tokens"] = max_tokens
                    request_kwargs["temperature"] = kwargs.get("temperature", 0.7)
                resp, attempts = self._request_with_retries(
                    "completion",
                    lambda: self._client.chat.completions.create(**request_kwargs),
                )
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                usage = _usage_data(resp.usage)
                in_tok = int(usage.get("prompt_tokens", 0) or 0)
                out_tok = int(usage.get("completion_tokens", 0) or 0)
                cost = estimate_cost_usd(model, in_tok, out_tok)
                span.set_attribute("input_tokens", in_tok)
                span.set_attribute("output_tokens", out_tok)
                span.set_attribute("cost_usd", cost)
                span.set_attribute("latency_ms", elapsed_ms)
                self.last_completion_meta = {
                    "text": resp.choices[0].message.content,
                    "model": model,
                    "usage": usage,
                    "cost": {"usd": cost, "tier": tier, "latency_ms": elapsed_ms},
                    "attempts": attempts,
                }
                return self.last_completion_meta
            except _OpenAIRequestFailure as e:
                logger.warning("OpenAI completion failed after %d attempt(s)", e.attempts, exc_info=True)
                span.record_exception(e.cause)
                self.last_completion_meta = {"error": str(e.cause), "model": model, "attempts": e.attempts}
                return self.last_completion_meta
            except Exception as e:
                logger.warning("OpenAI completion failed", exc_info=True)
                span.record_exception(e)
                self.last_completion_meta = {"error": str(e), "model": model, "attempts": 1}
                return self.last_completion_meta

    def analyze_image(
        self,
        image_path: str,
        prompt: str = "",
        *,
        max_tokens: int = 512,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        from shopstack.tracing import trace_call

        if not self._available:
            return {"error": self._error or "OpenAI not available", "attempts": 0}
        model = self._model
        with trace_call("llm.analyze_image", attributes={
            "provider": self.name,
            "model": model,
            "prompt_length": len(prompt),
        }) as span:
            try:
                t0 = time.monotonic()
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
                if not mime_type.startswith("image/"):
                    mime_type = "image/jpeg"
                data_url = f"data:{mime_type};base64,{b64}"
                messages: list[dict[str, Any]] = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or OPENAI_DESCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }]
                request_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }
                if str(model).lower().startswith("gpt-5"):
                    request_kwargs["max_completion_tokens"] = max_tokens
                    if reasoning_effort:
                        request_kwargs["reasoning_effort"] = reasoning_effort
                else:
                    request_kwargs["max_tokens"] = max_tokens
                resp, attempts = self._request_with_retries(
                    "vision",
                    lambda: self._client.chat.completions.create(**request_kwargs),
                )  # type: ignore[arg-type]
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                usage = _usage_data(resp.usage)
                in_tok = int(usage.get("prompt_tokens", 0) or 0)
                out_tok = int(usage.get("completion_tokens", 0) or 0)
                cost = estimate_cost_usd(model, in_tok, out_tok)
                span.set_attribute("input_tokens", in_tok)
                span.set_attribute("output_tokens", out_tok)
                span.set_attribute("cost_usd", cost)
                span.set_attribute("latency_ms", elapsed_ms)
                return {
                    "description": resp.choices[0].message.content,
                    "detected_items": [],
                    "model": model,
                    "usage": usage,
                    "cost": {"usd": cost, "latency_ms": elapsed_ms},
                    "attempts": attempts,
                }
            except _OpenAIRequestFailure as e:
                logger.warning("OpenAI vision analysis failed after %d attempt(s)", e.attempts, exc_info=True)
                span.record_exception(e.cause)
                return {"error": str(e.cause), "model": self.name, "attempts": e.attempts}
            except Exception as e:
                logger.warning("OpenAI vision analysis failed", exc_info=True)
                span.record_exception(e)
                return {"error": str(e), "model": self.name, "attempts": 1}

    def extract(self, image_path: str) -> dict[str, Any]:
        """Transcribe a receipt image for the canonical OCR pipeline.

        This deliberately returns raw text rather than structured receipt
        fields. ``parse_receipt_text`` remains the deterministic normalization
        boundary, and ``confirm_receipt`` remains the explicit mutation gate.
        """
        reasoning_effort = "high" if self._model.lower().startswith("gpt-5") else None
        response = self.analyze_image(
            image_path,
            prompt=OPENAI_RECEIPT_TEXT_EXTRACTION_PROMPT,
            max_tokens=1024,
            reasoning_effort=reasoning_effort,
        )
        if response.get("error"):
            return response
        text = response.get("description", "")
        if not isinstance(text, str):
            text = ""
        return {
            "raw_text": text.strip(),
            "text": text.strip(),
            "model": response.get("model", self._model),
            "usage": response.get("usage", {}),
            "cost": response.get("cost", {}),
            "latency_ms": response.get("cost", {}).get("latency_ms"),
            "attempts": response.get("attempts", 1),
        }

    def embed(self, texts: list[str]) -> list[list[float]]:
        from shopstack.tracing import trace_call

        if not self._available:
            self.last_embedding_meta = {
                "error": self._error or "OpenAI not available",
                "model": self._embedding_model,
                "attempts": 0,
            }
            return [[0.0] * 128 for _ in texts]
        with trace_call("llm.embed", attributes={
            "provider": self.name,
            "model": self._embedding_model,
            "input_count": len(texts),
        }) as span:
            try:
                t0 = time.monotonic()
                resp, attempts = self._request_with_retries(
                    "embedding",
                    lambda: self._client.embeddings.create(model=self._embedding_model, input=texts),
                )
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                result = [d.embedding for d in resp.data]
                usage = _usage_data(resp.usage)
                in_tok = int(usage.get("prompt_tokens", usage.get("total_tokens", 0)) or 0)
                cost = estimate_cost_usd(self._embedding_model, in_tok, 0)
                span.set_attribute("latency_ms", elapsed_ms)
                span.set_attribute("output_count", len(result))
                if result:
                    span.set_attribute("vector_dim", len(result[0]))
                span.set_attribute("input_tokens", in_tok)
                span.set_attribute("cost_usd", cost)
                self.last_embedding_meta = {
                    "model": self._embedding_model,
                    "usage": usage,
                    "cost": {"usd": cost, "latency_ms": elapsed_ms},
                    "attempts": attempts,
                }
                return result
            except _OpenAIRequestFailure as e:
                logger.warning("OpenAI embedding failed after %d attempt(s)", e.attempts, exc_info=True)
                span.record_exception(e.cause)
                self.last_embedding_meta = {
                    "error": str(e.cause),
                    "model": self._embedding_model,
                    "attempts": e.attempts,
                }
                return [[0.0] * 128 for _ in texts]
            except Exception as e:
                logger.warning("OpenAI embedding failed", exc_info=True)
                span.record_exception(e)
                self.last_embedding_meta = {"error": str(e), "model": self._embedding_model, "attempts": 1}
                return [[0.0] * 128 for _ in texts]

    def plan(self, context: dict[str, Any] | str) -> list[dict[str, Any]]:
        from shopstack.planner.parser import parse_tool_calls_with_diagnostics
        from shopstack.tracing import trace_call

        if not self._available:
            self.last_plan_diagnostics = {"status": "unavailable", "items_output": 0}
            return [{"tool": "respond", "args": {"message": self._error or "OpenAI not available"}}]

        with trace_call("llm.plan", attributes={
            "provider": self.name,
            "model": self._model,
        }) as _span:
            if isinstance(context, str):
                result = self.complete(context, max_tokens=128, temperature=0.0)
                text = result.get("text", "")
                if not isinstance(text, str):
                    text = ""
                if not text:
                    self.last_plan_diagnostics = {"status": "empty", "items_output": 0}
                    return [{"tool": "respond", "args": {"message": ""}}]
                tool_calls, diagnostics = parse_tool_calls_with_diagnostics(text)
                self.last_plan_diagnostics = diagnostics
                if (len(tool_calls) == 1
                    and tool_calls[0]["tool"] == "respond"
                    and "No structured data" in tool_calls[0]["args"].get("message", "")):
                    tool_calls = [{"tool": "respond", "args": {"message": text.strip()}}]
                return tool_calls

            prompt = context.get("prompt") or context.get("question") or ""
            # GPT-5 reasoning tokens and nested shopping-list JSON share this
            # completion budget. 256 can exhaust before the JSON closes.
            max_tokens = context.get("max_tokens", 512)
            temperature = context.get("temperature", 0.0)
            if not prompt:
                self.last_plan_diagnostics = {"status": "empty", "items_output": 0}
                return [{"tool": "respond", "args": {"message": ""}}]

            result = self.complete(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=context.get("reasoning_effort"),
            )
            text = result.get("text", "")
            if not isinstance(text, str):
                text = ""
            if not text:
                self.last_plan_diagnostics = {"status": "empty", "items_output": 0}
                return [{"tool": "respond", "args": {"message": ""}}]
            tool_calls, diagnostics = parse_tool_calls_with_diagnostics(text)
            self.last_plan_diagnostics = diagnostics
            if (len(tool_calls) == 1
                and tool_calls[0]["tool"] == "respond"
                and "No structured data" in tool_calls[0]["args"].get("message", "")):
                tool_calls = [{"tool": "respond", "args": {"message": text.strip()}}]
            return tool_calls

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error
