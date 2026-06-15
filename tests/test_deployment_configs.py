"""Tests for deployment config files (AI-11).

Per `docs/audits/ACTION_ITEMS.md` AI-11: Verify all 6 deployment
config files exist so the app can be deployed to multiple
platforms (Docker, Fly.io, Render, Railway, HF Spaces).

This test guards against accidental deletion of deployment configs
during cleanup or refactors. Each config represents a deployment
target; missing one means that target is broken.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_exists():
    """Dockerfile is required for Docker-based deployments."""
    assert (PROJECT_ROOT / "Dockerfile").is_file(), (
        "Dockerfile is missing. Without it, Docker-based deployments "
        "(Railway, Render, local docker-compose) will fail."
    )


def test_docker_compose_exists():
    """docker-compose.yml is required for local development."""
    assert (PROJECT_ROOT / "docker-compose.yml").is_file(), (
        "docker-compose.yml is missing. Local Docker-based dev "
        "environments will not work."
    )


def test_fly_toml_exists():
    """fly.toml is required for Fly.io deployments."""
    assert (PROJECT_ROOT / "fly.toml").is_file(), (
        "fly.toml is missing. Fly.io deployment config is gone."
    )


def test_render_yaml_exists():
    """render.yaml is required for Render deployments."""
    assert (PROJECT_ROOT / "render.yaml").is_file(), (
        "render.yaml is missing. Render deployment config is gone."
    )


def test_railway_json_exists():
    """railway.json is required for Railway deployments."""
    assert (PROJECT_ROOT / "railway.json").is_file(), (
        "railway.json is missing. Railway deployment config is gone."
    )


def test_hf_spaces_deployment_doc_exists():
    """The HF Spaces deployment doc must exist for AI-11 closure."""
    # Per motto_v3 §15 (Documentation Rules), the doc was moved to
    # `Docs/archive/huggingface-space-deployment.md` for archival
    # (per the workspace's archive policy for pre-rename documents).
    candidates = [
        PROJECT_ROOT / "Docs" / "huggingface-space-deployment.md",
        PROJECT_ROOT / "Docs" / "archive" / "huggingface-space-deployment.md",
    ]
    found = next((p for p in candidates if p.is_file()), None)
    assert found is not None, (
        f"None of {candidates} exists. Per the README, this doc is "
        f"the canonical guide for HF Spaces deployment. Without it, "
        f"HF Spaces users won't know how to deploy."
    )


def test_dockerfile_mentions_app_py():
    """Dockerfile should reference app.py as the entry point."""
    content = (PROJECT_ROOT / "Dockerfile").read_text()
    assert "app.py" in content, (
        "Dockerfile doesn't mention app.py. Without this, the "
        "Docker image won't know which file to launch."
    )


def test_readme_has_hf_metadata():
    """README.md should have HF Spaces metadata block (per AI-4)."""
    content = (PROJECT_ROOT / "README.md").read_text()
    # The HF metadata block is a YAML frontmatter at the top
    assert "sdk: gradio" in content or "app_file: app.py" in content, (
        "README.md missing HF Spaces metadata block (sdk: gradio, "
        "app_file: app.py). Per AI-4, this is required for HF "
        "Spaces auto-detection."
    )
