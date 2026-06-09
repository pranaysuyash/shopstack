from __future__ import annotations

import logging
import time
from typing import Any

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

    Falls back gracefully when the dependency or token is missing.

    Chat formatting
    ---------------
    When ``plan()`` receives a ``system`` key in the context dict, the
    system instructions are sent as a ``role=system`` message and the
    user question as a ``role=user`` message.  This produces better
    results on instruction-tuned chat models (Phi-3, Llama, etc.) than
    concatenating system + user into a single user message.
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

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"error": self._error or "HF not available", "model": self.name}

        max_tokens = kwargs.get("max_tokens", 512)
        temperature = kwargs.get("temperature", 0.3)

        start = time.monotonic()

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                self.last_latency_ms = int((time.monotonic() - start) * 1000)
                self.last_token_count = response.usage.total_tokens if response.usage else 0
                choice = response.choices[0]
                return {
                    "text": choice.message.content,
                    "model": self._model,
                    "usage": {
                        "total_tokens": self.last_token_count,
                    },
                }
            except Exception as e:
                logger.warning(
                    "HF completion attempt %d/%d failed: %s",
                    attempt + 1, self._max_retries + 1, e,
                )
                if attempt == self._max_retries:
                    return {"error": str(e), "model": self.name}

        return {"error": "HF completion failed after all retries", "model": self.name}

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send a structured chat conversation to the model.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.

        Returns:
            A dict with ``text``, ``model``, and optionally ``usage``.
            Returns ``{"error": ...}`` on failure.
        """
        if not self._available:
            return {"error": self._error or "HF not available", "model": self.name}

        start = time.monotonic()

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                self.last_latency_ms = int((time.monotonic() - start) * 1000)
                self.last_token_count = response.usage.total_tokens if response.usage else 0
                choice = response.choices[0]
                return {
                    "text": choice.message.content,
                    "model": self._model,
                    "usage": {"total_tokens": self.last_token_count},
                }
            except Exception as e:
                logger.warning(
                    "HF chat attempt %d/%d failed: %s",
                    attempt + 1, self._max_retries + 1, e,
                )
                if attempt == self._max_retries:
                    return {"error": str(e), "model": self.name}

        return {"error": "HF chat failed after all retries", "model": self.name}

    def plan(self, context: dict[str, Any] | str) -> list[dict[str, Any]]:
        from shopstack.planner.parser import parse_tool_calls

        if not self._available:
            return [{"tool": "respond", "args": {"message": self._error or "HF not available"}}]

        if isinstance(context, str):
            return [{"tool": "respond", "args": {"message": ""}}]

        max_tokens = context.get("max_tokens", 512)
        temperature = context.get("temperature", 0.3)

        # Prefer structured chat messages (system + user) for better
        # instruction-following on chat-tuned models.
        system = context.get("system", "")
        question = context.get("question", "") or context.get("prompt", "")

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
                return [{"tool": "respond", "args": {"message": ""}}]
            result = self.complete(prompt, max_tokens=max_tokens, temperature=temperature)

        text = result.get("text", "")
        if not text:
            return [{"tool": "respond", "args": {"message": ""}}]

        # Try to parse structured tool calls from model output.
        # If no JSON is found, wrap the raw text as a respond message.
        tool_calls = parse_tool_calls(text)
        if (len(tool_calls) == 1
            and tool_calls[0]["tool"] == "respond"
            and "No structured data" in tool_calls[0]["args"].get("message", "")):
            return [{"tool": "respond", "args": {"message": text.strip()}}]
        return tool_calls

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
