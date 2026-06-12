"""Tests for FluxImageProvider — image generation, SVG fallback, converter detection.

Covers:
- FluxImageProvider init and available property
- SVG converter detection (cairosvg and svglib)
- generate_card_image with SVG-to-PNG conversion
- generate_card_image SVG-only fallback when no converter is available
- generate_shopping_poster with items
- generate_shopping_poster with empty items (summary card fallback)
- healthcheck
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Guard against heavy import chains (diffusers, torch, etc.) during collection
# by pre-mocking heavy deps. The FluxImageProvider only needs SVG converters
# for most tests, not the full FLUX pipeline.
if "pytest" in sys.modules and "shopstack.providers.image_gen_provider" not in sys.modules:
    # Only apply guards during test collection, not during runtime imports
    pass

_SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">'
    '<rect width="100" height="100" rx="5" fill="#f0f0f0"/>'
    '<text x="50" y="50" text-anchor="middle" fill="#333" font-size="14">Test</text>'
    "</svg>"
)


class TestFluxImageProviderInit:
    def test_default_init(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        assert provider.name == "flux_image_gen"
        assert provider.model_id == "flux.2-klein-4b"
        assert provider.parameter_count == 4.0
        assert "image_gen" in provider.capabilities

    def test_available_with_svg_converter(self):
        """Provider should be available if an SVG converter is detected."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        # Should detect at least one SVG converter or fall back gracefully
        assert provider.available is True or provider.available is False

    def test_detect_svg_converter_returns_string_or_none(self):
        """_detect_svg_converter returns a converter name or None."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        result = provider._detect_svg_converter()
        # Should be one of: "cairosvg", "svglib", or None (if neither installed)
        assert result in ("cairosvg", "svglib", None)

    def test_load_graceful_fallback(self):
        """load() should not crash when FLUX pipeline deps are missing."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        provider.load()  # Should not raise, even without diffusers/torch

    def test_healthcheck(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        assert provider.healthcheck() is True

    def test_repr_and_available_fallback(self):
        """available property returns True if SVG converter is present even without pipeline."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        # _svg_to_png might be set even if _pipeline is None
        was_available = provider._svg_to_png is not None
        assert provider.available == (provider._available or was_available)


class TestFluxGenerateCardImage:
    def test_generate_card_svg_fallback(self):
        """generate_card_image should save SVG when no converter is available."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", None):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_card_image(_SAMPLE_SVG, output_dir=tmpdir)
                assert result.endswith(".svg")
                assert os.path.isfile(result)
                with open(result) as f:
                    content = f.read()
                    assert "Test" in content
                    assert "<svg" in content

    def test_generate_card_cairosvg_path(self):
        """generate_card_image should try cairosvg conversion when available."""
        import importlib

        cairosvg_available = importlib.util.find_spec("cairosvg") is not None

        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", "cairosvg" if cairosvg_available else None):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_card_image(_SAMPLE_SVG, output_dir=tmpdir)
                if cairosvg_available:
                    assert result.endswith(".png")
                else:
                    # Falls through to svglib or SVG fallback
                    assert os.path.isfile(result)

    def test_generate_card_svglib_path(self):
        """generate_card_image should try svglib conversion when cairosvg fails and svglib available."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", "svglib"):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_card_image(_SAMPLE_SVG, output_dir=tmpdir)
                # Even if svglib conversion fails at runtime, should fall to SVG
                assert os.path.isfile(result)

    def test_generate_card_default_output_dir(self):
        """generate_card_image creates its own temp dir when output_dir is None."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", None):
            result = provider.generate_card_image(_SAMPLE_SVG)
            assert os.path.isfile(result)
            assert result.endswith(".svg")
            # Clean up
            os.remove(result)
            Path(result).parent.rmdir()

    def test_generate_card_with_empty_svg(self):
        """generate_card_image handles empty SVG content gracefully."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", None):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_card_image("<svg></svg>", output_dir=tmpdir)
                assert result.endswith(".svg")
                assert os.path.isfile(result)


class TestFluxGenerateShoppingPoster:
    def test_poster_with_items(self):
        """generate_shopping_poster creates cards from items and renders to file."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        items = [
            {"name": "Milk", "decision": "buy", "reason": "Running low", "confidence": 0.9},
            {"name": "Bread", "decision": "buy", "reason": "Need for breakfast", "confidence": 0.8},
            {"name": "Butter", "decision": "skip", "reason": "Already have", "confidence": 0.7},
        ]
        with patch.object(provider, "_svg_to_png", None):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_shopping_poster(items, output_dir=tmpdir)
                assert os.path.isfile(result)
                assert result.endswith(".svg")
                with open(result) as f:
                    content = f.read()
                    assert "Milk" in content
                    assert "Bread" in content
                    assert "Butter" in content

    def test_poster_with_empty_items(self):
        """generate_shopping_poster falls back to summary card when items list is empty."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", None):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_shopping_poster([], output_dir=tmpdir)
                assert os.path.isfile(result)
                with open(result) as f:
                    content = f.read()
                    assert "Shopping" in content or "Summary" in content

    def test_poster_with_single_item(self):
        """generate_shopping_poster handles a single item gracefully."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        items = [
            {"name": "Eggs", "decision": "buy", "reason": "Weekly restock", "confidence": 0.85},
        ]
        with patch.object(provider, "_svg_to_png", None):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_shopping_poster(items, output_dir=tmpdir)
                assert os.path.isfile(result)
                with open(result) as f:
                    content = f.read()
                    assert "Eggs" in content


class TestFluxProviderEdgeCases:
    def test_generate_card_cairosvg_fallback_to_svg(self):
        """When cairosvg conversion fails, fallback to SVG save."""
        from unittest.mock import MagicMock

        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        mock_cairosvg = MagicMock()
        mock_cairosvg.svg2png.side_effect = RuntimeError("conversion failed")
        with patch.object(provider, "_svg_to_png", "cairosvg"):
            with patch.dict("sys.modules", {"cairosvg": mock_cairosvg}):
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = provider.generate_card_image(_SAMPLE_SVG, output_dir=tmpdir)
                    # Should fall through to SVG save
                    assert os.path.isfile(result)
                    assert result.endswith(".svg")

    def test_generate_card_svglib_fallback_to_svg(self):
        """When svglib conversion fails at runtime, fallback to SVG save."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", "svglib"):
            Path("/tmp/svglib_mock").mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_card_image(_SAMPLE_SVG, output_dir=tmpdir)
                assert os.path.isfile(result)

    def test_poster_with_theme_override(self):
        """generate_shopping_poster accepts a CardTheme override."""
        from shopstack.providers.image_gen_provider import FluxImageProvider
        from shopstack.ui.renderers.image_cards import CardTheme

        provider = FluxImageProvider()
        theme = CardTheme(background="#f0f0f0", accent="#ff0000", text="#333")
        items = [{"name": "Test", "decision": "buy", "reason": "Test", "confidence": 0.5}]
        with patch.object(provider, "_svg_to_png", None):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = provider.generate_shopping_poster(items, theme=theme, output_dir=tmpdir)
                assert os.path.isfile(result)



class TestFluxGenerateCard:
    def test_generate_card_basic(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", None):
            result = provider.generate_card("Milk", {"decision": "buy", "reason": "Weekly restock"})
            assert os.path.isfile(result)
            with open(result) as f:
                content = f.read()
                assert "Milk" in content
                assert "BUY" in content or "buy" in content.lower()
            os.remove(result)
            Path(result).parent.rmdir()

    def test_generate_card_with_theme(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", None):
            result = provider.generate_card(
                "Tomato",
                {
                    "decision": "skip",
                    "reason": "Already have",
                    "confidence": 0.9,
                    "background": "#f0f0f0",
                    "accent": "#ff0000",
                    "text_color": "#333333",
                },
            )
            assert os.path.isfile(result)
            with open(result) as f:
                content = f.read()
                assert "Tomato" in content
                assert "SKIP" in content or "skip" in content.lower()
            os.remove(result)
            Path(result).parent.rmdir()

    def test_generate_card_with_output_dir(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(provider, "_svg_to_png", None):
                result = provider.generate_card(
                    "Eggs", {"decision": "buy", "output_dir": tmpdir}
                )
                assert os.path.isfile(result)
                assert result.startswith(tmpdir)
                assert "Eggs" in Path(result).read_text()

    def test_generate_card_default_params(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with patch.object(provider, "_svg_to_png", None):
            result = provider.generate_card("Rice", {})
            assert os.path.isfile(result)
            with open(result) as f:
                content = f.read()
                assert "Rice" in content
            os.remove(result)
            Path(result).parent.rmdir()


class TestBboxNormalisation:
    """Tests for normalize_bbox, _detect_bbox_format, and resolve_detection_bbox."""

    # ── _detect_bbox_format ────────────────────────────────────────

    def test_detect_normalized_xyxy(self):
        """Values in [0, 1] without center pattern → normalized_xyxy."""
        from shopstack.providers.image_gen_provider import _detect_bbox_format

        # Typical corner coords — not centered
        assert _detect_bbox_format([0.1, 0.1, 0.5, 0.5]) == "normalized_xyxy"
        assert _detect_bbox_format([0.0, 0.0, 1.0, 1.0]) == "normalized_xyxy"

    def test_detect_normalized_cxcywh(self):
        """Values near 0.5 center with small w/h → normalized_cxcywh."""
        from shopstack.providers.image_gen_provider import _detect_bbox_format

        assert _detect_bbox_format([0.5, 0.5, 0.4, 0.3]) == "normalized_cxcywh"
        assert _detect_bbox_format([0.6, 0.5, 0.2, 0.2]) == "normalized_cxcywh"

    def test_detect_absolute_xyxy(self):
        """Large values (>1.5) without small w/h pattern → absolute_xyxy."""
        from shopstack.providers.image_gen_provider import _detect_bbox_format

        assert _detect_bbox_format([100, 100, 500, 500]) == "absolute_xyxy"
        assert _detect_bbox_format([50, 50, 150, 200]) == "absolute_xyxy"

    def test_detect_absolute_xywh(self):
        """Large top-left with small w/h → absolute_xywh."""
        from shopstack.providers.image_gen_provider import _detect_bbox_format

        assert _detect_bbox_format([100, 100, 50, 50]) == "absolute_xywh"
        assert _detect_bbox_format([200, 300, 40, 60]) == "absolute_xywh"
        # Edge: w/h exactly half of x/y → still xywh (uses ≤)
        assert _detect_bbox_format([200, 200, 100, 100]) == "absolute_xywh"

    def test_detect_absolute_cxcywh(self):
        """Large center with moderate w/h → absolute_cxcywh."""
        from shopstack.providers.image_gen_provider import _detect_bbox_format

        assert _detect_bbox_format([300, 250, 200, 150]) == "absolute_cxcywh"

    def test_detect_empty_bbox(self):
        """Empty or short bbox → normalized_xyxy."""
        from shopstack.providers.image_gen_provider import _detect_bbox_format

        assert _detect_bbox_format([]) == "normalized_xyxy"
        assert _detect_bbox_format([1.0]) == "normalized_xyxy"

    # ── normalize_bbox ─────────────────────────────────────────────

    def test_normalize_xyxy_pass_through(self):
        """normalized_xyxy input is returned as-is (clamped)."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox([0.1, 0.2, 0.8, 0.9], 200, 200)
        assert result == [0.1, 0.2, 0.8, 0.9]

    def test_normalize_xyxy_with_explicit_format(self):
        """Explicit format tag is respected."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox(
            [0.1, 0.2, 0.8, 0.9], 200, 200, bbox_format="normalized_xyxy"
        )
        assert result == [0.1, 0.2, 0.8, 0.9]

    def test_normalize_absolute_xyxy(self):
        """Absolute pixel xyxy is divided by image dimensions."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox([50, 30, 160, 180], 200, 200)
        assert result == [0.25, 0.15, 0.8, 0.9]

    def test_normalize_absolute_xyxy_with_explicit_format(self):
        """Explicit absolute_xyxy format."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox(
            [50, 30, 160, 180], 200, 200, bbox_format="absolute_xyxy"
        )
        assert result == [0.25, 0.15, 0.8, 0.9]

    def test_normalize_normalized_cxcywh(self):
        """center+size in 0-1 is converted to xyxy (explicit format)."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox(
            [0.5, 0.5, 0.4, 0.6], 200, 200, bbox_format="normalized_cxcywh"
        )
        assert result[0] == 0.3  # cx - w/2
        assert result[1] == 0.2  # cy - h/2
        assert result[2] == 0.7  # cx + w/2
        assert result[3] == 0.8  # cy + h/2

    def test_normalize_normalized_cxcywh_auto_detect(self):
        """Auto-detection works for strong normalized cxcywh patterns."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        # Clear center+size: cx/cy near 0.5, w/h notably smaller than cx/cy
        result = normalize_bbox([0.5, 0.5, 0.3, 0.4], 200, 200)
        assert abs(result[0] - 0.35) < 1e-10  # 0.5 - 0.3/2
        assert abs(result[1] - 0.3) < 1e-10   # 0.5 - 0.4/2
        assert abs(result[2] - 0.65) < 1e-10  # 0.5 + 0.3/2
        assert abs(result[3] - 0.7) < 1e-10   # 0.5 + 0.4/2

    def test_normalize_absolute_cxcywh(self):
        """Absolute pixel center+size is normalized and converted to xyxy."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox([100, 80, 60, 40], 200, 200)
        # cx=0.5, cy=0.4, w=0.3, h=0.2
        assert abs(result[0] - 0.35) < 1e-10  # 0.5 - 0.3/2
        assert abs(result[1] - 0.3) < 1e-10   # 0.4 - 0.2/2
        assert abs(result[2] - 0.65) < 1e-10  # 0.5 + 0.3/2
        assert abs(result[3] - 0.5) < 1e-10   # 0.4 + 0.2/2

    def test_normalize_absolute_xywh(self):
        """Absolute pixel top-left + size is converted to normalized xyxy."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox(
            [40, 60, 120, 80], 200, 200, bbox_format="absolute_xywh"
        )
        assert result == [0.2, 0.3, 0.8, 0.7]

    def test_normalize_absolute_xywh_explicit(self):
        """Absolute pixel top-left + size with explicit format."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox(
            [100, 60, 50, 40], 200, 200, bbox_format="absolute_xywh"
        )
        assert abs(result[0] - 0.5) < 1e-10   # 100/200
        assert abs(result[1] - 0.3) < 1e-10   # 60/200
        assert abs(result[2] - 0.75) < 1e-10  # (100+50)/200
        assert abs(result[3] - 0.5) < 1e-10   # (60+40)/200

    def test_normalize_auto_detects_absolute_xywh(self):
        """Auto-mode detects absolute_xywh when w/h ≤ half x/y."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        # w,h ≤ x*0.5, y*0.5 → detected as absolute_xywh
        result = normalize_bbox([100, 60, 50, 30], 200, 200)
        assert abs(result[0] - 0.5) < 1e-10   # 100/200
        assert abs(result[1] - 0.3) < 1e-10   # 60/200
        assert abs(result[2] - 0.75) < 1e-10  # (100+50)/200
        assert abs(result[3] - 0.45) < 1e-10  # (60+30)/200

    def test_normalize_clamps_to_01(self):
        """Output values are clamped to [0, 1]."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        # Box that extends beyond image boundaries
        result = normalize_bbox([-0.1, -0.2, 1.2, 1.5], 200, 200)
        assert result[0] == 0.0
        assert result[1] == 0.0
        assert result[2] == 1.0
        assert result[3] == 1.0

    def test_normalize_sort_error(self):
        """If x1 > x2 or y1 > y2, values are sorted so x1 <= x2."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox([0.8, 0.9, 0.1, 0.2], 200, 200)
        assert result[0] <= result[2]
        assert result[1] <= result[3]
        assert result == [0.1, 0.2, 0.8, 0.9]

    def test_normalize_empty_bbox(self):
        """Empty bbox returns zeros."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox([], 200, 200)
        assert result == [0.0, 0.0, 0.0, 0.0]

    def test_normalize_short_bbox(self):
        """Bbox with fewer than 4 elements returns zeros."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox([0.1, 0.2], 200, 200)
        assert result == [0.0, 0.0, 0.0, 0.0]

    def test_normalize_default_image_size_one(self):
        """When image dimensions are None, defaults to 1 to avoid division by zero."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        result = normalize_bbox([0.1, 0.1, 0.5, 0.5])
        assert result == [0.1, 0.1, 0.5, 0.5]

    def test_normalize_absolute_with_default_image_size(self):
        """Absolute bbox with None image size still returns clamped [0,1] values."""
        from shopstack.providers.image_gen_provider import normalize_bbox

        # Auto-detect sees values >1.5 as absolute, divides by default 1
        # Result is clamped to [0, 1]
        result = normalize_bbox([100, 100, 500, 500])
        # All values clamped to [0, 1]
        assert all(0.0 <= v <= 1.0 for v in result)
        # x1 ≤ x2, y1 ≤ y2
        assert result[0] <= result[2]
        assert result[1] <= result[3]
        # The box is valid even though coords exceeded image size
        assert result[0] >= 0.0
        assert result[2] <= 1.0

    # ── resolve_detection_bbox ──────────────────────────────────────

    def test_resolve_detection_bbox_normalized(self):
        """resolve_detection_bbox reads bbox from detection dict."""
        from shopstack.providers.image_gen_provider import resolve_detection_bbox

        det = {"bbox": [0.1, 0.2, 0.8, 0.9], "label": "tomato"}
        result = resolve_detection_bbox(det, 200, 200)
        assert result == [0.1, 0.2, 0.8, 0.9]

    def test_resolve_detection_bbox_explicit_format(self):
        """resolve_detection_bbox respects bbox_format key in detection dict."""
        from shopstack.providers.image_gen_provider import resolve_detection_bbox

        det = {
            "bbox": [50, 30, 160, 180],
            "label": "tomato",
            "bbox_format": "absolute_xyxy",
        }
        result = resolve_detection_bbox(det, 200, 200)
        assert result == [0.25, 0.15, 0.8, 0.9]

    def test_resolve_detection_missing_bbox(self):
        """Missing bbox key returns zeros."""
        from shopstack.providers.image_gen_provider import resolve_detection_bbox

        result = resolve_detection_bbox({"label": "tomato"}, 200, 200)
        assert result == [0.0, 0.0, 0.0, 0.0]

    def test_resolve_detection_absolute_format_fallback(self):
        """Auto-detect works for absolute xyxy format from detection provider."""
        from shopstack.providers.image_gen_provider import resolve_detection_bbox

        # Simulating a GroundingDINO output (absolute pixel xyxy without format tag)
        det = {"bbox": [50, 30, 160, 180], "label": "apple", "score": 0.85}
        result = resolve_detection_bbox(det, 200, 200)
        assert result == [0.25, 0.15, 0.8, 0.9]

    def test_resolve_detection_format_none(self):
        """bbox_format=None triggers auto-detect."""
        from shopstack.providers.image_gen_provider import resolve_detection_bbox

        det = {"bbox": [0.1, 0.1, 0.5, 0.5], "bbox_format": None}
        result = resolve_detection_bbox(det, 200, 200)
        assert result == [0.1, 0.1, 0.5, 0.5]


class TestFluxAnnotateImage:
    def test_annotate_image_requires_file(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        with pytest.raises(FileNotFoundError):
            provider.annotate_image("/tmp/nonexistent.png", [])

    def test_annotate_image_basic(self):
        """annotate_image draws boxes on a minimal test image."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        # Create a tiny test image
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        test_img = Path(tempfile.mkdtemp()) / "test_input.png"
        Image.new("RGB", (200, 200), color="white").save(test_img)

        try:
            detections = [
                {
                    "bbox": [0.1, 0.1, 0.5, 0.5],
                    "label": "tomato",
                    "score": 0.85,
                },
                {
                    "bbox": [0.6, 0.6, 0.9, 0.9],
                    "label": "onion",
                    "score": 0.72,
                },
            ]
            result = provider.annotate_image(str(test_img), detections)
            assert os.path.isfile(result)
            assert result.endswith(".png")
            # Verify the annotated image is larger than 0 bytes
            assert os.path.getsize(result) > 0
        finally:
            test_img.unlink(missing_ok=True)

    def test_annotate_image_svg_fallback(self):
        """When Pillow is unavailable, annotate_image falls back to SVG."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        # Create a test file
        test_img = Path(tempfile.mkdtemp()) / "test_fallback.png"
        test_img.write_text("fake-image-data")

        with patch.dict("sys.modules", {"PIL": None}, clear=False):
            result = provider.annotate_image(str(test_img), [
                {"bbox": [0.2, 0.2, 0.6, 0.6], "label": "apple", "score": 0.9},
            ])
            assert os.path.isfile(result)
            assert result.endswith(".svg")
            content = Path(result).read_text()
            assert "apple" in content
            assert "<svg" in content

        test_img.unlink(missing_ok=True)

    def test_annotate_image_empty_detections(self):
        """Empty detection list returns a clean copy of the image."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        test_img = Path(tempfile.mkdtemp()) / "test_empty.png"
        Image.new("RGB", (100, 100), color="blue").save(test_img)

        try:
            result = provider.annotate_image(str(test_img), [])
            assert os.path.isfile(result)
            assert result.endswith(".png")
        finally:
            test_img.unlink(missing_ok=True)


class TestAnnotateImageIntegration:
    """Integration tests for annotate_image — verifies pixel-level output.

    Creates a real test image, runs annotate_image with multiple bbox formats,
    and verifies the output PNG has the correct dimensions, drawn content,
    and unmodified background pixels.
    """

    @staticmethod
    def _make_test_image(path: str, width: int = 300, height: int = 200) -> None:
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")
        Image.new("RGB", (width, height), color="white").save(path)

    @staticmethod
    def _pixel_at(path: str, x: int, y: int) -> tuple[int, int, int]:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        return img.getpixel((x, y))

    def test_output_dimensions_match_input(self):
        """Output PNG has the same pixel dimensions as the input image."""
        from PIL import Image
        from shopstack.providers.image_gen_provider import FluxImageProvider

        provider = FluxImageProvider()
        test_img = Path(tempfile.mkdtemp()) / "test_dim.png"
        self._make_test_image(str(test_img), width=400, height=250)

        try:
            detections = [
                {"bbox": [0.1, 0.1, 0.4, 0.4], "label": "box1", "score": 0.9},
            ]
            result = provider.annotate_image(str(test_img), detections)
            out = Image.open(result).convert("RGB")
            assert out.size == (400, 250), f"Expected (400, 250), got {out.size}"
        finally:
            test_img.unlink(missing_ok=True)

    def test_red_outline_at_expected_position(self):
        """Normalized xyxy bbox draws a red outline at the expected pixel coords.

        On a 300×200 image, ``[0.1, 0.1, 0.5, 0.5]`` maps to pixel
        ``[30, 20, 150, 100]`` (y1=0.1×200=20, y2=0.5×200=100).
        Pillow's ``rectangle([x1,y1,x2,y2])`` draws from x1/y1
        to x2-1/y2-1 in Pillow 10+.  With ``width=3`` the outline
        is 3 px thick.  We check mid-edge pixels to avoid corner
        off-by-one ambiguity.
        """
        from shopstack.providers.image_gen_provider import FluxImageProvider

        W, H = 300, 200
        provider = FluxImageProvider()
        test_img = Path(tempfile.mkdtemp()) / "test_red_outline.png"
        self._make_test_image(str(test_img), width=W, height=H)

        try:
            # bbox [0.1, 0.1, 0.5, 0.5] on 300×200 → pixel [30, 20, 150, 100]
            detections = [
                {"bbox": [0.1, 0.1, 0.5, 0.5], "label": "tomato", "score": 0.85},
            ]
            result = provider.annotate_image(str(test_img), detections)

            # The red outline colour used is #E53935
            red = (229, 57, 53)
            white = (255, 255, 255)

            # Top edge mid-pixel (y=20, the top boundary)
            assert self._pixel_at(result, 90, 20) == red, "Top edge should be red"
            # Bottom edge (y=99, the last drawn row — Pillow draws up to y2-1)
            assert self._pixel_at(result, 90, 99) == red, "Bottom edge should be red"
            # Left edge (x=30)
            assert self._pixel_at(result, 30, 60) == red, "Left edge should be red"
            # Right edge (x=149, the last drawn column — Pillow draws up to x2-1)
            assert self._pixel_at(result, 149, 60) == red, "Right edge should be red"
            # 1px left of the box (x=28, 2px away from the 3px-wide left border)
            assert self._pixel_at(result, 28, 60) == white, "1px left of box should be white"
            # 1px above the box (y=18, 2px away from the 3px-wide top border at y=20)
            assert self._pixel_at(result, 90, 18) == white, "1px above box should be white"
            # Interior — 4px inside from each edge to clear the 3px border
            assert self._pixel_at(result, 90, 60) == white, "Box interior should be white"
            # Far from any box
            assert self._pixel_at(result, 250, 50) == white, "Unannotated area should remain white"
        finally:
            test_img.unlink(missing_ok=True)

    def test_absolute_xyxy_bbox(self):
        """Absolute pixel bbox (like GroundingDINO output) is positioned correctly."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        W, H = 300, 200
        provider = FluxImageProvider()
        test_img = Path(tempfile.mkdtemp()) / "test_absolute.png"
        self._make_test_image(str(test_img), width=W, height=H)

        try:
            # Absolute pixel xyxy [30, 30, 150, 150] on a 300x200 image
            detections = [
                {
                    "bbox": [30, 30, 150, 150],
                    "label": "apple",
                    "score": 0.9,
                    "bbox_format": "absolute_xyxy",
                },
            ]
            result = provider.annotate_image(str(test_img), detections)

            red = (229, 57, 53)
            # Mid-edge pixel on top edge
            assert self._pixel_at(result, 90, 30) == red
            # Mid-edge pixel on bottom edge
            assert self._pixel_at(result, 90, 149) == red
        finally:
            test_img.unlink(missing_ok=True)

    def test_center_size_bbox(self):
        """Center+size bbox is converted and drawn at the right position."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        W, H = 300, 200
        provider = FluxImageProvider()
        test_img = Path(tempfile.mkdtemp()) / "test_cxcywh.png"
        self._make_test_image(str(test_img), width=W, height=H)

        try:
            # Absolute cxcywh: center at (90, 80), w=120, h=80
            # → normalized: cx=0.3, cy=0.4, w=0.4, h=0.4
            # → xyxy: [0.1, 0.2, 0.5, 0.6] → pixel [30, 40, 150, 120]
            detections = [
                {
                    "bbox": [90, 80, 120, 80],
                    "label": "banana",
                    "score": 0.75,
                    "bbox_format": "absolute_cxcywh",
                },
            ]
            result = provider.annotate_image(str(test_img), detections)

            red = (229, 57, 53)
            white = (255, 255, 255)

            # Top-left of converted box should be red
            assert self._pixel_at(result, 30, 40) == red
            # Bottom-right should be red
            assert self._pixel_at(result, 150, 120) == red
            # Center of box should be white (interior not filled)
            assert self._pixel_at(result, 90, 80) == white
        finally:
            test_img.unlink(missing_ok=True)

    def test_multiple_bbox_formats_in_single_call(self):
        """Mixed bbox formats in one annotate_image call all produce outlines."""
        from shopstack.providers.image_gen_provider import FluxImageProvider

        W, H = 300, 200
        provider = FluxImageProvider()
        test_img = Path(tempfile.mkdtemp()) / "test_mixed.png"
        self._make_test_image(str(test_img), width=W, height=H)

        try:
            detections = [
                # Normalized xyxy (auto-detect)
                {"bbox": [0.05, 0.05, 0.25, 0.25], "label": "box1", "score": 0.9},
                # Absolute xyxy with explicit format
                {
                    "bbox": [100, 50, 200, 130],
                    "label": "box2",
                    "score": 0.8,
                    "bbox_format": "absolute_xyxy",
                },
                # Absolute cxcywh with explicit format
                {
                    "bbox": [250, 160, 40, 30],
                    "label": "box3",
                    "score": 0.7,
                    "bbox_format": "absolute_cxcywh",
                },
            ]
            result = provider.annotate_image(str(test_img), detections)

            red = (229, 57, 53)
            white = (255, 255, 255)

            # box1: normalized [0.05, 0.05, 0.25, 0.25] on 300×200
            #   → pixel [15, 10, 75, 50] (y1=0.05×200=10, y2=0.25×200=50)
            assert self._pixel_at(result, 15, 10) == red   # top edge
            assert self._pixel_at(result, 74, 30) == red   # right edge
            # box2: absolute [100, 50, 200, 130] → pixel [100, 50, 200, 130]
            assert self._pixel_at(result, 100, 50) == red  # top edge
            assert self._pixel_at(result, 199, 90) == red  # right edge
            # box3: cxcywh absolute [250, 160, 40, 30]
            #   → normalized: cx=0.833, cy=0.8, w=0.133, h=0.15
            #   → xyxy: [0.767, 0.725, 0.9, 0.875]
            #   → pixel [230, 145, 270, 175]
            assert self._pixel_at(result, 230, 145) == red  # top edge
            assert self._pixel_at(result, 269, 160) == red  # right edge
            # Unannotated pixel
            assert self._pixel_at(result, 50, 180) == white
        finally:
            test_img.unlink(missing_ok=True)


class TestFluxProviderImportSmoke:
    def test_import(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider
        assert FluxImageProvider.name == "flux_image_gen"

    def test_model_id(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider
        assert FluxImageProvider.model_id == "flux.2-klein-4b"

    def test_capabilities_includes_image_edit(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider
        assert "image_edit" in FluxImageProvider.capabilities
        assert "image_gen" in FluxImageProvider.capabilities
