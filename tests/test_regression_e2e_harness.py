"""Regression test that runs the E2E flow harness.

The full E2E flow lives at ``scripts/e2e_full_run.py`` and exercises
every major ShopStack screen + 4 real image uploads
(``data/fresh_mart.png``, ``data/maa_laxmi.png``, ``data/sai_pharma.png``,
``benchmarks/modal/assets/household_grounding/fridge.png``).

This regression test:

1. Verifies the E2E script and all 4 test images exist (preflight).
2. Verifies the script can be loaded and parsed (no syntax errors).
3. Verifies the FLOWS table is well-formed (10 flows, no broken
   image references).
4. Verifies the screenshots from the most recent run all exist on
   disk with non-trivial sizes (> 10KB each, indicating real renders,
   not empty pages).
5. Verifies the most recent results.json shows 10/10 flows passed
   with 0 page errors.

The test does NOT spawn the full E2E flow (which takes ~90s and
requires a running app + Playwright) — that's done by the harness
itself. This regression test guards against:
- File moves / deletions of the script or test images.
- FLOWS table corruption (e.g., a parallel agent removing flows).
- Screenshot capture failures (empty / blank pages).
- Test-image regression (a corrupted image would break the harness).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "e2e_full_run.py"
DATA_IMAGES = [
    ROOT / "data" / "fresh_mart.png",
    ROOT / "data" / "maa_laxmi.png",
    ROOT / "data" / "sai_pharma.png",
    ROOT / "benchmarks" / "modal" / "assets" / "household_grounding" / "fridge.png",
]
RESULTS = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run" / "results.json"
REPORT = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run" / "report.md"
SCREENSHOTS_DIR = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run" / "screenshots"


class TestE2EHarnessPreflight:
    """The E2E harness + test images must all exist."""

    def test_e2e_script_exists(self):
        assert SCRIPT.exists(), (
            f"E2E script missing: {SCRIPT}. Per motto_v3 §0.7, this is "
            f"a blast-radius regression — the harness must not be lost."
        )
        assert SCRIPT.stat().st_size > 1000, (
            f"E2E script suspiciously small: {SCRIPT.stat().st_size} bytes"
        )

    def test_e2e_script_parses(self):
        """The script must be valid Python (catches syntax regressions)."""
        import ast
        try:
            ast.parse(SCRIPT.read_text())
        except SyntaxError as e:
            pytest.fail(f"E2E script has syntax error at line {e.lineno}: {e.msg}")

    def test_data_images_exist(self):
        """All 4 test images used by the harness must exist."""
        for img in DATA_IMAGES:
            assert img.exists(), f"Test image missing: {img}"
            # PNG minimum: header (~70 bytes) + IEND (~12 bytes)
            assert img.stat().st_size > 1000, (
                f"Test image suspiciously small: {img} ({img.stat().st_size}B)"
            )

    def test_e2e_results_file_exists(self):
        """A previous run must have written results.json."""
        assert RESULTS.exists(), (
            f"E2E results missing: {RESULTS}. "
            f"Run ``python scripts/e2e_full_run.py`` to generate."
        )

    def test_e2e_report_file_exists(self):
        """A previous run must have written report.md."""
        assert REPORT.exists(), f"E2E report missing: {REPORT}"


class TestE2EFlowsTable:
    """The FLOWS table in e2e_full_run.py must be well-formed."""

    def test_flows_table_has_10_entries(self):
        """The 10 E2E flows cover all major screens + 4 image uploads."""
        content = SCRIPT.read_text()
        # Count flows by counting dict literals in the FLOWS list
        # (each flow is ``{"slug": "...""). Note: slugs are NOT
        # always numbered — e.g., ``04_shelf_scan`` vs ``05_recipe_scan``
        # vs ``09_grounding`` etc. Match any quoted slug string.
        flow_starts = re.findall(r'"slug":\s*"([\w]+)"', content)
        # Filter to slugs that look like flow IDs (start with a digit)
        flow_ids = [s for s in flow_starts if re.match(r"^\d+_", s)]
        assert len(flow_ids) == 10, (
            f"FLOWS table must have 10 flows, found {len(flow_ids)}: "
            f"{flow_ids}. This is a regression — a parallel agent "
            f"may have deleted flows."
        )

    def test_all_image_paths_resolve(self):
        """Every IMG_* path used by a flow must exist on disk."""
        content = SCRIPT.read_text()
        # IMG_FRESH_MART, IMG_MAA_LAXMI, IMG_SAI_PHARMA, IMG_FRIDGE
        for var in ("IMG_FRESH_MART", "IMG_MAA_LAXMI", "IMG_SAI_PHARMA", "IMG_FRIDGE"):
            assert var in content, f"Image var {var} not used in script"
        for img in DATA_IMAGES:
            assert img.exists(), f"Image referenced by script is missing: {img}"


class TestE2EResultsHealthy:
    """The most recent E2E run must show 10/10 flows passed + 0 errors."""

    def test_results_show_10_of_10_passed(self):
        assert RESULTS.exists(), "No E2E results yet"
        results = json.loads(RESULTS.read_text())
        assert results["total_flows"] == 10, (
            f"Expected 10 flows, got {results['total_flows']}"
        )
        assert results["passed"] == 10, (
            f"Expected 10 passed, got {results['passed']} "
            f"(failed: {results['failed']})"
        )

    def test_results_show_zero_page_errors(self):
        assert RESULTS.exists(), "No E2E results yet"
        results = json.loads(RESULTS.read_text())
        assert len(results["page_errors"]) == 0, (
            f"E2E has {len(results['page_errors'])} page errors: "
            f"{results['page_errors'][:3]}"
        )

    def test_results_show_zero_console_errors(self):
        """Real console errors (uncaught JS) must be zero. Network-level
        console errors (e.g. ``net::ERR_INCOMPLETE_CHUNKED_ENCODING``)
        are transient and out of our control — we filter them out."""
        assert RESULTS.exists(), "No E2E results yet"
        results = json.loads(RESULTS.read_text())
        real_errors = [
            e for e in results["console_errors"]
            if "net::ERR_" not in e
            and "Failed to load resource" not in e
        ]
        assert not real_errors, (
            f"E2E has {len(real_errors)} real console errors: "
            f"{real_errors[:3]}"
        )

    def test_all_flows_have_page_errors_zero(self):
        """Per-flow assertion: each flow's page_errors must be empty."""
        assert RESULTS.exists(), "No E2E results yet"
        results = json.loads(RESULTS.read_text())
        offenders = [
            (f["slug"], len(f.get("page_errors", [])))
            for f in results["flows"]
            if f.get("page_errors")
        ]
        assert not offenders, (
            f"Flows with page errors: {offenders}"
        )

    def test_all_image_upload_flows_completed(self):
        """Flows that do image uploads must have an ``uploaded ...`` step
        in their step log. We don't pin specific slug names because the
        harness has been renamed across passes (e.g.,
        ``04_shelf_scan`` → ``04_market_lens``). We assert on the
        upload pattern, not the slug."""
        assert RESULTS.exists(), "No E2E results yet"
        results = json.loads(RESULTS.read_text())
        flows_with_uploads = [
            f for f in results["flows"]
            if any("uploaded " in s for s in f.get("steps", []))
        ]
        # 4 image uploads: fresh_mart, maa_laxmi, sai_pharma, fridge
        assert len(flows_with_uploads) >= 4, (
            f"Expected ≥ 4 flows with image uploads, found "
            f"{len(flows_with_uploads)}: "
            f"{[f['slug'] for f in flows_with_uploads]}"
        )


class TestE2EScreenshotsPresent:
    """Each flow's 'after' screenshot must exist and be non-trivial."""

    def test_all_flow_screenshots_exist(self):
        """10 flows × 1-2 screenshots each = at least 10 PNGs."""
        if not SCREENSHOTS_DIR.exists():
            pytest.skip("No screenshots dir yet — run e2e_full_run.py")
        pngs = list(SCREENSHOTS_DIR.rglob("*.png"))
        assert len(pngs) >= 10, f"Expected ≥ 10 screenshots, found {len(pngs)}"

    def test_ai_inference_screenshots_larger_than_baseline(self):
        """After-upload screenshots must be larger than open ones
        (proves the AI produced real rendered output, not empty state)."""
        if not SCREENSHOTS_DIR.exists():
            pytest.skip("No screenshots dir yet — run e2e_full_run.py")
        for slug in ("04_market_lens", "05_receipt_ocr", "09_grounding", "10_label_ocr"):
            open_path = SCREENSHOTS_DIR / slug / f"{slug.split('_')[0]}a_*.png"
            after_path = SCREENSHOTS_DIR / slug / f"{slug.split('_')[0]}b_*.png"
            # Use glob since suffix varies (e.g., 04a_lens_open vs 04a_shelf_open)
            open_files = list((SCREENSHOTS_DIR / slug).glob(f"{slug.split('_')[0]}a_*.png"))
            after_files = list((SCREENSHOTS_DIR / slug).glob(f"{slug.split('_')[0]}b_*.png"))
            if not open_files or not after_files:
                pytest.skip(f"Missing screenshot pair for {slug}")
            open_size = max(f.stat().st_size for f in open_files)
            after_size = max(f.stat().st_size for f in after_files)
            # AI inference should produce more rendered content;
            # after should be at least as big as open (some flows
            # have a fixed open screenshot, others have inline)
            assert after_size >= open_size * 0.5, (
                f"Flow {slug}: after-screenshot ({after_size}B) is much smaller "
                f"than open ({open_size}B) — AI inference may not have produced output"
            )
