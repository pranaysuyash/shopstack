from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FluxImageProvider:
    name = "flux_image_gen"
    model_id = "flux.2-klein-4b"
    parameter_count = 4.0
    capabilities: set[str] = {"image_gen"}

    def __init__(self) -> None:
        self._pipeline = None
        self._available = False
        self._svg_to_png = self._detect_svg_converter()

    @property
    def available(self) -> bool:
        return self._available or self._svg_to_png is not None

    def _detect_svg_converter(self) -> str | None:
        try:
            import cairosvg  # noqa: F401

            return "cairosvg"
        except ImportError:
            pass
        try:
            from svglib.svglib import svg2rlg  # noqa: F401
            from reportlab.graphics import renderPM  # noqa: F401

            return "svglib"
        except ImportError:
            pass
        return None

    def load(self) -> None:
        try:
            from diffusers import FluxPipeline  # type: ignore[import-untyped]
            import torch

            self._pipeline = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.2-klein-4B",
                torch_dtype=torch.bfloat16,
            )
            self._available = True
            logger.info("FLUX pipeline loaded successfully")
        except Exception as e:
            logger.info("FLUX pipeline not available (%s), using SVG fallback", e)

    def healthcheck(self) -> bool:
        return True

    def generate_card_image(
        self, svg_content: str, output_dir: str | None = None
    ) -> str:
        out_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp())
        out_dir.mkdir(parents=True, exist_ok=True)

        if self._svg_to_png == "cairosvg":
            try:
                import cairosvg

                out_path = out_dir / "card.png"
                cairosvg.svg2png(
                    bytestring=svg_content.encode(), write_to=str(out_path)
                )
                return str(out_path)
            except Exception as e:
                logger.debug("cairosvg conversion failed: %s", e)

        if self._svg_to_png == "svglib":
            try:
                from reportlab.graphics import renderPM
                from svglib.svglib import svg2rlg

                svg_path = out_dir / "card.svg"
                svg_path.write_text(svg_content)
                drawing = svg2rlg(str(svg_path))
                if drawing:
                    out_path = out_dir / "card.png"
                    renderPM.drawToFile(drawing, str(out_path), fmt="PNG")
                    return str(out_path)
            except Exception as e:
                logger.debug("svglib conversion failed: %s", e)

        out_path = out_dir / "card.svg"
        out_path.write_text(svg_content, encoding="utf-8")
        return str(out_path)

    def generate_shopping_poster(
        self,
        items: list[dict[str, Any]],
        theme: Any = None,
        output_dir: str | None = None,
    ) -> str:
        from shopstack.ui.renderers.image_cards import (
            CardTheme,
            cards_to_grid,
            render_decision_card,
            render_shopping_summary_card,
        )

        t = theme or CardTheme()
        cards = []
        for item in items:
            cards.append(
                render_decision_card(
                    item_name=item.get("name", ""),
                    decision=item.get("decision", "buy"),
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence", 0.8),
                    theme=t,
                )
            )
        if not cards:
            cards.append(
                render_shopping_summary_card(
                    items_bought=0,
                    items_skipped=0,
                    total_saved=0.0,
                    theme=t,
                )
            )
        poster_svg = cards_to_grid(cards, columns=3)
        return self.generate_card_image(poster_svg, output_dir)
