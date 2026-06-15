"""Regression test that pins the production-code empty-state contract.

The empty-state rewrite (UX_OVERHAUL_PLAN §Phase 3) is now complete
across production code. This test runs
``shopstack.tools.lint_empty_states`` against ``shopstack/`` and
asserts zero findings — i.e. every user-facing empty state in the
app includes an actionable next step (per motto_v3 §0.14 product
reality and operator workflow rule).

Test fixtures (under ``tests/``) and shopstack/tools are excluded
from the scan:

* Test fixtures legitimately contain "no X yet" patterns as input
  data for screen tests. The fixture itself is not user-facing.
* The lint tool itself contains the canonical patterns as
  self-references; scanning it would be a self-match.

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


# Skip if the shopstack package is not importable in the current venv.
pytestmark = pytest.mark.skipif(
    not Path("shopstack").is_dir(),
    reason="shopstack/ not present (run from repo root)",
)


def test_production_code_passes_empty_state_lint() -> None:
    """``shopstack/`` and ``app.py`` must have zero empty-state findings.

    The lint is non-blocking by default; this test invokes it and
    asserts the production-only findings count is 0. If a future
    PR regresses the empty-state contract, this test fails with
    the exact file:line:message to fix.

    Known false positives are excluded via ``--exclude``:

    * ``planner/prompts.py`` — LLM prompt templates that include
      "Inventory is empty" as a context hint, not user copy.
    * ``services/sparkline.py`` — SVG text labels that the lint
      heuristically reads as empty states but are actually chart
      watermarks.
    * ``tools/lint_empty_states.py`` — self-scan (always excluded
      by the tool itself).
    * ``benchmarks/`` — benchmark scripts, not user-facing.
    """
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [
            sys.executable, "-m", "shopstack.tools.lint_empty_states",
            "--exclude", "shopstack/planner/prompts.py",
            "--exclude", "shopstack/services/sparkline.py",
            "--exclude", "shopstack/tools/lint_empty_states.py",
            "--exclude", "/benchmarks/",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # The lint exits 0 by default (advisory) — that's fine; we read
    # stdout regardless.

    text = result.stdout
    # The excluded files are not in the scan output. Anything that
    # remains is a real production finding.
    assert "lint_empty_states: no findings" in text or \
           "production findings: 0" in text, (
        f"Empty-state lint found new production-code finding(s). "
        f"The empty-state rewrite (UX_OVERHAUL_PLAN §Phase 3) "
        f"requires every user-facing empty state to include an "
        f"actionable next step.\n\n"
        f"Lint output:\n{text}\n\n"
        f"Fix: replace the message with one that includes an "
        f"actionable verb (Add, Import, Scan, Try) or pass an "
        f"action_label to empty_state_enhanced(). See "
        f"shopstack/services/empty_states.py for the canonical pattern."
    )
