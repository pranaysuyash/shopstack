"""Tests for the receipt OCR pipeline — ReceiptOCRPipeline and run_ocr_pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shopstack.services.ocr_pipeline import (
    ReceiptOCRPipeline,
    _is_failure,
    _validate_ocr_result,
)


# ─── Failure detection tests ───────────────────────────────────────


class TestIsFailure:
    """Unit tests for _is_failure text-quality heuristics."""

    def test_empty_text(self):
        assert _is_failure("") is True
        assert _is_failure("   ") is True

    def test_very_short_text(self):
        assert _is_failure("ab") is True
        assert _is_failure("123") is True

    def test_normal_text(self):
        assert _is_failure("Onion 1kg 40.00") is False
        assert _is_failure("Milk 2 120") is False

    def test_repeated_special_tokens(self):
        """GLM-OCR failure mode: repeated <|image|> tokens."""
        text = "<|image|> <|image|> <|image|> <|image|>"
        assert _is_failure(text) is True

    def test_special_tokens_below_threshold(self):
        """Two special tokens is not a failure."""
        text = "<|image|> <|image|> Some text"
        assert _is_failure(text) is False

    def test_im_start_end_patterns(self):
        text = "<|im_start|> <|im_start|> <|im_start|> <|im_start|>"
        assert _is_failure(text) is True

    def test_endoftext_pattern(self):
        text = "<|endoftext|> <|endoftext|> <|endoftext|>"
        assert _is_failure(text) is True

    def test_mixed_normal_and_special_tokens(self):
        """Real receipt text with some special noise should pass."""
        text = "Store Name\nOnion 1kg 40.00\nTotal 120.50\n<|endoftext|>"
        # Only 1 endoftext token, not >= 3
        assert _is_failure(text) is False


class TestValidateOcrResult:
    """Unit tests for _validate_ocr_result."""

    def test_valid_result(self):
        result = {"text": "Onion 1kg 40.00", "model": "glm-ocr"}
        assert _validate_ocr_result(result) is True

    def test_error_result(self):
        result = {"error": "Model not loaded"}
        assert _validate_ocr_result(result) is False

    def test_empty_text(self):
        result = {"text": "", "model": "glm-ocr"}
        assert _validate_ocr_result(result) is False

    def test_special_token_output(self):
        result = {"text": "<|image|> <|image|> <|image|> <|image|>"}
        assert _validate_ocr_result(result) is False

    def test_fallback_to_raw_text(self):
        result = {"raw_text": "Onion 1kg 40.00"}
        assert _validate_ocr_result(result) is True


# ─── Pipeline tests (mocked) ──────────────────────────────────────


def _make_mock_available(available: bool = True, error: str | None = None):
    """Create a mock OCR provider that returns canned results."""
    mock = MagicMock()
    mock.available = available
    mock.name = "test-ocr"
    if error:
        mock.extract.side_effect = Exception(error)
    else:
        mock.extract.return_value = {"text": "Onion 1kg 40.00\nMilk 2 120.00", "model": "test"}
    return mock


class TestReceiptOCRPipeline:
    """Integration tests for ReceiptOCRPipeline with mocked providers."""

    def test_primary_succeeds(self, tmp_path):
        """Primary OCR succeeds, fallback is never called."""
        primary = _make_mock_available()
        fallback = _make_mock_available()

        img = tmp_path / "receipt.png"
        img.write_text("fake-image-data")

        pipeline = ReceiptOCRPipeline(primary_ocr=primary, fallback_ocr=fallback)
        result = pipeline.extract(str(img))

        assert result["pipeline_stage"] == "primary"
        assert "Onion" in result.get("text", "")
        primary.extract.assert_called_once()
        fallback.extract.assert_not_called()

    def test_primary_fails_fallback_succeeds(self, tmp_path):
        """Primary returns empty/special tokens, fallback provides text."""
        primary = _make_mock_available()
        primary.extract.return_value = {"text": "<|image|> <|image|> <|image|> <|image|>", "model": "test"}

        fallback = _make_mock_available()
        fallback.extract.return_value = {"text": "Onion 1kg 40.00\nTesseract result", "model": "tesseract"}

        img = tmp_path / "receipt.png"
        img.write_text("fake-image-data")

        pipeline = ReceiptOCRPipeline(primary_ocr=primary, fallback_ocr=fallback)
        result = pipeline.extract(str(img))

        assert result["pipeline_stage"] in ("fallback", "fallback_preprocessed")
        assert "Tesseract" in result.get("text", "")

    def test_primary_fails_no_fallback(self, tmp_path):
        """Primary fails and no fallback available returns error."""
        primary = _make_mock_available()
        primary.extract.return_value = {"text": "<|image|> <|image|> <|image|> <|image|>", "model": "test"}

        img = tmp_path / "receipt.png"
        img.write_text("fake-image-data")

        pipeline = ReceiptOCRPipeline(primary_ocr=primary, fallback_ocr=None)
        result = pipeline.extract(str(img))

        assert result["pipeline_stage"] == "all_failed"
        assert "error" in result

    def test_no_providers_available(self, tmp_path):
        """No providers available at all returns error."""
        primary = _make_mock_available(available=False)
        fallback = _make_mock_available(available=False)

        img = tmp_path / "receipt.png"
        img.write_text("fake-image-data")

        pipeline = ReceiptOCRPipeline(primary_ocr=primary, fallback_ocr=fallback)
        result = pipeline.extract(str(img))

        assert result["pipeline_stage"] == "all_failed"
        assert "error" in result

    def test_file_not_found(self):
        """Missing image file returns error."""
        pipeline = ReceiptOCRPipeline(primary_ocr=None, fallback_ocr=None)
        result = pipeline.extract("/nonexistent/path.png")
        assert "error" in result
        assert "not found" in result["error"]

    def test_primary_exception_fallback_succeeds(self, tmp_path):
        """Primary throws an exception, fallback handles it."""
        primary = _make_mock_available(error="GPU OOM")

        fallback = _make_mock_available()
        fallback.extract.return_value = {"text": "Fallback result here", "model": "tesseract"}

        img = tmp_path / "receipt.png"
        img.write_text("fake-image-data")

        pipeline = ReceiptOCRPipeline(primary_ocr=primary, fallback_ocr=fallback)
        result = pipeline.extract(str(img))

        assert "Fallback" in result.get("text", "")

    def test_last_pipeline_stage_property(self, tmp_path):
        """last_pipeline_stage tracks the stage used."""
        primary = _make_mock_available()
        fallback = _make_mock_available()

        img = tmp_path / "receipt.png"
        img.write_text("fake-image-data")

        pipeline = ReceiptOCRPipeline(primary_ocr=primary, fallback_ocr=fallback)
        assert pipeline.last_pipeline_stage == "none"
        pipeline.extract(str(img))
        assert pipeline.last_pipeline_stage == "primary"

    def test_preprocessing_disabled_skips_stage_2(self, tmp_path):
        """When preprocessing is disabled, stage 2 (primary+preprocessing) is skipped."""
        primary = _make_mock_available()
        primary.extract.return_value = {"text": "<|image|> <|image|> <|image|> <|image|>", "model": "test"}

        fallback = _make_mock_available()
        fallback.extract.return_value = {"text": "Fallback result", "model": "tesseract"}

        img = tmp_path / "receipt.png"
        img.write_text("fake-image-data")

        pipeline = ReceiptOCRPipeline(
            primary_ocr=primary,
            fallback_ocr=fallback,
            enable_preprocessing=False,
        )
        result = pipeline.extract(str(img))

        # Should go straight to fallback, not through primary_preprocessed
        assert result["pipeline_stage"] == "fallback"
