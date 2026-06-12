from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import shopstack.scanner as _scanner_module

# Save the original function at module import time, before the conftest
# ``_patch_decode_barcode`` autouse fixture replaces it with a Mock.  Without
# this, ``_scanner_module.decode_barcode`` in the test body would point to
# the Mock, and ``side_effect=_scanner_module.decode_barcode`` would test
# the Mock instead of the real implementation — a subtle false positive.
_decode_barcode_original = _scanner_module.decode_barcode


class TestDecodeBarcode:
    """Regression tests for :func:`shopstack.scanner.decode_barcode`."""

    def test_nonexistent_path_returns_empty_list(self):
        """``decode_barcode`` should return ``[]`` (not crash) when the image
        path does not exist on disk.

        The conftest ``_patch_decode_barcode`` autouse fixture patches this
        function module-wide, so we temporarily restore the original
        implementation via a nested ``patch`` with ``side_effect``.
        """
        with patch("shopstack.scanner.decode_barcode", side_effect=_decode_barcode_original):
            result = _decode_barcode_original("/nonexistent/test/path.jpg")
            assert result == []

    def test_empty_path_returns_empty_list(self):
        """``decode_barcode`` with an empty string path should return ``[]``."""
        with patch("shopstack.scanner.decode_barcode", side_effect=_decode_barcode_original):
            result = _decode_barcode_original("")
            assert result == []

    def test_real_image_file_does_not_crash(self):
        """``decode_barcode`` should not crash when given a valid image file
        (even one without a barcode).  Creates a small white PNG, passes it to
        the real function, and asserts it returns ``[]`` without raising.
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        try:
            # Create a small white PNG
            from PIL import Image as _PILImage
            img = _PILImage.new("RGB", (100, 30), color="white")
            img.save(tmp_path, format="PNG")

            with patch("shopstack.scanner.decode_barcode", side_effect=_decode_barcode_original):
                result = _decode_barcode_original(tmp_path)
                assert result == []
        finally:
            Path(tmp_path).unlink(missing_ok=True)
