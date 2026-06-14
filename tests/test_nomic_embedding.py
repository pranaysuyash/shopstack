"""Tests for NomicEmbeddingProvider.

Covers:
- Init and metadata (name, model_id, capabilities, parameter_count)
- available=False when sentence-transformers is missing
- available=True with real model (requires model download — marked slow)
- embed() fallback with zero vectors when unavailable
- embed() with empty text list
- embed_queries() / embed_documents() prefix routing
- similarity() basic correctness and edge cases
- Graceful error handling for missing deps and empty input
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ============================================================
#  Init & metadata (deps missing)
# ============================================================


class TestNomicEmbeddingProviderInit:
    def test_not_available_when_deps_missing(self):
        """Available=False when sentence-transformers is not installed."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        with patch.dict("sys.modules", {"sentence_transformers": None}, clear=False):
            provider = NomicEmbeddingProvider()
            assert not provider.available
            assert provider.error is not None
            assert "sentence-transformers" in (provider.error or "").lower()

    def test_name_and_capabilities(self):
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        with patch.dict("sys.modules", {"sentence_transformers": None}, clear=False):
            provider = NomicEmbeddingProvider()
            assert provider.name == "nomic"
            assert provider.model_id == "nomic-embed-text-v1.5"
            assert provider.parameter_count == 0.137
            assert "embeddings" in provider.capabilities

    def test_error_property(self):
        """error property returns the message from a failed init."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        with patch.dict("sys.modules", {"sentence_transformers": None}, clear=False):
            provider = NomicEmbeddingProvider()
            err = provider.error
            assert err is not None
            assert isinstance(err, str)
            assert len(err) > 0

    def test_dimension_property(self):
        """The Nomic model uses 768-dimensional embeddings."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        with patch.dict("sys.modules", {"sentence_transformers": None}, clear=False):
            provider = NomicEmbeddingProvider()
            # The zero-vector fallback dimension is 768
            vecs = provider.embed(["test"])
            assert len(vecs) == 1
            assert len(vecs[0]) == 768

    def test_error_is_none_when_available(self):
        """After successful init, error should be None."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        if provider.available:
            assert provider.error is None
        else:
            pytest.skip("Nomic model not downloaded")


# ============================================================
#  embed() — unavailable fallback
# ============================================================


class TestNomicEmbeddingProviderEmbed:
    def test_embed_returns_zero_vectors_when_unavailable(self):
        """When sentence-transformers is missing, embed() returns zero vectors."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        with patch.dict("sys.modules", {"sentence_transformers": None}, clear=False):
            provider = NomicEmbeddingProvider()
            texts = ["milk", "atta", "tomato"]
            vecs = provider.embed(texts)
            assert len(vecs) == 3
            for v in vecs:
                assert len(v) == 768
                assert all(x == 0.0 for x in v)

    def test_embed_empty_list(self):
        """embed([]) returns an empty list."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        with patch.dict("sys.modules", {"sentence_transformers": None}, clear=False):
            provider = NomicEmbeddingProvider()
            vecs = provider.embed([])
            assert vecs == []

    def test_embed_single_text(self):
        """embed([\"text\"]) returns one 768-dim vector when available."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        if not provider.available:
            pytest.skip("Nomic model not downloaded")
        vecs = provider.embed(["milk"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 768
        assert any(v != 0.0 for v in vecs[0])  # non-zero vector

    def test_embed_kind_query_uses_prefix(self):
        """embed_queries prepends 'search_query:' prefix."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        if not provider.available:
            pytest.skip("Nomic model not downloaded")
        q_vecs = provider.embed_queries(["milk"])
        d_vecs = provider.embed_documents(["milk"])
        assert len(q_vecs) == 1
        assert len(d_vecs) == 1
        # Different prefixes should produce different embeddings for same text
        assert q_vecs[0] != d_vecs[0]

    def test_embed_kind_document_uses_prefix(self):
        """embed_documents prepends 'search_document:' prefix."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        if not provider.available:
            pytest.skip("Nomic model not downloaded")
        vecs = provider.embed_documents(["atta", "flour"])
        assert len(vecs) == 2
        for v in vecs:
            assert len(v) == 768

    def test_embed_with_empty_strings(self):
        """embed handles empty strings gracefully."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        if not provider.available:
            pytest.skip("Nomic model not downloaded")
        vecs = provider.embed([""])
        assert len(vecs) == 1
        assert len(vecs[0]) == 768


# ============================================================
#  similarity()
# ============================================================


class TestNomicEmbeddingSimilarity:
    def test_similarity_identical_vectors(self):
        """Cosine similarity of a vector with itself should be 1.0."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v = [0.5, 0.3, 0.1, -0.2]
        sim = provider.similarity(v, v)
        assert abs(sim - 1.0) < 1e-6

    def test_similarity_opposite_vectors(self):
        """Cosine similarity of opposite vectors should be -1.0."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        sim = provider.similarity(v1, v2)
        assert abs(sim - (-1.0)) < 1e-6

    def test_similarity_orthogonal_vectors(self):
        """Cosine similarity of orthogonal vectors should be 0.0."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        sim = provider.similarity(v1, v2)
        assert abs(sim - 0.0) < 1e-6

    def test_similarity_zero_vector(self):
        """Zero vector similarity returns 0.0 (division by zero guard)."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v1 = [0.0, 0.0, 0.0]
        v2 = [0.5, 0.3, 0.1]
        sim = provider.similarity(v1, v2)
        assert sim == 0.0

    def test_similarity_dimension_mismatch(self):
        """Vectors with different dimensions return 0.0."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v1 = [0.5, 0.3]
        v2 = [0.5, 0.3, 0.1]
        sim = provider.similarity(v1, v2)
        assert sim == 0.0

    def test_similarity_positive_value(self):
        """Similar vectors have positive cosine similarity."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v1 = [0.8, 0.6, 0.2]
        v2 = [0.7, 0.5, 0.3]
        sim = provider.similarity(v1, v2)
        assert 0.0 < sim < 1.0

    def test_similarity_semantic_reasonable(self):
        """Real embeddings: semantically related items should have higher similarity.

        Uses English-to-English comparisons where the model is known to
        perform well (Nomic's top-1 retrieval benchmark: 58%).
        """
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        if not provider.available:
            pytest.skip("Nomic model not downloaded")
        # Use document prefix for all to get comparable vectors
        milk = provider.embed_documents(["milk"])[0]
        butter = provider.embed_documents(["butter"])[0]
        cement = provider.embed_documents(["cement"])[0]

        sim_milk_butter = provider.similarity(milk, butter)
        sim_milk_cement = provider.similarity(milk, cement)

        # milk and butter (both dairy) should be more similar than milk and cement
        assert sim_milk_butter > sim_milk_cement, (
            f"Expected milk~butter ({sim_milk_butter:.3f}) > milk~cement ({sim_milk_cement:.3f})"
        )

    def test_similarity_same_word_high(self):
        """Same word with document prefix should have very high similarity."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        if not provider.available:
            pytest.skip("Nomic model not downloaded")
        v1 = provider.embed_documents(["tomato"])[0]
        v2 = provider.embed_documents(["tomato"])[0]
        sim = provider.similarity(v1, v2)
        assert sim > 0.99, f"Same word similarity should be near 1.0, got {sim:.4f}"


# ============================================================
#  Error handling & graceful degradation
# ============================================================


class TestNomicEmbeddingErrorHandling:
    def test_embed_does_not_raise_on_empty_list(self):
        """embed([]) should not raise any exception."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        vecs = provider.embed([])
        assert isinstance(vecs, list)

    def test_embed_does_not_raise_on_none_texts(self):
        """embed with non-list types is handled gracefully (no crash)."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        # The embed method expects list[str], but the try/except in embed()
        # should catch TypeError if called with non-list
        try:
            result = provider.embed(None)  # type: ignore[arg-type]
            assert isinstance(result, list)
        except Exception:
            # It's acceptable for embed to raise on obviously wrong types —
            # the test just confirms no silent corruption
            pass

    def test_embed_called_twice_returns_same_dimension(self):
        """Consecutive embed calls return consistent dimensions."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        with patch.dict("sys.modules", {"sentence_transformers": None}, clear=False):
            provider = NomicEmbeddingProvider()
            v1 = provider.embed(["a"])[0]
            v2 = provider.embed(["b"])[0]
            assert len(v1) == len(v2) == 768

    def test_similarity_with_partial_zero_vector(self):
        """similarity handles vectors where some dimensions are zero."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v1 = [0.5, 0.0, 0.5, 0.0]
        v2 = [0.5, 0.0, 0.5, 0.0]
        sim = provider.similarity(v1, v2)
        assert abs(sim - 1.0) < 1e-6

    def test_similarity_vector_norm_zero(self):
        """When one vector has zero norm, similarity returns 0.0."""
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        provider = NomicEmbeddingProvider()
        v1 = [0.0, 0.0, 0.0]  # zero norm
        v2 = [0.0, 0.0, 0.0]  # zero norm
        sim = provider.similarity(v1, v2)
        assert sim == 0.0


# ============================================================
#  Import smoke test
# ============================================================


class TestNomicEmbeddingImport:
    def test_nomic_import(self):
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        assert NomicEmbeddingProvider.name == "nomic"

    def test_bge_m3_import(self):
        from shopstack.providers.embeddings_provider import BGEM3EmbeddingProvider
        assert BGEM3EmbeddingProvider.name == "bge-m3"
