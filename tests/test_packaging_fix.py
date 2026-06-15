"""Regression tests for pyproject.toml packaging fix (2026-06-14).

Per the GitHub audit finding (pyproject.toml had heavy ML deps in the
base `dependencies` list, forcing every user to install 2+ GB even for
a mock-only Gradio app), the heavy deps are now split into optional
extras:

  - cloud: openai
  - local-gguf: llama-cpp-python
  - local-mlx: mlx
  - vision: transformers, torch
  - embeddings: sentence-transformers
  - all: everything

The base install should only have the lightweight core deps.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestPyprojectPackaging:
    """The packaging metadata must be consistent with the local-first
    philosophy (lightweight base, heavy deps in extras)."""

    @pytest.fixture
    def pyproject(self) -> dict:
        with open(REPO_ROOT / "pyproject.toml", "rb") as f:
            return tomllib.load(f)

    def test_no_heavy_deps_in_base_dependencies(self, pyproject: dict):
        """torch, transformers, mlx, llama-cpp-python, sentence-transformers,
        openai must NOT be in the base dependencies."""
        base_deps = pyproject["project"]["dependencies"]
        heavy_deps = [
            "torch", "transformers", "mlx", "llama-cpp-python",
            "sentence-transformers", "openai",
        ]
        # Strip version specifiers for comparison
        base_names = []
        for dep in base_deps:
            base_names.append(
                dep.split(">=")[0].split("==")[0].split("<")[0].split(">")[0].strip()
            )
        leaked = [d for d in heavy_deps if d in base_names]
        assert not leaked, (
            f"Heavy ML deps must NOT be in base dependencies. "
            f"Move them to optional extras (cloud/local-gguf/local-mlx/"
            f"vision/embeddings). Found in base: {leaked}"
        )

    def test_cloud_extra_has_openai(self, pyproject: dict):
        extras = pyproject["project"]["optional-dependencies"]
        assert "cloud" in extras, "Missing 'cloud' extra"
        assert "openai" in " ".join(extras["cloud"]), (
            "cloud extra should include openai"
        )

    def test_local_gguf_extra_has_llama_cpp(self, pyproject: dict):
        extras = pyproject["project"]["optional-dependencies"]
        assert "local-gguf" in extras, "Missing 'local-gguf' extra"
        assert "llama-cpp-python" in " ".join(extras["local-gguf"]), (
            "local-gguf extra should include llama-cpp-python"
        )

    def test_local_mlx_extra_has_mlx(self, pyproject: dict):
        extras = pyproject["project"]["optional-dependencies"]
        assert "local-mlx" in extras, "Missing 'local-mlx' extra"
        assert "mlx" in " ".join(extras["local-mlx"]), (
            "local-mlx extra should include mlx"
        )

    def test_vision_extra_has_transformers_torch(self, pyproject: dict):
        extras = pyproject["project"]["optional-dependencies"]
        assert "vision" in extras, "Missing 'vision' extra"
        joined = " ".join(extras["vision"])
        assert "transformers" in joined
        assert "torch" in joined

    def test_embeddings_extra_has_sentence_transformers(self, pyproject: dict):
        extras = pyproject["project"]["optional-dependencies"]
        assert "embeddings" in extras, "Missing 'embeddings' extra"
        assert "sentence-transformers" in " ".join(extras["embeddings"])

    def test_all_extra_exists(self, pyproject: dict):
        """The 'all' extra should include all the heavy ML deps."""
        extras = pyproject["project"]["optional-dependencies"]
        assert "all" in extras, (
            "Missing 'all' meta-extra that bundles all heavy ML deps"
        )

    def test_core_deps_include_gradio_pydantic(self, pyproject: dict):
        """The base install should still have the Gradio + Pydantic core."""
        base_deps = pyproject["project"]["dependencies"]
        joined = " ".join(base_deps)
        assert "gradio" in joined, "gradio must be in base deps"
        assert "pydantic" in joined, "pydantic must be in base deps"
