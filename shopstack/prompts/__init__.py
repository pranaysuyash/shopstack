"""Versioned prompt registry for ShopStack.

motto_v3 §0.9 mandate: all prompts must be versioned, evaluated, and documented.

Usage:
    from shopstack.prompts import get_prompt, list_prompts

    # Get a specific prompt
    prompt = get_prompt("vision.understand_product_shelf")

    # List all prompts
    for name, meta in list_prompts().items():
        print(f"{name} v{meta['version']} ({meta['date']})")

When adding a new prompt:
1. Create a versioned constant in the appropriate module (vision.py, planner.py, etc.)
2. Register it in _REGISTRY below with version, date, description, and eval link
3. Run the eval harness to confirm it works: benchmarks/modal/bench_prompt_eval.py
4. Update the eval link in the registry entry
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PromptMeta:
    """Metadata for a versioned prompt."""

    name: str
    version: str
    date: str  # YYYY-MM-DD
    description: str
    eval_link: str | None = None
    tags: tuple[str, ...] = ()
    _content_hash: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self._content_hash and hasattr(self, "_content"):
            # Compute hash from content if available
            object.__setattr__(
                self,
                "_content_hash",
                hashlib.sha256(self._content.encode()).hexdigest()[:12],
            )

    @property
    def content_hash(self) -> str:
        return self._content_hash


# ── Registry ────────────────────────────────────────────────────────────────
# Maps dotted name → PromptMeta. Populated by module imports below.

_REGISTRY: dict[str, PromptMeta] = {}


def register_prompt(meta: PromptMeta) -> None:
    """Register a prompt in the global registry."""
    _REGISTRY[meta.name] = meta


def get_prompt(name: str) -> PromptMeta:
    """Get prompt metadata by dotted name (e.g., 'vision.understand_product_shelf')."""
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise KeyError(f"Unknown prompt '{name}'. Available: {available}")
    return _REGISTRY[name]


def list_prompts() -> dict[str, PromptMeta]:
    """List all registered prompts."""
    return dict(_REGISTRY)


def get_content_hash(name: str) -> str:
    """Get the content hash for a prompt (useful for eval traceability)."""
    return get_prompt(name).content_hash


# ── Import modules to register prompts ──────────────────────────────────────
# Each module registers its prompts on import.

from shopstack.prompts import vision  # noqa: E402, F401
from shopstack.prompts import planner  # noqa: E402, F401
from shopstack.prompts import ocr  # noqa: E402, F401
