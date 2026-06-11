"""OCR pipeline — robust receipt/document text extraction with fallback.

Pipeline logic:
  1. Try primary OCR provider (GLM-OCR by default)
  2. Detect failure: repeated ``<|image|>`` tokens, empty output, or very short output
  3. On failure, preprocess image (deskew, binarize, enhance contrast) and retry
  4. If still failing, fall back to Tesseract OCR (works on real-world photos)
  5. Return unified result dict

This solves the problem that GLM-OCR achieves ~62% field accuracy on clean
generated receipts but COMPLETELY FAILS on real-world receipt photos
(repeated ``<|image|>`` special tokens), while Tesseract reads all three
tested real photos in ~0.4s.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ReceiptOCRPipeline",
    "run_ocr_pipeline",
]


# ── Failure detection ──────────────────────────────────────────────────


_FAILURE_PATTERNS = [
    b"<|image|>",        # GLM-OCR failure mode on real photos
    b"<|im_start|>",
    b"<|im_end|>",
    b"<|endoftext|>",
]


def _is_failure(text: str) -> bool:
    """Detect if OCR output indicates a model failure.

    Returns True if the output is empty, very short, or contains
    repeated special tokens (GLM-OCR failure mode on real photos).
    """
    stripped = text.strip()
    if not stripped:
        return True
    # Check for very short only-special-token output
    if len(stripped) < 10:
        return True
    # Check for repeated special tokens
    byte_text = stripped.encode("utf-8")
    for pattern in _FAILURE_PATTERNS:
        if byte_text.count(pattern) >= 3:
            return True
    return False


def _validate_ocr_result(result: dict[str, Any]) -> bool:
    """Check if an OCR provider result is usable (not a failure)."""
    if "error" in result:
        return False
    text = result.get("text") or result.get("raw_text") or ""
    return not _is_failure(text)


# ── Image preprocessing ────────────────────────────────────────────────


def _preprocess_image(image_path: str) -> str:
    """Preprocess a receipt photo for better OCR: grayscale, binarize, deskew.

    Returns the path to the preprocessed image (may be same as input if
    preprocessing fails).
    """
    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            logger.warning("OpenCV could not read image: %s", image_path)
            return image_path

        # 1. Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 2. Deskew
        coords = np.column_stack(np.where(gray > 0))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) > 2.0:
                h, w = gray.shape[:2]
                center = (w // 2, h // 2)
                rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
                gray = cv2.warpAffine(
                    gray, rot_mat, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )

        # 3. Adaptive binarization
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 10,
        )

        # 4. Denoise
        denoised = cv2.fastNlMeansDenoising(binary, h=30)

        # Write preprocessed image to a temp file
        preprocessed_path = image_path + "_preprocessed.png"
        cv2.imwrite(preprocessed_path, denoised)
        return preprocessed_path

    except ImportError:
        logger.debug("OpenCV not available — skipping image preprocessing")
        return image_path
    except Exception as e:
        logger.warning("Image preprocessing failed: %s", e)
        return image_path


# ── OCR pipeline ───────────────────────────────────────────────────────


class ReceiptOCRPipeline:
    """Pipeline that tries primary OCR (e.g. GLM-OCR) with Tesseract fallback.

    Usage::

        pipeline = ReceiptOCRPipeline(primary_ocr, fallback_ocr)
        result = pipeline.extract("receipt.jpg")
    """

    def __init__(
        self,
        primary_ocr: Any | None = None,
        fallback_ocr: Any | None = None,
        enable_preprocessing: bool = True,
    ):
        self._primary = primary_ocr
        self._fallback = fallback_ocr
        self._enable_preprocessing = enable_preprocessing
        self._last_pipeline_stage: str = "none"

    def extract(self, image_path: str) -> dict[str, Any]:
        """Extract text from a receipt photo using the fallback pipeline.

        Returns a dict with ``text``, ``raw_text``, ``model``, ``pipeline_stage``,
        and ``latency_ms`` keys.
        """
        if not os.path.isfile(image_path):
            return {"error": f"Image file not found: {image_path}", "pipeline_stage": "none"}

        path = image_path
        t_start = time.monotonic()

        # ── Stage 1: Primary OCR (GLM-OCR) ──────────────────────────
        if self._primary is not None and getattr(self._primary, "available", False):
            self._last_pipeline_stage = "primary"
            try:
                result = self._primary.extract(path)
                if _validate_ocr_result(result):
                    elapsed = time.monotonic() - t_start
                    result["pipeline_stage"] = "primary"
                    result["latency_ms"] = result.get("latency_ms", round(elapsed * 1000, 1))
                    logger.info(
                        "OCR pipeline: primary succeeded (%.1fms)",
                        result.get("latency_ms", 0),
                    )
                    return result
                else:
                    logger.info(
                        "OCR pipeline: primary failed (empty/special tokens), trying preprocessing..."
                    )
            except Exception as e:
                logger.warning("OCR pipeline: primary error: %s", e)

        # ── Stage 2: Primary OCR with preprocessing ─────────────────
        if self._primary is not None and getattr(self._primary, "available", False) and self._enable_preprocessing:
            self._last_pipeline_stage = "primary_preprocessed"
            try:
                preprocessed = _preprocess_image(path)
                if preprocessed != path:
                    result = self._primary.extract(preprocessed)
                    # Clean up temp file
                    try:
                        os.remove(preprocessed)
                    except OSError:
                        pass
                    if _validate_ocr_result(result):
                        elapsed = time.monotonic() - t_start
                        result["pipeline_stage"] = "primary_preprocessed"
                        result["latency_ms"] = result.get("latency_ms", round(elapsed * 1000, 1))
                        logger.info(
                            "OCR pipeline: primary+preprocessing succeeded (%.1fms)",
                            result.get("latency_ms", 0),
                        )
                        return result
                else:
                    logger.info("OCR pipeline: preprocessing skipped (path unchanged)")
            except Exception as e:
                logger.warning("OCR pipeline: primary+preprocessing error: %s", e)

        # ── Stage 3: Fallback OCR (Tesseract) ───────────────────────
        if self._fallback is not None and getattr(self._fallback, "available", False):
            self._last_pipeline_stage = "fallback"
            try:
                # Try preprocessed image first, original as fallback
                if self._enable_preprocessing:
                    preprocessed = _preprocess_image(path)
                    try:
                        result = self._fallback.extract(preprocessed)
                    finally:
                        if preprocessed != path:
                            try:
                                os.remove(preprocessed)
                            except OSError:
                                pass
                    if _validate_ocr_result(result):
                        elapsed = time.monotonic() - t_start
                        result["pipeline_stage"] = "fallback_preprocessed"
                        result["latency_ms"] = result.get("latency_ms", round(elapsed * 1000, 1))
                        logger.info(
                            "OCR pipeline: fallback succeeded (%.1fms)",
                            result.get("latency_ms", 0),
                        )
                        return result

                result = self._fallback.extract(path)
                elapsed = time.monotonic() - t_start
                result["pipeline_stage"] = "fallback"
                result["latency_ms"] = result.get("latency_ms", round(elapsed * 1000, 1))
                return result
            except Exception as e:
                logger.warning("OCR pipeline: fallback error: %s", e)

        # ── All stages failed ────────────────────────────────────────
        elapsed = time.monotonic() - t_start
        self._last_pipeline_stage = "all_failed"
        return {
            "error": "All OCR stages failed",
            "text": "",
            "raw_text": "",
            "pipeline_stage": "all_failed",
            "latency_ms": round(elapsed * 1000, 1),
        }

    @property
    def last_pipeline_stage(self) -> str:
        return self._last_pipeline_stage


def run_ocr_pipeline(
    image_path: str,
    providers: Any,
    enable_preprocessing: bool = True,
) -> dict[str, Any]:
    """Convenience: build and run the OCR pipeline from a ProviderRegistry.

    Tries GLM-OCR as primary, Tesseract as fallback.
    """
    primary = providers.get("ocr") if hasattr(providers, "get") else None
    fallback = None
    if hasattr(providers, "get"):
        # Try to get Tesseract specifically
        try:
            from shopstack.providers.tesseract_provider import TesseractOCRProvider
            fallback = TesseractOCRProvider()
        except Exception:
            pass

    pipeline = ReceiptOCRPipeline(
        primary_ocr=primary,
        fallback_ocr=fallback,
        enable_preprocessing=enable_preprocessing,
    )
    return pipeline.extract(image_path)
