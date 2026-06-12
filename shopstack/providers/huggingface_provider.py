from __future__ import annotations

import logging
import time
from typing import Any

from shopstack.cost_tracker import estimate_cost_usd
from shopstack.planner.parser import parse_tool_calls_with_diagnostics
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "microsoft/Phi-3-mini-4k-instruct"


def _huggingface_available() -> tuple[bool, str]:
    try:
        import huggingface_hub  # noqa: F401
        return True, ""
    except ImportError:
        return False, "huggingface_hub package not installed. Run: uv pip install huggingface_hub"


class HuggingFaceProvider:
    """Planner provider using Hugging Face Inference API (serverless).

    Uses the ``huggingface_hub.InferenceClient`` to call chat-completion
    models via HF's serverless API.  Requires a Hugging Face API token
    set via ``SHOPSTACK_HF_API_KEY`` or ``HF_API_KEY`` env vars.

    Falls back gracefully when deps/token are missing.

    Chat formatting
    ---------------
    When ``plan()`` receives a ``system`` key in the context dict, the
    system instructions are sent as a ``role=system`` message and the
    user question as a ``role=user`` message.
    """

    name = "huggingface"
    model_id: str = DEFAULT_MODEL
    parameter_count: float = 3.8  # Phi-3-mini ~3.8B
    capabilities: set[str] = {"text", "planning"}

    def __init__(
        self,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        max_retries: int = 2,
    ):
        self._model = model
        self._max_retries = max_retries
        self._client: Any = None
        self._available = False
        self._error: str | None = None
        self.last_latency_ms: float | None = None
        self.last_token_count: int | None = None
        self.last_usage: dict[str, Any] = {}
        self._last_plan_diagnostics: dict[str, Any] = {}
        self._init_client(api_key)

    def _init_client(self, api_key: str) -> None:
        deps_ok, deps_error = _huggingface_available()
        if not deps_ok:
            self._error = deps_error
            self._available = False
            return

        key = api_key or self._env_key()
        if not key:
            self._error = (
                "Hugging Face API key not found. "
                "Set SHOPSTACK_HF_API_KEY or HF_API_KEY env var."
            )
            self._available = False
            return

        try:
            from huggingface_hub import InferenceClient
            self._client = InferenceClient(token=key)
            self._available = True
        except Exception as e:
            self._error = f"Failed to init HF InferenceClient: {e}"
            self._available = False

    @staticmethod
    def _env_key() -> str:
        import os
        return os.getenv("SHOPSTACK_HF_API_KEY") or os.getenv("HF_API_KEY", "")

    def _normalize_usage(self, usage: Any) -> dict[str, Any]:
        if usage is None:
            return {}
        if isinstance(usage, dict):
            return dict(usage)
        return {"total_tokens": int(getattr(usage, "total_tokens", 0) or 0)}

    def _record_call_attributes(
        self, response: Any, start_ms: float, span: Any
    ) -> tuple[list[float], dict[str, Any], float]:
        usage = {}
        if response and getattr(response, "usage", None) is not None:
            usage = self._normalize_usage(response.usage)
        else:
            usage = self.last_usage
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(
            usage.get("completion_tokens", usage.get("output_tokens", 0) or 0) or 0
        )
        if not output_tokens:
            output_tokens = int(usage.get("total_tokens", 0) or 0)
        token_count = output_tokens if output_tokens else int(self.last_token_count or 0)
        latency_ms = start_ms
        cost = estimate_cost_usd(self._model, input_tokens, output_tokens)
        if span is not None:
            span.set_attribute("input_tokens", input_tokens)
            span.set_attribute("output_tokens", output_tokens)
            span.set_attribute("total_tokens", token_count)
            span.set_attribute("cost_usd", cost)
            span.set_attribute("latency_ms", latency_ms)
        self.last_token_count = token_count
        self.last_latency_ms = latency_ms
        return usage, {"usd": cost, "latency_ms": latency_ms, "tier": "inference"}, latency_ms

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        from shopstack.tracing import trace_call

        if not self._available:
            return {"error": self._error or "HF not available", "model": self.name}

        max_tokens = kwargs.get("max_tokens", 512)
        temperature = kwargs.get("temperature", 0.3)

        with trace_call("llm.complete", attributes={
            "provider": self.name,
            "model": self._model,
            "prompt_length": len(prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }) as span:
            t0 = time.monotonic()

            for attempt in range(self._max_retries + 1):
                try:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                    self.last_usage = self._normalize_usage(getattr(response, "usage", None))
                    usage = dict(self.last_usage)
                    choice = response.choices[0]
                    _, cost, _ = self._record_call_attributes(
                        response=response,
                        start_ms=elapsed_ms,
                        span=span,
                    )
                    return {
                        "text": choice.message.content,
                        "model": self._model,
                        "usage": usage,
                        "cost": cost,
                    }
                except Exception as e:
                    logger.warning(
                        "HF complete attempt %d/%d failed: %s",
                        attempt + 1, self._max_retries + 1, e,
                    )
                    if attempt == self._max_retries:
                        span.record_exception(e)
                        return {"error": str(e), "model": self.name}

            return {"error": "HF complete failed after all retries", "model": self.name}

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send a structured chat conversation to the model."""
        from shopstack.tracing import trace_call

        if not self._available:
            return {"error": self._error or "HF not available", "model": self.name}

        with trace_call("llm.chat", attributes={
            "provider": self.name,
            "model": self._model,
            "message_count": len(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }) as span:
            t0 = time.monotonic()
            for attempt in range(self._max_retries + 1):
                try:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                    self.last_usage = self._normalize_usage(getattr(response, "usage", None))
                    usage = dict(self.last_usage)
                    choice = response.choices[0]
                    _, cost, _ = self._record_call_attributes(
                        response=response,
                        start_ms=elapsed_ms,
                        span=span,
                    )
                    return {
                        "text": choice.message.content,
                        "model": self._model,
                        "usage": usage,
                        "cost": cost,
                    }
                except Exception as e:
                    logger.warning(
                        "HF chat attempt %d/%d failed: %s",
                        attempt + 1, self._max_retries + 1, e,
                    )
                    if attempt == self._max_retries:
                        span.record_exception(e)
                        return {"error": str(e), "model": self.name}

            return {"error": "HF chat failed after all retries", "model": self.name}

    def plan(self, context: dict[str, Any] | str) -> list[dict[str, Any]]:
        from shopstack.tracing import trace_call

        if not self._available:
            return [{"tool": "respond", "args": {"message": self._error or "HF not available"}}]

        start = time.monotonic()
        with trace_call("llm.plan", attributes={
            "provider": self.name,
            "model": self._model,
        }) as span:
            if isinstance(context, str):
                result = self.complete(context, max_tokens=64, temperature=0.0)
                text = result.get("text", "")
                if not isinstance(text, str):
                    text = ""
                self._last_plan_diagnostics = {
                    "source": "planner_plan_string",
                    "status": "ok" if text else "empty",
                    "raw_length": len(context),
                }
                if not text:
                    return [{"tool": "respond", "args": {"message": ""}}]
                tool_calls, diagnostics = parse_tool_calls_with_diagnostics(text)
                if (len(tool_calls) == 1
                    and tool_calls[0]["tool"] == "respond"
                    and "No structured data" in tool_calls[0]["args"].get("message", "")):
                    tool_calls = [{"tool": "respond", "args": {"message": text.strip()}}]
                diagnostics["source"] = "planner_plan_string"
                self._last_plan_diagnostics = diagnostics
                self._record_plan_outcomes(span, diagnostics, text, context)
                return tool_calls

            prompt = context.get("prompt") or context.get("question") or ""
            max_tokens = context.get("max_tokens", 64)
            temperature = context.get("temperature", 0.0)
            if not prompt:
                self._last_plan_diagnostics = {"status": "empty_prompt"}
                return [{"tool": "respond", "args": {"message": ""}}]

            # Prefer structured chat messages for better instruction adherence.
            system = context.get("system", "")
            question = context.get("question", "")
            if system and question:
                messages: list[dict[str, str]] = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"{question}\n\nJSON tool calls:"},
                ]
                result = self.chat(messages, max_tokens=max_tokens, temperature=temperature)
            else:
                # Fallback: use the combined prompt as a single user message
                prompt = context.get("prompt", "") or question
                if not prompt:
                    self._last_plan_diagnostics = {"status": "empty_prompt"}
                    return [{"tool": "respond", "args": {"message": ""}}]
                result = self.complete(prompt, max_tokens=max_tokens, temperature=temperature)

            text = result.get("text", "")
            if not isinstance(text, str):
                text = ""
            if not text:
                self._last_plan_diagnostics = {"status": "empty_output"}
                return [{"tool": "respond", "args": {"message": ""}}]

            self._last_plan_diagnostics = parse_tool_calls_with_diagnostics(text)[1]
            self._last_plan_diagnostics["source"] = "planner_plan_context"
            self._record_plan_outcomes(span, self._last_plan_diagnostics, text, prompt)
            self._last_plan_diagnostics["provider_latency_ms"] = round((time.monotonic() - start) * 1000, 1)
            tool_calls, _ = parse_tool_calls_with_diagnostics(text)
            if (len(tool_calls) == 1
                and tool_calls[0]["tool"] == "respond"
                and "No structured data" in tool_calls[0]["args"].get("message", "")):
                tool_calls = [{"tool": "respond", "args": {"message": text.strip()}}]
            return tool_calls

    def _record_plan_outcomes(self, span: Any, diagnostics: dict[str, Any], text: str, prompt: str) -> None:
        if span is None:
            return
        span.set_attribute("raw_length", len(text))
        span.set_attribute("prompt_length", len(prompt))
        span.set_attribute("tool_calls", diagnostics.get("items_output", 0))
        span.set_attribute("parser_status", diagnostics.get("status"))
        span.set_attribute("parse_errors", diagnostics.get("errors", 0))

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return self._available
