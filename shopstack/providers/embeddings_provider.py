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
        self._init()

    def _init(self) -> None:
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
