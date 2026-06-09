from __future__ import annotations

import logging
import time
from typing import Any

from shopstack.cost_tracker import estimate_cost_usd

logger = logging.getLogger(__name__)


class MiniCPM5Provider:
    """Lightweight planner provider using MiniCPM5-1B via transformers.

    Provides text generation and planning for lightweight tasks.
    Falls back gracefully when deps are missing.
    """

    name = "minicpm5"
    model_id = "minicpm5-1b"
    parameter_count = 1.0
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"text", "planning"}

    def __init__(
        self,
        model_name: str = "openbmb/MiniCPM5-1B",
        device: str = "auto",
        max_new_tokens: int = 256,
        temperature: float = 0.3,
    ):
        self._model_name = model_name
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._temperature = temperature
        self._model = None
        self._tokenizer = None
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._last_token_count: int | None = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForCausalLM,
                AutoTokenizer,
            )
            self._available = True
            self._error = None
            logger.info("MiniCPM5 provider initialised (model=%s)", self._model_name)
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            self._available = False

    def load(self) -> None:
        if self._model is not None:
            return
        self._load_model()

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info("Loading MiniCPM5 model %s ...", self._model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_name, trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_name,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16,
            )
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("MiniCPM5 model loaded")
            return True
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            return False
        except Exception as e:
            self._error = f"Failed to load MiniCPM5 model: {e}"
            logger.warning("MiniCPM5 model load failed", exc_info=True)
            return False

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        if not self._available:
            return {"error": self._error or "MiniCPM5 not available", "model": self.name}

        if self._model is None and not self._load_model():
            return {"error": self._error or "MiniCPM5 not available", "model": self.name}

        try:
            import torch

            max_tokens = kwargs.get("max_tokens", self._max_new_tokens)
            temperature = kwargs.get("temperature", self._temperature)

            t0 = time.monotonic()

            inputs = self._tokenizer(prompt, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                inputs = {k: v.to("mps") for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    do_sample=temperature > 0,
                    pad_token_id=self._tokenizer.pad_token_id or self._tokenizer.eos_token_id,
                )

            text = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

            elapsed = time.monotonic() - t0
            elapsed_ms = round(elapsed * 1000, 1)
            token_count = max_tokens
            self._last_latency_ms = elapsed_ms
            self._last_token_count = token_count

            cost = estimate_cost_usd(self._model_name, 0, token_count)

            return {
                "text": text.strip(),
                "model": self._model_name,
                "usage": {"total_tokens": token_count},
                "cost": {"usd": cost, "latency_ms": elapsed_ms},
            }
        except Exception as e:
            logger.warning("MiniCPM5 completion failed", exc_info=True)
            return {"error": str(e), "model": self.name}

    def plan(self, context: dict[str, Any] | str) -> list[dict[str, Any]]:
        from shopstack.planner.parser import parse_tool_calls

        if not self._available:
            return [{"tool": "respond", "args": {"message": self._error or "MiniCPM5 not available"}}]

        if isinstance(context, str):
            return [{"tool": "respond", "args": {"message": ""}}]

        prompt = context.get("prompt") or context.get("question") or ""
        max_tokens = context.get("max_tokens", 64)
        temperature = context.get("temperature", 0.0)

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

    def healthcheck(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms

    @property
    def last_token_count(self) -> int | None:
        return self._last_token_count
