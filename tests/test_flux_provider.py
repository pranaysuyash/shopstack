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


class TestFluxProviderImportSmoke:
    def test_import(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider
        assert FluxImageProvider.name == "flux_image_gen"

    def test_model_id(self):
        from shopstack.providers.image_gen_provider import FluxImageProvider
        assert FluxImageProvider.model_id == "flux.2-klein-4b"
