from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Bounding box normalisation ────────────────────────────────────────

# Supported bbox formats for ``normalize_bbox()``.
# Each format's value indicates its index order and semantics:
BBOX_FORMATS: dict[str, tuple[str, ...]] = {
    "normalized_xyxy": ("x1", "y1", "x2", "y2"),
    "absolute_xyxy": ("x1", "y1", "x2", "y2"),
    "normalized_cxcywh": ("cx", "cy", "w", "h"),
    "absolute_cxcywh": ("cx", "cy", "w", "h"),
    "absolute_xywh": ("x", "y", "w", "h"),
}


def _detect_bbox_format(bbox: list[float]) -> str:
    """Heuristic convention detection for an unlabelled bbox.

    Rules:
        1. If any value > 1.5 → assume absolute pixels.
        2. For absolute values: if width/height are much smaller than
           x/y it's likely xywh (top-left + size); if comparable to
           x/y it's likely cxcywh (center + size); otherwise xyxy.
        3. For 0-1 values: if first two coords are near 0.5 and the
           last two are moderate in size → likely normalized_cxcywh.
        4. Otherwise → assume normalized [x1, y1, x2, y2].

    .. note::

        xywh ([x, y, w, h]) and cxcywh ([cx, cy, w, h]) are
        inherently ambiguous without image dimensions because
        ``[300, 200, 100, 80]`` could be xywh (box starts at 300,200,
        spans 100×80 rightward) **or** cxcywh (box centered at 300,200,
        spans 100×80 symmetrically).  Both are geometrically valid.
        The heuristic prefers xywh when w/h are very small relative
        to x/y (suggesting a tight extent from a top-left corner) and
        cxcywh for the remaining cases where the geometry allows it.

    Returns one of the keys in ``BBOX_FORMATS``.
    """
    if not bbox or len(bbox) < 4:
        return "normalized_xyxy"

    # Any value > 1.5 → absolute pixels
    if any(v > 1.5 for v in bbox):
        w, h = bbox[2], bbox[3]
        x, y = bbox[0], bbox[1]

        # xywh: width/height ≤ half the x/y magnitude.
        # This check can also match cxcywh boxes where cx >> w, but
        # without image dimensions the two are indistinguishable.
        if w <= x * 0.5 and h <= y * 0.5:
            return "absolute_xywh"

        # Guard: cxcywh is impossible if w > 2*x or h > 2*y
        # because the left/top edge (cx - w/2) would be negative.
        # Must be xyxy or xywh (already ruled out above).
        if w > 2 * x or h > 2 * y:
            return "absolute_xyxy"

        # cxcywh: width/height comparable to center coordinates.
        # Uses a 1.5× threshold as a pragmatic trade-off — higher
        # values (e.g. 2×) would reduce false-negatives for cxcywh
        # at the cost of increasing false-positives for xyxy boxes
        # in the same ambiguous ratio range.
        if w < x * 1.5 and h < y * 1.5:
            return "absolute_cxcywh"

        return "absolute_xyxy"

    # All values <= 1.5 → normalized range
    mid = 0.5
    cx_near_center = abs(bbox[0] - mid) < 0.4
    cy_near_center = abs(bbox[1] - mid) < 0.4
    if cx_near_center and cy_near_center:
        # Heuristic: if the last two values look like dimensions
        # (not corners), classify as normalized_cxcywh.
        # Both w and h should be < 0.9 and at least one should be
        # notably smaller than its corresponding center coordinate.
        w, h = bbox[2], bbox[3]
        if w < 0.9 and h < 0.9:
            if w < bbox[0] or h < bbox[1]:
                return "normalized_cxcywh"

    return "normalized_xyxy"


def _format_to_normalized_xyxy(
    bbox: list[float],
    img_w: int,
    img_h: int,
    bbox_format: str | None = None,
) -> list[float]:
    """Convert a bounding box to normalized [x1, y1, x2, y2] format.

    Args:
        bbox: Four-element list describing the bounding box.
        img_w: Image width in pixels (used for absolute→normalised conversion).
        img_h: Image height in pixels.
        bbox_format: One of the keys in ``BBOX_FORMATS``, or ``None`` for auto-detect.

    Returns:
        Normalised [x1, y1, x2, y2] with each value in [0, 1].
    """
    if not bbox or len(bbox) < 4:
        return [0.0, 0.0, 0.0, 0.0]

    fmt = bbox_format or _detect_bbox_format(bbox)

    if fmt == "normalized_xyxy":
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
    elif fmt == "absolute_xyxy":
        x1 = bbox[0] / max(img_w, 1)
        y1 = bbox[1] / max(img_h, 1)
        x2 = bbox[2] / max(img_w, 1)
        y2 = bbox[3] / max(img_h, 1)
    elif fmt == "normalized_cxcywh":
        cx, cy, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
        x1 = max(0.0, cx - w / 2)
        y1 = max(0.0, cy - h / 2)
        x2 = min(1.0, cx + w / 2)
        y2 = min(1.0, cy + h / 2)
    elif fmt == "absolute_cxcywh":
        cx = bbox[0] / max(img_w, 1)
        cy = bbox[1] / max(img_h, 1)
        w = bbox[2] / max(img_w, 1)
        h = bbox[3] / max(img_h, 1)
        x1 = max(0.0, cx - w / 2)
        y1 = max(0.0, cy - h / 2)
        x2 = min(1.0, cx + w / 2)
        y2 = min(1.0, cy + h / 2)
    elif fmt == "absolute_xywh":
        x = bbox[0] / max(img_w, 1)
        y = bbox[1] / max(img_h, 1)
        w = bbox[2] / max(img_w, 1)
        h = bbox[3] / max(img_h, 1)
        x1 = max(0.0, x)
        y1 = max(0.0, y)
        x2 = min(1.0, x + w)
        y2 = min(1.0, y + h)
    else:
        logger.warning("Unknown bbox format '%s', falling back to normalized_xyxy", fmt)
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]

    # Clamp to valid range and ensure x1 <= x2, y1 <= y2
    x1_c, x2_c = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1_c, y2_c = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
    return [x1_c, y1_c, x2_c, y2_c]


def normalize_bbox(
    bbox: list[float],
    image_width: int | None = None,
    image_height: int | None = None,
    bbox_format: str | None = None,
) -> list[float]:
    """Normalise a bounding box to [x1, y1, x2, y2] with values in [0, 1].

    Supports automatic convention detection and explicit format specification.
    Detection dicts can include a ``bbox_format`` key to skip auto-detection.

    Supported formats (see ``BBOX_FORMATS``):

        ``normalized_xyxy`` (default / auto-detect for 0-1 values)
            [x_min, y_min, x_max, y_max] in 0-1 range.  Pass-through.

        ``absolute_xyxy``
            [x_min, y_min, x_max, y_max] in absolute pixels.
            Divided by ``image_width`` / ``image_height``.

        ``normalized_cxcywh``
            [center_x, center_y, width, height] in 0-1 range.
            Converted to [x1, y1, x2, y2].

        ``absolute_cxcywh``
            [center_x, center_y, width, height] in absolute pixels.
            Normalised to 0-1 then converted.

        ``absolute_xywh``
            [x, y, width, height] in absolute pixels (top-left origin).
            Normalised to 0-1 then converted.

    Auto-detection heuristic:
        - Any value > 1.5 → absolute pixels. Further disambiguates
          between xyxy, cxcywh, and xywh by comparing width/height
          to x/y magnitudes.
        - Values near 0.5 for first two coords and small last two →
          normalized_cxcywh.
        - Otherwise → normalized_xyxy.

    Args:
        bbox: Four-element list describing the bounding box.
        image_width: Image width in pixels (required for absolute formats).
        image_height: Image height in pixels (required for absolute formats).
        bbox_format: Explicit format string. If ``None`` (or omitted),
            the format is auto-detected.

    Returns:
        Normalised [x1, y1, x2, y2] with values clamped to [0, 1].
    """
    w = image_width or 1
    h = image_height or 1
    return _format_to_normalized_xyxy(bbox, w, h, bbox_format)


def resolve_detection_bbox(
    detection: dict[str, Any],
    img_w: int,
    img_h: int,
) -> list[float]:
    """Extract and normalise the bbox from a detection dict.

    Reads the ``bbox`` key and an optional ``bbox_format`` key
    (which can be set by the detection provider).  Falls back to
    auto-detection when ``bbox_format`` is absent.

    Returns a normalised [x1, y1, x2, y2] list.
    """
    raw_bbox = detection.get("bbox", None)
    if not raw_bbox or not isinstance(raw_bbox, list) or len(raw_bbox) < 4:
        return [0.0, 0.0, 0.0, 0.0]
    fmt = detection.get("bbox_format", None)
    return _format_to_normalized_xyxy(raw_bbox, img_w, img_h, fmt)


class FluxImageProvider:
    name = "flux_image_gen"
    model_id = "flux.2-klein-4b"
    parameter_count = 4.0
    capabilities: set[str] = {"image_gen", "image_edit"}

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

    # ── ImageEditProvider interface ──────────────────────────────────

    def generate_card(self, item_name: str, details: dict[str, Any]) -> str:
        """Generate a single decision card image for an item.

        Implements ``ImageEditProvider.generate_card()`` by rendering
        a decision card SVG and converting it to a raster image (or
        falling back to SVG when no converter is available).

        Args:
            item_name: Display name of the item.
            details: Dict with optional keys:
                - decision (str): buy/skip/use_soon/etc. Default "buy".
                - reason (str): Reason text for the decision.
                - confidence (float): 0-1 confidence score. Default 0.8.
                - output_dir (str): Output directory. Default temp dir.
                - background (str): Card background colour hex.
                - accent (str): Card accent colour hex.
                - text_color (str): Card text colour hex.

        Returns:
            File path to the generated card image (PNG or SVG).
        """
        from shopstack.ui.renderers.image_cards import (
            CardTheme,
            render_decision_card,
        )

        # Build theme from details if any theme keys are present
        theme_keys = ("background", "accent", "text_color")
        if any(k in details for k in theme_keys):
            t = CardTheme(
                background=details.get("background", "#ffffff"),
                accent=details.get("accent", "#1A9E4A"),
                text=details.get("text_color", "#1e293b"),
            )
        else:
            t = None

        card_svg = render_decision_card(
            item_name=item_name,
            decision=details.get("decision", "buy"),
            reason=details.get("reason", ""),
            confidence=details.get("confidence", 0.8),
            theme=t,
        )
        return self.generate_card_image(card_svg, details.get("output_dir"))

    def annotate_image(self, image_path: str, detections: list[dict]) -> str:
        """Draw bounding box annotations on an image.

        Implements ``ImageEditProvider.annotate_image()`` by drawing
        rectangles and labels from detection results onto the source
        image using Pillow. The output is saved as a PNG alongside
        the original.

        Bounding boxes are normalised via :func:`resolve_detection_bbox`,
        which supports multiple input conventions:

        * normalized [x1, y1, x2, y2] (0-1 range, default)
        * absolute pixel [x1, y1, x2, y2]
        * center+size [cx, cy, w, h] (normalized or absolute)
        * top-left + size [x, y, w, h] (absolute)

        Detection dicts can include a ``bbox_format`` key to skip
        auto-detection (e.g. ``bbox_format="absolute_xyxy"``).

        Args:
            image_path: Path to the source image file.
            detections: List of detection dicts, each with:
                - bbox (list[float]): Bounding box in any supported format.
                - label (str): Object label.
                - score (float, optional): Confidence score.
                - ``bbox_format`` (str, optional): Explicit format string.

        Returns:
            File path to the annotated image (PNG).
        """
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            from PIL import Image, ImageDraw

            img = Image.open(image_path).convert("RGB")
            draw = ImageDraw.Draw(img)
            img_w, img_h = img.size

            for det in detections:
                # Normalise bbox — handles multiple input conventions
                n_bbox = resolve_detection_bbox(det, img_w, img_h)
                # Normalised [x1, y1, x2, y2] → pixel coords
                x1 = int(n_bbox[0] * img_w)
                y1 = int(n_bbox[1] * img_h)
                x2 = int(n_bbox[2] * img_w)
                y2 = int(n_bbox[3] * img_h)

                label = str(det.get("label", ""))
                score = det.get("score", det.get("confidence", 0.0))
                caption = f"{label} {score:.2f}" if score else label

                draw.rectangle([x1, y1, x2, y2], outline="#E53935", width=3)
                # Background pill for label text
                text_bbox = draw.textbbox((x1, y1 - 14), caption)
                label_w = text_bbox[2] - text_bbox[0] + 6
                label_h = text_bbox[3] - text_bbox[1] + 4
                draw.rectangle(
                    [x1, y1 - label_h, x1 + label_w, y1],
                    fill="#E53935",
                )
                draw.text((x1 + 2, y1 - label_h + 1), caption, fill="#ffffff")

            out_dir = Path(tempfile.mkdtemp())
            out_path = out_dir / "annotated.png"
            img.save(out_path, "PNG")
            return str(out_path)

        except ImportError:
            # Pillow not installed — save a lightweight SVG annotation instead
            logger.warning(
                "Pillow not available for annotate_image, saving SVG annotation"
            )
            return self._annotate_svg_fallback(image_path, detections)

    def _annotate_svg_fallback(
        self, image_path: str, detections: list[dict]
    ) -> str:
        """Fallback for annotate_image when Pillow is missing — returns an SVG
        wrapper that references the source image and draws overlay boxes."""
        from html import escape

        out_dir = Path(tempfile.mkdtemp())
        # Use a fixed viewport 800x600 — the image reference scales to fit
        svg_w, svg_h = 800, 600
        svg_parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="100%" height="100%" viewBox="0 0 {svg_w} {svg_h}">',
            f'<image xlink:href="file://{escape(image_path)}" '
            f'width="{svg_w}" height="{svg_h}" '
            'preserveAspectRatio="xMidYMid meet"/>',
        ]
        for det in detections:
            # Normalise bbox then scale to SVG viewport
            n_bbox = resolve_detection_bbox(det, svg_w, svg_h)
            x1 = n_bbox[0] * svg_w
            y1 = n_bbox[1] * svg_h
            x2 = n_bbox[2] * svg_w
            y2 = n_bbox[3] * svg_h
            label = escape(str(det.get("label", "")))
            score = det.get("score", det.get("confidence", 0.0))
            caption = f"{label} {score:.2f}" if score else label
            svg_parts.append(
                f'<rect x="{x1:.0f}" y="{y1:.0f}" '
                f'width="{x2 - x1:.0f}" height="{y2 - y1:.0f}" '
                f'fill="none" stroke="#E53935" stroke-width="3"/>'
            )
            svg_parts.append(
                f'<rect x="{x1:.0f}" y="{y1 - 18:.0f}" '
                f'width="{len(caption) * 7 + 6:.0f}" height="18" '
                f'fill="#E53935" rx="2"/>'
            )
            svg_parts.append(
                f'<text x="{x1 + 2:.0f}" y="{y1 - 4:.0f}" '
                f'fill="#ffffff" font-size="11" '
                f'font-family="system-ui,sans-serif">'
                f'{escape(caption[:40])}</text>'
            )
        svg_parts.append("</svg>")
        out_path = out_dir / "annotated.svg"
        out_path.write_text("".join(svg_parts), encoding="utf-8")
        return str(out_path)
