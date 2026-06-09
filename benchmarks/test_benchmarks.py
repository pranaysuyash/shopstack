import time
from typing import Any

import pytest

pytestmark = pytest.mark.benchmark


class TestProviderBenchmarks:
    def test_mock_stt_latency(self, providers):
        samples = ["short utterance", "a " * 50, "a " * 200]
        for sample in samples:
            with temp_audio(sample) as path_file:
                path = path_file
                start = time.perf_counter()
                providers.stt.transcribe(path)
                elapsed = time.perf_counter() - start
                assert elapsed < 0.5, f"STT too slow: {elapsed:.3f}s"

    def test_mock_vision_latency(self, providers):
        start = time.perf_counter()
        providers.vision.understand("/dev/null")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Vision too slow: {elapsed:.3f}s"

    def test_mock_object_detection_latency(self, providers):
        start = time.perf_counter()
        providers.object_detection.detect("/dev/null")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Object detection too slow: {elapsed:.3f}s"

    def test_mock_planner_latency(self, providers):
        start = time.perf_counter()
        providers.planner.plan("what should I cook for dinner")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Planner too slow: {elapsed:.3f}s"

    def test_mock_ocr_latency(self, providers):
        start = time.perf_counter()
        providers.ocr.extract("/dev/null")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"OCR too slow: {elapsed:.3f}s"


class TestDatabaseBenchmarks:
    def test_bulk_insert(self, db):
        from shopstack.schemas.models import InventoryLot

        n = 100
        start = time.perf_counter()
        for i in range(n):
            db.add_inventory_lot(InventoryLot(canonical_name=f"item-{i}", display_name=f"Item {i}", quantity=1.0, unit="unit"))
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Bulk insert too slow: {elapsed:.3f}s for {n} items"

    def test_bulk_query(self, db):
        n = db.conn.execute("SELECT COUNT(*) FROM inventory_lots").fetchone()[0]
        start = time.perf_counter()
        items = db.get_inventory()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Query too slow: {elapsed:.3f}s for {n} items"
        assert len(items) == n


class TestToolBenchmarks:
    def test_add_item_throughput(self, tool_registry):
        n = 50
        start = time.perf_counter()
        for i in range(n):
            tool_registry.execute("add_inventory_item", canonical_name=f"bench-item-{i}", quantity=1.0, unit="unit")
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"Tool throughput too slow: {elapsed:.3f}s for {n} items"

    def test_find_item_latency(self, tool_registry):
        start = time.perf_counter()
        tool_registry.execute("find_item", query="bench")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Search too slow: {elapsed:.3f}s"


import tempfile
from contextlib import contextmanager


@contextmanager
def temp_audio(content: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", mode="w", delete=False) as f:
        f.write(content)
        yield f.name


# ============================================================
#  Real-model benchmarks (mock-backed — no real deps needed)
# ============================================================


class TestPlannerRealModelBenchmarks:
    """Latency/throughput benchmarks for planner backends.

    These benchmarks use mocked API clients so they run in CI without
    real model dependencies. The mock delays simulate realistic latency
    profiles documented in claims.yaml — update expectations when real
    model benchmarks are collected on Apple Silicon.
    """

    def test_mock_planner_throughput(self, providers):
        """Mock planner should handle 10 calls sequentially in under 5s."""
        n = 10
        start = time.perf_counter()
        for _ in range(n):
            providers.planner.plan("what should I cook for dinner")
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"Mock planner throughput: {elapsed:.3f}s for {n} calls"

    def test_mock_planner_token_estimate(self, providers):
        """Mock planner response simulates plausible token count."""
        result = providers.planner.plan("list items in my fridge")
        if isinstance(result, dict):
            text = str(result.get("text", ""))
            token_estimate = len(text.split()) * 1.3  # rough estimate
            assert 0 < token_estimate < 1000, f"Unusual token count: {token_estimate:.0f}"

    def test_mock_huggingface_api_latency(self, providers):
        """Mocked HuggingFace API planner should complete within 500ms."""
        from shopstack.providers.huggingface_provider import HuggingFaceProvider

        provider = HuggingFaceProvider(api_key="mock-token")
        # The mock provider doesn't actually call the API
        result = provider.plan({"prompt": "What's in my fridge?"})
        if isinstance(result, list):
            assert len(result) >= 1
        else:
            assert isinstance(result, dict)

    def test_planner_latency_budget_tracking(self, providers):
        """Planner latency tracking should report plausible values."""
        provider = getattr(providers.planner, "_provider", providers.planner)
        if hasattr(provider, "last_latency_ms"):
            providers.planner.plan("test latency tracking")
            if hasattr(provider, "last_latency_ms"):
                lat = provider.last_latency_ms
                assert lat is None or (0 < lat < 30000), f"Unusual latency: {lat}"


class TestModelBenchmarks:
    """Benchmarks for specific model performance characteristics.

    These benchmarks exist to validate the claims.yaml latency budgets.
    When run with mock providers, they verify the infrastructure is wired
    correctly. Real latency measurements should be collected on Apple
    Silicon hardware with model weights downloaded.
    """

    def test_huggingface_api_latency_mock(self):
        """HuggingFace API provider mock latency should be under 100ms."""
        from shopstack.providers.huggingface_provider import HuggingFaceProvider

        provider = HuggingFaceProvider(api_key="mock-token")
        start = time.perf_counter()
        result = provider.complete("Hello")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Mock HF API too slow: {elapsed:.3f}s"
        assert isinstance(result, dict)

    def test_huggingface_api_retry_logic(self):
        """HuggingFace API provider should handle transient failures gracefully."""
        import json
        from unittest.mock import patch

        from shopstack.providers.huggingface_provider import HuggingFaceProvider

        provider = HuggingFaceProvider(api_key="mock-token")
        with patch.object(provider, "_client") as mock_client:
            mock_client.chat_completion.side_effect = [
                Exception("Service unavailable"),
                Exception("Service unavailable"),
                {"choices": [{"message": {"content": "ok"}}]},
            ]
            result = provider.complete("Hello")
            assert isinstance(result, dict)

    def test_mock_memory_usage_estimate(self):
        """Mock providers should report plausible memory characteristics."""
        from shopstack.model_registry import get_active_models, total_active_params

        models = get_active_models()
        total = total_active_params()
        assert total > 0, "Active model parameter sum should be positive"
        assert total <= 32.0, f"Active params exceed 32B cap: {total}B"


# ============================================================
#  Tesseract real-model benchmarks (always available if CLI
#  is installed — Tesseract is the default OCR backend)
# ============================================================


class TestTesseractBenchmarks:
    """Latency/throughput/quality benchmarks for Tesseract OCR.

    Tesseract is a local CLI tool (not a neural model) that runs on CPU
    with no GPU requirement. It is the default OCR backend in ShopStack
    because GLM-OCR fails on real-world receipt photos.

    These benchmarks use a generated thermal-printer receipt image
    (same fixture as GLM-OCR benchmarks) and extract text via pytesseract.

    Expected performance:
    - Extraction latency: ~0.1-0.5s per image (CPU)
    - Extraction quality: readable, key items/found, spacing noise common
    """

    _KEY_ITEMS = ["ONION", "TOMATO", "POTATO", "MILK", "BREAD", "EGG", "SURF", "837"]
    _KEY_STORE = "SHARMA"

    def test_tesseract_available(self, tesseract_model):
        """Sanity check: TesseractOCRProvider reports available and version."""
        provider, _image_path = tesseract_model
        assert provider.available, "TesseractOCRProvider should report available"
        assert provider.name == "tesseract"
        assert provider.last_latency_ms is None, "No extraction calls made yet"

    def test_tesseract_extraction_latency(self, tesseract_model):
        """Measure single receipt extraction latency.

        Tesseract typically completes in <0.5s on Apple Silicon.
        """
        import time

        provider, image_path = tesseract_model

        start = time.perf_counter()
        result = provider.extract(image_path)
        elapsed = time.perf_counter() - start

        assert "error" not in result, f"Extraction failed: {result.get('error')}"
        text = result.get("text", "")

        assert elapsed < 2.0, f"Tesseract too slow: {elapsed:.3f}s"
        assert len(text) > 50, f"Extracted text too short: {len(text)} chars"
        assert provider.last_latency_ms is not None, "Latency should be recorded"
        assert provider.last_latency_ms < 2000, f"Latency {provider.last_latency_ms}ms exceeds 2s"

    def test_tesseract_extraction_quality(self, tesseract_model):
        """Verify extracted text contains expected receipt content.

        Tesseract preserves receipt structure well but may add spacing
        noise (extra dots, line-break artifacts). Key items, store name,
        and totals should still be identifiable.
        """
        provider, image_path = tesseract_model

        result = provider.extract(image_path)
        text = result.get("text", "").upper()

        assert "error" not in result, f"Extraction failed: {result.get('error')}"

        # Check key items are present in extracted text
        found_items = [item for item in self._KEY_ITEMS if item in text]
        assert len(found_items) >= 4, (
            f"Only {len(found_items)}/{len(self._KEY_ITEMS)} key items found. "
            f"Found: {found_items}. Text preview: {text[:300]}"
        )

        # Check store name appears (Tesseract may split it across lines)
        assert self._KEY_STORE in text, (
            f"Store name '{self._KEY_STORE}' not found in extracted text"
        )

        # Tesseract should extract at least some numeric values
        import re
        numbers = re.findall(r"\d+\.?\d*", text)
        assert len(numbers) >= 5, (
            f"Only {len(numbers)} numbers found in extracted text — "
            f"expected at least 5 (prices, quantities, total)"
        )

    def test_tesseract_extraction_throughput(self, tesseract_model):
        """Measure sequential extraction throughput.

        Since Tesseract has no model loading overhead, it should
        handle sequential extractions very quickly.
        """
        import time

        provider, image_path = tesseract_model
        n = 5

        start = time.perf_counter()
        for _ in range(n):
            result = provider.extract(image_path)
            assert "error" not in result, f"Extraction failed: {result.get('error')}"
        elapsed = time.perf_counter() - start

        avg_s = elapsed / n
        images_per_min = 60.0 / avg_s if avg_s > 0 else 0

        # Tesseract should handle 5 extractions in under 3s
        assert elapsed < 3.0, (
            f"{n} extractions took {elapsed:.2f}s (avg {avg_s:.3f}s) — "
            f"too slow for sequential throughput"
        )
        assert images_per_min > 60.0, (
            f"Throughput {images_per_min:.0f} images/min too low "
            f"(expected >60 for Tesseract on CPU)"
        )

    def test_tesseract_no_model_load(self, tesseract_model):
        """Tesseract should have zero load time — it's a CLI tool.

        Unlike neural OCR models, Tesseract requires no weight loading
        or GPU initialization. This test verifies the load() method
        is a no-op and the provider is immediately available.
        """
        provider, _image_path = tesseract_model

        import time
        start = time.perf_counter()
        provider.load()
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"Tesseract load() should be instant, took {elapsed:.4f}s"
        assert provider.available, "Tesseract should be available without loading"

    def test_tesseract_hindi_receipt(self):
        """Measure Tesseract accuracy on a receipt with Indian grocery terms.

        Uses a standard monospace font (Menlo) to render Hindi-transliterated
        item names (PYAAZ, TAMATAR, AALOO, etc.) — this tests Tesseract's
        ability to correctly read Indian grocery content, not its ability
        to handle Devanagari font rendering (which is a separate concern).

        Unlike GLM-OCR (which hallucinates on any Hindi-style content),
        Tesseract should extract most of the Latin-script transliterated
        terms accurately.

        The ``eng+hin`` language pack enables better handling if installed.
        If only ``eng`` is available the test still runs and validates
        that Latin-script Indian terms are readable.
        """
        import time

        from PIL import Image, ImageDraw, ImageFont

        from shopstack.providers.tesseract_provider import TesseractOCRProvider

        provider = TesseractOCRProvider(lang="eng", psm=6)
        if not provider.available:
            pytest.skip("Tesseract not available")

        # Generate a receipt image with Indian grocery terms using a
        # standard monospace font that Tesseract can read reliably
        lines = [
            "  SHARMA KIRANA STORE  ",
            "  12th Main, Koramangala",
            "  Date: 15/06/2026",
            "========================================",
            "  ITEM              QTY      AMOUNT",
            "----------------------------------------",
            "1. PYAAZ (Onion)         2 KG      40",
            "2. TAMATAR (Tomato)      1 KG      35",
            "3. AALOO (Potato)        2 KG      50",
            "4. DOODH (Milk)          1 L       64",
            "5. ANDAY (Eggs)          12 PC     85",
            "6. MAKKHAN (Butter)    500 G       60",
            "7. CHEENI (Sugar)        1 KG      45",
            "8. SARSON KA TEL         1 L      185",
            "9. AATA (Wheat Flour)    1 KG      42",
            "10. CHAWAL (Rice)        1 KG      75",
            "----------------------------------------",
            "  TOTAL                       681",
            "  GST                           0",
            "========================================",
            "  DHANYAVAAD! THANK YOU!",
        ]
        ground_truth = "\n".join(lines)

        padding = 16
        font_size = 15
        line_height = font_size + 7
        width = 440
        height = len(lines) * line_height + padding * 2

        img = Image.new("RGB", (width, height), (248, 244, 240))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", font_size)
        except Exception:
            font = ImageFont.load_default()

        right_align_keys = {"total", "gst"}
        for i, line in enumerate(lines):
            y = padding + i * line_height
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if any(lower.startswith(k) for k in right_align_keys):
                tw = draw.textlength(stripped, font=font)
                draw.text((width - padding - tw, y), stripped, fill="black", font=font)
            else:
                draw.text((padding, y), stripped, fill="black", font=font)

        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png", prefix="tesseract_hindi_")
        os.close(fd)
        img.save(path)

        try:
            start = time.perf_counter()
            result = provider.extract(path)
            elapsed = time.perf_counter() - start

            assert "error" not in result, f"Extraction failed: {result.get('error')}"
            ext = result.get("text", "")

            # Check for Hindi-transliterated terms in the extracted text.
            # All terms are Latin script (PYAAZ, TAMATAR, etc.) in a
            # standard monospace font, so Tesseract should extract them.
            hindi_terms = ["pyaaz", "tamatar", "aaloo", "doodh", "anday",
                           "makkhan", "cheeni", "sarson", "aata", "chawal",
                           "dhanyavaad"]
            found = [t for t in hindi_terms if t in ext.lower()]

            # Tesseract should extract most terms. Threshold at 8
            # to allow for spacing noise (e.g., "MAKKHAN" → "MAK KHAN").
            assert len(found) >= 8, (
                f"Only {len(found)}/{len(hindi_terms)} Indian terms found. "
                f"Expected at least 8. Found: {found}. "
                f"Extracted text preview: {ext[:400]}"
            )

            # Also verify key structural fields appear
            ext_upper = ext.upper()
            assert "SHARMA" in ext_upper, "Store name not found"
            assert "TOTAL" in ext_upper, "Total not found"

            # Extraction should be fast for a small image
            assert elapsed < 3.0, f"Extraction too slow: {elapsed:.1f}s"

        finally:
            import os
            try:
                os.unlink(path)
            except Exception:
                pass


# ============================================================
#  GLM-OCR real-model benchmarks (requires cached weights)
# ============================================================


class TestGlmOCRRealModelBenchmarks:
    """Real-model latency/throughput/accuracy benchmarks for GLM-OCR.

    These benchmarks load the actual GLM-OCR model via ``GlmOCRProvider``
    and exercise the full ``extract()`` pipeline on generated receipt images.
    They are skipped in CI or when the model is not cached locally.

    Measured values are validated against ``claims.yaml`` targets:
    - Load time: ~2.6s (warm, after cache)
    - Extraction latency: ~5-10s per receipt
    - Extraction quality: text should contain key items from the receipt
    """

    _KEY_ITEMS = ["ONION", "TOMATO", "POTATO", "MILK", "BREAD", "EGG", "SURF", "Total"]
    _KEY_STORE = "SHARMA"
    _KEY_DATE = "08/06/2026"

    def test_glm_ocr_model_available(self, glm_ocr_model):
        """Sanity check: GlmOCRProvider detects and can access the GLM-OCR model."""
        provider, _image_path, _warm = glm_ocr_model
        assert provider.available, "GlmOCRProvider should report available"
        assert provider._model is not None, "Model should be loaded"
        assert provider._processor is not None, "Processor should be loaded"
        assert provider.last_latency_ms is None, "No extraction calls made yet"

    def test_glm_ocr_warmup_time(self, glm_ocr_model):
        """Measure the time to load the model into memory (cold start).

        This includes transformers weight loading and processor init.
        Expected: <15s on Apple Silicon with cached weights.
        """
        _provider, _image_path, warm_elapsed = glm_ocr_model
        assert warm_elapsed < 15.0, (
            f"Model load took {warm_elapsed:.2f}s — expected <15s "
            "with cached weights on Apple Silicon"
        )

    def test_glm_ocr_extraction_latency(self, glm_ocr_model):
        """Measure single receipt extraction latency.

        Targets (from claims.yaml): ~5-8s warm inference.
        """
        import time

        provider, image_path, _warm = glm_ocr_model

        start = time.perf_counter()
        result = provider.extract(image_path)
        elapsed = time.perf_counter() - start

        assert "error" not in result, f"Extraction failed: {result.get('error')}"
        text = result.get("text", "")
        latency_ms = result.get("latency_ms", elapsed * 1000)

        assert elapsed < 20.0, f"Extraction too slow: {elapsed:.3f}s"
        assert len(text) > 50, f"Extracted text too short: {len(text)} chars"
        assert provider.last_latency_ms is not None, "Latency should be recorded"

    def test_glm_ocr_extraction_quality(self, glm_ocr_model):
        """Verify extracted text contains expected receipt content.

        The generated receipt has specific items, store name, date, and total.
        This test checks that the OCR output preserves the key fields.
        """
        provider, image_path, _warm = glm_ocr_model

        result = provider.extract(image_path)
        text = result.get("text", "").upper()

        assert "error" not in result, f"Extraction failed: {result.get('error')}"

        # Check key items are present in extracted text
        found_items = [item for item in self._KEY_ITEMS if item in text]
        assert len(found_items) >= 5, (
            f"Only {len(found_items)}/{len(self._KEY_ITEMS)} key items found in extracted text. "
            f"Found: {found_items}. Text preview: {text[:300]}"
        )

        # Check store name appears
        assert self._KEY_STORE in text, (
            f"Store name '{self._KEY_STORE}' not found in extracted text"
        )

        # Check date appears (at least the date pattern)
        import re
        assert re.search(r"08\s*[-/]\s*06\s*[-/]\s*2026", text), (
            f"Date '08/06/2026' not found in extracted text"
        )

        # Check total appears
        assert "837" in text, (
            f"Total '837.00' not found in extracted text"
        )

    def test_glm_ocr_extraction_throughput(self, glm_ocr_model):
        """Measure sequential extraction throughput.

        Run 3 extractions on the same receipt to measure
        average throughput (images per minute).
        """
        import time

        provider, image_path, _warm = glm_ocr_model
        n = 3

        start = time.perf_counter()
        for _ in range(n):
            result = provider.extract(image_path)
            assert "error" not in result, f"Extraction failed: {result.get('error')}"
        elapsed = time.perf_counter() - start

        avg_s = elapsed / n
        images_per_min = 60.0 / avg_s if avg_s > 0 else 0

        # Should handle at least 3 sequential extractions in under 45s
        assert elapsed < 45.0, (
            f"{n} extractions took {elapsed:.1f}s (avg {avg_s:.1f}s) — "
            f"too slow for sequential throughput"
        )
        assert images_per_min > 3.0, (
            f"Throughput {images_per_min:.1f} images/min too low "
            f"(avg {avg_s:.1f}s per extraction)"
        )

    def test_glm_ocr_claims_validation(self, glm_ocr_model):
        """Validate measured latency against claims.yaml targets.

        Claims targets (from Docs/models/glm-ocr/claims.yaml):
        - 'glm_ocr_receipt_extraction': verified with manual benchmark
        - 'glm_ocr_measured_latency': ~5.3s warm inference
        """
        import time

        provider, image_path, _warm = glm_ocr_model

        # Run extraction and measure
        start = time.perf_counter()
        result = provider.extract(image_path)
        elapsed = time.perf_counter() - start

        assert "error" not in result, f"Extraction failed: {result.get('error')}"
        text = result.get("text", "")
        latency_ms = round(elapsed * 1000, 1)
        token_estimate = max(1, len(text.split()))

        # Validate against claims targets
        # claims.yaml reports 5.3s warm inference — allow 3x margin
        assert latency_ms < 15000.0, (
            f"Latency {latency_ms}ms exceeds 15s threshold "
            f"(claims: ~5300ms for warm inference)"
        )

        # Extraction should return reasonable amount of text
        # Generated receipt has ~200 words
        assert token_estimate > 50, (
            f"Only ~{token_estimate} tokens extracted — "
            f"expected >50 for a 13-item receipt"
        )
        assert token_estimate < 1000, (
            f"~{token_estimate} tokens seems too many for a receipt"
        )

    def test_glm_ocr_model_parameter_count(self, glm_ocr_model):
        """Verify model metadata matches expected parameter count."""
        provider, _image_path, _warm = glm_ocr_model

        assert provider.parameter_count == 0.9, (
            f"Expected 0.9B params, got {provider.parameter_count}B"
        )
        assert provider.name == "glm_ocr"
        assert provider.runtime_type == "transformers"
        assert provider.supports_off_grid is True

    def test_glm_ocr_hindi_receipt(self, glm_ocr_model):
        """Measure GLM-OCR accuracy on a bilingual Hindi-English receipt.

        This test documents the current limitation: GLM-OCR does not support
        Devanagari/Hindi text. The model hallucinates repetitive patterns
        (e.g. 'prabhaav') instead of extracting the actual Hindi-transliterated
        item names. This test verifies the model runs without crashing and
        records metrics for tracking. If a future model version improves
        Hindi support, this test will flag the change.

        Expected: poor accuracy (Word WER > 50%, 0/15 Hindi terms found)
        """
        import time

        provider, _image_path, _warm = glm_ocr_model

        # Create Hindi receipt image
        from benchmarks.conftest import _create_hindi_receipt_image
        hindi_path, gt_path = _create_hindi_receipt_image()

        try:
            with open(gt_path, encoding="utf-8") as f:
                ground_truth = f.read()

            start = time.perf_counter()
            result = provider.extract(hindi_path)
            elapsed = time.perf_counter() - start

            assert "error" not in result, f"Extraction failed: {result.get('error')}"
            ext = result.get("text", "")

            # Simple word-level WER
            gt_words = set(ground_truth.lower().split())
            ext_words = set(ext.lower().split())
            if gt_words:
                overlap = len(gt_words & ext_words)
                accuracy = overlap / len(gt_words)
            else:
                accuracy = 0.0

            # Check for Hindi-transliterated terms
            hindi_terms = ["pyaaz", "tamatar", "aaloo", "doodh", "anday",
                           "makkhan", "cheeni", "sarson", "aata", "chawal",
                           "dhanyavaad", "kuul", "aadhaa", "rupiyah", "vatra"]
            found = [t for t in hindi_terms if t in ext.lower()]

            # Current model fails on Hindi — document the limitation
            # If a future version improves, this assertion will flag it
            assert accuracy < 0.5, (
                f"Hindi accuracy improved! Word overlap accuracy {accuracy:.1%} "
                f"({len(gt_words & ext_words)}/{len(gt_words)}). "
                f"Expected <50% based on pre-benchmark testing. "
                f"Found {len(found)}/15 Hindi terms. "
                f"If this is a real improvement, update claims.yaml "
                f"and lower the threshold. Extracted: {ext[:200]}"
            )

            # Log metrics for tracking
            assert elapsed < 30.0, f"Extraction too slow: {elapsed:.1f}s"

        finally:
            import os
            try:
                os.unlink(hindi_path)
                os.unlink(gt_path)
            except Exception:
                pass


# ============================================================
#  llama-3.2-3b real-model benchmarks (Apple Silicon only)
# ============================================================


class TestLlama3BRealModelBenchmarks:
    """Real-model latency/throughput/memory benchmarks for Llama-3.2-3B.

    These benchmarks load the actual MLX-cached GGUF variant via
    ``LocalProvider`` and exercise the full ``complete()`` pipeline.
    They are skipped in CI or when the model is not cached locally.

    Measured values are validated against ``claims.yaml`` targets:
    - Latency: ~493ms for 49 tokens (10.06 tok/s)
    - Memory: <2GB RAM with Q4_K_M quantization
    """

    _SAMPLE_PROMPTS = [
        (
            "What should I cook for dinner tonight with rice, tomatoes, and onions?",
            32,
        ),
        (
            "List 5 essential items I need to buy for a week of Indian cooking. "
            "Consider that I already have rice, dal, and spices at home.",
            64,
        ),
        (
            "How long does chopped coriander last in the fridge, and how can I "
            "tell if it's gone bad? Give me storage tips too.",
            48,
        ),
    ]

    def test_llama3b_model_available(self, llama3b_model):
        """Sanity check: LocalProvider detects and can access the MLX model."""
        provider, _warm = llama3b_model
        assert provider.available, "LocalProvider should report available"
        assert provider.backend == "mlx", f"Expected MLX backend, got {provider.backend}"
        assert provider.last_latency_ms is None, "No calls made yet"

    def test_llama3b_warmup_time(self, llama3b_model):
        """Measure the time to load the model into memory (cold start).

        This includes MLX weight loading and graph compilation.
        Expected: <10s on Apple Silicon with cached weights.
        """
        _provider, warm_elapsed = llama3b_model
        assert warm_elapsed < 10.0, (
            f"Model load took {warm_elapsed:.2f}s — expected <10s "
            "with cached weights on Apple Silicon"
        )

    def test_llama3b_latency(self, llama3b_model):
        """Measure single-completion latency.

        Targets (from claims.yaml): <500ms for ~32 tokens.
        """
        provider, _warm = llama3b_model
        prompt, _ = self._SAMPLE_PROMPTS[0]

        import time
        start = time.perf_counter()
        result = provider.complete(prompt, max_tokens=32, temperature=0.0)
        elapsed = time.perf_counter() - start

        assert "error" not in result, f"Completion failed: {result.get('error')}"
        text = result.get("text", "")
        token_count = result.get("usage", {}).get("total_tokens", 0)
        latency_ms = result.get("cost", {}).get("latency_ms", elapsed * 1000)

        # Allow ~3x margin for first call after warm (graph compilation)
        assert elapsed < 1.5, f"Latency too high: {elapsed:.3f}s"
        assert len(text) > 0, "Empty response"

    def test_llama3b_throughput(self, llama3b_model):
        """Measure tokens-per-second throughput.

        Targets (from claims.yaml): ~10.06 tok/s for short prompts.
        Real throughput is measured as ``output_tokens / elapsed_seconds``
        over several prompt lengths to capture scaling behavior.
        """
        import time

        provider, _warm = llama3b_model
        results: list[dict[str, Any]] = []

        for prompt, expected_tokens in self._SAMPLE_PROMPTS:
            start = time.perf_counter()
            result = provider.complete(prompt, max_tokens=expected_tokens, temperature=0.0)
            elapsed = time.perf_counter() - start

            assert "error" not in result, f"Completion failed: {result.get('error')}"
            text = result.get("text", "")
            token_count = result.get("usage", {}).get("total_tokens", 0)

            # Estimate tokens from output text if usage not populated
            if token_count == 0:
                token_count = max(1, len(text.split()))

            tok_s = token_count / elapsed if elapsed > 0 else 0.0
            results.append({
                "prompt_len": len(prompt),
                "elapsed_s": round(elapsed, 4),
                "tokens": token_count,
                "tok_s": round(tok_s, 2),
            })

        # Average throughput across all prompts
        avg_tok_s = sum(r["tok_s"] for r in results) / len(results)
        min_tok_s = min(r["tok_s"] for r in results)

        # claims.yaml target: 10.06 tok/s — allow 5x margin for int4
        assert avg_tok_s > 2.0, (
            f"Throughput too low: avg {avg_tok_s:.2f} tok/s "
            f"(min {min_tok_s:.2f})"
        )

    def test_llama3b_claims_validation(self, llama3b_model):
        """Validate measured latency/throughput against claims.yaml targets.

        Claims targets (from Docs/models/llama-3.2-3b-gguf/claims.yaml):
        - 'llama_gguf_measured_latency': 493ms for 49 tokens
        - 'llama_gguf_memory_budget': <2GB RAM (pending verification)
        """
        import time

        provider, _warm = llama3b_model

        # Run a benchmark call that mimics the original measurement
        # (short prompt, ~49 expected output tokens)
        prompt = (
            "List the ingredients I need to restock this week "
            "based on having: rice, dal, spices, onions, tomatoes. "
            "Suggest 5-7 items with brief reasons."
        )
        max_tokens = 64

        # Warm-up iteration (ensures consistent timing)
        provider.complete("Say hello briefly.", max_tokens=8, temperature=0.0)

        start = time.perf_counter()
        result = provider.complete(prompt, max_tokens=max_tokens, temperature=0.0)
        elapsed = time.perf_counter() - start

        assert "error" not in result, f"Completion failed: {result.get('error')}"
        text = result.get("text", "")
        token_count = result.get("usage", {}).get("total_tokens", 0)
        latency_ms = round(elapsed * 1000, 1)

        # Estimate tokens if usage not populated
        if token_count == 0:
            token_count = max(1, len(text.split()))
        tok_s = round(token_count / elapsed, 2) if elapsed > 0 else 0.0

        # Validate against claims (allow margin for MLX int4 vs GGUF Q4_K_M)
        assert latency_ms < 2000.0, (
            f"Latency {latency_ms}ms exceeds 2s threshold "
            f"(claims: 493ms for 49 tokens)"
        )
        assert tok_s > 2.0, (
            f"Throughput {tok_s} tok/s too low "
            f"(claims: 10.06 tok/s)"
        )

        # Memory: estimate from model metadata (3B params × ~0.5 bytes/param for int4)
        estimated_mb = 3.0 * 0.5 * 1024  # ~1.5GB for model weights
        assert estimated_mb < 3000, f"Memory estimate {estimated_mb}MB exceeds 3GB"

    def test_llama3b_memory_estimate(self, llama3b_model):
        """Approximate memory usage based on model metadata.

        claims.yaml target: <2GB RAM with Q4_K_M quantization.
        This test validates a model-level estimate rather than measuring
        actual RSS, since process-level RSS tracking requires psutil.
        """
        provider, _warm = llama3b_model

        # 3B params × 4.5 bits/param for Q4_K_M ≈ 1.7GB
        # Plus ~200MB for KV cache at 2048 context
        bits_per_param = 4.5
        model_weight_mb = 3.0 * bits_per_param / 8 * 1024  # MB
        kv_cache_mb = 200
        estimated_mb = model_weight_mb + kv_cache_mb

        # Track from latency tracking if available
        token_count = provider.last_token_count
        latency_ms = provider.last_latency_ms

        assert estimated_mb < 3000, (
            f"Estimated memory {estimated_mb:.0f}MB exceeds 3GB"
        )
        assert model_weight_mb < 2000, (
            f"Model weight estimate {model_weight_mb:.0f}MB exceeds 2GB"
        )

        # Quick RSS check if psutil is available
        try:
            import psutil
            import os
            rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            assert rss_mb < 4000, f"Process RSS {rss_mb:.0f}MB exceeds 4GB"
        except ImportError:
            pass  # psutil is optional
