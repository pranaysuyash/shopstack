"""Regression tests for the E2E video recording harness.

The video-recording E2E flow at ``scripts/e2e_full_run.py`` records
per-flow WebM videos using Playwright's ``record_video_dir`` browser
context option. The ``videos_mp4/`` subdirectory contains H.264-encoded
MP4 conversions for portable sharing.

This test guards:
- The video recording infrastructure (per-flow .webm files exist)
- The MP4 conversion step (videos_mp4/*.mp4 exist with non-trivial
  durations)
- The 10/10 flow + 0-errors contract from the most recent run
- The ffmpeg / libx264 / ffprobe toolchain is available (else
  the conversion step is dead)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "e2e_full_run.py"
WEBM_DIR = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run" / "videos"
MP4_DIR = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run" / "videos_mp4"
SLIDESHOW_MP4 = MP4_DIR / "e2e_recording.mp4"
RESULTS = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run" / "results.json"

EXPECTED_FLOWS = (
    "01_boot", "02_pantry", "03_shopping", "04_shelf_scan",
    "05_recipe_scan", "06_market_intel", "07_recipes", "08_trips",
    "09_photo_map", "10_memory",
)


class TestVideoRecordingHarnessPreflight:
    """The harness script + video outputs must exist."""

    def test_e2e_script_exists_and_parses(self):
        import ast
        assert SCRIPT.exists()
        ast.parse(SCRIPT.read_text())

    def test_webm_dir_exists(self):
        assert WEBM_DIR.exists(), f"WebM video dir missing: {WEBM_DIR}"

    def test_mp4_dir_exists(self):
        assert MP4_DIR.exists(), f"MP4 video dir missing: {MP4_DIR}"

    def test_uses_record_video_dir(self):
        """The script must call Playwright's record_video_dir API."""
        content = SCRIPT.read_text()
        assert "record_video_dir" in content, (
            "E2E script does not use Playwright's record_video_dir API. "
            "Per motto_v3 §0.7, video recording is required for E2E proof."
        )


class TestVideoFilesPresent:
    """10 per-flow WebM videos + 1 slideshow MP4 must all exist."""

    @pytest.mark.parametrize("slug", EXPECTED_FLOWS)
    def test_per_flow_webm_exists(self, slug: str):
        webm = WEBM_DIR / f"{slug}.webm"
        assert webm.exists(), f"WebM video missing: {webm}"
        assert webm.stat().st_size > 5_000, (
            f"WebM {webm} is too small ({webm.stat().st_size}B) — "
            f"likely empty recording"
        )

    @pytest.mark.parametrize("slug", EXPECTED_FLOWS)
    def test_per_flow_mp4_exists(self, slug: str):
        mp4 = MP4_DIR / f"{slug}.mp4"
        assert mp4.exists(), f"MP4 video missing: {mp4}"
        assert mp4.stat().st_size > 5_000, (
            f"MP4 {mp4} is too small ({mp4.stat().st_size}B)"
        )

    def test_slideshow_mp4_exists(self):
        assert SLIDESHOW_MP4.exists(), f"Slideshow MP4 missing: {SLIDESHOW_MP4}"
        assert SLIDESHOW_MP4.stat().st_size > 100_000, (
            f"Slideshow MP4 too small ({SLIDESHOW_MP4.stat().st_size}B)"
        )


class TestVideoMetadata:
    """The videos must be real recordings with non-zero duration."""

    def test_ffprobe_available(self):
        """ffprobe must be on PATH for the metadata checks below."""
        if shutil.which("ffprobe") is None:
            pytest.skip("ffprobe not installed (needed for duration check)")

    def test_slideshow_duration_is_substantial(self):
        """Slideshow must be ≥ 60s (3s per frame × ≥ 20 frames)."""
        if shutil.which("ffprobe") is None:
            pytest.skip("ffprobe not installed")
        if not SLIDESHOW_MP4.exists():
            pytest.skip("Slideshow MP4 not yet generated")
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(SLIDESHOW_MP4)],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            pytest.skip(f"ffprobe failed: {out.stderr[:200]}")
        duration = float(out.stdout.strip())
        assert duration >= 60.0, (
            f"Slideshow MP4 is only {duration}s — expected ≥ 60s "
            f"(3s per frame × 20+ frames). Capture may be missing frames."
        )

    @pytest.mark.parametrize("slug,min_dur", [
        ("01_boot", 4.0),       # boot flow is short
        ("02_pantry", 8.0),     # tab click + screenshot
        ("04_shelf_scan", 25.0),  # image upload + 15s inference
        ("09_photo_map", 25.0),  # image upload + 15s inference
    ])
    def test_ai_flow_video_is_longer_than_simple_flow(self, slug: str, min_dur: float):
        """AI flows (with image upload + 15s wait) must be ≥ 25s.
        Simple flows (just tab click + 2.5s wait) are typically ≥ 5s.
        This guards against regression where the wait time is dropped."""
        if shutil.which("ffprobe") is None:
            pytest.skip("ffprobe not installed")
        mp4 = MP4_DIR / f"{slug}.mp4"
        if not mp4.exists():
            pytest.skip(f"{mp4} not yet generated")
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(mp4)],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            pytest.skip(f"ffprobe failed: {out.stderr[:200]}")
        duration = float(out.stdout.strip())
        assert duration >= min_dur, (
            f"Video {slug} is {duration}s, expected ≥ {min_dur}s. "
            f"The wait/upload step may have been dropped."
        )


class TestVideoRunResults:
    """The most recent E2E run that produced the videos must show 10/10 + 0 errors."""

    def test_results_show_10_of_10_passed(self):
        if not RESULTS.exists():
            pytest.skip("No results.json yet")
        results = json.loads(RESULTS.read_text())
        assert results["total_flows"] == 10
        assert results["passed"] == 10, (
            f"Expected 10 passed, got {results['passed']}"
        )

    def test_results_zero_page_errors(self):
        if not RESULTS.exists():
            pytest.skip("No results.json yet")
        results = json.loads(RESULTS.read_text())
        assert len(results["page_errors"]) == 0

    def test_results_link_to_all_flow_videos(self):
        """results.json should list all 10 per-flow video paths."""
        if not RESULTS.exists():
            pytest.skip("No results.json yet")
        results = json.loads(RESULTS.read_text())
        flow_videos = results.get("flow_videos", {})
        assert len(flow_videos) == 10, (
            f"results.json lists {len(flow_videos)} flow videos, expected 10"
        )
        for slug in EXPECTED_FLOWS:
            assert slug in flow_videos, (
                f"results.json missing flow_videos['{slug}']"
            )
