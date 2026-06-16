"""Regression tests for INFRA-1 and INFRA-2 (Pass 17, 2026-06-15).

These tests pin the current state of the deployment infrastructure
after the addendum to ``MASTER_AUDIT.md`` reclassified both
findings as resolved (INFRA-2) or acceptable-by-design (INFRA-1).

**Why this exists (motto_v3 §6 pre-existing is not an excuse):**

The original MASTER_AUDIT claimed:

  * INFRA-1: "CI Python matrix (3.11/3.12/3.13) diverges from
    Dockerfile (3.12) and doc-health/wcag workflows (3.14). The mlx
    segfault (py3.14) is untested in CI's primary matrix."

  * INFRA-2: "`docker-compose.yml` targets `runtime` stage which does
    not exist in Dockerfile (stages are `builder`, default, `dev`)."

The Pass 17 re-verification found:

  * INFRA-1: the "divergence" is by design. The primary matrix
    verifies backward compat (3.11-3.13); the other workflows run
    on the dev runtime (3.14) to catch forward-compat regressions.
    The 3.14 experimental job in `ci.yml` is the bridge.

  * INFRA-2: the original evidence was stale. The current
    Dockerfile has 3 named stages (`builder`, `runtime`, `dev`)
    and `docker-compose.yml`'s `target: runtime` correctly
    resolves to the runtime stage.

These tests guard against future drift that re-introduces the
original bugs. The tests run fast (no DB, no I/O) and can be
wired into pre-commit later.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
DOCKER_COMPOSE = ROOT / "docker-compose.yml"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"


# ── INFRA-2: Dockerfile has the `runtime` stage ─────────────────────


def test_dockerfile_has_runtime_stage():
    """The Dockerfile declares a ``runtime`` stage (INFRA-2 guard).

    The original audit said "stages are `builder`, default, `dev`" —
    that was stale. The current Dockerfile has 3 named stages
    (builder, runtime, dev). This test pins the runtime stage
    so a future refactor can't accidentally remove it and
    re-break `docker compose up`.
    """
    content = DOCKERFILE.read_text()
    # The line ``FROM python:3.12-slim AS runtime`` is what
    # `docker-compose.yml` targets. Match the literal.
    assert re.search(
        r"^FROM\s+\S+\s+AS\s+runtime\b",
        content,
        re.MULTILINE,
    ), (
        "Dockerfile must declare a `runtime` stage (`FROM ... AS runtime`). "
        "Without it, `docker-compose.yml`'s `target: runtime` fails. "
        "Re-introduces INFRA-2."
    )


def test_dockerfile_has_three_named_stages():
    """The Dockerfile declares exactly the 3 stages (builder, runtime, dev).

    This pins the multi-stage build contract. Adding a 4th stage
    without updating the compose file would silently break the
    pipeline. Removing a stage would break the workflow that
    depends on it.
    """
    content = DOCKERFILE.read_text()
    stages = set(re.findall(r"^FROM\s+\S+\s+AS\s+(\w+)\s*$", content, re.MULTILINE))
    expected = {"builder", "runtime", "dev"}
    assert stages == expected, (
        f"Dockerfile must declare exactly {sorted(expected)} stages. "
        f"Found: {sorted(stages)}. Adding or removing stages without "
        f"updating the compose file is a regression."
    )


# ── INFRA-2: docker-compose targets an existing stage ──────────────


def test_docker_compose_targets_existing_stage():
    """The ``target:`` in docker-compose.yml must match a real stage in the Dockerfile.

    Re-introduces the original INFRA-2: ``docker compose up`` fails
    if the target stage doesn't exist. We parse the target
    dynamically (not hardcoded to "runtime") so this test catches
    ANY drift between compose and Dockerfile.
    """
    compose = DOCKER_COMPOSE.read_text()
    target_match = re.search(
        r"^\s*target:\s*(\S+)\s*$",
        compose,
        re.MULTILINE,
    )
    assert target_match, (
        "docker-compose.yml must have a `target:` line. "
        "Without it, docker compose up uses the default (final) "
        "stage of the Dockerfile — which may not be the intended "
        "runtime stage."
    )
    target = target_match.group(1).strip()
    dockerfile = DOCKERFILE.read_text()
    stages = set(re.findall(r"^FROM\s+\S+\s+AS\s+(\w+)\s*$", dockerfile, re.MULTILINE))
    assert target in stages, (
        f"docker-compose.yml targets `{target}` but the Dockerfile "
        f"only has stages {sorted(stages)}. This is the original "
        f"INFRA-2 bug. Either (a) add a `FROM ... AS {target}` "
        f"stage to the Dockerfile, or (b) change the compose file "
        f"to target an existing stage."
    )


# ── INFRA-1: CI Python matrix is intentional (the 3.14 bridge exists) ─


def test_ci_workflow_has_3_14_experimental_job():
    """``ci.yml`` must have a 3.14 job in addition to the primary matrix.

    The original INFRA-1 evidence said "3.14 is untested in CI's
    primary matrix". The fix (per the addendum) is a dedicated
    3.14 job, not changing the primary matrix. This test guards
    that the 3.14 job is present.
    """
    content = CI_YML.read_text()
    # Find all python-version declarations.
    versions = re.findall(r"python-version:\s*\[?\"([0-9.]+)\"?\]?", content)
    assert "3.14" in versions, (
        f"ci.yml must reference Python 3.14 (the experimental "
        f"forward-compat job). Found: {versions}. Per the addendum, "
        f"the 3.14 experimental job is the bridge that catches "
        f"forward-compat regressions (e.g. mlx segfault). Removing "
        f"it re-introduces INFRA-1."
    )


def test_ci_workflow_primary_matrix_supports_3_11_to_3_13():
    """The primary CI matrix is 3.11/3.12/3.13 (the supported production versions).

    This pins the contract: the primary matrix verifies backward
    compatibility for the 3 supported production Python versions.
    The 3.14 job is the separate experimental gate.
    """
    content = CI_YML.read_text()
    # The primary matrix is the FIRST ``matrix:`` block (the
    # experimental job has its own strategy if separate). We
    # look for the line ``python-version: ["3.11", "3.12", "3.13"]``
    # or the equivalent with quotes.
    matrix_match = re.search(
        r"python-version:\s*\[([^\]]+)\]",
        content,
    )
    assert matrix_match, (
        "ci.yml must have a `python-version: [...]` matrix. "
        "If this fails, the matrix declaration was changed to "
        "use a non-list format (e.g. a single string)."
    )
    listed_versions = [
        v.strip().strip("'\"") for v in matrix_match.group(1).split(",")
    ]
    expected = ["3.11", "3.12", "3.13"]
    assert listed_versions == expected, (
        f"ci.yml's primary python-version matrix must be exactly "
        f"{expected} (the supported production versions). "
        f"Found: {listed_versions}. Changing the primary matrix is "
        f"a breaking change for the backward-compat story."
    )


def test_dev_workflows_use_python_3_14():
    """doc-health, quality-gates, wcag all run on 3.14 (the dev runtime).

    Per the INFRA-1 addendum, the dev workflows (doc-health,
    quality-gates, wcag) all run on Python 3.14 to catch
    forward-compat regressions. The Dockerfile uses 3.12 for
    production. This test pins the dev runtime.
    """
    expected = {"doc-health.yml", "quality-gates.yml", "wcag.yml"}
    for filename in expected:
        path = ROOT / ".github" / "workflows" / filename
        if not path.exists():
            pytest.skip(f"{filename} not present in this checkout")
        content = path.read_text()
        # The python-version line should be exactly "3.14" (not a list).
        # If it's a list, that's a regression — the dev workflow
        # should pin to a single version.
        assert re.search(
            r'python-version:\s*["\']3\.14["\']',
            content,
        ), (
            f"{filename} must pin python-version to 3.14 (the dev "
            f"runtime). If the dev runtime changes, update this test "
            f"AND update the AGENTS.md / Dockerfile docs."
        )
