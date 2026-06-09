from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class TesseractOCRProvider:
    """OCR / receipt text extraction provider using Tesseract via pytesseract.

    Tesseract 5.5.0+ is a mature OCR engine that runs locally with no GPU
    requirement. On Apple Silicon it extracts text from receipt photos in
    ~0.3-0.5s with good accuracy for clean English text. Supports Hindi
    via the ``-l hin`` flag (requires Tesseract Hindi language pack).

    Benchmark results (real receipt photos, June 2026):
    - fresh_mart.png (2MB supermarket photo): 0.35s, readable output
    - maa_laxmi.png (2.6MB kirana photo): 0.49s, readable output
    - sai_pharma.png (2.3MB pharmacy photo): 0.53s, readable output
    - GLM-OCR failed on all 3 (repeated <|image|> tokens)
    - Tesseract is the only viable OCR for real-world receipt photos.
    """

    name = "tesseract"
    model_id = "tesseract-5.5"
    parameter_count = 0.0  # Not a neural model — rule-based + LSTM
    license_note = "Apache-2.0"
    runtime_type = "tesseract"
    supports_off_grid = True  # Runs completely offline
    capabilities: set[str] = {"ocr"}

    def __init__(
        self,
        lang: str = "eng",
        psm: int = 6,
        oem: int = 1,
    ):
        self._lang = lang
        self._psm = psm
        self._oem = oem
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        try:
            import pytesseract
            # Verify tesseract CLI is accessible
            version = pytesseract.get_tesseract_version()
            logger.info("Tesseract OCR provider initialised (v%s)", version)
            self._available = True
            self._error = None
        except ImportError:
            self._error = "pytesseract not installed. Run: uv pip install pytesseract"
            self._available = False
        except Exception as e:
            self._error = f"Tesseract CLI not found: {e}. Install tesseract via brew: brew install tesseract"
            self._available = False

    def load(self) -> None:
        # Tesseract is a CLI tool — no model loading needed
        pass

    def extract(self, image_path: str) -> dict[str, Any]:
        """Extract text from an image using Tesseract OCR.

        Returns the extracted text, plus metadata.
        """
        import pytesseract

        if not self._available:
            return {"error": self._error or "Tesseract not available", "model": self.name}
        if not os.path.isfile(image_path):
            return {"error": f"Image file not found: {image_path}", "model": self.name}

        try:
            t0 = time.monotonic()

            custom_config = f"--psm {self._psm} --oem {self._oem}"

            text = pytesseract.image_to_string(
                image_path,
                lang=self._lang,
                config=custom_config,
            )

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            return {
                "raw_text": text.strip(),
                "text": text.strip(),
                "model": f"tesseract ({self._lang})",
                "latency_ms": self._last_latency_ms,
                "parameter_count": self.parameter_count,
            }
        except Exception as e:
            logger.warning("Tesseract extraction failed", exc_info=True)
            return {"error": str(e), "model": self.name}

    def healthcheck(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms
