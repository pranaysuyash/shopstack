from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


class BGEM3EmbeddingProvider:
    name = "bge-m3"
    model_id = "bge-m3"
    parameter_count = 0.6
    license_note = "MIT"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"embeddings"}

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._model_name = model_name
        self._model = None
        self._tokenizer = None
        self._available = False
        self._initialised = False

    def _ensure_model(self) -> None:
        """Lazy-load the model on first use to avoid pulling torch at import time."""
        if self._initialised:
            return
        self._initialised = True
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self._available = True
        except ImportError:
            logger.info(
                "sentence-transformers not installed; "
                "semantic search will fall back to prefix search. "
                "Install: uv pip install sentence-transformers"
            )
        except Exception as e:
            logger.warning("Failed to load BGE-M3: %s", e)

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        if not self._available or self._model is None:
            dim = 1024
            return [[0.0] * dim for _ in texts]
        try:
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        except Exception as e:
            logger.warning("BGE-M3 embed failed: %s", e)
            dim = 1024
            return [[0.0] * dim for _ in texts]

    def similarity(self, query_emb: list[float], item_emb: list[float]) -> float:
        if len(query_emb) != len(item_emb):
            return 0.0
        dot = sum(a * b for a, b in zip(query_emb, item_emb))
        nq = math.sqrt(sum(a * a for a in query_emb))
        ni = math.sqrt(sum(b * b for b in item_emb))
        if nq == 0.0 or ni == 0.0:
            return 0.0
        return dot / (nq * ni)

    @property
    def available(self) -> bool:
        return self._available


class NomicEmbeddingProvider:
    """Embedding provider using nomic-ai/nomic-embed-text-v1.5.

    Won the 13-Jun-2026 Modal A10G embeddings bench on 50 query-product pairs:
    - Top-1 retrieval: 58% (vs BGE-M3 48%, Qwen3-0.6B 50%, mxbai-large 56%)
    - Top-3 retrieval: 90%
    - Embedding dim: 768 (smallest of all candidates)
    - License: Apache-2.0 (vs BGE-M3 MIT, both permissive)
    - Latency: ~20s load (1.2B params), <1ms per pair

    Apache-2.0 license, no usage restrictions. 137M params, fits in
    32B cap easily (vs 600M for BGE-M3).

    Uses sentence-transformers with task prefix "search_query:" / "search_document:".
    """

    name = "nomic"
    model_id = "nomic-embed-text-v1.5"
    parameter_count = 0.137
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"embeddings"}

    QUERY_PREFIX = "search_query: "
    DOC_PREFIX = "search_document: "

    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        max_seq_length: int = 2048,
    ):
        self._model_name = model_name
        self._max_seq_length = max_seq_length
        self._model = None
        self._available = False
        self._error: str | None = None
        self._initialised = False

    def _ensure_model(self) -> None:
        """Lazy-load the model on first use to avoid pulling torch at import time."""
        if self._initialised:
            return
        self._initialised = True
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name, trust_remote_code=True)
            self._model.max_seq_length = self._max_seq_length
            self._available = True
            self._error = None
            logger.info("Nomic-embed provider initialised (model=%s)", self._model_name)
        except ImportError:
            self._error = "sentence-transformers not installed"
            logger.info(self._error)
        except Exception as e:
            self._error = f"Failed to load Nomic-Embed: {e}"
            logger.warning(self._error)

    def embed_queries(self, queries: list[str]) -> list[list[float]]:
        return self.embed(queries, kind="query")

    def embed_documents(self, docs: list[str]) -> list[list[float]]:
        return self.embed(docs, kind="document")

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        self._ensure_model()
        if not self._available or self._model is None:
            dim = 768
            return [[0.0] * dim for _ in texts]
        prefix = self.QUERY_PREFIX if kind == "query" else self.DOC_PREFIX
        prefixed = [prefix + t for t in texts]
        try:
            import torch
            embeddings = self._model.encode(prefixed, normalize_embeddings=True, convert_to_numpy=True)
            if isinstance(embeddings, torch.Tensor):
                embeddings = embeddings.cpu().numpy()
            return embeddings.tolist()
        except Exception as e:
            logger.warning("Nomic-Embed embed failed: %s", e)
            dim = 768
            return [[0.0] * dim for _ in texts]

    def similarity(self, query_emb: list[float], item_emb: list[float]) -> float:
        if len(query_emb) != len(item_emb):
            return 0.0
        dot = sum(a * b for a, b in zip(query_emb, item_emb))
        nq = math.sqrt(sum(a * a for a in query_emb))
        ni = math.sqrt(sum(b * b for b in item_emb))
        if nq == 0.0 or ni == 0.0:
            return 0.0
        return dot / (nq * ni)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error
