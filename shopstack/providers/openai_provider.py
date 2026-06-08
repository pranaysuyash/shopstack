from __future__ import annotations

import base64
import logging
import time
from typing import Any

from shopstack.cost_tracker import estimate_cost_usd, estimate_model_tier

logger = logging.getLogger(__name__)


def _check_deps() -> tuple[bool, str]:
    try:
        import openai  # noqa: F401
        return True, ""
    except ImportError:
        return False, "openai package not installed. Run: uv pip install openai"


class OpenAIProvider:
    name = "openai"
    capabilities: set[str] = {"text", "vision", "embeddings"}

    def __init__(self, api_key: str = "", model: str = "gpt-4o", embedding_model: str = "text-embedding-3-small"):
        self._api_key = api_key
        self._model = model
        self._embedding_model = embedding_model
        self._available = False
        self._error: str | None = None
        self._init_client()

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

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        from shopstack.tracing import trace_call

        if not self._available:
            return {"error": self._error or "OpenAI not available", "model": self.name}
        model = kwargs.get("model", self._model)
        tier = estimate_model_tier(len(prompt))
        with trace_call("llm.complete", attributes={
            "model": model,
            "tier": tier,
            "provider": self.name,
            "prompt_length": len(prompt),
        }) as span:
            try:
                t0 = time.monotonic()
                resp = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 512),
                )
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                usage = dict(resp.usage) if resp.usage else {}
                in_tok = usage.get("prompt_tokens", 0)
                out_tok = usage.get("completion_tokens", 0)
                cost = estimate_cost_usd(model, in_tok, out_tok)
                span.set_attribute("input_tokens", in_tok)
                span.set_attribute("output_tokens", out_tok)
                span.set_attribute("cost_usd", cost)
                span.set_attribute("latency_ms", elapsed_ms)
                return {
                    "text": resp.choices[0].message.content,
                    "model": model,
                    "usage": usage,
                    "cost": {"usd": cost, "tier": tier, "latency_ms": elapsed_ms},
                }
            except Exception as e:
                logger.warning("OpenAI completion failed", exc_info=True)
                span.record_exception(e)
                return {"error": str(e), "model": self.name}

    def analyze_image(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        if not self._available:
            return {"error": self._error or "OpenAI not available"}
        try:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{b64}"
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "Describe what you see in this image in detail. List any food items, products, or text you can identify."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                max_tokens=512,
            )
            text = resp.choices[0].message.content
            return {
                "description": text,
                "detected_items": [],
                "model": self._model,
            }
        except Exception as e:
            logger.warning("OpenAI vision analysis failed", exc_info=True)
            return {"error": str(e), "model": self.name}

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._available:
            return [[0.0] * 128 for _ in texts]
        try:
            resp = self._client.embeddings.create(model=self._embedding_model, input=texts)
            return [d.embedding for d in resp.data]
        except Exception:
            logger.warning("OpenAI embedding failed", exc_info=True)
            return [[0.0] * 128 for _ in texts]

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error
